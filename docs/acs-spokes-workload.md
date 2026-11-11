# Workload Deployment on ACM Spoke Clusters

This document describes how to use the workload deployment playbook to schedule pods on ACM managed spoke clusters with automatic replica scaling and pod anti-affinity distribution.

## Overview

The `spokes-workload-deployment.yml` playbook automates:

1. **Reading container image names** from a configuration file
2. **Building fully qualified image references** with configurable registry and tag
3. **Determining worker node count** in each spoke cluster
4. **Creating deployments** with replicas matching worker count
5. **Distributing pods** across worker nodes using pod anti-affinity
6. **Applying manifests** to each spoke cluster

## Prerequisites

- Deployed ACM hub cluster with managed clusters in the inventory
- Managed clusters must have worker nodes with the `node-role.kubernetes.io/worker: ""` label
- `oc` CLI installed and configured with access to hub cluster
- Container image names available in a text file (one per line)
- **Ansible inventory with `managed_clusters` group**: List of managed cluster names

## Assumptions

- **Container registry configuration**: This role assumes that the spoke clusters are already configured to access the container registry (via ImageContentSourcePolicy, mirrors, or other registry configuration). Registry setup (DNS resolution, credentials, ICSP/IDMS) is the responsibility of spoke cluster deployment/provisioning, not this playbook.
- The registry hostname/port specified in variables is accessible from the spoke clusters
- Spoke clusters have the necessary pull secrets or registry authentication configured

Example inventory:
```ini
[managed_clusters]
standard-00001
standard-00002
standard-00003
```

Kubeconfig secrets on the hub cluster at `<namespace>/<namespace>-admin-kubeconfig` (created automatically by ACM cluster instance manifests).

## Configuration

### Container Images File

Create a text file with one container image name per line (no registry or tag):

```bash
cat > workload_images.txt <<EOF
nginx
redis
postgres
EOF
```

Image names are resolved to fully qualified references using:
```
{registry}:{port}/{namespace}/{image_name}:{tag}
```

By default, the playbook uses:
- `registry`: bastion hostname (from ansible inventory)
- `port`: `5000`
- `namespace`: `operator-containers`
- `tag`: `acs-testing`

### Playbook Variables

| Variable | Default | Description |
| - | - | - |
| `container_images_file` | (required) | Path to file containing image names |
| `container_image_registry` | bastion hostname | Container image registry |
| `container_registry_port` | `5000` | Container registry port |
| `container_registry_namespace` | `operator-containers` | Container registry namespace/org |
| `container_image_tag` | `acs-testing` | Container image tag |
| `workload_namespace` | `workload` | Kubernetes namespace for deployment |
| `workload_deployment_name` | `workload-deployment` | Name of the Deployment resource |
| `container_cpu_request` | `10m` | CPU resource request per container |
| `container_cpu_limit` | `10m` | CPU resource limit per container |
| `container_memory_request` | `128Mi` | Memory resource request per container |
| `container_memory_limit` | `128Mi` | Memory resource limit per container |

## Usage

### Basic Deployment (Bastion Registry with acs-testing Tag)

The playbook automatically uses the bastion hostname as the registry and `acs-testing` as the tag:

```bash
time ansible-playbook -i ansible/inventory/cloud30.local \
  ansible/acs-spokes-workload.yml \
  -e container_images_file=./workload_images.txt
```

This will resolve images like:
- `bastion-hostname:5000/operator-containers/nginx:acs-testing`
- `bastion-hostname:5000/operator-containers/redis:acs-testing`
- `bastion-hostname:5000/operator-containers/postgres:acs-testing`

### Custom Registry and Tag

```bash
time ansible-playbook -i ansible/inventory/cloud30.local \
  ansible/acs-spokes-workload.yml \
  -e container_images_file=./workload_images.txt \
  -e container_image_registry=registry.example.com \
  -e container_registry_port=5000 \
  -e container_image_tag=v1.0.0
```

### Custom Namespace

```bash
time ansible-playbook -i ansible/inventory/cloud30.local \
  ansible/acs-spokes-workload.yml \
  -e container_images_file=./workload_images.txt \
  -e workload_namespace=my-app
```

## How It Works

### 1. Image Reference Building

Container image names from the file are transformed into fully qualified references with registry, port, namespace, and tag:

```
Input file:           nginx
                      redis
                      postgres

With playbook defaults (bastion registry):
                      bastion-host:5000/operator-containers/nginx:acs-testing
                      bastion-host:5000/operator-containers/redis:acs-testing
                      bastion-host:5000/operator-containers/postgres:acs-testing

With custom vars:     registry.example.com:5000/myorg/nginx:v1.0.0
                      registry.example.com:5000/myorg/redis:v1.0.0
                      registry.example.com:5000/myorg/postgres:v1.0.0
```

### 2. Worker Node Discovery

For each spoke cluster:
1. Retrieve the cluster's kubeconfig from hub
2. Query the number of worker nodes (excluding infra): `oc get nodes -l node-role.kubernetes.io/worker=,node-role.kubernetes.io/infra!=`
3. Set deployment replicas to match worker count

Example: 3 worker nodes (excluding infra) → 3 deployment replicas

Note: Nodes with the `infra` role are excluded from the count, as they are typically reserved for cluster infrastructure components.

### 3. Deployment Generation

A Kubernetes Deployment manifest is generated with:

- **Dynamic replicas**: Matches worker node count
- **Dynamic containers**: One container per image in the list
- **Resource limits**: 
  - requests: 100m CPU, 128Mi memory
  - limits: 500m CPU, 512Mi memory
- **Node selector**: Schedules on worker nodes only
- **Pod anti-affinity**: Ensures one pod per worker node (when replicas ≤ workers)

