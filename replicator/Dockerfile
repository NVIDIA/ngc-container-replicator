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
