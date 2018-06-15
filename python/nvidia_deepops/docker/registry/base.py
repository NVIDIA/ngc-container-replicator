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

import abc


__all__ = ('BaseRegistry',)


ABC = abc.ABCMeta('ABC', (object,), {})  # compatible with Python 2 *and* 3


class BaseRegistry(ABC):

    @abc.abstractmethod
    def get_image_names(self, project=None):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_image_tags(self, image_name):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_state(self, project=None, filter_fn=None):
        """
        Returns a unique hash for each image and tag with the ability to filter
        on the project/prefix.

        :param str project: Filter images on the prefix, e.g. project="nvidia"
            filters all `nvidia/*` images
        :param filter_fn: Callable function that takes (name, tag, docker_id)
            kwargs and returns true/false. Ff the image should be included in
            the returned set.
        :return: dict of dicts
            {
                "image_name_A": {
                    "tag_1": "dockerImageId_1",
                    "tag_2": "dockerImageId_2",
                }, ...
            }

        """
        raise NotImplementedError()

    def docker_url(self, name, tag):
        return "{}/{}:{}".format(self.url, name, tag)

    def get_images_and_tags(self, project=None):
        """
        Returns a dict keyed on image_name with values as a list of tags names
        :param project: optional filter on image_name, e.g. project='nvidia'
            filters all 'nvidia/*' images
        :return: Dict key'd by image names. Dict val are lists of tags. Ex.:
            {
                "nvidia/pytorch": ["17.07"],
                "nvidia/tensorflow": ["17.07", "17.06"],
            }
        """
        image_names = self.get_image_names(project=project)
        return {name: self.get_image_tags(name) for name in image_names}
