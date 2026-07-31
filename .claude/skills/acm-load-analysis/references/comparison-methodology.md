# Comparison Methodology

How to compare two acm-deploy-load or acm-telco-core-load test results.

## Phase Matching

When comparing two results, match data sources correctly:

| Result A | Result B | Compare |
|---|---|---|
| Has phase dirs | Has phase dirs | **Both**: phase-by-phase AND full-test (see below) |
| Has phase dirs | No phase dirs | Full-test analysis dirs only |
| No phase dirs | Has phase dirs | Full-test analysis dirs only |
| No phase dirs | No phase dirs | Full-test analysis dirs only |

The full-test Prometheus analysis directory prefix depends on which orchestration
script produced the result: `deploy-pa-*` for acm-deploy-load
(`interval-ztp-install-all.sh`) or `acm-telco-load-hub-*` for acm-telco-core-load
(`acm-telco-core-load.sh`).

**When both results have phase directories, the report MUST include both:**

1. **Phase-by-phase comparison** — a separate section per matching phase (idle↔idle,
   deployment↔deployment, soak↔soak). Each phase section includes per-node resources,
   cluster-level resources, ODF/component data (when present in that phase), and etcd.
   Phases reveal workload-specific differences (idle overhead, deployment peaks,
   sustained soak behavior) that full-test aggregates obscure.

2. **Full-test overview** — using the `deploy-pa-*` or `acm-telco-load-hub-*`
   directories. This provides the aggregate view and includes data typically only
   available at full-test scope (disk I/O, full component breakdown).

Never produce only a full-test comparison when phase data exists in both results.

For telco-core-load batch phases (`phase2-batch-{N}`), match by batch index.

## Delta Calculation

For each metric, compute:
- **Absolute delta**: Result B value - Result A value
- **Percentage delta**: ((Result B - Result A) / Result A) * 100

Present both in the comparison table. Use Result A as the baseline (denominator).

When Result A is zero, the percentage delta is undefined — show "N/A" or "—"
in the percentage column and report the absolute delta only.

## Significance Thresholds

| Delta Range | Classification | Presentation |
|---|---|---|
| < 5% | Within run-to-run variance | Note but do not emphasize |
| 5% - 10% | Minor difference | Report normally |
| 10% - 25% | Notable difference | Highlight in findings |
| > 25% | Significant difference | Call out explicitly in key findings |

These thresholds apply to resource metrics (CPU, memory, network, disk). For
timing metrics, apply a stricter standard:
- < 5%: run-to-run variance
- 5% - 15%: minor
- > 15%: notable

## Comparison Report Structure

Every comparison report uses numbered sections and a mandatory preamble that
identifies both results. The template below is the canonical structure — follow
it exactly, including only the `[conditional]` sections when data exists.

### Report Preamble

```markdown
# ACM Deploy Load Comparison: {Label A} vs {Label B}

- **Result A ({Label A}):** `{full-directory-name-A}`
- **Result B ({Label B}):** `{full-directory-name-B}`
```

Always include the full result directory names so the report is self-contained.

### Section Template

```
## 1. Test Environment Summary
## 2. Timing Comparison
     ### Deployment Milestones
     ### ICI Per-Cluster Install Time (seconds)
     ### CGU Per-Cluster Policy Time (seconds)
     ### ClusterInstance Total Duration (seconds)
     [### ACI Per-Cluster Install Time — if AI method]
## 3. Phase 1 — Idle Baseline Comparison      [conditional: both have phases]
     ### Cluster-Level Resources
     ### Per-Node CPU P95 (cores)
     ### Per-Node Memory Max (GiB)
     ### Per-Node Network P95 (Mbps)
     ### etcd
     [### {Asymmetric Component} Footprint]
## 4. Phase 2 — Cluster Deployment Comparison  [conditional]
     (same sub-structure as Phase 1)
## 5. Phase 3 — Soak Baseline Comparison       [conditional]
     (same sub-structure as Phase 1)
## N. Full-Test Hub Cluster Resource Comparison
     ### Cluster-Level Resources (Full Test)
       [graphs: cpu-cluster, mem-cluster]
     ### Per-Node CPU P95 (cores)
       [graph: cpu-node]
     ### Per-Node Memory Max (GiB)
       [graph: mem-node]
     ### Per-Node Network P95 (Mbps)
       [graphs: net-rcv-node, net-xmt-node]
     ### Per-Node Disk I/O — etcd Partition
       [graphs: disk-iops-write-etcd, disk-tput-write-etcd]
     ### Per-Node Disk Usage Max (GB)
     ### Per-Node Non-Terminated Pods Max
## N+1. Full-Test etcd Comparison
       [graphs: backend-commit-etcd, fsync-etcd, peer-rtt-etcd, db-size-etcd]
## N+2. Full-Test Component Comparison
     ### Components Present in Both Results
       (canonical order — see metrics-and-units.md)
     [### {Asymmetric Component} Resource Footprint]
## N+3. Storage Comparison
     ### PVC Usage Max (GB)
     [### Ceph Metrics — ODF Only]
     [### {Storage} Cluster Health]
## N+4. Pod Health
     ### {Label A} (A)
     ### {Label B} (B)
## N+5. Key Differences
     [### Cross-Phase Trends]
     ### Summary of Significant Findings
```

