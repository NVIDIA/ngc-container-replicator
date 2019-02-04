# -*- coding: utf-8 -*-
#
# Copyright (c) 2017, NVIDIA CORPORATION. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#  * Neither the name of NVIDIA CORPORATION nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS ``AS IS'' AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
# OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import collections
import base64
import logging

import contexttimer
import requests

from nvidia_deepops import utils
from nvidia_deepops.docker.registry.base import BaseRegistry


log = utils.get_logger(__name__, level=logging.INFO)
dev = utils.get_logger("devel", level=logging.ERROR)


__all__ = ('DGXRegistry',)


class DGXRegistry(BaseRegistry):

    def __init__(self, api_key, nvcr_url='nvcr.io',
                 nvcr_api_url=None):
        self.api_key = api_key
        self.api_key_b64 = base64.b64encode(api_key.encode("utf-8"))\
            .decode("utf-8")
        self.url = nvcr_url
        nvcr_api_url = 'https://compute.nvidia.com' if nvcr_api_url is None \
            else nvcr_api_url
        self._nvcr_api_url = nvcr_api_url

    def _get(self, endpoint):
        dev.debug("GET %s" % self._api_url(endpoint))
        with contexttimer.Timer() as timer:
            req = requests.get(self._api_url(endpoint), headers={
                'Authorization': 'APIKey {}'.format(self.api_key_b64),
                'Accept': 'application/json',
            })
        log.info("GET {} - took {} sec".format(self._api_url(endpoint),
                                               timer.elapsed))
        req.raise_for_status()
        data = req.json()
        # dev.debug("GOT {}: {}".format(self._api_url(endpoint),
        #                               pprint.pformat(data, indent=4)))
        return data

    def _api_url(self, endpoint):
        return "{}/rest/api/v1/".format(self._nvcr_api_url) + endpoint

    def _get_repo_data(self, project=None):
        """
        Returns a list of dictionaries containing top-level details for each
        image.

        :param project: optional project/namespace; filter on all `nvidia` or
            `nvidian_sas` projects
        :return: list of dicts with the following format:
            {
                "isReadOnly": true,
                "isPublic": true,
                "namespace": "nvidia",
                "name": "caffe2",
                "description": "## What is Caffe2?\n\nCaffe2 is a deep-learning
                    framework ... "
            }
        """
        def in_project(img):
            if project:
                return img["namespace"] == project
            return True

        def update(image):
            image["image_name"] = image["namespace"] + "/" + image["name"]
            return image
        data = self._get("repository?includePublic=true")
        return [update(image) for image in data["repositories"]
                if in_project(image)]

    def get_image_names(self, project=None, cache=None):
        """
        Returns a list of image names optionally filtered on project.  All
        names include the base project/namespace.

        :param project: optional filter, e.g. project="nvidia" filters all
            "nvidia/*" images
        :return: ["nvidia/caffe", "nvidia/cuda", ...]
        """
        return [image["image_name"]
                for image in cache or self._get_repo_data(project=project)]

    def get_image_descriptions(self, project=None, cache=None):
        return {image['image_name']: image.get("description", "")
                for image in cache or self._get_repo_data(project=project)}

    def get_image_tags(self, image_name, cache=None):
        """
        Returns only the list of tag names similar to how the v2 api behaves.

        :param image_name: should consist of `<project>/<repo>`, e.g.
            `nvidia/caffe`
        :return: list of tag strings: ['17.07', '17.06', ... ]
        """
        return [tag['name']
                for tag in cache or self._get_image_data(image_name)]

    def _get_image_data(self, image_name):
        """
        Returns tags and other attributes of interest for each version of
        `image_name`

        :param image_name: should consist of `<project>/<repo>`, e.g.
            `nvidia/caffe`
        :return: list of dicts for each tag with the following format:
            {
                "dockerImageId": "9c496e628c7d64badd2b587d4c0a387b0db00...",
                "lastModified": "2017-03-27T18:48:21.000Z",
                "name": "17.03",
                "size": 1244439426
            }
        """
        endpoint = "/".join(["repository", image_name])
        return self._get(endpoint)['tags']

    def get_state(self, project=None, filter_fn=None):
        names = self.get_image_names(project=project)
        state = collections.defaultdict(dict)
        for name in names:
            for tag in self._get_image_data(name):
                if filter_fn is not None and callable(filter_fn):
                    if not filter_fn(name=name, tag=tag["name"],
                                     docker_id=tag["dockerImageId"]):
                        continue
                state[name][tag["name"]] = {
                    "docker_id": tag["dockerImageId"],
                    "registry": "nvcr.io",
                }
        return state
