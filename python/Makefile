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

BASE_IMAGE ?= python:3.6-slim
IMAGE_NAME ?= deepops_python
RELEASE_VERSION=0.4.2
RELEASE_IMAGE ?= deepops/python

APT_PROXY ?= "false"
APT_CACHE="RUN echo 'Acquire::HTTP::Proxy \"${APT_PROXY}\";' >> /etc/apt/apt.conf.d/01proxy"
ifdef PYPI_PROXY
PYPI_CACHE="RUN mkdir -p ~/.pip && echo [global] > ~/.pip/pip.conf && echo trusted-host = ${PYPI_PROXY} >> ~/.pip/pip.conf && echo index-url = http://${PYPI_PROXY}:3141/root/pypi/+simple/ >> ~/.pip/pip.conf"
else
PYPI_CACHE=""
endif

.PHONY: build tag push release clean distclean

default: clean build

build:
	@echo FROM ${BASE_IMAGE} > .Dockerfile
	@echo ${APT_CACHE} >> .Dockerfile
	@echo ${PYPI_CACHE} >> .Dockerfile
	@cat Dockerfile >> .Dockerfile
	@echo "RUN rm -f /etc/apt/apt.conf.d/01proxy" >> .Dockerfile
	@echo "RUN rm -rf ~/.pip" >> .Dockerfile
	docker build -t ${IMAGE_NAME} -f .Dockerfile .

build-dev: build
	@echo FROM ${IMAGE_NAME} > .Dockerfile
	@echo ${APT_CACHE} >> .Dockerfile
	@echo ${PYPI_CACHE} >> .Dockerfile
	@cat Dockerfile.test >> .Dockerfile
	@echo "RUN rm -f /etc/apt/apt.conf.d/01proxy" >> .Dockerfile
	@echo "RUN rm -rf ~/.pip" >> .Dockerfile
	docker build -t ${IMAGE_NAME}:dev -f .Dockerfile .

dev: build-dev
	docker run --rm -ti -v ${PWD}:/devel -v /var/run/docker.sock:/var/run/docker.sock \
		--entrypoint=/devel/entrypoint-devel.sh --workdir=/devel ${IMAGE_NAME}:dev sh

test: build-dev
	docker run --rm -ti -v /var/run/docker.sock:/var/run/docker.sock ${IMAGE_NAME}:dev

tag: build
	docker tag ${IMAGE_NAME} ${RELEASE_IMAGE}:${RELEASE_VERSION}
	docker tag ${IMAGE_NAME} ${RELEASE_IMAGE}:latest

push: tag
	docker push ${RELEASE_IMAGE}:${RELEASE_VERSION}
	docker push ${RELEASE_IMAGE}:latest

release: push
	make -f Makefile.pypi dist

clean:
	@rm -f .Dockerfile 2> /dev/null ||:
	@find . -name "__pycache__" | xargs sudo rm -rf
	@docker rm -v `docker ps -a -q -f "status=exited"` 2> /dev/null ||:
	@docker rmi `docker images -q -f "dangling=true"` 2> /dev/null ||:

distclean: clean
	@docker rmi ${BASE_IMAGE} 2> /dev/null ||:
	@docker rmi ${IMAGE_NAME} 2> /dev/null ||:
	@docker rmi ${RELEASE_IMAGE} 2> /dev/null ||:
