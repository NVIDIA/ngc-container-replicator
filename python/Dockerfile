RUN pip install --upgrade pip

RUN apt update && apt install -y --no-install-recommends curl tar vim-tiny make sudo && \
    rm -rf /var/cache/apt/*

ENV DOCKER_CHANNEL stable
ENV DOCKER_VERSION 17.12.0-ce
RUN if ! curl -fL -o docker.tgz "https://download.docker.com/linux/static/${DOCKER_CHANNEL}/x86_64/docker-${DOCKER_VERSION}.tgz"; then \
		echo >&2 "error: failed to download 'docker-${DOCKER_VERSION}' from '${DOCKER_CHANNEL}'"; \
		exit 1; \
	fi; \
	\
	tar --extract \
		--file docker.tgz \
		--strip-components 1 \
		--directory /usr/local/bin/ \
	; \
	rm docker.tgz

COPY ./requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

WORKDIR /source/nvidia_deepops
COPY . .
#RUN pip install -r requirements.txt
RUN python setup.py install

ENTRYPOINT []
CMD ["/bin/bash"]

# DeepOps containers will have {{ cluster_config }} mapped to /opt/deepops as read-only.
# Each container also owns {{ cluster_config }}/{{ container_name }} in which it has full
# access -- this path is mapped to /data inside the container.
RUN mkdir -p /data
