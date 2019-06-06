BASE_IMAGE ?= deepops_python
IMAGE_NAME ?= replicator
RELEASE_VERSION=0.4.0
RELEASE_IMAGE ?= deepops/replicator

APT_PROXY ?= "false"
CACHE="RUN echo 'Acquire::HTTP::Proxy \"${APT_PROXY}\";' >> /etc/apt/apt.conf.d/01proxy"

.PHONY: build tag push release clean distclean

default: clean build

build:
	@echo FROM ${BASE_IMAGE} > .Dockerfile
	@echo ${CACHE} >> .Dockerfile
	@cat Dockerfile >> .Dockerfile
	@echo "RUN rm -f /etc/apt/apt.conf.d/01proxy" >> .Dockerfile
	docker build -t ${IMAGE_NAME} -f .Dockerfile .

dev: build
	docker build ${CACHES} -t ${IMAGE_NAME}:dev -f Dockerfile.test .
	docker run --rm -ti -v ${PWD}:/devel -v /var/run/docker.sock:/var/run/docker.sock --net=host \
		--entrypoint=/devel/entrypoint-devel.sh --workdir=/devel ${IMAGE_NAME}:dev sh

test: build
	docker build ${CACHES} -t ${IMAGE_NAME}:dev -f Dockerfile.test .
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
	@rm -f ./tests/__pycache__ 2> /dev/null ||:
	@docker rm -v `docker ps -a -q -f "status=exited"` 2> /dev/null ||:
	@docker rmi `docker images -q -f "dangling=true"` 2> /dev/null ||:

distclean: clean
	@docker rmi ${BASE_IMAGE} 2> /dev/null ||:
	@docker rmi ${IMAGE_NAME} 2> /dev/null ||:
	@docker rmi ${RELEASE_IMAGE} 2> /dev/null ||:
