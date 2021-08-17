ARG BASE_IMAGE=deepops_python
FROM $BASE_IMAGE AS singularity

ARG APT_PROXY=false
RUN echo "Acquire::HTTP::Proxy \"$APT_PROXY\";" >> /etc/apt/apt.conf.d/01proxy

# Singularity build requirements
RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        libssl-dev \
        uuid-dev \
        libgpgme11-dev \
        wget \
        git \
        ca-certificates \
        squashfs-tools \
        gcc \
        tzdata && \
    rm -rf /var/lib/apt/lists/*

# Go
RUN cd /var/tmp && \
    mkdir -p /tmp && wget -q -nc --no-check-certificate -P /tmp https://dl.google.com/go/go1.13.linux-amd64.tar.gz && \
    mkdir -p /usr/local && tar -x -f /tmp/go1.13.linux-amd64.tar.gz -C /usr/local -z && \
    rm -rf /tmp/go1.13.linux-amd64.tar.gz
ENV GOPATH=/root/go \
    PATH=/usr/local/go/bin:$PATH:/root/go/bin

# Singularity
RUN mkdir -p /tmp && wget -q -nc --no-check-certificate -P /tmp https://github.com/sylabs/singularity/releases/download/v3.7.4/singularity-3.7.4.tar.gz && \
    mkdir -p $GOPATH/src/github.com/sylabs && tar -x -f /tmp/singularity-3.7.4.tar.gz -C $GOPATH/src/github.com/sylabs -z && \
    cd $GOPATH/src/github.com/sylabs/singularity && \
    go env -w GO111MODULE=off && \
    go get -u -v github.com/golang/dep/cmd/dep && \
    cd $GOPATH/src/github.com/sylabs/singularity && \
    ./mconfig --prefix=/usr/local/singularity && \
    cd builddir && \
    make && \
    make install && \
    rm -rf /tmp/singularity-3.7.4.tar.gz

FROM $BASE_IMAGE

ARG APT_PROXY=false
RUN echo "Acquire::HTTP::Proxy \"$APT_PROXY\";" >> /etc/apt/apt.conf.d/01proxy

# Singularity
RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        squashfs-tools && \
    rm -rf /var/lib/apt/lists/*
COPY --from=singularity /usr/local/singularity /usr/local/singularity
ENV PATH=/usr/local/singularity/bin:$PATH

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

WORKDIR /source/ngc_replicator
COPY . .
RUN mkdir -p /output
RUN python setup.py install
ENTRYPOINT ["ngc_replicator"]

RUN apt-get update && apt-get install -y --no-install-recommends \
        jq && \
    rm -rf /var/lib/apt/lists/*

COPY scripts/docker-utils /usr/bin/docker-utils

RUN rm -f /etc/apt/apt.conf.d/01proxy
