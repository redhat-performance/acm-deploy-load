# Prometheus Query Reference

Catalog of Prometheus queries useful for hardware sizing analysis. These queries
target Kubernetes/OpenShift clusters via Thanos Querier or Prometheus directly.

## Query Execution

### Endpoint discovery (OpenShift)
```bash
# Get Thanos Querier route
oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}'

# Get bearer token
oc sa get-token prometheus-k8s -n openshift-monitoring
# Or: oc whoami -t
```

### Query via API
```bash
curl -k -H "Authorization: Bearer $TOKEN" \
  "https://$THANOS_HOST/api/v1/query_range" \
  --data-urlencode "query=<QUERY>" \
  --data-urlencode "start=2026-01-01T00:00:00Z" \
  --data-urlencode "end=2026-01-01T12:00:00Z" \
  --data-urlencode "step=60"
```

### Response format
```json
{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": [
      {
        "metric": {"instance": "node1", ...},
        "values": [[1700000000, "3.14"], [1700000060, "3.25"], ...]
      }
    ]
  }
}
```

Values are always strings. Timestamps are Unix epoch seconds. Step=60 gives
1-minute resolution.

## Node-Level Queries

### CPU — Total usage per node (cores)

Sum of all container CPU on the node:
```promql
sum by (instance) (
  node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster=''}
)
```

CPU used by applications (excludes system containers):
```promql
sum by (instance) (
  node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{
    cluster='',
    namespace!~'openshift-.*|kube-.*|default|openshift'
  }
)
```

### Memory — Usage per node (bytes, convert to GiB)

Total memory minus available:
```promql
(node_memory_MemTotal_bytes{cluster=''} - node_memory_MemAvailable_bytes{cluster=''})
```

Container working set memory per node:
```promql
sum by (instance) (
  container_memory_working_set_bytes{cluster='', container!='', container!='POD'}
)
```

### Network — Per node (bytes/s, convert to MiB/s)

Receive (1-minute rate, excludes loopback):
```promql
instance:node_network_receive_bytes_excluding_lo:rate1m{cluster=''}
```

Transmit:
```promql
instance:node_network_transmit_bytes_excluding_lo:rate1m{cluster=''}
```

### Disk I/O

Write IOPS per device:
```promql
irate(node_disk_writes_completed_total{cluster='', device=~'sd.*|nvme.*'}[5m])
```

Write throughput (bytes/s):
```promql
irate(node_disk_written_bytes_total{cluster='', device=~'sd.*|nvme.*'}[5m])
```

Read IOPS:
```promql
irate(node_disk_reads_completed_total{cluster='', device=~'sd.*|nvme.*'}[5m])
```

Read throughput:
```promql
irate(node_disk_read_bytes_total{cluster='', device=~'sd.*|nvme.*'}[5m])
```

### Disk Usage (bytes, convert to GB)

```promql
node_filesystem_size_bytes{cluster='', mountpoint=~'/sysroot|/var/lib/etcd|/var/lib/containers'}
- node_filesystem_avail_bytes{cluster='', mountpoint=~'/sysroot|/var/lib/etcd|/var/lib/containers'}
```

### Non-terminated pod count per node

```promql
sum by (node) (
  kube_pod_status_phase{cluster='', phase!='Succeeded', phase!='Failed'}
)
```

Note: `apiserver_storage_objects{resource='pods'}` counts ALL pods including
terminated (Succeeded/Failed). Use `kube_pod_status_phase` for non-terminated count.

## etcd Queries

### Database size (bytes, convert to GiB)

```promql
etcd_mvcc_db_total_size_in_bytes{cluster=''}
```

In-use size (after compaction):
```promql
etcd_mvcc_db_total_size_in_use_in_bytes{cluster=''}
```

### Latency

Backend commit duration (P99):
```promql
histogram_quantile(0.99,
  irate(etcd_disk_backend_commit_duration_seconds_bucket{cluster=''}[5m])
)
```
Target: P99 < 25ms (0.025s)

WAL fsync duration (P99):
```promql
histogram_quantile(0.99,
  irate(etcd_disk_wal_fsync_duration_seconds_bucket{cluster=''}[5m])
)
```
Target: P99 < 10ms (0.010s)

### Leader elections

```promql
changes(etcd_server_leader_changes_seen_total{cluster=''}[1d])
```
Target: 0 changes per day in stable operation.

## Namespace/Component Queries

### CPU per namespace group (cores)

```promql
sum(
  node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{
    cluster='',
    namespace=~'namespace1|namespace2|namespace3'
  }
)
```

### Memory per namespace group (bytes)

```promql
sum(
  container_memory_working_set_bytes{
    cluster='',
    container!='', container!='POD',
    namespace=~'namespace1|namespace2|namespace3'
  }
)
```

### Network per namespace (bytes/s)

Receive:
```promql
sum by (namespace) (
  irate(container_network_receive_bytes_total{
    cluster='',
    namespace=~'namespace1|namespace2'
  }[5m])
)
```

## Resource Count Queries

### API object counts

```promql
apiserver_storage_objects{resource='pods'}
apiserver_storage_objects{resource='configmaps'}
apiserver_storage_objects{resource='secrets'}
apiserver_storage_objects{resource='namespaces'}
apiserver_storage_objects{resource='deployments.apps'}
apiserver_storage_objects{resource='services'}
```

Note: These counts include ALL objects (including terminated pods, completed jobs).

### PVC usage (bytes, convert to GiB)

```promql
sum by (namespace) (
  kubelet_volume_stats_used_bytes{cluster=''}
)
```

## Cluster-Wide Aggregates

### Total cluster CPU (cores)

```promql
sum(
  node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster=''}
)
```

### Total cluster memory (bytes)

```promql
sum(
  container_memory_working_set_bytes{cluster='', container!='', container!='POD'}
)
```

### Node status

```promql
sum by (condition) (
  kube_node_status_condition{cluster='', status='true'}
)
```

## Common Namespace Groupings

These are examples — the actual groupings depend on what's installed. Always confirm
with the user.

### OpenShift base platform
```
openshift-apiserver|openshift-authentication|openshift-cloud-controller-manager|
openshift-cluster-machine-approver|openshift-cluster-node-tuning-operator|
openshift-cluster-samples-operator|openshift-cluster-storage-operator|
openshift-cluster-version|openshift-config-operator|openshift-console|
openshift-controller-manager|openshift-dns|openshift-etcd|
openshift-image-registry|openshift-ingress|openshift-kube-apiserver|
openshift-kube-controller-manager|openshift-kube-scheduler|
openshift-kube-storage-version-migrator|openshift-machine-api|
openshift-machine-config-operator|openshift-marketplace|
openshift-monitoring|openshift-multus|openshift-network-operator|
openshift-oauth-apiserver|openshift-operator-lifecycle-manager|
openshift-route-controller-manager|openshift-sdn|openshift-service-ca
```

## Unit Conversion Reference

| Prometheus Unit | Sizing Unit | Conversion |
|----------------|-------------|------------|
| CPU irate (cores) | cores | direct (no conversion) |
| bytes (memory) | GiB | divide by 1024^3 (1,073,741,824) |
| bytes/s (network) | MiB/s | divide by 1024^2 (1,048,576) |
| bytes (disk usage) | GB | divide by 1000^3 (1,000,000,000) |
| bytes/s (disk tput) | MB/s | divide by 1000^2 (1,000,000) |
| seconds (latency) | seconds | direct |
| count (objects) | count | direct |
