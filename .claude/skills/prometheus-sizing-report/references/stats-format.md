# Stats File Format — Sizing Report Reference

For the full stats file format (pandas describe parsing, `Unit:` header detection,
unit conversion table, CSV format, analysis metadata), see
`.claude/skills/shared-references/stats-file-format.md`.

This file documents which stats files to read for hardware sizing reports.

## Key Files for Sizing (Node-Level)

Always present in every Prometheus analysis directory.

| File | Metric | Unit | Sizing Use |
|------|--------|------|------------|
| `node/stats/cpu-node.stats` | CPU usage | cores | P95 for sizing |
| `node/stats/mem-node.stats` | Memory usage | GiB | Max for sizing |
| `node/stats/net-rcv-node.stats` | Network receive | Mbps or MiB/s* | P95 for NIC sizing |
| `node/stats/net-xmt-node.stats` | Network transmit | Mbps or MiB/s* | P95 for NIC sizing |
| `node/stats/disk-iops-*-node.stats` | Disk IOPS | IOPS | P95 for disk sizing |
| `node/stats/disk-tput-*-node.stats` | Disk throughput | MB/s | P95 for disk sizing |
| `node/stats/disk-util-*-node.stats` | Disk partition used space | **GB (not %)** | Max for capacity planning |
| `node/stats/nonterm-pods-node.stats` | Non-terminated pods | count | Max vs max-pods limit |

## Key Files for Sizing (etcd)

Always present on control plane nodes.

| File | Metric | Unit | Sizing Use |
|------|--------|------|------------|
| `etcd/stats/db-size.stats` | DB total size | **GB** (bytes/1000^3) | Max vs 8.59 GB quota |
| `etcd/stats/db-size-in-use.stats` | DB used size | **GB** (bytes/1000^3) | Actual data size |
| `etcd/stats/backend-commit-duration.stats` | Commit latency | seconds | P99 < 25ms target |
| `etcd/stats/fsync-duration.stats` | WAL sync latency | seconds | P99 < 10ms target |

## Key Files for Resource Counts

| File | Metric | Unit | Note |
|------|--------|------|------|
| `resource/stats/namespaces.stats` | Namespace count | count | |
| `resource/stats/pods.stats` | Total pod count | count | **Includes terminated — do not use for max-pods** |
| `resource/stats/configmaps.stats` | ConfigMap count | count | |
| `resource/stats/pvc-usage.stats` | PVC usage per namespace | **GB** (bytes/1000^3) | |

Use `cluster/stats/nonterm-pods-cluster.stats` for max-pods comparison, NOT
`resource/stats/pods.stats`.

## Key Files for Component Breakdown

| File Pattern | Metric | Unit |
|-------------|--------|------|
| `{comp}/stats/cpu-{comp}.stats` | Component CPU | cores |
| `{comp}/stats/mem-{comp}.stats` | Component memory | GiB |
| `{comp}/stats/net-rcv-{comp}.stats` | Component net receive | Mbps or MiB/s* |
| `{comp}/stats/net-xmt-{comp}.stats` | Component net transmit | Mbps or MiB/s* |

**Always use `mem-{comp}.stats` for total memory.** Sub-grouping and per-pod
files undercount.

\* Check the `Unit:` header on the first line of the stats file. If present
(e.g., `Unit: Network (Mbps)`), values are in Mbps. If no header, values are
in MiB/s (old format) — convert to Mbps with: Mbps = MiB/s × 8.388608.
