#!/usr/bin/env python
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
import logging
import os
# import pprint

import pytest

import traceback

from click.testing import CliRunner
from docker.errors import APIError

from nvidia_deepops import utils
# from nvidia_deepops import cli
from nvidia_deepops.docker import (BaseClient, DockerClient, registry)


BaseRegistry = registry.BaseRegistry
# DockerRegistry = registry.DockerRegistry
DGXRegistry = registry.DGXRegistry
NGCRegistry = registry.NGCRegistry


dev = utils.get_logger(__name__, level=logging.DEBUG)

try:
    from .secrets import ngcpassword, dgxpassword
    HAS_SECRETS = True
except Exception:
    HAS_SECRETS = False

secrets = pytest.mark.skipif(not HAS_SECRETS, reason="No secrets.py file found")

@pytest.fixture
def response():
    """Sample pytest fixture.

    See more at: http://doc.pytest.org/en/latest/fixture.html
    """
    # import requests
    # return requests.get('https://github.com/audreyr/cookiecutter-pypackage')


def test_content(response):
    """Sample pytest test function with the pytest fixture as an argument."""
    # from bs4 import BeautifulSoup
    # assert 'GitHub' in BeautifulSoup(response.content).title.string


def test_command_line_interface():
    """Test the CLI."""
    runner = CliRunner()
    # result = runner.invoke(cli.main)
    # assert result.exit_code == 0
    # assert 'cloner.cli.main' in result.output
    # help_result = runner.invoke(cli.main, ['--help'])
    # assert help_result.exit_code == 0
    # assert '--help  Show this message and exit.' in help_result.output


class FakeClient(BaseClient):

    def __init__(self, registries=None, images=None):
        self.registries = registries or []
        self.images = images or []

    def registry_for_url(self, url):
        for reg in self.registries:
            if url.startswith(reg.url):
                return reg
        raise RuntimeError("registry not found for %s" % url)

    def url_to_name_and_tag(self, url, reg=None):
        dev.debug("url: %s" % url)
        reg = reg or self.registry_for_url(url)
        return reg.url_to_name_and_tag(url)

    def should_be_present(self, url):
        if url not in self.images:
            dev.debug(self.images)
            raise ValueError("client does not have an image named %s" % url)

    def pull(self, url):
        reg = self.registry_for_url(url)
        name, tag = self.url_to_name_and_tag(url, reg=reg)
        reg.should_be_present(name, tag=tag)
        self.images.append(url)
        self.should_be_present(url)

    def tag(self, src, dst):
        self.should_be_present(src)
        self.images.append(dst)

    def push(self, url):
        self.should_be_present(url)
        reg = self.registry_for_url(url)
        dev.debug("push %s" % url)
        name, tag = self.url_to_name_and_tag(url, reg=reg)
        reg.images[name].append(tag)

    def remove(self, url):
        self.should_be_present(url)
        self.images.remove(url)


class FakeRegistry(BaseRegistry):

    def __init__(self, url, images=None):
        self.url = url
        self.images = collections.defaultdict(list)
        images = images or {}
        for name, tags in images.items():
            self.images[name] = tags

    def docker_url(self, name, tag="latest"):
        return "{}/{}:{}".format(self.url, name, tag)

    def url_to_name_and_tag(self, url):
        name_tag = url.replace(self.url + "/", "").split(":")
        dev.debug("name_tag: %s" % name_tag)
        if len(name_tag) == 1:
            return name_tag, "latest"
        elif len(name_tag) == 2:
            return name_tag
        else:
            raise RuntimeError("bad name_tag")

    def should_be_present(self, url_or_name, tag=None):
        if url_or_name.startswith(self.url) and tag is None:
            name, tag = self.url_to_name_and_tag(url_or_name)
        else:
            name, tag = url_or_name, tag or "latest"
        if tag not in self.images[name]:
            dev.debug(self.images)
            raise ValueError("%s not found for %s" % (tag, name))

    def get_image_tags(self, image_name):
        return self.images[image_name]

    def get_image_names(self, project=None):
        def predicate(name):
            if project:
                return name.startswith(project + "/")
            return True
        return [name for name in self.images.keys() if predicate(name)]

    def get_state(self, project=None, filter_fn=None):
        image_names = self.get_image_names(project=project)
        state = collections.defaultdict(dict)
        for name in image_names:
            for tag in self.images[name]:
                if filter_fn is not None and callable(filter_fn):
                    if not filter_fn(name=name, tag=tag, docker_id=tag):
                        continue
                state[name][tag] = tag
        return state


def test_fakeregistry_docker_url():
    fqdn = FakeRegistry("nvcr.io")
    assert fqdn.docker_url("nvidia/pytorch") == "nvcr.io/nvidia/pytorch:latest"
    assert fqdn.docker_url("nvidia/pytorch", "17.05") == \
        "nvcr.io/nvidia/pytorch:17.05"

    fqdn = FakeRegistry("nvcr.io:5000")
    assert fqdn.docker_url("nvidia/pytorch") == \
        "nvcr.io:5000/nvidia/pytorch:latest"
    assert fqdn.docker_url("nvidia/pytorch", "17.05") == \
        "nvcr.io:5000/nvidia/pytorch:17.05"


@pytest.fixture
def nvcr():
    return FakeRegistry("nvcr.io", images={
        "nvidia/tensorflow": ["17.07", "17.06"],
        "nvidia/pytorch": ["17.07", "17.05"],
        "nvidia/cuda": ["8.0-devel", "9.0-devel"],
        "nvidian_sas/dgxbench": ["16.08"],
        "nvidian_sas/dgxdash": ["latest"],
    })


@pytest.fixture
def locr():
    return FakeRegistry("registry:5000", images={
        "nvidia/pytorch": ["17.06", "17.05"],
        "nvidia/cuda": ["8.0-devel"],
    })


def test_get_state(nvcr):
    state = nvcr.get_state(project="nvidia")
    assert len(state.keys()) == 3
    assert len(state["nvidia/tensorflow"].keys()) == 2
    assert state["nvidia/cuda"]["9.0-devel"] == "9.0-devel"


def test_get_state_filter(nvcr):
    def filter_on_tag(*, name, tag, docker_id):
        try:
            val = float(tag)
        except Exception:
            traceback.print_exc()
            return True
        return val >= 17.06

    state = nvcr.get_state(project="nvidia", filter_fn=filter_on_tag)
    assert len(state.keys()) == 3
    assert len(state["nvidia/tensorflow"].keys()) == 2
    assert len(state["nvidia/pytorch"].keys()) == 1


def test_client_lifecycle(nvcr, locr):
    client = FakeClient(registries=[nvcr, locr])
    # we should see an exception when the image is not in the registry
    with pytest.raises(Exception):
        client.pull(nvcr.docker_url("nvidia/pytorch", tag="17.06"))
    src = nvcr.docker_url("nvidia/pytorch", tag="17.07")
    dst = locr.docker_url("nvidia/pytorch", tag="17.07")
    with pytest.raises(Exception):
        locr.should_be_present(dst)
    client.pull(src)
    client.should_be_present(src)
    client.tag(src, dst)
    client.push(dst)
    locr.should_be_present(dst)
    client.remove(src)
    with pytest.raises(Exception):
        client.should_be_present(src)
#   client.delete_remote(src)
#   with pytest.raises(Exception):
#       nvcr.should_be_present(src)


def test_pull_nonexistent_image(nvcr):
    client = FakeClient(registries=[nvcr])
    with pytest.raises(Exception):
        client.pull(nvcr.docker_url("nvidia/tensorflow", "latest"))


def test_push_nonexistent_image(locr):
    client = FakeClient(registries=[locr])
    with pytest.raises(Exception):
        client.push(locr.docker_url("ryan/awesome"))


def docker_client_pull_and_remove(client, url):
    client.pull(url)
    image = client.get(url=url)
    assert image is not None
    client.remove(url)
    with pytest.raises(APIError):
        client.client.images.get(url)
    assert client.get(url=url) is None


