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

import logging
import os

import docker

from nvidia_deepops import utils
from nvidia_deepops.docker.client.base import BaseClient


__all__ = ('DockerPy',)


log = utils.get_logger(__name__, level=logging.INFO)


class DockerPy(BaseClient):

    def __init__(self):
        self.client = docker.from_env(timeout=600)

    def login(self, *, username, password, registry):
        self.client.login(username=username,
                          password=password, registry=registry)

    def get(self, *, url):
        try:
            return self.client.images.get(url)
        except docker.errors.ImageNotFound:
            return None

    def pull(self, url):
        log.debug("docker pull %s" % url)
        self.client.images.pull(url)

    def push(self, url):
        log.debug("docker push %s" % url)
        self.client.images.push(url)

    def tag(self, src_url, dst_url):
        log.debug("docker tag %s --> %s" % (src_url, dst_url))
        image = self.client.images.get(src_url)
        image.tag(dst_url)

    def remove(self, url):
        log.debug("docker rmi %s" % url)
        self.client.images.remove(url)

    def url2filename(self, url):
        return "docker_image_{}.tar".format(url).replace("/", "%%")

    def filename2url(self, filename):
        return os.path.basename(filename).replace("docker_image_", "")\
            .replace(".tar", "").replace("%%", "/")

    def save(self, url, path=None):
        filename = self.url2filename(url)
        if path:
            filename = os.path.join(path, filename)
        log.debug("saving %s --> %s" % (url, filename))
        image = self.client.api.get_image(url)
        with open(filename, "wb") as tarfile:
            tarfile.write(image.data)
        return filename

    def load(self, filename):
        log.debug("loading image from %s" % filename)
        with open(filename, "rb") as file:
            self.client.images.load(file)
        basename = os.path.basename(filename)
        if basename.startswith("docker_image_"):
            url = self.filename2url(filename)
            log.debug("expected url from %s is %s" % (filename, url))
            return url
