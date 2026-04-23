---
name: prometheus-sizing-report
description: >
  Generate hardware sizing recommendations from Prometheus/Thanos test data collected during
  load or scale tests on Kubernetes/OpenShift clusters. Use this skill whenever the user has
  performance test results (stats files, CSV time-series, or a live Prometheus endpoint) and
  wants to produce hardware sizing guidance, resource consumption analysis, or capacity
  planning reports. Triggers on: sizing reports, hardware recommendations from test data,
  Prometheus data analysis for capacity planning, resource consumption reports, load test
  result analysis, scale test analysis, cluster sizing, node sizing. Works with both
  Single Node (SNO) and multi-node clusters. Supports PDF, Markdown, and plain text output.
---

# Prometheus Sizing Report

Generate hardware sizing recommendations from Prometheus-collected test data on
Kubernetes/OpenShift clusters.

## When to use

- User has Prometheus/Thanos test data and wants hardware sizing recommendations
- User has stats files (from analyze-prometheus.py or similar) and wants a sizing report
- User asks for capacity planning based on observed resource usage
- User wants to convert load test results into hardware requirements

## Workflow

Follow these steps in order. Each step builds on the previous one. Do not skip the
interview or test methodology steps — without understanding the test structure, the
data cannot be interpreted correctly.

### Step 1: Interview — Understand the Environment

Before reading any data, gather this information from the user. If any of these are
unknown, help the user find them from the test artifacts (kubeconfig, cluster nodes,
installed operators).

**Cluster topology:**
- Single Node (SNO) or Multi-Node (MNO)?
- If MNO: how many control plane nodes? How many workers? Are control planes schedulable?
- Hardware per node: CPU count (logical vs physical cores), RAM, disk types

**Software stack:**
- Kubernetes/OpenShift version
- Key operators or platform components installed (the user defines these — do not assume
  a fixed set of components like ACM or GitOps)
- Any external services that should be excluded from sizing (e.g., external object storage)

**Workload under test:**
- What workload was applied? (managed clusters, application deployments, policy enforcement, etc.)
- What is the scale? (number of managed clusters, pods, namespaces, etc.)

### Step 2: Interview — Understand the Test Methodology

This is critical. Different test structures require different analysis approaches.
Ask the user to describe:

**Test phases:**
- How many phases does the test have?
- What does each phase represent? (idle baseline, ramp-up, active workload, steady state, cooldown)
- Duration of each phase
- Was the workload applied all at once or in incremental batches?

**If batched/stepped:**
- How many batches?
- What was added in each batch? (e.g., 8 clusters per batch)
- Was there a measurement window between batches?
- Was the workload active (churn/activity) or static during measurement?

**Phase mapping to data:**
- Which directories or time ranges correspond to which phases?
- Are there separate analysis runs per phase, or one continuous run?

**Example test structures the skill should handle:**
- Simple two-phase: deploy everything, measure active + steady state
- Multi-phase stepped: idle baseline, incremental batches with measurement windows, steady state
- Single continuous: one long run with no distinct phases
- Before/after: baseline measurement, then change applied, then re-measure

### Step 3: Collect Data

The skill supports two data input methods:

#### Method A: Pre-collected stats files (preferred)

Stats files from analyze-prometheus.py (or compatible tools) contain pre-computed
statistics. Read `references/stats-format.md` for the exact file format.

**Resolving unit uncertainty — consult analyze-prometheus.py directly:**
If any metric's unit is unclear, read the script at
`acm-deploy-load/analyze-prometheus.py` (in the project root). It is the
authoritative source for both the Prometheus query and the unit conversion applied.
Two things to look up for any stats file:

1. **The `y_unit` string** passed to `query_thanos()` for that metric (e.g.,
   `"DISK_USAGE"`, `"MEMORY"`, `"CORES"`). Search for the output filename
   (e.g., `"pvc-usage"`, `"db-size"`) to find the call.

2. **The conversion block** in `query_thanos()` that handles that `y_unit` value.
   Each branch shows the exact divisor:
   - `MEMORY`     → `bytes / (1024^3)`  → GiB (binary)
   - `DISK_USAGE` → `bytes / (1000^3)`  → GB  (decimal) — applies to disk-util,
                                           etcd DB size, AND PVC usage
   - `NET`        → `bytes / (1024^2)`  → MiB/s
   - `DISK_TPUT_MB` → `bytes / (1000^2)` → MB/s

Do not rely on the stats filename or intuition alone to infer units. Always verify
against the script when in doubt.

