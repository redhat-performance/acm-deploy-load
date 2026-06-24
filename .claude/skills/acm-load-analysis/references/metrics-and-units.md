# Metrics and Units Reference

Canonical list of every metric, its stats file location, unit, and which statistic
to extract. When in doubt about a unit, consult the `y_unit` parameter in
`acm-deploy-load/analyze-prometheus.py` — it is the authoritative source.

## Statistic Selection Rules

| Resource Type | Statistic | Rationale |
|---|---|---|
| CPU | P95 | Sustained load excluding brief spikes (GC, cert rotation) |
| Memory | Max | Memory pressure causes OOM kills — size for worst case |
| Network | P95 | Sustained throughput, not momentary bursts |
| Disk IOPS | P95 | Sustained I/O load |
| Disk Throughput | P95 | Sustained throughput |
| Disk Usage | Max | Capacity planning — worst case consumed |
| etcd Latency | P99 | etcd SLO targets are defined at P99 |
| etcd DB Size | Max | Quota enforcement is on absolute size |
| Pod/Object Counts | Max | Limit enforcement is on peak count |
| PVC Usage | Max | Capacity planning — worst case consumed |

**Never use mean/average for any resource metric.**

## Node-Level Metrics

Stats files under `node/stats/` — one column per node hostname.

| Metric | Stats File | Stats Unit | Report Unit | Statistic |
|---|---|---|---|---|
| CPU Total | `node/stats/cpu-node.stats` | cores | cores | P95 |
| CPU App | `node/stats/cpu-node-app.stats` | cores | cores | P95 |
| Memory Total | `node/stats/mem-node.stats` | GiB | GiB | Max |
| Memory App | `node/stats/mem-node-app.stats` | GiB | GiB | Max |
| Network Receive | `node/stats/net-rcv-node.stats` | MiB/s or Mbps† | Mbps | P95 |
| Network Transmit | `node/stats/net-xmt-node.stats` | MiB/s or Mbps† | Mbps | P95 |
| Disk IOPS Read (root) | `node/stats/disk-iops-read-root-node.stats` | IOPS | IOPS | P95 |
| Disk IOPS Write (root) | `node/stats/disk-iops-write-root-node.stats` | IOPS | IOPS | P95 |
| Disk IOPS Read (etcd) | `node/stats/disk-iops-read-etcd-node.stats` | IOPS | IOPS | P95 |
| Disk IOPS Write (etcd) | `node/stats/disk-iops-write-etcd-node.stats` | IOPS | IOPS | P95 |
| Disk Throughput Read (root) | `node/stats/disk-tput-read-root-node.stats` | MB/s | MB/s | P95 |
| Disk Throughput Write (root) | `node/stats/disk-tput-write-root-node.stats` | MB/s | MB/s | P95 |
| Disk Throughput Read (etcd) | `node/stats/disk-tput-read-etcd-node.stats` | MB/s | MB/s | P95 |
| Disk Throughput Write (etcd) | `node/stats/disk-tput-write-etcd-node.stats` | MB/s | MB/s | P95 |
| Disk Usage (root) | `node/stats/disk-util-root-node.stats` | GB | GB | Max |
| Disk Usage (etcd) | `node/stats/disk-util-etcd-node.stats` | GB | GB | Max |
| Disk Usage (containers) | `node/stats/disk-util-containers-node.stats` | GB | GB | Max |
| Non-terminated Pods | `node/stats/nonterm-pods-node.stats` | count | count | Max |

**Disk usage is in GB (decimal, bytes/1000^3), NOT a percentage.**

## Cluster-Level Metrics

Stats files under `cluster/stats/` — single column labeled `cluster`.

| Metric | Stats File | Stats Unit | Report Unit | Statistic |
|---|---|---|---|---|
| CPU Total | `cluster/stats/cpu-cluster.stats` | cores | cores | P95 |
| CPU App | `cluster/stats/cpu-cluster-app.stats` | cores | cores | P95 |
| Memory Total | `cluster/stats/mem-cluster.stats` | GiB | GiB | Max |
| Memory App | `cluster/stats/mem-cluster-app.stats` | GiB | GiB | Max |
| Network Receive | `cluster/stats/net-rcv-cluster.stats` | MiB/s or Mbps† | Mbps/Gbps | P95 |
| Network Transmit | `cluster/stats/net-xmt-cluster.stats` | MiB/s or Mbps† | Mbps/Gbps | P95 |
| Non-terminated Pods | `cluster/stats/nonterm-pods-cluster.stats` | count | count | Max |
| Node Status | `cluster/stats/cluster-node-status.stats` | count | count | Max |

**Cluster network** is the sum of all container network I/O across all pods on
the entire cluster, including intra-node pod-to-pod traffic that never leaves
the host (e.g., API server to etcd, Prometheus scraping local targets, OVN
internal traffic, Ceph replication between co-located OSDs). It will be much
larger than per-node NIC throughput. These measure different things — do not
compare them directly. Reports should include a note below cluster-level
resource tables explaining this distinction.

## etcd Metrics

Stats files under `etcd/stats/` — one column per etcd member (node hostname).

| Metric | Stats File | Unit | Statistic | Target |
|---|---|---|---|---|
| DB Size | `etcd/stats/db-size.stats` | GB | Max | < 8.59 GB |
| DB Size In Use | `etcd/stats/db-size-in-use.stats` | GB | Max | — |
| Backend Commit Duration | `etcd/stats/backend-commit-duration.stats` | seconds | P99 | < 0.025s |
| WAL Fsync Duration | `etcd/stats/fsync-duration.stats` | seconds | P99 | < 0.010s |
| Peer Round-Trip Time | `etcd/stats/peer-round-trip-time.stats` | seconds | P99 | — |
| Leader Elections | `etcd/stats/leader-elections-day.stats` | count | Max | 0 |

**etcd DB size is in GB (decimal), NOT GiB.** The etcd quota of 8 GiB binary
equals 8.59 GB decimal. Compare Max against 8.59 GB.

## Component Metrics

Stats files under `{component}/stats/` — column labels vary (aggregate label,
namespace name, or pod name).

| Metric | Stats File | Stats Unit | Report Unit | Statistic |
|---|---|---|---|---|
| CPU | `{comp}/stats/cpu-{comp}.stats` | cores | cores | P95 |
| Memory | `{comp}/stats/mem-{comp}.stats` | GiB | GiB | Max |
| Network Receive | `{comp}/stats/net-rcv-{comp}.stats` | MiB/s or Mbps† | Mbps | P95 |
| Network Transmit | `{comp}/stats/net-xmt-{comp}.stats` | MiB/s or Mbps† | Mbps | P95 |

**Always use `mem-{comp}.stats` for total memory.** A component directory may
contain sub-grouping files (e.g., `mem-acm-obs-rcv-total.stats`) and per-pod
files (e.g., `mem-acm-obs-pods.stats`). These undercount and must not be used
for the component total.

### Known Components (detected by analyze-prometheus.py)

| Directory | Description | Namespaces |
|---|---|---|
| `acm-mce-complete` | ACM + MCE combined | open-cluster-management*, hive, hypershift, multicluster-engine, openshift-user-workload-monitoring |
| `acm-complete` | ACM all namespaces | open-cluster-management* |
| `mce-complete` | MCE all namespaces | hive, hypershift, multicluster-engine, openshift-user-workload-monitoring |
| `acm` | ACM core | open-cluster-management |
| `acm-hub` | ACM hub | open-cluster-management-hub |
| `acm-agent` | ACM agent | open-cluster-management-agent, -agent-addon |
| `acm-observability` | ACM Observability | open-cluster-management-observability |
| `mce` | MCE core | multicluster-engine |
| `hive` | Hive | hive |
| `hypershift` | HyperShift | hypershift |
| `hypershift-uwm` | User Workload Monitoring | openshift-user-workload-monitoring |
| `base-ocp` | Base OpenShift platform | openshift-* (platform namespaces) |
| `core-ocp` | Core OCP control plane | openshift-etcd, -kube-apiserver, etc. |
| `odf` | OpenShift Data Foundation | openshift-storage |
| `lso` | Local Storage Operator | openshift-local-storage |
| `gitops` | GitOps/ArgoCD | openshift-gitops, openshift-gitops-operator |
| `talm` | TALM | openshift-cluster-group-upgrades |
| `aap` | Ansible Automation Platform | ansible-automation-platform |
| `minio` | MinIO | minio |
| `mcgh` | Multicluster Global Hub | multicluster-global-hub |
| `ztp-day2` | ZTP Day 2 Automation | ztp-day2-automation |

## Resource Count Metrics

Stats files under `resource/stats/`.

| Metric | Stats File | Unit | Statistic |
|---|---|---|---|
| All API Objects | `resource/stats/all.stats` | count | Max |
| Pods (all phases) | `resource/stats/pods.stats` | count | Max |
| Namespaces | `resource/stats/namespaces.stats` | count | Max |
| ConfigMaps | `resource/stats/configmaps.stats` | count | Max |
| Secrets | `resource/stats/secrets.stats` | count | Max |
| Deployments | `resource/stats/deployments.stats` | count | Max |
| Services | `resource/stats/services.stats` | count | Max |
| PVC Usage | `resource/stats/pvc-usage.stats` | GB | Max |

**Warning:** `resource/stats/pods.stats` counts all pods including
terminated/completed. Use `cluster/stats/nonterm-pods-cluster.stats` for
max-pods limit comparison.

## ODF/Ceph Metrics (when present)

Stats files under `odf/stats/`. Only present when ODF is installed.

| Metric | Stats File | Unit | Statistic |
|---|---|---|---|
| Ceph Used Capacity | `odf/stats/ceph-cluster-used-capacity.stats` | GB | Max |
| Ceph Total Capacity | `odf/stats/ceph-cluster-total-capacity.stats` | TB | (constant) |
| Ceph IOPS Read | `odf/stats/ceph-iops-read.stats` | IOPS | P95 |
| Ceph IOPS Write | `odf/stats/ceph-iops-write.stats` | IOPS | P95 |
| Ceph OSD Used Total | `odf/stats/ceph-osd-used-total.stats` | GB | Max |
| NooBaa Usage | `odf/stats/noobaa-usage.stats` | GB | Max |

## Unit Conversion and Stats File Format

For the full unit conversion reference table, `Unit:` header detection logic,
stats file parsing format, and CSV/analysis metadata formats, see
`.claude/skills/shared-references/stats-file-format.md`.

Summary: Memory uses **binary** prefixes (GiB). Disk usage, disk throughput,
etcd DB size, and PVC usage use **decimal** prefixes (GB, MB). Network stats
without a `Unit:` header are in MiB/s — convert to Mbps (× 8.388608).

## Workload Timing Stats

These files at the result top level use plaintext format (NOT pandas describe).
Parse by looking for the lines containing percentile values:

| Metric | Stats File Pattern | Unit |
|---|---|---|
| ICI install time | `imageclusterinstalls-{TS}.stats` | seconds |
| CGU policy time | `clustergroupupgrades-ztp-install-{TS}.stats` | seconds |
| CI total duration | `clusterinstances-{TS}.stats` | seconds |
| ACI install time | `agentclusterinstalls-{TS}.stats` | seconds |

Extract: Count, p50, p95, p99, Max. Ignore Average/Min.
