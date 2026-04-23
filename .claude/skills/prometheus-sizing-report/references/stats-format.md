# Stats File Format Reference

Stats files are produced by analyze-prometheus.py (or compatible tools) and contain
pre-computed statistics from Prometheus time-series data.

## File Format

Each `.stats` file is a pandas `describe()` output with added percentiles (95%, 99%).
Format is whitespace-aligned columns.

### Single-column example (one node or aggregate)

```
       d26-h10-000-r650
count       1498.000000
mean           3.118071
std            0.704942
min            2.112000
25%            2.697083
50%            2.967833
75%            3.372417
95%            4.263050
99%            5.332863
max           12.535333
```

### Multi-column example (multiple nodes, pods, or namespaces)

```
       multicluster-engine  open-cluster-management-observability  openshift-monitoring
count          1498.000000                            1498.000000           1498.000000
mean              3.114103                              19.945023             14.937174
std               0.000031                               0.018498              0.548514
min               3.114090                              19.908485             13.483614
25%               3.114090                              19.932463             14.617506
50%               3.114090                              19.946287             14.959174
75%               3.114090                              19.961555             15.353569
95%               3.114152                              19.971705             15.762342
99%               3.114152                              19.973777             15.896560
max               3.114648                              19.974119             15.963668
```

## Parsing

To parse stats files:
1. Read the file as whitespace-separated values
2. First row contains column headers (node names, pod names, or labels)
3. Subsequent rows are labeled: count, mean, std, min, 25%, 50%, 75%, 95%, 99%, max
4. Values are floating point

### Python parsing example

```python
import pandas as pd

def read_stats(filepath):
    """Read a .stats file and return a dict of {column: {stat: value}}."""
    df = pd.read_csv(filepath, sep=r'\s+', index_col=0)
    return df.to_dict()

# Or without pandas:
def read_stats_simple(filepath):
    """Parse stats file without pandas."""
    with open(filepath) as f:
        lines = f.readlines()
    headers = lines[0].split()
    result = {h: {} for h in headers}
    for line in lines[1:]:
        parts = line.split()
        stat_name = parts[0]
        for i, h in enumerate(headers):
            result[h][stat_name] = float(parts[i + 1])
    return result
```

## Directory Structure

Each analysis run produces this structure:

```
{analysis-run}/
├── analysis                      # Metadata (plain text key-value)
├── report.html                   # HTML report with embedded graphs
├── node/
│   ├── cpu-node.png             # Graph
│   ├── csv/cpu-node.csv         # Time-series data
│   └── stats/cpu-node.stats     # Statistics
├── etcd/
│   ├── csv/
│   └── stats/
├── cluster/
│   ├── csv/
│   └── stats/
├── resource/
│   ├── csv/
│   └── stats/
├── base-ocp/                    # (if detected)
│   ├── csv/
│   └── stats/
└── {component}/                 # One directory per detected component
    ├── csv/
    └── stats/
```

## Key Files by Category

### Node-level (always present)
| File | Metric | Unit | Sizing Use |
|------|--------|------|------------|
| `node/stats/cpu-node.stats` | CPU usage | cores | P95 for sizing |
| `node/stats/mem-node.stats` | Memory usage | GiB | Max for sizing |
| `node/stats/net-rcv-node.stats` | Network receive | MiB/s | P95 for NIC sizing |
| `node/stats/net-xmt-node.stats` | Network transmit | MiB/s | P95 for NIC sizing |
| `node/stats/disk-iops-*-node.stats` | Disk IOPS | IOPS | P95 for disk sizing |
| `node/stats/disk-tput-*-node.stats` | Disk throughput | MB/s | P95 for disk sizing |
| `node/stats/disk-util-*-node.stats` | Disk partition used space | **GB (not %)** | Max for capacity planning |
| `node/stats/nonterm-pods-node.stats` | Non-terminated pods | count | Max vs max-pods limit |

### etcd (always present on control plane)
| File | Metric | Unit | Sizing Use |
|------|--------|------|------------|
| `etcd/stats/db-size.stats` | DB total size | **GB** (bytes/1000^3) | Max vs quota |
| `etcd/stats/db-size-in-use.stats` | DB used size | **GB** (bytes/1000^3) | Actual data size |
| `etcd/stats/backend-commit-duration.stats` | Commit latency | seconds | P99 < 25ms target |
| `etcd/stats/fsync-duration.stats` | WAL sync latency | seconds | P99 < 10ms target |

### Resource counts
| File | Metric | Unit |
|------|--------|------|
| `resource/stats/namespaces.stats` | Namespace count | count |
| `resource/stats/pods.stats` | Total pod count **including terminated/completed pods** | count |
| `resource/stats/configmaps.stats` | ConfigMap count | count |
| `resource/stats/pvc-usage.stats` | PVC usage per namespace | **GB** (bytes/1000^3) |

**Warning:** `resource/stats/pods.stats` counts all pods regardless of phase,
including completed Jobs and terminated pods. It will be higher than the
schedulable pod count and must **not** be used to assess max-pods headroom.
Use `cluster/stats/nonterm-pods-cluster.stats` for max-pods comparison.

### Component-level (per detected component)
| File Pattern | Metric | Unit |
|-------------|--------|------|
| `{comp}/stats/cpu-{comp}.stats` | Component CPU | cores |
| `{comp}/stats/mem-{comp}.stats` | Component memory | GiB |
| `{comp}/stats/net-rcv-{comp}.stats` | Component net receive | MiB/s |
| `{comp}/stats/net-xmt-{comp}.stats` | Component net transmit | MiB/s |

## CSV File Format

CSV files contain the raw time-series data at 1-minute resolution:

```csv
,datetime,d26-h10-000-r650
0,2026-04-11 13:46:00+00:00,3.187333333333399
1,2026-04-11 13:47:00+00:00,2.8093333333333845
2,2026-04-11 13:48:00+00:00,3.5690000000000452
```

- First column: row index
- `datetime`: ISO 8601 with UTC timezone
- Remaining columns: one per series (node, pod, aggregate)
- Values in the same units as stats files

## Analysis Metadata File

The `analysis` file in each run directory contains:

```
Analyzed Cluster Version: 4.20.15
Start Time: 2026-04-11 13:44:53
End Time: 2026-04-12 14:45:21
Buffer time: 0s
Examining duration: 90028s :: 1 day, 1:00:28
Query duration: 1500m
Query route: https://thanos-querier-openshift-monitoring.apps.example.com
```