**Directory structure per analysis run:**
```
{analysis-run}/
├── analysis                    # Metadata: cluster version, time range, duration
├── node/stats/                 # Node-level CPU, memory, disk, network
├── etcd/stats/                 # etcd DB size, latencies, leader elections
├── cluster/stats/              # Cluster-wide aggregates
├── resource/stats/             # API object counts, PVC usage
├── {component}/stats/          # Per-component CPU, memory, network
└── {component}/csv/            # Raw time-series (1-minute resolution)
```

**Key files to read for sizing (node-level):**
- `node/stats/cpu-node.stats` — CPU usage in cores (use P95 for sizing)
- `node/stats/mem-node.stats` — Memory usage in GiB (use Max for sizing)
- `node/stats/disk-iops-*-node.stats`, `disk-tput-*-node.stats` — Disk I/O (IOPS and throughput in MB/s)
- `node/stats/disk-util-*-node.stats` — Disk partition **used space in GB** (bytes/1000^3); NOT a percentage
- `node/stats/net-rcv-node.stats`, `net-xmt-node.stats` — Network in MiB/s
- `etcd/stats/db-size.stats` — etcd database size in **GB** (decimal, bytes/1000^3)

**Key files for component breakdown:**
- `{component}/stats/cpu-{component}.stats` — Component CPU in cores
- `{component}/stats/mem-{component}.stats` — Component memory in GiB

**Warning:** A component directory often contains multiple memory stats files —
sub-groupings (e.g., `mem-acm-obs-rcv-total.stats`) and per-pod files
(e.g., `mem-acm-obs-pods.stats`). Always use the file whose name matches
`mem-{component}.stats` exactly for the component's total memory footprint.
Sub-component files will undercount and must not be used to characterize or
compare the component as a whole (e.g., as a fraction of a parent aggregate).

**Key files for resource counts:**
- `resource/stats/*.stats` — Object counts (pods, configmaps, secrets, etc.)
- `resource/stats/pvc-usage.stats` — PVC consumption in **GB** (decimal, bytes/1000^3)

**Reading stats files:**
The stats format is pandas `describe()` output with added percentiles. Each column
is a separate series (node name, pod name, or aggregate label). Key rows:
- `count` — number of data points (1-minute samples)
- `mean`, `std` — average and standard deviation
- `min`, `25%`, `50%`, `75%`, `95%`, `99%`, `max` — distribution

**Units (already converted in stats files):**
- CPU: cores
- Memory: GiB (bytes / 1024^3)
- Network: MiB/s (bytes / 1024^2)
- Disk usage: GB (bytes / 1000^3)
- Disk throughput: MB/s (bytes / 1000^2)
- IOPS: operations/second
- etcd DB size: GB (bytes / 1000^3)
- PVC usage: GB (bytes / 1000^3)

For multi-node clusters, stats files will have one column per node. Sum or take the
per-node value depending on the metric (CPU and memory are per-node; use each node's
value independently for per-node sizing).

#### Method B: Direct Prometheus queries

If the user has a live Prometheus/Thanos endpoint, query it directly. Read
`references/prometheus-queries.md` for a catalog of useful queries.

Prometheus queries return raw values in base units (bytes, seconds). Convert:
- CPU: cores (from irate of cpu_seconds_total)
- Memory: bytes → GiB (divide by 1024^3)
- Network: bytes/s → MiB/s (divide by 1024^2)
- Disk: bytes → GB (divide by 1000^3)

### Step 4: Analyze and Size

#### Sizing metrics

- **CPU sizing metric: P95 (95th percentile)** — represents sustained load excluding
  brief spikes. P95 is preferred over max because momentary spikes (GC, cert rotation)
  should not drive hardware selection.
- **Memory sizing metric: Max** — memory is the binding constraint in most deployments.
  Unlike CPU, memory pressure causes OOM kills, so size for the worst case observed.

#### Per-phase analysis

For each test phase, extract:
1. Node-level CPU P95 and Memory Max
2. Per-component CPU P95 and Memory Max (for component breakdown)
3. Disk usage max (root, etcd, container storage partitions)
4. Network throughput P95
5. etcd DB size (P95 or Max)
6. Resource counts (pods, namespaces, configmaps)

#### Growth rate analysis (for stepped/batched tests)

If the test has incremental batches, compute per-unit growth rates:
- CPU cores per added unit (cluster, namespace, pod batch, etc.)
- Memory GiB per added unit
- etcd GiB per added unit

