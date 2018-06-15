#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import tempfile

"""Tests for `ngc_replicator` package."""

import pytest

from ngc_replicator import ngc_replicator

try:
    from .secrets import ngcpassword, dgxpassword
    HAS_SECRETS = True
except Exception:
    HAS_SECRETS = False

secrets = pytest.mark.skipif(not HAS_SECRETS, reason="No secrets.py file found")

@secrets
def nvsa_replicator(*, output_path):
    """
    Instance of the test NGC Registry on compute.nvidia.com (project=nvsa)
    """
    return ngc_replicator.Replicator(
        project="nvsa_clone",
        api_key=dgxpassword,
        exporter=True,
        output_path=output_path,
        min_version="16.04"
    )


@secrets
def test_clone():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = os.path.join(tmpdir, "state.yml")
        assert not os.path.exists(state_file)
        replicator = nvsa_replicator(output_path=tmpdir)
        replicator.sync()
        assert os.path.exists(state_file)
        assert 'nvsa_clone/busybox' in replicator.state
