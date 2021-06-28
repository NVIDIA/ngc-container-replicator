# NGC Replicator

Clones nvcr.io using the either DGX (compute.nvidia.com) or NGC (ngc.nvidia.com)
API keys.

The replicator will make an offline clone of the NGC/DGX container registry.
In its current form, the replicator will download every CUDA container image as
well as each Deep Learning framework image in the NVIDIA project.

Tarfiles will be saved in `/output` inside the container, so be sure to volume
mount that directory. In the following example, we will collect our images in
`/tmp` on the host.

Use `--min-version` to limit the number of versions to download.  In the example
below, we will only clone versions `17.10` and later DL framework images.

```
docker run --rm -it -v /var/run/docker.sock:/var/run/docker.sock -v /tmp:/output \
    deepops/replicator --project=nvidia --min-version=17.12 \
                       --api-key=<your-dgx-or-ngc-api-key>
```

You can also filter on specific images.
If you want to filter only on image names containing the strings "tensorflow",
"pytorch", and "tensorrt", you would simply add `--image` for each option, e.g.

```
docker run --rm -it -v /var/run/docker.sock:/var/run/docker.sock -v /tmp:/output \
    deepops/replicator --project=nvidia --min-version=17.12 \
                       --image=tensorflow --image=pytorch --image=tensorrt \
                       --dry-run \
                       --api-key=<your-dgx-or-ngc-api-key>
```

Note: the `--dry-run` option lets you see what will happen without committing
to a lengthy download.

By default, the `--image` flag does a substring match in order to ensure you match
all images that may be desired.
Sometimes, however, you only want to download a specific image with no substring
matching.
In this case, you can add the `--strict-name-match` flag, e.g.

```
docker run --rm -it -v /var/run/docker.sock:/var/run/docker.sock -v /tmp:/output \
    deepops/replicator --project=nvidia --min-version=17.12 \
                       --image=nvidia/tensorflow \
                       --strict-name-match \
                       --dry-run \
                       --api-key=<your-dgx-or-ngc-api-key>
```

Note: when using `--strict-name-match`, the image name must be specified as a full name including project.

Note: a `state.yml` file will be created the output directory.  This saved state will be used to
avoid pulling images that were previously pulled.  If you wish to repull and save an image, just
delete the entry in `state.yml` corresponding to the `image_name` and `tag` you wish to refresh.

## Kubernetes Deployment

If you don't already have a `deepops` namespace, create one now.

```
kubectl create namespace deepops
```

Next, create a secret with your NGC API Key

```
kubectl -n deepops create secret generic  ngc-secret
--from-literal=apikey=<your-api-key-goes-here>
```

Next, create a persistent volume claim that will life outside the lifecycle of the CronJob. If
you are using [DeepOps](https://github.com/nvidia/deepops) you can use a Rook/Ceph PVC similar
to:

```
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ngc-replicator-pvc
  namespace: deepops
  labels:
    app: ngc-replicator
spec:
  storageClassName: rook-raid0-retain  # <== Replace with your StorageClass
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 32Mi
```

Finally, create a `CronJob` that executes the replicator on a schedule.  This
eample run the replicator every hour.  Note: This example used 
[Rook](https://rook.io) block storage to provide a persistent volume to hold the
`state.yml` between executions.  This ensures you will only download new
container images. For more details, see our [DeepOps
project](https://github.com/nvidia/deepops).

```
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: replicator-config
  namespace: deepops
data:
  ngc-update.sh: |
    #!/bin/bash
    ngc_replicator                                        \
      --project=nvidia                                    \
      --min-version=$(date +"%y.%m" -d "1 month ago")     \
      --py-version=py3                                    \
      --image=tensorflow --image=pytorch --image=tensorrt \
      --no-exporter                                       \
      --registry-url=registry.local  # <== Replace with your local repo
---
apiVersion: batch/v1beta1
kind: CronJob
metadata:
  name: ngc-replicator
  namespace: deepops
  labels:
    app: ngc-replicator
spec:
  schedule: "0 4 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          nodeSelector:
            node-role.kubernetes.io/master: ""
          containers:
            - name: replicator
              image: deepops/replicator
              imagePullPolicy: Always
              command: [ "/bin/sh", "-c", "/ngc-update/ngc-update.sh" ]
              env:
              - name: NGC_REPLICATOR_API_KEY
                valueFrom:
                  secretKeyRef:
                    name: ngc-secret
                    key: apikey
              volumeMounts:
              - name: registry-config
                mountPath: /ngc-update
              - name: docker-socket
                mountPath: /var/run/docker.sock
              - name: ngc-replicator-storage
                mountPath: /output
          volumes:
            - name: registry-config
              configMap:
                name: replicator-config
                defaultMode: 0777
            - name: docker-socket
              hostPath:
                path: /var/run/docker.sock
                type: File
            - name: ngc-replicator-storage
              persistentVolumeClaim:
                claimName: ngc-replicator-pvc
          restartPolicy: Never
```

## Developer Quickstart

```
make dev
py.test
```

## TODOs

- [x] save markdown readmes for each image.  these are not version controlled
- [x] test local registry push service.  coded, beta testing
- [ ] add templater to workflow
