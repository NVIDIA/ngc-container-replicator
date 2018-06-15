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
import hashlib
import itertools
import json
import logging
import os

import requests
import yaml

from contextlib import contextmanager

from . import utils

log = utils.get_logger(__name__, level=logging.INFO)

STATES = {
    "waiting": "waiting",
    "running": "running",
    "complete": "complete",
    "error": "error",
}

def filename(name, path=None):
    path = path or "/tmp"
    sha256 = hashlib.sha256()
    sha256.update(os.path.join("/tmp/{}".format(name)).encode("utf-8"))
    filename = sha256.hexdigest()
    return os.path.join(path, filename)

@contextmanager
def load_state(name, progress_uri=None, path=None):
    progress_uri = progress_uri or os.environ.get("DEEPOPS_WEBUI_PROGRESS_URI")
    _filename = filename(name, path=path)
    p = Progress(uri=progress_uri)
    if os.path.exists(_filename):
        p.read_prgress(_filename)
    yield p
    p.write_progress(_filename)


class Progress:

    def __init__(self, *, uri=None, progress_length_unknown=False):
        self.uri = uri
        self.steps = collections.OrderedDict()
        self.progress_length_unknown = progress_length_unknown

    def add_step(self, *, key, status=None, header=None, subHeader=None):
        self.steps[key] = {
            "status": STATES.get(status, "waiting"),
            "header": header or key,
            "subHeader": subHeader or ""
        }

    def set_infinite_progress(self):
        self.progress_length_unknown = True

    def set_fixed_progress(self):
        self.progress_length_unknown = False

    def update_step(self, *, key, status, header=None, subHeader=None):
        step = self.steps[key]
        step["status"] = STATES[status]
        if header:
            step["header"] = header
        if subHeader:
            step["subHeader"] = subHeader

    def write_progress(self, path):
        ordered_data = {
            "keys": list(self.steps.keys()),
            "vals": list(self.steps.values()),
            "length_unknown": self.progress_length_unknown
        }
        with open(path, "w") as file:
            yaml.dump(ordered_data, file)

    def read_prgress(self, path):
        if not os.path.exists(path):
            raise RuntimeError("{} does not exist".format(path))
        with open(path, "r") as file:
            ordered_data = yaml.load(file)
        if ordered_data is None:
            return
        steps = collections.OrderedDict()
        for key, val in zip(ordered_data["keys"], ordered_data["vals"]):
            steps[key] = val
        self.steps = steps
        self.progress_length_unknown = ordered_data["length_unknown"]


    @contextmanager
    def run_step(self, *, key, post_on_complete=True, progress_length_unknown=None):
        progress_length_unknown = progress_length_unknown or self.progress_length_unknown
        step = self.steps[key]
        step["status"] = STATES["running"]
        self.post(progress_length_unknown=progress_length_unknown)
        try:
            yield step
            step["status"] = STATES["complete"]
        except Exception as err:
            step["status"] = STATES["error"]
            step["subHeader"] = str(err)
            post_on_complete = True
            raise
        finally:
            if post_on_complete:
                self.post(progress_length_unknown=progress_length_unknown)


    def data(self, progress_length_unknown=False):
        progress_length_unknown = progress_length_unknown or self.progress_length_unknown
        steps = [v for _, v in self.steps.items()]
        return {
            "percent": -2 if progress_length_unknown else -1,
            "steps": steps
        }

    def post(self, progress_length_unknown=None):
        progress_length_unknown = progress_length_unknown or self.progress_length_unknown
        data = self.data(progress_length_unknown=progress_length_unknown)
        log.debug(data)
        if self.uri:
            try:
                r = requests.post(self.uri, json=data)
                r.raise_for_status()
            except Exception as err:
                log.warn("progress update failed with {}".format(str(err)))

