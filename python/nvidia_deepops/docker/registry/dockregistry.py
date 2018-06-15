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

import pprint
import logging

import contexttimer
import requests
from requests.auth import AuthBase, HTTPBasicAuth

from nvidia_deepops import utils
from nvidia_deepops.docker.registry.base import BaseRegistry


__all__ = ('DockerRegistry',)


log = utils.get_logger(__name__, level=logging.INFO)


class RegistryError(Exception):
    def __init__(self, message, code=None, detail=None):
        super(RegistryError, self).__init__(message)
        self.code = code
        self.detail = detail

    @classmethod
    def from_data(cls, data):
        """
        Encapsulate an error response in an exception
        """
        errors = data.get('errors')
        if not errors or len(errors) == 0:
            return cls('Unknown error!')

        # For simplicity, we'll just include the first error.
        err = errors[0]
        return cls(
            message=err.get('message'),
            code=err.get('code'),
            detail=err.get('detail'),
        )


class BearerAuth(AuthBase):
    def __init__(self, token):
        self.token = token

    def __call__(self, req):
        req.headers['Authorization'] = 'Bearer {}'.format(self.token)
        return req


class DockerRegistry(BaseRegistry):

    def __init__(self, *, url, username=None, password=None, verify_ssl=False):
        url = url.rstrip('/')
        if not (url.startswith('http://') or url.startswith('https://')):
            url = 'https://' + url
        self.url = url

        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.auth = None

    def authenticate(self):
        """
        Forcefully auth for testing
        """
        r = requests.head(self.url + '/v2/', verify=self.verify_ssl)
        self._authenticate_for(r)

    def _authenticate_for(self, resp):
        """
        Authenticate to satsify the unauthorized response
        """
        # Get the auth. info from the headers
        scheme, params = resp.headers['Www-Authenticate'].split(None, 1)
        assert (scheme == 'Bearer')
        info = {k: v.strip('"') for k, v in (i.split('=')
                                             for i in params.split(','))}

        # Request a token from the auth server
        params = {k: v for k, v in info.items() if k in ('service', 'scope')}
        auth = HTTPBasicAuth(self.username, self.password)
        r2 = requests.get(info['realm'], params=params,
                          auth=auth, verify=self.verify_ssl)

        if r2.status_code == 401:
            raise RuntimeError("Authentication Error")
        r2.raise_for_status()

        self.auth = BearerAuth(r2.json()['token'])

    def _get(self, endpoint):
        url = '{0}/v2/{1}'.format(self.url, endpoint)
        log.debug("GET {}".format(url))

        # Try to use previous bearer token
        with contexttimer.Timer() as timer:
            r = requests.get(url, auth=self.auth, verify=self.verify_ssl)

        log.info("GET {} - took {} sec".format(url, timer.elapsed))

        # If necessary, try to authenticate and try again
        if r.status_code == 401:
            self._authenticate_for(r)
            r = requests.get(url, auth=self.auth, verify=self.verify_ssl)

        data = r.json()

        if r.status_code != 200:
            raise RegistryError.from_data(data)

        log.debug("GOT {}: {}".format(url, pprint.pformat(data, indent=4)))
        return data

    def get_image_names(self, project=None):
        data = self._get('_catalog')
        return [image for image in data['repositories']]

    def get_image_tags(self, image_name):
        endpoint = '{name}/tags/list'.format(name=image_name)
        return self._get(endpoint)['tags']

    def get_manifest(self, name, reference):
        data = self._get(
            '{name}/manifests/{reference}'.format(name=name,
                                                  reference=reference))
        pprint.pprint(data)