**Section numbering rules:**
- Sections 1-2 are always present.
- Phase sections start at 3 and increment per phase (3, 4, 5, ...).
- Full-test and subsequent sections number consecutively after the last phase.
- If no phases exist, full-test starts at 3.

**Phase subsection headings:** Do NOT include the phase number in subsection
headings — the parent `## N. Phase X — ...` heading already establishes context.
Use `### etcd`, not `### etcd — Phase 1`. Use `### ODF Footprint`, not
`### ODF Footprint — Phase 1`.

**Deployment Milestones:** The comparison milestones table includes only Install
Duration and DU Compliant Duration. Omit peak metrics (Peak Cluster Installing,
Peak DU Applying, Peak Concurrency) and derived gaps (DU - Install Gap) — these
reflect run-specific scheduling patterns and are not meaningful for comparison.

**Phase section descriptions:** Each phase heading includes a 1-line description
of what the phase captures (e.g., "Captures the hub cluster at rest before any
cluster deployments begin (2 hours).")

### Test Environment Summary (Section 1) Table

The Section 1 table uses these rows in this order:

```
| Parameter               | {Label A} (A) | {Label B} (B) |
|-------------------------|----------------|----------------|
| ACM Version             |                |                |
| MCE Version             |                |                |
| Hub OCP Version         |                |                |
| Deployed OCP Version    |                |                |
| Test Label              |                |                |
| Deployment Method       |                |                |
| Clusters Deployed       | count          | count          |
| Clusters Installed      | count (%)      | count (%)      |
| Managed Clusters        | count (%)      | count (%)      |
| DU Profile Compliant    | count (%)      | count (%)      |
| Clusters per ArgoCD App |                |                |
| Batch Size / Interval   | N / Xs         | N / Xs         |
| WAN Emulation           | (Xms/Y) / Z   | (Xms/Y) / Z   |
| Hub Nodes               | N (names)      | N (names)      |
| Total Duration          | Xs (H:MM:SS)   | Xs (H:MM:SS)   |
| Phase 1 (Idle)          | Xs (H:MM:SS)   | Xs (H:MM:SS)   |
| Phase 2 (Deploy)        | Xs (H:MM:SS)   | Xs (H:MM:SS)   |
| Phase 3 (Soak)          | Xs (H:MM:SS)   | Xs (H:MM:SS)   |
```

Rules:
- **Test Label**: provided by the user (defaults suggested from the directory
  name suffix — the human-readable portion after the timestamp-method prefix)
- **Success rows** (Installed, Managed, DU Profile): always show count and
  percentage — count conveys scale, percentage conveys success rate
- **Batch Size / Interval**: combined in one row
- **Hub Nodes**: node count and short names (see Node Name Convention below)
- **Duration**: always include seconds and human-readable time; Total Duration
  comes before phase durations
- **Phase rows**: conditional — include only when phase directories exist

Follow with 1-2 sentences noting what the variable under test is and any
noteworthy differences in outcomes (e.g., DU profile timeouts, duration
differences caused by test anomalies).

### Table Format Standards

**Comparison tables (5-column standard):**
```
| Metric | {Label A} (A) | {Label B} (B) | Delta | Delta % |
```

**Phase etcd table (4-column, no %):**
```
| Metric | {Label A} (A) | {Label B} (B) | Delta |
```
Rows (always all 6): DB Size Max (GB), DB Size In Use Max (GB),
Backend Commit P99 (ms), WAL Fsync P99 (ms), Peer RTT P99 (ms),
Leader Elections (during test).

**Full-test etcd:** Same 6 rows in a 5-column table (with Delta %) plus
a Target column. Follow with a threshold status table.

**Full-test etcd threshold status table (5-column):**
```
| Metric | {Label A} (A) | {Label B} (B) | Threshold | Status |
|---|---|---|---|---|
| Backend Commit P99 | {value} ms | {value} ms | < 25 ms | PASS/FAIL |
| WAL Fsync P99 | {value} ms | {value} ms | < 10 ms | PASS/FAIL |
| Peer RTT P99 | {value} ms | {value} ms | < 50 ms | PASS/FAIL |
| DB Size Max | {value} GB | {value} GB | < 8.59 GB | PASS/FAIL |
| Leader Elections | {count} | {count} | 0 | PASS/FAIL |
```
Rules:
- Values include units inline (e.g., `14.13 ms`, `7.97 GB`, `0` for elections)
- Metric names are clean — no threshold embedded in the metric name
- Threshold column uses the same format as the Target column in the main table
- Status is `PASS` when the worst-case value across both results is within the threshold; `FAIL` otherwise
- Rows appear in this fixed order regardless of which metrics are near their limit

**Per-node network — phases (compact, no deltas):**
```
| Node | A Rcv | B Rcv | A Xmt | B Xmt |
```

**Per-node network — full-test (with deltas):**
```
| Node | A Rcv | B Rcv | Delta | Delta % | A Xmt | B Xmt | Delta | Delta % |
```

**Asymmetric component footprint (2-column):**
```
| Metric | Value |
```
Always include: CPU P95 (cores), Memory Max (GiB). Optionally include:
Ceph Used Capacity Max (GB) — when data exists for that phase/scope.
Do NOT include component-level network (see below).

**Cluster-level resource tables** always include 5 rows: CPU P95 (cores),
App CPU P95 (cores), Memory Max (GiB), App Memory Max (GiB),
Non-term Pods Max.

**Component tables (Section N+2):** Use the canonical component order defined in
`metrics-and-units.md` (section "Canonical Component Table Order") — do NOT sort
by value. The CPU table and Memory table use the same component order. Include
`acm-complete` and `acm-complete-no-obs` as two separate rows from the same
`acm-complete/stats/` directory. Skip any row whose stats file is absent. ODF and
other asymmetric components (present in one result only) are reported in a
separate sub-section (`### {Component} Resource Footprint`) outside the main table.

### Node Name Convention

Use the shortest unambiguous form. If all nodes share the same domain suffix
(e.g., `-000-r650`), strip it (use `d16-h10` instead of `d16-h10-000-r650`).
If nodes have different suffixes, use the full name. Apply this consistently
across all tables in the report.

## Causation Rule

**Report observations, not theories.** State what differs and by how much.
Do not assert why two values differ unless the test design explicitly isolates
that variable.

Acceptable: "ODF run used 16 GiB more cluster memory (Max) than the No-ODF run."

Not acceptable: "ODF caused 16 GiB additional memory consumption due to Ceph
caching behavior."

When a variable is explicitly isolated by test design (e.g., the only difference
between two runs is ODF vs No-ODF), it is acceptable to attribute the delta to
that variable, but phrase it as an observation: "The 16 GiB memory delta
corresponds to the ODF overhead, as ODF was the only configuration difference."

## Handling Asymmetric Components

When one result has components the other does not (e.g., ODF in one, LSO in the
other), report the unique component's resource footprint separately rather than
as a comparison row with zero on one side. Present it as additive cost.

Asymmetric component footprint sections use the same statistics as every other
table: CPU P95, Memory Max. Never use Mean — it understates the footprint at
the percentiles that matter for sizing.

"ODF resource footprint (not present in Result A):"
| Metric | Value |
|---|---|
| CPU P95 | 0.39 cores |
| Memory Max | 8.78 GiB |

## Component Network Exclusion

Do NOT include component-level network data in comparison reports — not as a
standalone section and not in asymmetric component footprint tables.
Component-level network measures container I/O within a namespace, which
includes intra-node pod-to-pod traffic (e.g., Ceph replication between
co-located OSDs, API server to etcd). These values routinely exceed physical
NIC capacity and do not reflect actual network utilization. Report network at
the per-node level only.

## Statistic Consistency

Every table in a comparison report — whether full-test, per-phase,
per-component, or asymmetric component footprint — must use the statistic
specified in the metrics reference: P95 for CPU/Network, Max for Memory,
P99 for etcd latency, Max for etcd DB size. This applies at every scope
(phase etcd sections, full-test etcd, component footprints, cross-phase
trend tables). If data was collected without the required percentile,
re-read the stats file rather than substituting a different statistic.
Never use Mean for any resource metric.

## Comparison Graphs

When both results have full-test Prometheus analysis directories, generate
overlay time-series graphs using `graph-acm-compare.py`. The script handles
x-axis alignment (elapsed minutes), aggregation, and styling.

**Aggregation:**
- Cluster-level (cpu-cluster, mem-cluster): single data column, used directly.
- Per-node network (net-rcv-node, net-xmt-node): **max** across node columns
  at each timestamp (peak node / worst-case NIC utilization). Do not sum —
  the sum exceeds any single interface's capacity and misrepresents hardware
  requirements.
- etcd (db-size): **max** across member columns (worst-case member). The script
  adds a dashed reference line at 8.59 GB (quota).

**Resource graphs (12, from deploy-pa CSVs):**

| File Suffix | CSV | Method | Y Unit | Reference Line |
|---|---|---|---|---|
| `cpu-cluster` | `cluster/csv/cpu-cluster.csv` | Direct | Cores | — |
| `cpu-node` | `node/csv/cpu-node.csv` | Node max | Cores | — |
| `mem-cluster` | `cluster/csv/mem-cluster.csv` | Direct | GiB | — |
| `mem-node` | `node/csv/mem-node.csv` | Node max | GiB | — |
| `net-rcv-node` | `node/csv/net-rcv-node.csv` | Node max | Mbps | — |
| `net-xmt-node` | `node/csv/net-xmt-node.csv` | Node max | Mbps | — |
| `backend-commit-etcd` | `etcd/csv/backend-commit-duration.csv` | Member max | ms (CSV seconds × 1000) | 25ms |
| `db-size-etcd` | `etcd/csv/db-size.csv` | Member max | GB | 8.59 GB (8 GiB quota) |
| `disk-iops-write-etcd` | `node/csv/disk-iops-write-etcd-node.csv` | Node max | IOPS | — |
| `disk-tput-write-etcd` | `node/csv/disk-tput-write-etcd-node.csv` | Node max | MB/s | — |
| `fsync-etcd` | `etcd/csv/fsync-duration.csv` | Member max | ms (CSV seconds × 1000) | 10ms |
| `peer-rtt-etcd` | `etcd/csv/peer-roundtrip-time.csv` | Member max | ms (CSV seconds × 1000) | 50ms |

**Cluster deploy graphs (4, from monitor_data.csv):**

| File Suffix | Data Source | Y Unit |
|---|---|---|
| `deploy-installed` | `cluster_applied` + `cluster_install_completed` | # Clusters |
| `deploy-managed` | `cluster_applied` + `managed` | # Clusters |
| `deploy-compliant` | `cluster_applied` + `policy_compliant` | # Clusters |
| `deploy-all` | `cluster_applied` + all 3 milestones | # Clusters |

Each individual deploy graph shows `cluster_applied` alongside one milestone
metric. The combined `deploy-all` graph overlays all milestones with a right-side
legend. Result A uses solid blue lines (dark navy Applied, lighter blues for
milestones). Result B uses densely dotted lines graduating from dark red (Applied)
to dark orange (milestones). Applied lines are the darkest and boldest (width 2)
to emphasize the workload submission rate. Deploy graphs dynamically trim the
x-axis: idle is trimmed to 30 minutes before the earliest deploy start (only if
idle exceeds 30 min), soak is trimmed to 60 minutes after the latest soak start
(only if soak exceeds 60 min), and the deploy phase is never trimmed — the union
of both results' deploy windows is always fully visible. These are auto-generated
when `monitor_data.csv` exists in both results. Place deploy graphs in Section 2
after Deployment Milestones.

**Naming:** `comparison-{metric}.png` where metric is the file suffix from the
tables above (e.g., `comparison-cpu-cluster.png`, `comparison-deploy-installed.png`).

etcd latency thresholds: WAL fsync P99 < 10ms (Red Hat OCP docs, etcd.io FAQ),
backend commit P99 < 25ms (etcd.io FAQ, Prometheus `EtcdHighBackendCommitLatency`
alert rule), peer RTT P99 < 50ms (monitoring guidance). Memory graphs use
base-2 tick intervals (32, 64, 128 GiB, etc.).

## Multiple-Phase Comparison

When comparing phase-by-phase, produce a separate comparison section per phase
with full per-node, cluster-level, etcd, and component/ODF tables for each.

The Key Differences section at the end MUST include:
1. **A cross-phase trends table** showing how the key deltas (memory, CPU,
   network) change across phases — this is the most valuable part of a
   phase-by-phase comparison as it reveals growth patterns and workload-specific
   overhead (e.g., ODF memory growing from idle to soak, network peaks during
   deployment that subside in soak).
2. **Key findings that reference phase-specific behavior** — e.g., "overhead is
   X at idle but Y during deployment" rather than a single full-test number.
