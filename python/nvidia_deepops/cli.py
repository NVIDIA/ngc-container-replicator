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

"""Console script for nvidia_deepops."""

import click
import hashlib
import yaml

from . import progress

@click.command()
def main(args=None):
    """Console script for nvidia_deepops."""
    click.echo("cli coming soon...")


@click.command()
@click.option("--name", required=True)
@click.option("--key", required=True)
@click.option("--status", type=click.Choice(progress.STATES.values()))
@click.option("--header")
@click.option("--subtitle")
@click.option("--fixed/--infinite", default=True)
@click.option("--op", type=click.Choice(["create", "append", "update", "run"]))
def progress_cli(name, key, status, header, subtitle, fixed, op):
    op = op or "run"
    with progress.load_state(name) as state:
        if fixed:
            state.set_fixed_progress()
        else:
            state.set_infinite_progress()
        if op == "create":
            state.steps.clear()
        if op == "create" or op == "append":
            state.add_step(key=key, status=status, header=header, subHeader=subtitle)
        elif op == "update":
            step = state.steps[key]
            status = status or step["status"]
            header = header or step["header"]
            subtitle = subtitle or step["subHeader"]
            state.update_step(key=key, status=status, header=header, subHeader=subtitle)
            state.post()
        elif op == "run":
            keys = list(state.steps.keys())
            completed_keys = keys[0:keys.index(key)]
            for k in completed_keys:
                state.update_step(key=k, status="complete")
            state.update_step(key=key, status="running")
            click.echo("{op} Step: {key}\nHeader: {header}\nSubtitle: {subHeader}".format(
                op=op.title(), key=key, **state.steps[key])
            )
            state.post()
        else:
            raise RuntimeError("this shouldn't happen")


if __name__ == "__main__":
    main()
