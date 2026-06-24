# Stats File Format and Unit Reference

Shared reference for skills that read stats files produced by analyze-prometheus.py.

## Stats File Format (pandas describe)

Each `.stats` file is a pandas `describe()` output with added percentiles (95%, 99%).
Format is whitespace-aligned columns.

### Unit: Header Detection

Stats files produced after commit 310f8ab include a `Unit:` header as the first
line (e.g., `Unit: Network (Mbps)`, `Unit: CPU (cores)`). Older stats files have
no header — the first line is the column label.

**Detection logic:**
1. Read the first line of the stats file.
2. If it starts with `Unit:`, parse the unit string — values are in the stated
   unit (e.g., `Network (Mbps)` → values are in Mbps). Skip this line before
   reading the pandas output.
3. If no `Unit:` header exists (old results), infer unit from context:
   - Network files are in **MiB/s** — convert to Mbps for reports:
     `Mbps = MiB/s × 8.388608` (1 MiB = 1,048,576 bytes = 8,388,608 bits)
   - All other metrics retain their default units (cores, GiB, GB, etc.)

The `Unit:` header applies to ALL stats files (not just network). For non-network
metrics the unit hasn't changed, but the header confirms it (e.g., `Unit: CPU (cores)`,
`Unit: Memory (GiB)`, `Unit: Disk Usage (GB)`).

Use Gbps when the Mbps value exceeds 1000 (divide Mbps by 1000).

### Single-Column Example (with Unit: header)

```
Unit: CPU (cores)
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

### Multi-Column Example (multiple nodes/pods/namespaces)

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

### Parsing

1. Read the first line — if it starts with `Unit:`, record the unit and skip
2. The next row contains column headers (node names, pod names, or labels)
3. Subsequent rows: count, mean, std, min, 25%, 50%, 75%, 95%, 99%, max
4. Values are floating point

```python
def read_stats_simple(filepath):
    """Parse stats file without pandas."""
    with open(filepath) as f:
        lines = f.readlines()
    start = 1 if lines[0].startswith('Unit:') else 0
    headers = lines[start].split()
    result = {h: {} for h in headers}
    for line in lines[start + 1:]:
        parts = line.split()
        stat_name = parts[0]
        for i, h in enumerate(headers):
            result[h][stat_name] = float(parts[i + 1])
    return result
```

## Unit Conversion Reference

| Stats Unit | Raw Prometheus Unit | Conversion | Type |
|---|---|---|---|
| cores | CPU seconds (irate) | direct | — |
| GiB | bytes | / 1024^3 (1,073,741,824) | binary |
| MiB/s | bytes/s | / 1024^2 (1,048,576) | binary (old, no Unit: header) |
| Mbps | bytes/s | × 8 / 1,000,000 (÷ 125,000) | decimal (new, Unit: header present) |
| GB | bytes | / 1000^3 (1,000,000,000) | decimal |
| MB/s | bytes/s | / 1000^2 (1,000,000) | decimal |
| IOPS | operations/s | direct | — |
| seconds | seconds | direct | — |
| count | count | direct | — |

Memory uses **binary** prefixes (GiB).
Disk usage, disk throughput, etcd DB size, and PVC usage use **decimal** prefixes (GB, MB).

**Resolving unit uncertainty — consult analyze-prometheus.py directly:**
If any metric's unit is unclear, read `acm-deploy-load/analyze-prometheus.py` (in
the project root). It is the authoritative source. Two things to look up:

1. **The `y_unit` string** passed to `query_thanos()` for that metric (e.g.,
   `"DISK_USAGE"`, `"MEMORY"`, `"CORES"`). Search for the output filename
   (e.g., `"pvc-usage"`, `"db-size"`) to find the call.

2. **The conversion block** in `query_thanos()` that handles that `y_unit` value.
   Each branch shows the exact divisor:
   - `MEMORY`       → `bytes / (1024^3)`        → GiB (binary)
   - `DISK_USAGE`   → `bytes / (1000^3)`        → GB  (decimal)
   - `NET`          → `bytes × 8 / 1,000,000`   → Mbps (new, Unit: header)
                      Previously `bytes / (1024^2)` → MiB/s (old, no header)
   - `DISK_TPUT_MB` → `bytes / (1000^2)`        → MB/s

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

The `analysis` file in each Prometheus analysis directory contains:

```
Analyzed Cluster Version: 4.20.15
Start Time: 2026-04-11 13:44:53
End Time: 2026-04-12 14:45:21
Buffer time: 0s
Examining duration: 90028s :: 1 day, 1:00:28
Query duration: 1500m
Query route: https://thanos-querier-openshift-monitoring.apps.example.com
```

## Prometheus Analysis Directory Structure

Each phase directory and full-test analysis directory has this internal layout:

```
{analysis-dir}/
├── analysis                    # Metadata: cluster version, time range, duration
├── report.html                 # HTML report with embedded graph links
├── cluster/
│   ├── {metric}.png
│   ├── csv/{metric}.csv
│   └── stats/{metric}.stats
├── node/
│   ├── {metric}.png
│   ├── csv/{metric}.csv
│   └── stats/{metric}.stats
├── etcd/
│   ├── csv/{metric}.csv
│   └── stats/{metric}.stats
├── resource/
│   ├── csv/{metric}.csv
│   └── stats/{metric}.stats
├── base-ocp/
│   └── stats/{metric}.stats
├── core-ocp/
│   └── stats/{metric}.stats
└── {component}/                # One per detected component
    ├── {metric}.png
    ├── csv/{metric}.csv
    └── stats/{metric}.stats
```

**Stats files are always under the `stats/` subdirectory** — never directly
under the component directory.
