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
import pprint

import contexttimer
import requests

from nvidia_deepops import utils
from nvidia_deepops.docker.registry.base import BaseRegistry


log = utils.get_logger(__name__, level=logging.INFO)
dev = utils.get_logger("devel", level=logging.ERROR)


__all__ = ('NGCRegistry',)


class NGCRegistry(BaseRegistry):

    def __init__(self, api_key, nvcr_url='nvcr.io',
                 nvcr_api_url=None,
                 ngc_auth_url=None):
        self.api_key = api_key
        self.api_key_b64 = base64.b64encode(
            api_key.encode("utf-8")).decode("utf-8")
        self.url = nvcr_url

        nvcr_api_url = 'https://api.ngc.nvidia.com' if nvcr_api_url is None \
            else nvcr_api_url
        self._nvcr_api_url = nvcr_api_url
        ngc_auth_url = 'https://authn.nvidia.com' if ngc_auth_url is None \
            else ngc_auth_url
        self._ngc_auth_url = ngc_auth_url

        self._token = None
        self.orgs = None
        self.default_org = None
        self._authenticate_for(None)

    def _authenticate_for(self, resp):
        """
        Authenticate to satsify the unauthorized response
        """
        # Invalidate current bearer token
        self._token = None

        # Future-proofing the API so the response from the failed request could
        # be evaluated here

        # Request a token from the auth server
        req = requests.get(
            url="{}/token?scope=group/ngc".format(self._ngc_auth_url),
            headers={
                'Authorization': 'ApiKey {}'.format(self.api_key_b64),
                'Accept': 'application/json',
            }
        )

        # Raise error on failed request
        req.raise_for_status()

        # Set new Bearer Token
        self._token = req.json()['token']

        # Unfortunately NGC requests require an org-name, even for requests
        # where the org-name is extra/un-needed information.
        # To handle this condition, we will get the list of orgs the user
        # belongs to
        if not self.orgs:
            log.debug("no org list - fetching that now")
            data = self._get("orgs")
            self.orgs = data['organizations']
            self.default_org = self.orgs[0]['name']
            log.debug("default_org: {}".format(self.default_org))

    @property
    def token(self):
        if not self._token:
            self._authenticate_for(None)
        if not self._token:
            raise RuntimeError(
                "NGC Bearer token is not set; this is unexpected")
        return self._token

    def _get(self, endpoint):
        dev.debug("GET %s" % self._api_url(endpoint))

        # try to user current bearer token; this could result in a 401 if the
        # token is expired
        with contexttimer.Timer() as timer:
            req = requests.get(self._api_url(endpoint), headers={
                'Authorization': 'Bearer {}'.format(self.token),
                'Accept': 'application/json',
            })
        log.info("GET {} - took {} sec".format(self._api_url(endpoint),
                                               timer.elapsed))

        if req.status_code == 401:
            # re-authenticate and repeat the request -  failure here is final
            self._authenticate_for(req)
            req = requests.get(self._api_url(endpoint), headers={
                'Authorization': 'Bearer {}'.format(self.token),
                'Accept': 'application/json',
            })

        req.raise_for_status()

        data = req.json()
        dev.debug("GOT {}: {}".format(self._api_url(
            endpoint), pprint.pformat(data, indent=4)))
        return data

    def _api_url(self, endpoint):
        return "{}/v2/".format(self._nvcr_api_url) + endpoint

    def _get_repo_data(self, project=None):
        """
        Returns a list of dictionaries containing top-level details for each
        image.
        :param project: optional project/namespace; filter on all `nvidia` or
            `nvidian_sas` projects
        :return: list of dicts with the following format:
            {
              "requestStatus": {
                "statusCode": "SUCCESS",
                "requestId": "edbbaccf-f1f0-4107-b2ba-47bda0b4b308"
              },
              "repositories": [
                {
                  "isReadOnly": true,
                  "isPublic": true,
                  "namespace": "nvidia",
                  "name": "caffe",
                  "description": "## What is NVCaffe?\n\nCaffe is a deep
                      learning framework ...",
                },
                {
                  "isReadOnly": true,
                  "isPublic": true,
                  "namespace": "nvidia",
                  "name": "caffe2",
                  "description": "## What is Caffe2?\n\nCaffe2 is a
                      deep-learning framework ...",
                },
                ...
              ]
            }
        """
        def in_project(img):
            if project:
                return img["namespace"] == project
            return True

        def update(image):
            image["image_name"] = image["namespace"] + "/" + image["name"]
            return image

        data = self._get(
            "org/{}/repos?include-teams=true&include-public=true"
            .format(self.default_org))
        return [update(image)
                for image in data["repositories"] if in_project(image)]

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
        return {image['image_name']: image["description"]
                for image in cache or self._get_repo_data(project=project)}

    def get_image_tags(self, image_name, cache=None):
        """
        Returns only the list of tag names similar to how the v2 api behaves.

        :param image_name: should consist of `<project>/<repo>`, e.g.
            `nvidia/caffe`
        :return: list of tag strings: ['17.07', '17.06', ... ]
        """
        return [image['tag']
                for image in cache or self._get_image_data(image_name)]

    def _get_image_data(self, image_name):
        """
        Returns tags and other attributes of interest for each version of
        `image_name`

        :param image_name: should consist of `<project>/<repo>`, e.g.
            `nvidia/caffe`
        :return: list of dicts for each tag with the following format:
            {
              "requestStatus": {
                "statusCode": "SUCCESS",
                "requestId": "49468dff-8cba-4dcf-a841-a8bd43495fb5"
              },
              "images": [
                {
                  "updatedDate": "2017-12-04T05:56:41.1440512Z",
                  "tag": "17.12",
                  "user": {},
                  "size": 1350502380
                },
                {
                  "updatedDate": "2017-11-16T21:19:08.363176299Z",
                  "tag": "17.11",
                  "user": {},
                  "size": 1350349188
                },
              ]
            }
        """
        org_name, repo_name = image_name.split('/')
        endpoint = "org/{}/repos/{}/images".format(org_name, repo_name)
        return self._get(endpoint)['images']

    def get_state(self, project=None, filter_fn=None):
        names = self.get_image_names(project=project)
        state = collections.defaultdict(dict)
        for name in names:
            image_data = self._get_image_data(name)
            for image in image_data:
                tag = image["tag"]
                docker_id = image["updatedDate"]
                if filter_fn is not None and callable(filter_fn):
                    if not filter_fn(name=name, tag=tag, docker_id=docker_id):
                        # if filter_fn is false, then the image is not added to
                        # the state
                        continue
                state[name][tag] = {
                    "docker_id": docker_id,
                    "registry": "nvcr.io",
                }
        return state
