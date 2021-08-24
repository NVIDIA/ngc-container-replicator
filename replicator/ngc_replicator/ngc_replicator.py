# -*- coding: utf-8 -*-
import collections
import json
import logging
import os
import pprint
import re
import time

from concurrent import futures

import click
#import grpc
import yaml

from nvidia_deepops import Progress, utils
from nvidia_deepops.docker import DockerClient, NGCRegistry, DGXRegistry

from . import replicator_pb2
#from . import replicator_pb2_grpc

log = utils.get_logger(__name__, level=logging.INFO)

_ONE_DAY_IN_SECONDS = 60 * 60 * 24


class Replicator:

    def __init__(self, *, api_key, project, **optional_config):
        log.info("Initializing Replicator")
        self._config = optional_config
        self.project = project
        self.service = self.config("service")
        if len(api_key) == 40:
            self.nvcr = DGXRegistry(api_key)
        else:
            self.nvcr = NGCRegistry(api_key)
        self.nvcr_client = DockerClient()
        self.nvcr_client.login(username="$oauthtoken", password=api_key, registry="nvcr.io/v2")
        self.registry_client = None
        self.min_version = self.config("min_version")
        self.py_version = self.config("py_version")
        self.images = self.config("image") or []
        self.progress = Progress(uri=self.config("progress_uri"))
        if self.config("registry_url"):
            self.registry_url = self.config("registry_url")
            self.registry_client = DockerClient()
            if self.config("registry_username") and self.config("registry_password"):
                self.registry_client.login(username=self.config("registry_username"),
                                           password=self.config("registry_password"),
                                           registry=self.config("registry_url"))
        self.output_path = self.config("output_path") or "/output"
        self.state_path = os.path.join(self.output_path, "state.yml")
        self.state = collections.defaultdict(dict)
        if os.path.exists(self.state_path):
            with open(self.state_path, "r") as file:
                tmp = yaml.load(file, Loader=yaml.UnsafeLoader)
            if tmp:
                for key, val in tmp.items():
                    self.state[key] = val
        self.export_to_tarfile = self.config("exporter")
        self.third_party_images = []
        if self.config("external_images"):
            self.third_party_images.extend(self.read_external_images_file())
        if self.export_to_tarfile:
            log.info("tarfiles will be saved to {}".format(self.output_path))
        self.export_to_singularity = self.config("singularity")
        if self.export_to_singularity:
            log.info("singularity images will be saved to {}".format(self.output_path))
        log.info("Replicator initialization complete")

    def read_external_images_file(self):
        with open(self.config("external_images"), "r") as file:
            data = yaml.load(file, Loader=yaml.UnsafeLoader)
        images = data.get("images", [])
        images = [replicator_pb2.DockerImage(name=image["name"], tag=image.get("tag", "latest")) for image in images]
        return images

    def config(self, key, default=None):
        return self._config.get(key, default)

    def save_state(self):
        with open(self.state_path, "w") as file:
            yaml.dump(self.state, file)

    def sync(self, project=None):
        log.info("Replicator Started")

        # pull images
        new_images = {image.name: image.tag for image in self.sync_images(project=project)}

        # pull image descriptions - new_images should be empty for dry runs
        self.progress.update_step(key="markdown", status="running")
        self.update_progress()
        descriptions = self.nvcr.get_image_descriptions(project=project)
        for image_name, _ in new_images.items():
            markdown = os.path.join(self.output_path, "description_{}.md".format(image_name.replace('/', '%%')))
            with open(markdown, "w") as out:
                out.write(descriptions.get(image_name, ""))
        self.progress.update_step(key="markdown", status="complete")
        self.update_progress()
        log.info("Replicator finished")

    def sync_images(self, project=None):
        project = project or self.project
        for image in self.images_to_download(project=project):
            if self.config("dry_run"):
                click.echo("[dry-run] clone_image({}, {}, {})".format(image.name, image.tag, image.docker_id))
                continue
            log.info("Pulling {}:{}".format(image.name, image.tag))
            self.clone_image(image.name, image.tag, image.docker_id)  # independent
            self.state[image.name][image.tag] = image.docker_id  # dep [clone]
            yield image
        self.save_state()

    def images_to_download(self, project=None):
        project = project or self.project

        self.progress.add_step(key="query", status="running", header="Getting list of Docker images to clone")
        self.update_progress(progress_length_unknown=True)

        # determine images and tags (and dockerImageIds) from the remote registry
        if self.config("strict_name_match"):
            filter_fn = self.filter_on_tag_strict if self.min_version or self.images else None
        else:
            filter_fn = self.filter_on_tag if self.min_version or self.images else None
        remote_state = self.nvcr.get_state(project=project, filter_fn=filter_fn)

        # determine which images need to be fetch for the local state to match the remote
        to_pull = self.missing_images(remote_state)

        # sort images into two buckets: cuda and not cuda
        cuda_images = { key: val for key, val in to_pull.items() if key.endswith("cuda") }
        other_images = { key: val for key, val in to_pull.items() if not key.endswith("cuda") }

        all_images = [image for image in self.images_from_state(cuda_images)]
        all_images.extend([image for image in self.images_from_state(other_images)])

        if self.config("external_images"):
            all_images.extend(self.third_party_images)

        for image in all_images:
            self.progress.add_step(key="{}:{}".format(image.name, image.tag),
                                   header="Cloning {}:{}".format(image.name, image.tag),
                                   subHeader="Waiting to pull image")
        self.progress.add_step(key="markdown", header="Downloading NVIDIA Deep Learning READMEs")
        self.progress.update_step(key="query", status="complete")
        self.update_progress()

        for image in self.images_from_state(cuda_images):
            yield image

        for image in self.images_from_state(other_images):
            yield image

        if self.config("external_images"):
            for image in self.third_party_images:
                yield image

    def update_progress(self, progress_length_unknown=False):
        self.progress.post(progress_length_unknown=progress_length_unknown)

    @staticmethod
    def images_from_state(state):
        for image_name, tag_data in state.items():
            for tag, docker_id in tag_data.items():
                yield replicator_pb2.DockerImage(name=image_name, tag=tag, docker_id=docker_id.get("docker_id", ""))

    def clone_image(self, image_name, tag, docker_id):
        if docker_id:
            url = self.nvcr.docker_url(image_name, tag=tag)
        else:
            url = "{}:{}".format(image_name, tag)
        if self.export_to_tarfile:
            tarfile = self.nvcr_client.url2filename(url)
            if os.path.exists(tarfile):
                log.warning("{} exists; removing and rebuilding".format(tarfile))
                os.remove(tarfile)
            log.info("cloning %s --> %s" % (url, tarfile))
            self.progress.update_step(key="{}:{}".format(image_name, tag), status="running", subHeader="Pulling image from Registry")
            self.update_progress()
            self.nvcr_client.pull(url)
            self.progress.update_step(key="{}:{}".format(image_name, tag), status="running", subHeader="Saving image to tarfile")
            self.update_progress()
            self.nvcr_client.save(url, path=self.output_path)
            self.progress.update_step(key="{}:{}".format(image_name, tag), status="complete", subHeader="Saved {}".format(tarfile))
            log.info("Saved image: %s --> %s" % (url, tarfile))
        if self.export_to_singularity:
            sif = os.path.join(self.output_path, "{}.sif".format(url).replace("/", "_"))
            if os.path.exists(sif):
                log.warning("{} exists; removing and rebuilding".format(sif))
                os.remove(sif)
            log.info("cloning %s --> %s" % (url, sif))
            self.progress.update_step(key="{}:{}".format(image_name, tag), status="running", subHeader="Pulling image from Registry")
            self.update_progress()
            self.nvcr_client.pull(url)
            self.progress.update_step(key="{}:{}".format(image_name, tag), status="running", subHeader="Saving image to singularity image file")
            self.update_progress()
            utils.execute("singularity build {} docker-daemon://{}".format(sif, url))
            self.progress.update_step(key="{}:{}".format(image_name, tag), status="complete", subHeader="Saved {}".format(sif))
            log.info("Saved image: %s --> %s" % (url, sif))
        if self.registry_client:
            push_url = "{}/{}:{}".format(self.registry_url, image_name, tag)
            self.nvcr_client.pull(url)
            self.registry_client.tag(url, push_url)
            self.registry_client.push(push_url)
            self.registry_client.remove(push_url)
        if not self.config("no_remove") and not image_name.endswith("cuda") and self.nvcr_client.get(url=url):
            try:
                self.nvcr_client.remove(url)
            except:
                log.warning("tried to remove docker image {}, but unexpectedly failed".format(url))
        return image_name, tag, docker_id

    def filter_on_tag(self, *, name, tag, docker_id, strict_name_match=False):
        """
        Filter function used by the `nvidia_deepops` library for selecting images.

        Return True if the name/tag/docker_id combo should be included for consideration.
        Return False and the image will be excluded from consideration, i.e. not cloned/replicated.
        """
        if self.images:
            log.debug("filtering on images name, only allow {}".format(self.images))
            found = False
            for image in self.images:
                if (not strict_name_match) and (image in name):
                    log.debug("{} passes filter; matches {}".format(name, image))
                    found = True
                elif (strict_name_match) and image.strip() == (name.split('/')[-1]).strip():
                    log.debug("{} passes strict filter; matches {}".format(name, image))
                    found = True
            if not found:
                log.debug("{} fails filter by image name".format(name))
                return False
        # if you are here, you have passed the name test
        # now, we check the version of the container by trying to extract the YY.MM details from the tag
        if self.py_version:
            if tag.find(self.py_version) == -1:
                log.debug("tag {} fails py_version {} filter".format(tag, self.py_version))
                return False
        version_regex = re.compile(r"^(\d\d\.\d\d)")
        float_tag = version_regex.findall(tag)
        if float_tag and len(float_tag) == 1:
            try:
                # this is a bit ugly, but if for some reason the cast of float_tag[0] or min_verison fail
                # we fallback to safety and skip tag filtering
                val = float(float_tag[0])
                lower_bound = float(self.min_version)
                if val < lower_bound:
                    return False
            except Exception:
                pass
        # if you are here, you have passed the tag test
        return True

    def filter_on_tag_strict(self, *, name, tag, docker_id):
        return self.filter_on_tag(name=name, tag=tag, docker_id=docker_id, strict_name_match=True)

    def missing_images(self, remote):
        """
        Generates a dict of dicts on a symmetric difference between remote/local which also includes
        any image/tag pair in both but with differing dockerImageIds.
        :param remote: `image_name:tag:docker_id` of remote content
        :param local: `image_name:tag:docker_id` of local content
        :return: `image_name:tag:docker_id` for each missing or different entry in remote but not in local
        """
        to_pull = collections.defaultdict(dict)
        local = self.state

        # determine which images are not present
        image_names = set(remote.keys()) - set(local.keys())
        for image_name in image_names:
            to_pull[image_name] = remote[image_name]

        # log.debug("remote image names: %s" % remote.keys())
        # log.debug("local  image names: %s" % local.keys())
        log.debug("image names not present: %s" % to_pull.keys())

        # determine which tags are not present
        for image_name, tag_data in remote.items():
            tags = set(tag_data.keys()) - set(local[image_name].keys())
            # log.debug("remote %s tags: %s" % (image_name, tag_data.keys()))
            # log.debug("local  %s tags: %s" % (image_name, local[image_name].keys()))
            log.debug("tags not present for image {}: {}".format(image_name, tags))
            for tag in tags:
                to_pull[image_name][tag] = remote[image_name][tag]

        # determine if any name/tag pairs have a different dockerImageId than previously seen
        # this handles the cases where someone push a new images and overwrites a name:tag image
        for image_name, tag_data in remote.items():
            if image_name not in local: continue
            for tag, docker_id in tag_data.items():
                if tag not in local[image_name]: continue
                if docker_id.get("docker_id") != local[image_name][tag]:
                    log.debug("%s:%s changed on server" % (image_name, tag))
                    to_pull[image_name][tag] = docker_id

        log.info("images to be fetched: %s" % pprint.pformat(to_pull, indent=4))
        return to_pull


