COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

WORKDIR /source/ngc_replicator
COPY . .
RUN mkdir -p /output
RUN python setup.py install
ENTRYPOINT ["ngc_replicator"]

COPY scripts/docker-utils /usr/bin/docker-utils