### 4. Manifest Application

Each deployment is applied to the spoke cluster using `oc apply`:

```bash
oc apply -f deployment.yaml --kubeconfig=<spoke_kubeconfig>
```

## Deployment Manifest Template

The generated deployment includes:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: workload-deployment
  namespace: workload
  labels:
    app: workload-deployment
spec:
  replicas: 3  # Matches worker count
  selector:
    matchLabels:
      app: workload-deployment
  template:
    metadata:
      labels:
        app: workload-deployment
    spec:
      nodeSelector:
        node-role.kubernetes.io/worker: ""
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values:
                - workload-deployment
            topologyKey: "kubernetes.io/hostname"
      containers:
      - name: test-workload-0-0
        image: bastion-host:5000/operator-containers/nginx:acs-testing
        imagePullPolicy: Always
        resources:
          requests:
            cpu: "10m"
            memory: "128Mi"
          limits:
            cpu: "10m"
            memory: "128Mi"
        securityContext:
          privileged: false
      - name: test-workload-0-1
        image: bastion-host:5000/operator-containers/redis:acs-testing
        imagePullPolicy: Always
        resources:
          requests:
            cpu: "10m"
            memory: "128Mi"
          limits:
            cpu: "10m"
            memory: "128Mi"
        securityContext:
          privileged: false
      - name: test-workload-0-2
        image: bastion-host:5000/operator-containers/postgres:acs-testing
        imagePullPolicy: Always
        resources:
          requests:
            cpu: "10m"
            memory: "128Mi"
          limits:
            cpu: "10m"
            memory: "128Mi"
        securityContext:
          privileged: false
```

## Pod Distribution

With pod anti-affinity configured, Kubernetes ensures that:

1. No two pods with the same `app=workload-deployment` label run on the same hostname
2. Pods are distributed across available worker nodes
3. If replicas > available nodes, some nodes will not receive pods
4. If a node fails, pods are rescheduled to other available nodes

Example with 3 workers and 3 replicas:
```
Worker-1: pod-0 (nginx), pod-1 (redis), pod-2 (postgres)
Worker-2: pod-3 (nginx), pod-4 (redis), pod-5 (postgres)
Worker-3: pod-6 (nginx), pod-7 (redis), pod-8 (postgres)
```

Wait, that's not quite right with the anti-affinity. Let me reconsider:

With anti-affinity by hostname and 3 images:
- One pod per image can run on each worker
- Total pods = 3 replicas × 3 containers = 9 pods across 3 workers

Actually the deployment spec has `replicas: 3`, meaning 3 copies of the entire pod template (which contains 3 containers). The anti-affinity prevents multiple copies of the deployment pod on the same node.

Distribution with 3 workers:
```
Worker-1: workload-deployment-xxxxx (3 containers: nginx, redis, postgres)
Worker-2: workload-deployment-yyyyy (3 containers: nginx, redis, postgres)
Worker-3: workload-deployment-zzzzz (3 containers: nginx, redis, postgres)
```

## Output

The playbook displays a summary after all clusters are processed:

```
TASK [spokes-workload-deployment : Display deployment summary footer]
ok: [localhost] => {
    "msg": "============================================\nWorkload Deployment Summary\n============================================\nTotal clusters processed: 3\nSuccessfully deployed: 3\nFailed: 0\n============================================"
}
```

Per-cluster details show:
- Cluster name
- Status (SUCCESS or FAILED)
- Replica count used
- Deployment timestamp

## Idempotency

The playbook is idempotent:
- Running it multiple times applies the same manifest without error
- Existing deployments are updated (via `oc apply`)
- Changes are only applied when manifest differs from running deployment

## Troubleshooting

### "container_images_file must be set to a valid file path"

Ensure the file exists and the path is correct:
```bash
ls -la ./workload_images.txt
```

### "managed_clusters group must exist"

Verify the inventory file has a `[managed_clusters]` section with cluster names:
```bash
grep -A 5 "\[managed_clusters\]" ansible/inventory/cloud30.local
```

### "get nodes" fails on spoke cluster

Verify kubeconfig is valid:
```bash
oc get nodes --kubeconfig=/tmp/spoke.kubeconfig
```

### Pods not scheduling on workers

Check worker node labels:
```bash
oc get nodes --show-labels
```

Ensure workers have: `node-role.kubernetes.io/worker=`

### Customizing resource limits and registry namespace

Adjust resource requests/limits and registry namespace via playbook variables:
```bash
time ansible-playbook -i ansible/inventory/cloud30.local \
  ansible/acs-spokes-workload.yml \
  -e container_images_file=./workload_images.txt \
  -e container_registry_namespace=myapp \
  -e container_cpu_request=50m \
  -e container_cpu_limit=100m \
  -e container_memory_request=256Mi \
  -e container_memory_limit=512Mi
```

## Best Practices

1. **Test with small images first**: Use lightweight images like `nginx:alpine` before deploying large containers
2. **Verify worker node count**: Check `oc get nodes -l node-role.kubernetes.io/worker=` before running playbook
3. **Use consistent image names**: Ensure image names in file match actual availability in registry
4. **Monitor deployment progress**: Watch pod creation with `oc get pods -n workload -w`
5. **Set appropriate resource limits**: Ensure cluster has capacity for requested resources
6. **Use namespaces**: Deploy to separate namespaces for isolation between tests

## Related Documentation

- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Pod Anti-Affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#affinity-and-anti-affinity)
- [OpenShift Node Roles](https://docs.openshift.com/container-platform/latest/nodes/nodes/nodes-nodes-working.html)
- [ACM Managed Clusters](https://access.redhat.com/documentation/en-us/red_hat_advanced_cluster_management/)
