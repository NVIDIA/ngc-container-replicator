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
import shlex
import subprocess
import sys

import docker

from nvidia_deepops import utils
from nvidia_deepops.docker.client.base import BaseClient

__all__ = ('DockerClient',)

log = utils.get_logger(__name__, level=logging.INFO)


class DockerClient(BaseClient):

    def __init__(self):
        self.client = docker.from_env(timeout=600)

    def call(self, command, stdout=None, stderr=None, quiet=False):
        stdout = stdout or sys.stderr
        stderr = stderr or sys.stderr
        if quiet:
            stdout = subprocess.PIPE
            stderr = subprocess.PIPE
        log.debug(command)
        subprocess.check_call(shlex.split(command), stdout=stdout,
                              stderr=stderr)

    def login(self, *, username, password, registry):
        self.call(
            "docker login -u {} -p {} {}".format(username, password, registry))
        self.client.login(username=username,
                          password=password, registry=registry)

    def get(self, *, url):
        try:
            return self.client.images.get(url)
        except docker.errors.ImageNotFound:
            return None

    def pull(self, url):
        self.call("docker pull %s" % url)
        return url

    def push(self, url):
        self.call("docker push %s" % url)
        return url

    def tag(self, src_url, dst_url):
        self.call("docker tag %s %s" % (src_url, dst_url))
        return dst_url

    def remove(self, url):
        self.call("docker rmi %s" % url)
        return url

    def url2filename(self, url):
        return "docker_image_{}.tar".format(url).replace("/", "%%")

    def filename2url(self, filename):
        return os.path.basename(filename).replace("docker_image_", "")\
            .replace(".tar", "").replace("%%", "/")

    def save(self, url, path=None):
        filename = self.url2filename(url)
        if path:
            filename = os.path.join(path, filename)
        self.call("docker save -o {} {}".format(filename, url))
        return filename

    def image_exists(self, url):
        try:
            self.call("docker image inspect {}".format(url), quiet=True)
            return True
        except Exception:
            return False

    def load(self, filename, expected_url=None):
        url = expected_url or self.filename2url(filename)
        basename = os.path.basename(filename)
        if expected_url is None and not basename.startswith("docker_image_"):
            raise RuntimeError("Invalid filename")
        self.call("docker load -i %s" % filename)
        if not self.image_exists(url):
            log.error("expected url from %s is %s" % (filename, url))
            raise RuntimeError("Image {} not found".format(url))
        log.debug("loaded {} from {}".format(url, filename))
        return url

    def build(self, *, target_image, dockerfile="Dockerfile"):
        self.call("docker build -f {} -t {} .".format(dockerfile, target_image))