## class ReplicatorService(replicator_pb2_grpc.ReplicatorServicer):
## 
##     def __init__(self, *, replicator):
##         self.replicator = replicator
##         self.replicator.service = True
## 
##     def StartReplication(self, request, context):
##         project = request.org_name or self.replicator.project
##         for image in self.replicator.sync_images(project=project):
##             yield image
## 
##     def ListImages(self, request, context):
##         project = request.org_name or self.replicator.project
##         for image in self.replicator.images_to_download(project=project):
##             yield image
## #       images_and_tags = self.replicator.nvcr.get_images_and_tags(project=project)
## #       for image_name, tags in images_and_tags.items():
## #           for tag in tags:
## #               yield replicator_pb2.DockerImage(name=image_name, tag=tag)
## 
##     def DownloadedImages(self, request, context):
##         for images in self.replicator.images_from_state(self.replicator.state):
##             yield images


@click.command()
@click.option("--api-key", envvar="NGC_REPLICATOR_API_KEY")
@click.option("--project", default="nvidia")
@click.option("--output-path", default="/output")
@click.option("--min-version")
@click.option("--py-version")
@click.option("--image", multiple=True)
@click.option("--registry-url")
@click.option("--registry-username")
@click.option("--registry-password")
@click.option("--dry-run", is_flag=True)
@click.option("--service", is_flag=True)
@click.option("--external-images")
@click.option("--progress-uri")
@click.option("--no-remove", is_flag=True)
@click.option("--exporter/--no-exporter", default=True)
@click.option("--templater/--no-templater", default=False)
@click.option("--singularity/--no-singularity", default=False)
@click.option("--strict-name-match/--no-strict-name-match", default=False)
def main(**config):
    """
    NGC Replication Service
    """
    if config.get("api_key", None) is None:
        click.echo("API key required; use --api-key or NGC_REPLICATOR_API_KEY", err=True)
        raise click.Abort

    replicator = Replicator(**config)

    if replicator.service:
#       server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
#       replicator_pb2_grpc.add_ReplicatorServicer_to_server(
#           ReplicatorService(replicator=replicator), server
#       )
#       server.add_insecure_port('[::]:50051')
#       log.info("starting GRPC service on port 50051")
#       server.start()
#       try:
#           while True:
#               time.sleep(_ONE_DAY_IN_SECONDS)
#       except KeyboardInterrupt:
#           server.stop(0)
        raise NotImplementedError("GPRC Service has been depreciated")
    else:
        replicator.sync()


if __name__ == "__main__":
    main(auto_envvar_prefix='NGC_REPLICATOR')