Use these to identify which components scale most aggressively.

#### Hardware tier calculation

For each deployment scale and phase, compute hardware requirements at multiple
utilization targets:

| Target | Use Case | Formula |
|--------|----------|---------|
| 60% | Conservative — maximum headroom | observed / 0.60 |
| 75% | Balanced — recommended default | observed / 0.75 |
| 90% | Cost-optimized — minimal headroom | observed / 0.90 |

Round up to the nearest standard hardware tier:
- **CPU tiers (vCPUs):** 8, 12, 16, 24, 32, 48, 64, 96, 128
- **Memory tiers (GiB):** 32, 64, 96, 128, 192, 256, 384, 512, 768, 1024

For multi-node clusters, compute per-node requirements. Note whether workload is
evenly distributed or if control plane nodes have different resource profiles than
workers.

#### Operational limits to flag

Check and report on these limits when applicable:
- **etcd DB size:** Default quota is 8 GiB binary = 8.59 GB decimal. Stats files
  are in decimal GB (bytes/1000^3), so compare observed values against 8.59 GB,
  not 8.00. Flag if observed or projected size approaches this limit.
- **Max pods:** Default is 250 per node (110 on some configurations). Report
  non-terminated pod count as a percentage of the limit. Use
  `cluster/stats/nonterm-pods-cluster.stats` for this — NOT
  `resource/stats/pods.stats`, which includes terminated and completed pods
  (e.g., finished Jobs) and will overcount against the limit.
- **Memory pressure:** Flag if observed memory exceeds 80% of installed RAM.

### Step 5: Generate Report

Ask the user which output format they prefer:
- **PDF** (via reportlab) — best for sharing with field consultants
- **Markdown** — best for embedding in wikis, docs, or repos
- **Plain text** — best for quick consumption in terminal

#### Report structure

Regardless of format, include these sections:

1. **Test Environment** — cluster topology, hardware, software versions, workload description
2. **Test Methodology** — phases, durations, what each phase represents
3. **Resource Consumption** — per-phase tables for CPU, memory, disk, network
   - For stepped tests: show per-batch progression
   - For multi-scenario tests: cross-scenario comparison
4. **Component Breakdown** — which components consume what share of resources
   - Identify the top consumers and fastest-growing components
5. **Disk and Storage** — filesystem usage, PVC consumption, etcd DB size
6. **Network** — throughput at P95 and peak, NIC recommendation
7. **Hardware Sizing Recommendations** — utilization target tables, consolidated tiers
8. **Key Findings** — bullet-point summary of the most important takeaways

#### PDF generation

When generating PDF output, use reportlab with:
- BaseDocTemplate with TableOfContents
- Letter page size, 0.6-inch margins
- Styled tables with header row, alternating row colors
- Highlight rows for peak/worst-case values

Read the `references/pdf-patterns.md` file for reportlab code patterns.

#### Markdown generation

Use standard GitHub-flavored Markdown with tables. Include a table of contents
using heading links.

#### Plain text generation

Use fixed-width formatted tables. Keep line width under 120 characters.

## Important considerations

- **Never assume components.** The user defines what software stack they're running.
  Don't hardcode ACM, MCE, GitOps, or any specific operator set. Ask what components
  are installed and which namespace groupings matter.

- **Always understand the test methodology first.** Data without context is meaningless.
  A CPU spike during provisioning means something very different from a CPU spike during
  steady state.

- **Memory is usually the binding constraint** for Kubernetes control planes. CPU
  drops significantly at steady state; memory does not. Flag this pattern when observed.

- **Separate peak from steady state.** Hardware recommendations should cover the
  worst case (peak during active workload), but also call out the steady-state
  baseline since many deployments spend most of their time in steady state.

- **Be explicit about units.** CPU in cores, memory in GiB (binary), disk in GB
  (decimal), network in MiB/s. State units in every table header.

- **For multi-node clusters, report per-node.** Sizing recommendations are per-machine.
  Show how total cluster resources map to per-node requirements.

- **Flag non-obvious risks.** Max-pods limits, etcd quota, memory-to-CPU imbalance,
  disk I/O bottlenecks — call these out even if the user didn't ask.

- **Report observations, not theories.** Describe what the data shows; do not speculate
  about why. If two tests differ, state the difference and note that the cause is unknown
  unless the test design explicitly isolates that variable. Avoid causal language
  ("X drives Y", "because of Z") unless it is directly supported by the test data.
  Recommendations for further investigation are appropriate; assertions about root cause
  are not.