@pytest.mark.remote
@pytest.mark.dockerclient
@pytest.mark.parametrize("image_name", [
    "busybox:latest",
    "ubuntu:16.04",
])
def test_pull_and_remove_from_docker_hub(image_name):
    client = DockerClient()
    docker_client_pull_and_remove(client, image_name)


@secrets
@pytest.mark.nvcr
@pytest.mark.remote
@pytest.mark.dockerclient
@pytest.mark.parametrize("image_name", [
    "nvcr.io/nvsa_clone/busybox:latest",
    "nvcr.io/nvsa_clone/ubuntu:16.04",
])
def test_pull_and_remove_from_nvcr(image_name):
    client = DockerClient()
    client.login(
        username="$oauthtoken",
        password=dgxpassword,
        registry="nvcr.io/v2")
    docker_client_pull_and_remove(client, image_name)


@secrets
@pytest.mark.remote
@pytest.mark.dockerregistry
def test_get_state_dgx():
    dgx_registry = DGXRegistry(dgxpassword)
    state = dgx_registry.get_state(project="nvidia")
    dev.debug(state)
    assert state["nvidia/cuda"]["8.0-cudnn5.1-devel-ubuntu14.04"] == \
        "c61f351b591fbfca93b3c0fcc3bd0397e7f3c6c2c2f1880ded2fdc1e5f9edd9e"


@secrets
@pytest.mark.remote
@pytest.mark.dockerregistry
def test_get_state_ngc():
    ngc_registry = NGCRegistry(ngcpassword)
    state = ngc_registry.get_state(project="nvidia")
    dev.debug(state)
    assert "9.0-cudnn7-devel-ubuntu16.04" in state["nvidia/cuda"]


@secrets
@pytest.mark.nvcr
@pytest.mark.remote
@pytest.mark.dockerregistry
def test_dgx_registry_list():
    dgx_registry = DGXRegistry(dgxpassword)
    images_and_tags = dgx_registry.get_images_and_tags(project="nvsa_clone")
    dev.debug(images_and_tags)
    assert "nvsa_clone/busybox" in images_and_tags
    assert "nvsa_clone/ubuntu" in images_and_tags
    assert "latest" in images_and_tags["nvsa_clone/busybox"]
    assert "16.04" in images_and_tags["nvsa_clone/ubuntu"]


@secrets
@pytest.mark.nvcr
@pytest.mark.remote
@pytest.mark.dockerregistry
def test_ngc_registry_list():
    ngc_registry = NGCRegistry(ngcpassword)
    images_and_tags = ngc_registry.get_images_and_tags(project="nvidia")
    dev.debug(images_and_tags)
    images = ["nvidia/tensorflow", "nvidia/pytorch",
              "nvidia/mxnet", "nvidia/tensorrt"]
    for image in images:
        assert image in images_and_tags
        assert "17.12" in images_and_tags[image]


@secrets
@pytest.mark.nvcr
@pytest.mark.remote
def test_dgx_markdowns():
    dgx_registry = DGXRegistry(dgxpassword)
    markdowns = dgx_registry.get_image_descriptions(project="nvidia")
    dev.debug(markdowns)
    assert "nvidia/cuda" in markdowns


@secrets
@pytest.mark.nvcr
@pytest.mark.remote
def test_ngc_markdowns():
    ngc_registry = NGCRegistry(ngcpassword)
    markdowns = ngc_registry.get_images_and_tags(project="nvidia")
    dev.debug(markdowns)
    images = ["nvidia/tensorflow", "nvidia/pytorch",
              "nvidia/mxnet", "nvidia/tensorrt"]
    for image in images:
        assert image in markdowns


@pytest.mark.new
@pytest.mark.remote
@pytest.mark.parametrize("url", [
    "busybox:latest",
])
def test_pull_and_save_and_remove(url):
    client = DockerClient()
    client.pull(url)
    filename = client.save(url)
    assert os.path.exists(filename)
    client.remove(url)
    assert client.get(url=url) is None
    read_url = client.load(filename)
    assert read_url == url
    assert client.get(url=url) is not None
    client.remove(url)
    os.unlink(filename)
    assert not os.path.exists(filename)
