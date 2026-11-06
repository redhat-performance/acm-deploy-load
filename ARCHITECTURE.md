# ARCHITECTURE.md

## Overview

**acm-deploy-load** is a comprehensive testing and analysis framework for Red Hat Advanced Cluster Management (ACM) and Multicluster Engine (MCE) on OpenShift Container Platform (OCP). The framework orchestrates large-scale cluster deployments, monitors system behavior in real-time, collects performance metrics, and generates detailed analysis reports for capacity planning and performance tuning.

**Design Goals:**
- **Scalability**: Test ACM/MCE at production scale (1000+ managed clusters)
- **Observability**: Continuous monitoring with time-series data capture
- **Analysis**: Comprehensive resource consumption and timing analysis
- **Reproducibility**: Structured test execution with versioned results
- **Modularity**: Independent tools that compose into full test workflows

---

## System Architecture

The framework follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Orchestration Layer                         │
│  (Bash scripts: interval-ztp-install-all.sh, etc.)             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                     Workload Layer                              │
│  (Python: acm-deploy-load.py, acm-telco-core-load.py, etc.)   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                  Monitoring & Data Collection                   │
│  (ZTPMonitor thread, Prometheus queries, oc commands)          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                    Analysis & Reporting                         │
│  (analyze-*.py, graph-*.py, report generation)                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                      Utilities Layer                            │
│  (command.py, output.py, common_ocp.py, etc.)                  │
└─────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

**1. Orchestration Layer** (`scripts/`)
- Full test execution workflows
- Phase coordination (idle baseline → deployment → soak baseline)
- Post-test data collection and analysis triggering
- Result directory management

**2. Workload Layer** (`acm-deploy-load/*.py` main scripts)
- Cluster deployment execution (manifest apply, GitOps push)
- Workload scheduling (interval-based, batch-based)
- Monitoring thread lifecycle management
- Report card generation

**3. Monitoring & Data Collection**
- Real-time cluster state sampling (ZTPMonitor)
- Prometheus/Thanos metric queries
- OpenShift API resource snapshots
- Time-series CSV generation

**4. Analysis & Reporting**
- Per-cluster timing analysis (ICI, CGU, CI)
- Hub cluster resource consumption analysis
- Visualization (time-series graphs, comparison overlays)
- Multi-format reports (markdown, plain text, CSV)

**5. Utilities Layer** (`acm-deploy-load/utils/`)
- Command execution with retry and dry-run support
- Version detection (ACM, MCE, OCP, TALM)
- Prometheus token management and Thanos routing
- Report formatting and statistics calculation

---

## Core Components

### Workload Tools

#### 1. `acm-deploy-load.py` — Cluster Deployment Workload

**Purpose**: Deploy SNO/Compact/Standard clusters via Assisted Installer (AI) or Image-Based Installer (IBI).

**Deployment Methods**:
- `ai-manifest` — Direct apply of AgentClusterInstall manifests
- `ai-clusterinstance` — ClusterInstance API (AI backend)
- `ai-clusterinstance-gitops` — ClusterInstance via ArgoCD/ZTP GitOps
- `ai-siteconfig-gitops` — SiteConfig via ZTP GitOps (legacy)
- `ibi-manifest` — Direct apply of ImageClusterInstall manifests
- `ibi-clusterinstance` — ClusterInstance API (IBI backend)
- `ibi-clusterinstance-gitops` — ClusterInstance via ArgoCD/ZTP GitOps

**Key Features**:
- **Interval-based deployment**: Deploy N clusters every M seconds
- **Batch-based deployment**: Deploy N clusters, wait for install completion, repeat
- **GitOps integration**: Render kustomization files, commit, and push to Git
- **Phase structure**:
  - Phase 1 (Idle Baseline): Capture baseline metrics before workload
  - Phase 2 (Deployment): Manifest apply + cluster install + DU profile + playbook
  - Phase 3 (Soak Baseline): Sustained load metrics after deployment complete
- **Background Prometheus analysis**: Automatically launch `analyze-prometheus.py` for each phase
- **Monitoring thread**: ZTPMonitor samples cluster state every N seconds
- **Wait conditions**: Configurable wait for cluster install, DU profile, and playbook completion

**Output**:
- `results/<timestamp>-<method>-<suffix>/`
  - `report.txt` — Test summary and statistics
  - `monitor_data.csv` — Time-series cluster state
  - `versions.json` — ACM/MCE/OCP versions
  - `phase1-idle-baseline-*/`, `phase2-cluster-deployment-*/`, `phase3-soak-baseline-*/` — Per-phase Prometheus analysis
  - Cluster manifests, install data, logs

#### 2. `acm-telco-core-load.py` — Telco Core Deployment Workload

**Purpose**: Deploy Telco Core MNO (Multi-Node OpenShift) clusters via GitOps with policy churn workload.

**Key Features**:
- Batch deployment with inter-batch policy churn
- Hub policy generator integration
- Cluster-specific DU profile policies
- Phase structure similar to acm-deploy-load.py but with batch phases

#### 3. `acm-mc-load.py` — Managed Cluster Policy Churn

**Purpose**: Apply policy workload to existing managed clusters without deploying new clusters.

**Use Case**: Sustained policy churn testing, capacity planning for policy controller.

### Monitoring Components

#### ZTPMonitor (`utils/ztp_monitor.py`)

**Architecture**: Python thread running in background during workload execution.

**Purpose**: Continuously sample OpenShift resources to track cluster deployment state.

**Sampling Interval**: Configurable (default 60 seconds).

**Resources Monitored**:
- `AgentClusterInstall` (AI method) or `ImageClusterInstall` (IBI method)
- `BareMetalHost` (node boot status)
- `Agent` (discovered nodes, AI only)
- `ManagedCluster` (import status)
- `ClusterGroupUpgrade` (DU profile policy status)
- `AnsibleJob` (ZTP Day2 playbook status, optional)

**State Tracking**:
- Cluster states: applied, init, notstarted, installing, failed, completed, managed
- Policy states: init, notstarted, applying, timedout, compliant
- Playbook states: notstarted, running, completed
- Node states: booted, discovered

**Output**: `monitor_data.csv` with timestamp and state counts at each sample.

**Thread Lifecycle**:
1. Started by workload script before manifest apply
2. Runs continuously, writing CSV rows at each interval
3. Signaled to stop after wait conditions met
4. Joins back to main thread

**Key Implementation Details**:
- Retry on transient `oc` command failures (3 retries)
- JSON parsing error handling (log warning, continue)
- No-log mode for high-frequency queries (reduces log noise)
- Dry-run mode support (returns empty data)

### Analysis Tools

#### Prometheus Analysis (`analyze-prometheus.py`)

**Purpose**: Query Prometheus/Thanos for hub cluster resource consumption metrics.

**Input**:
- Start/end timestamps (ISO 8601 format)
- Kubeconfig for hub cluster
- Buffer time (default: 0s, adds post-query delay for Prometheus scrape lag)

**Metrics Collected**:
- **Cluster-level**: CPU, memory, network (container I/O), non-terminated pods
- **Per-node**: CPU, memory, network (NIC utilization), disk IOPS/throughput/usage, pods
- **Per-component**: CPU, memory for ACM, MCE, GitOps, TALM, etcd, monitoring, etc.
- **etcd health**: DB size, backend commit duration, WAL fsync, peer RTT, leader elections
- **Storage**: PVC usage per namespace, ODF/Ceph metrics (if detected)

**Component Detection**:
- Automatically detects installed components via namespace presence
- Supports: ACM Hub, ACM Observability, MCE, Hive, GitOps, TALM, LSO, ODF, AAP, ADP

**Output Structure**:
```
<report-dir>/<prefix>-<timestamp>/
├── cluster/
│   └── stats/
│       ├── cpu-cluster.stats        # Cluster-level CPU (P95)
│       ├── mem-cluster.stats        # Cluster-level memory (Max)
│       ├── cpu-node.stats           # Per-node CPU (P95)
│       ├── mem-node.stats           # Per-node memory (Max)
│       ├── net-rcv-node.stats       # Per-node network receive (P95)
│       └── ...
├── acm-complete/
│   ├── cpu-acm.csv                  # Time-series CPU data
│   └── stats/
│       ├── cpu-acm.stats            # Pandas describe() output
│       └── mem-acm.stats
├── etcd/
│   └── stats/
│       ├── backend-commit-etcd.stats  # Backend commit duration (P99)
│       ├── db-size-etcd.stats         # DB size (Max)
│       └── ...
└── ...
```

**Stats File Format** (Pandas `describe()` output):
```
Unit: <unit>
count    NNN
mean     X.XX
std      Y.YY
min      Z.ZZ
25%      A.AA
50%      B.BB   ← P50 (median)
75%      C.CC
95%      D.DD   ← P95 (used for CPU, network, disk)
99%      E.EE   ← P99 (used for etcd latency)
max      F.FF   ← Max (used for memory, disk usage)
```

**Thanos Routing**: Automatically detects if Thanos querier route exists; routes queries through Thanos if present, otherwise directly to Prometheus.

**Background Execution**: Launched as subprocess by workload scripts for each phase (idle, deployment, soak).

#### Timing Analysis Scripts

**Per-Cluster Install Timing**:
- `analyze-imageclusterinstalls.py` — IBI per-cluster install timing (ICI)
- `analyze-agentclusterinstalls.py` — AI per-cluster install timing (ACI)
- `analyze-clusterinstances.py` — ClusterInstance provisioning timing
- `analyze-clustergroupupgrades.py` — CGU per-cluster policy timing

**Output**: `.stats` files with plaintext percentile breakdowns (p50, p95, p99, max).

**Deployment Milestones**:
- `analyze-acm-deploy-time.py` — Generates `deploy-time-*` file with:
  - Cluster Install Duration (first apply → last install completed)
  - DU Compliant Duration (first apply → last DU compliant)
  - Full Duration (first apply → last playbook completed, if applicable)
  - Peak Cluster Installing, Peak DU Applying, Peak Concurrency

**Upgrade Analysis**:
- `analyze-upgrade.py`, `analyze-clusterversion.py`, `analyze-imagebasedupgrades.py`, `analyze-imagebasedgroupupgrades.py`

**Single Cluster Deep Dive**:
- `analyze-single-cluster-time.py` — Breakdown of one cluster's install timeline

### Graphing Tools

#### `graph-acm-deploy.py` — Deployment Graphs

**Purpose**: Visualize `monitor_data.csv` time-series data.

**Graphs Generated**:
- Cluster + Node (cluster_applied, cluster_init, node_booted, node_discovered, cluster_installing, cluster_install_failed, cluster_install_completed)
- Cluster (cluster states only)
- Policy (DU profile states)
- Playbook (ZTP Day2 playbook states)
- Share (combined cluster + policy overlay)

**Technology**: Plotly (Python) → PNG export via Kaleido/Chrome.

#### `graph-acm-compare.py` — Comparison Overlay Graphs

**Purpose**: Overlay two test results for side-by-side comparison.

**Graph Types**:
- **Resource graphs** (12 total):
  - CPU (cluster, per-node peak)
  - Memory (cluster, per-node peak)
  - Network (per-node peak receive/transmit)
  - etcd (backend commit, DB size, WAL fsync, peer RTT)
  - Disk (etcd partition IOPS, throughput)
- **Cluster deploy graphs** (4 total):
  - Installed, Managed, Compliant, All Milestones overlay

**Features**:
- Phase boundary shading (idle, deploy, soak)
- Aggregation (max across nodes for per-node metrics, max across etcd members)
- Reference lines (etcd SLO targets: 25ms backend commit, 10ms fsync, 50ms peer RTT, 8.59 GB DB size)
- Dynamic x-axis trimming (idle/soak phases trimmed if > 30 min / 60 min)

**Output**: Comparison graphs in `results/comparison-<A>-vs-<B>/` directory.

#### `graph-clusterversion.py`, `graph-upgrade.py` — Upgrade Graphs

**Purpose**: Visualize cluster upgrade progression and timing.

### Utility Modules

#### `utils/command.py` — Command Execution Wrapper

**Purpose**: Centralized subprocess execution for `oc` commands with error handling.

**Features**:
- **Dry-run support**: Prepends `echo` to command, logs without executing
- **Retry with backoff**: Configurable retries (default 1), exponential backoff
- **Directory context**: Change to specified directory before execution, restore after
- **Streaming output**: Optional line-by-line output logging
- **No-log mode**: Suppress output logging for high-frequency queries

**Signature**: `command(cmd, dry_run, cmd_directory="", retries=1, retry_backoff=True, no_log=False, readlines=False)`

#### `utils/output.py` — Report Generation

**Key Functions**:
- `generate_deploy_load_report()` — Generate `report.txt` with test summary, statistics, and percentages
- `assemble_stats()` — Calculate min/avg/p50/p95/p99/max from list of values
- `phase_break()` — Print formatted section separators
- `log_write()` — Write to both logger and file handle

**Report Card Structure**:
```
================================================================================
acm-deploy-load Report Card
================================================================================
Versions
 * ACM: 5.0.0
 * MCE: 5.0.0
 * Test: ZTP Scale Run 17-mcoa
 * Hub OCP: 5.0.0-rc.7
 * Deployed OCP: 5.0.0-rc.7
Deployed Cluster Results
 * Available Clusters: 2592
 * Deployed (Applied/Committed) Clusters: 2592
 * Installed Clusters: 2592
 * Failed Clusters: 0
 * Cluster Successful Percent: 100.0%
Managed Cluster Results
 * Managed Clusters: 2592
 * Managed Successful Percent: 100.0%
DU Profile Results
 * DU Profile Compliant: 2592
 * DU Profile Successful Percent: 100.0%
Overall Results
 * Overall Success (DU Compliant / Deployed): 2592 / 2592
 * Overall Success Percent: 100.0%
Workload Parameters
 * Method: ibi-clusterinstance-gitops
 * Clusters Per App: 1000
 * Interval: 1800s (30 min)
 * Batch Size: 500
...
```

#### `utils/common_ocp.py` — OCP Utilities

**Key Functions**:
- `get_ocp_version(kubeconfig)` — Parse ClusterVersion for major/minor/patch
- `get_mch_version(kubeconfig)` — Get ACM version from MultiClusterHub CR
- `get_mce_version(kubeconfig)` — Get MCE version from MultiClusterEngine CR
- `get_aap_version(kubeconfig)` — Get AAP version from CSV
- `get_prometheus_token(kubeconfig, ocp_version)` — Create or retrieve Prometheus bearer token
- `get_thanos_querier_route(kubeconfig)` — Get Thanos querier route if observability enabled
- `get_ocp_namespace_list(kubeconfig)` — List all namespaces
- `get_base_ocp_namespaces(ocp_version)` — Return base OCP namespace list for version
- `validate_kubeconfig(kubeconfig)` — Check kubeconfig file exists

**Thanos Routing Logic**:
```python
if thanos_route_exists:
    endpoint = thanos_route
else:
    endpoint = prometheus_route
```

This allows the framework to work with or without ACM Observability (Thanos) installed.

#### `utils/analysis.py` — Prometheus Analysis Launcher

**Purpose**: Launch `analyze-prometheus.py` as background subprocess.

**Key Function**: `launch_prometheus_analysis(report_dir, phase_name, start_ts, end_ts, kubeconfig, base_dir)`

**Features**:
- Validates phase duration (minimum 15 minutes, skips shorter phases)
- Formats timestamps to ISO 8601
- Redirects stdout/stderr to `pa-<phase_name>.log`
- Starts process in new session (detached from parent)
- Logs PID for tracking

**Usage by Workload Scripts**:
```python
# After Phase 1 (Idle Baseline) completes
launch_prometheus_analysis(report_dir, "phase1-idle-baseline", start_ts, end_ts, kubeconfig, base_dir)

# After Phase 2 (Deployment) completes
launch_prometheus_analysis(report_dir, "phase2-cluster-deployment", start_ts, end_ts, kubeconfig, base_dir)

# After Phase 3 (Soak Baseline) completes
launch_prometheus_analysis(report_dir, "phase3-soak-baseline", start_ts, end_ts, kubeconfig, base_dir)
```

#### `utils/talm.py` — TALM Version Detection

**Purpose**: Detect TALM (Topology Aware Lifecycle Manager) minor version.

**Why Needed**: TALM behavior differs across versions (4.16 vs 4.17+), affecting how CGU conditions are checked.

**Detection Logic**:
1. Query for ClusterServiceVersion matching `openshift-cluster-group-upgrades-operator.*`
2. Parse version from CSV name
3. Fall back to CLI arg `--talm-version` if detection fails

---

## Key Architectural Patterns

### 1. **Phased Workload Execution**

All workload tools follow a three-phase pattern:

**Phase 1 (Idle Baseline)**: Capture metrics before workload starts
- Duration: `--start-delay` seconds (default 15s)
- Purpose: Establish baseline resource consumption

**Phase 2 (Deployment)**: Execute workload and wait for completion
- Manifest apply or GitOps push
- Monitor thread samples cluster state
- Wait for cluster install, DU profile, playbook (optional)
- Background Prometheus analysis launched at phase end

**Phase 3 (Soak Baseline)**: Capture sustained load metrics
- Duration: `--end-delay` seconds (default 120s)
- Purpose: Measure steady-state resource consumption after workload complete

**Benefits**:
- Baseline metrics isolate workload impact
- Phase directories enable focused analysis
- Soak metrics reveal memory leaks or resource creep

### 2. **Background Monitoring**

**Design**: Python `Thread` subclass (`ZTPMonitor`) runs in parallel with main workload.

**Benefits**:
- Non-blocking: Main thread proceeds with deployment while monitor samples
- Time-series data: CSV captures state transitions at fine granularity
- Decoupled: Monitor thread is workload-agnostic (same code for AI/IBI, interval/batch)

**Synchronization**:
- Shared dictionary `monitor_data` for latest state
- Signal flag `self.signal` to stop thread
- Main thread calls `monitor_thread.join()` to wait for completion

**Example**:
```python
monitor_data = {...}  # Shared state
monitor_thread = ZTPMonitor(method, talm_minor, monitor_data, csv_file, dry_run, interval, kubeconfig)
monitor_thread.start()

# Main thread: deploy clusters
deploy_clusters(...)

# Wait for completion
while monitor_data["cluster_install_completed"] < target:
    time.sleep(60)

# Stop monitor
monitor_thread.signal = False
monitor_thread.join()
```

### 3. **Deferred Prometheus Analysis**

**Design**: Prometheus analysis runs in **background subprocess**, not in main process.

**Why**:
- Prometheus queries are slow (15-30 minutes per phase for large time windows)
- Main workload process can exit immediately after test completes
- Analysis results written to disk, read later by analysis scripts or users

**Implementation**:
```python
subprocess.Popen(
  [sys.executable, "analyze-prometheus.py", ...],
  stdout=log_file,
  stderr=subprocess.STDOUT,
  start_new_session=True  # Detach from parent
)
```

**Orchestration Script Responsibility**: Wait for all background Prometheus processes to complete before running final analysis.

### 4. **Timestamped Result Directories**

**Pattern**: `results/<timestamp>-<method>-<suffix>/`

**Example**: `results/20261028-041457-ibi-clusterinstance-gitops-1000cpa-500b-1800i-17-mcoa/`

**Components**:
- `20261028-041457` — UTC timestamp (YYYYMMDD-HHMMSS)
- `ibi-clusterinstance-gitops` — Deployment method
- `1000cpa-500b-1800i` — Workload parameters (1000 clusters per app, 500 batch size, 1800s interval)
- `17-mcoa` — User-provided suffix (`--results-dir-suffix`)

**Benefits**:
- **Chronological ordering**: ls -t lists latest first
- **Self-documenting**: Directory name encodes test metadata
- **Unique**: Timestamp prevents collisions
- **Analysis-friendly**: Suffix enables human-readable report filenames

### 5. **Modular Analysis Pipeline**

**Design**: Each analysis task is a standalone Python script.

**Scripts**:
- `analyze-prometheus.py` → Prometheus metrics
- `analyze-imageclusterinstalls.py` → ICI timing
- `analyze-clustergroupupgrades.py` → CGU timing
- `analyze-acm-deploy-time.py` → Deployment milestones
- `graph-acm-deploy.py` → Monitor data visualization
- `graph-acm-compare.py` → Result comparison visualization

**Benefits**:
- **Composability**: Orchestration scripts call subset of analyzers as needed
- **Testability**: Each analyzer can be run standalone with `--help`
- **Reusability**: Same analyzers used by acm-deploy-load, acm-telco-core-load, and acm-mc-load
- **Extensibility**: Add new analyzer without modifying existing tools

**Orchestration**:
```bash
#!/bin/bash
# scripts/interval-ztp-install-all.sh

# Run workload
python acm-deploy-load/acm-deploy-load.py interval ...

# Wait for background Prometheus analysis
wait

# Run timing analysis
python acm-deploy-load/analyze-imageclusterinstalls.py $RESULT_DIR
python acm-deploy-load/analyze-clustergroupupgrades.py $RESULT_DIR
python acm-deploy-load/analyze-acm-deploy-time.py $RESULT_DIR

# Generate graphs
python acm-deploy-load/graph-acm-deploy.py $RESULT_DIR

# Run full-test Prometheus analysis
python acm-deploy-load/analyze-prometheus.py -s $START -e $END -p deploy-pa $RESULT_DIR
```

### 6. **Dry-Run Support**

**Design**: Every script that modifies cluster state supports `--dry-run` flag.

**Implementation**: `command.py` prepends `echo` to every command.

**Benefits**:
- **Safe testing**: Validate test logic without deploying clusters
- **Documentation**: Dry-run output shows exact commands executed
- **CI/CD**: Dry-run tests catch syntax errors in CI

**Example**:
```bash
$ python acm-deploy-load/acm-deploy-load.py --dry-run interval -b 10 -i 60
2024-10-28 12:00:00 : INFO : Command(1): echo oc --kubeconfig /root/mno/kubeconfig get agentclusterinstall -A -o json
2024-10-28 12:00:01 : INFO : Command(1): echo git add /root/rhacm-ztp/.../kustomization.yaml
2024-10-28 12:00:02 : INFO : Command(1): echo git commit -m "Deploying Clusters 0 to 10"
2024-10-28 12:00:03 : INFO : Command(1): echo git push
```

### 7. **Version Detection and Compatibility**

**Design**: Automatically detect installed versions and adapt behavior.

**Detected Versions**:
- OCP version (from ClusterVersion CR)
- ACM version (from MultiClusterHub CR)
- MCE version (from MultiClusterEngine CR)
- AAP version (from CSV)
- TALM version (from CSV)

**Use Cases**:
- **Namespace lists**: OCP 4.20 vs 4.21 have different base namespaces
- **Prometheus token**: OCP 4.11+ requires token creation, 4.10 reads from secret
- **TALM behavior**: 4.16 vs 4.17+ have different CGU condition fields
- **Report formatting**: ACM-only vs MCE-only installations

**Example**:
```python
ocp_version = get_ocp_version(kubeconfig)
if ocp_version["major"] == 4 and ocp_version["minor"] >= 11:
    token = create_prometheus_token(kubeconfig)
else:
    token = read_prometheus_token_from_secret(kubeconfig)
```

---

## Data Flow

### End-to-End Workload Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. User invokes orchestration script                            │
│    $ scripts/interval-ztp-install-all.sh                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Orchestration script calls workload script                   │
│    $ python acm-deploy-load.py interval -b 500 -i 1800 ...      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Workload script creates result directory                     │
│    results/20241028-120000-ibi-clusterinstance-gitops-17-mcoa/  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Phase 1 (Idle Baseline): Sleep --start-delay seconds         │
│    - Launch Prometheus analysis for idle baseline (background)  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Start ZTPMonitor thread                                      │
│    - Samples cluster state every 60s                            │
│    - Writes monitor_data.csv                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Phase 2 (Deployment): Deploy clusters                        │
│    - Interval: Apply N clusters every M seconds                 │
│    - Batch: Apply N clusters, wait for install, repeat          │
│    - GitOps: Render kustomization, commit, push                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. Wait for completion                                          │
│    - Poll monitor_data until all clusters installed             │
│    - Optional: Wait for DU profile compliant                    │
│    - Optional: Wait for playbook completed                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. Launch Prometheus analysis for deployment phase (background) │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 9. Phase 3 (Soak Baseline): Sleep --end-delay seconds           │
│    - Launch Prometheus analysis for soak baseline (background)  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 10. Stop ZTPMonitor thread                                      │
│     - Set signal flag False                                     │
│     - Join thread                                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 11. Generate report.txt and versions.json                       │
│     - Write summary, statistics, success rates                  │
│     - Exit workload script                                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 12. Orchestration script waits for background analysis          │
│     - Wait for all Prometheus analysis subprocesses             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 13. Post-test data collection                                   │
│     $ scripts/post-ztp-install-data-collection.sh               │
│     - Save pods, events, CRs to install-data/                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 14. Run timing analysis                                         │
│     $ python analyze-imageclusterinstalls.py $RESULT_DIR        │
│     $ python analyze-clustergroupupgrades.py $RESULT_DIR        │
│     $ python analyze-acm-deploy-time.py $RESULT_DIR             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 15. Generate graphs                                             │
│     $ python graph-acm-deploy.py $RESULT_DIR                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 16. Run full-test Prometheus analysis                           │
│     $ python analyze-prometheus.py -p deploy-pa $RESULT_DIR     │
│     - Queries entire test duration (Phase 1 + 2 + 3)            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 17. Results ready for analysis                                  │
│     - Use /acm-load-analysis skill for comprehensive report     │
│     - Compare with prior runs via graph-acm-compare.py          │
└─────────────────────────────────────────────────────────────────┘
```

### Result Directory Structure

```
results/20241028-041457-ibi-clusterinstance-gitops-17-mcoa/
├── report.txt                                      # Test summary
├── versions.json                                   # ACM/MCE/OCP versions
├── monitor_data.csv                                # Time-series cluster state
├── deploy-time-ibi-clusterinstance-gitops.txt      # Deployment milestones
├── imageclusterinstalls-20241028-120000.csv        # Per-cluster ICI timing (raw)
├── imageclusterinstalls-20241028-120000.stats      # ICI timing (percentiles)
├── clustergroupupgrades-20241028-120000.csv        # Per-cluster CGU timing (raw)
├── clustergroupupgrades-20241028-120000.stats      # CGU timing (percentiles)
├── clusterinstances-20241028-120000.csv            # Per-cluster CI timing (raw)
├── clusterinstances-20241028-120000.stats          # CI timing (percentiles)
├── phase1-idle-baseline-20241028-120015/           # Phase 1 Prometheus analysis
│   ├── cluster/
│   │   └── stats/
│   │       ├── cpu-cluster.stats
│   │       ├── mem-cluster.stats
│   │       └── ...
│   ├── acm-complete/
│   │   ├── cpu-acm.csv
│   │   └── stats/
│   │       ├── cpu-acm.stats
│   │       └── mem-acm.stats
│   └── ...
├── phase2-cluster-deployment-20241028-120045/      # Phase 2 Prometheus analysis
│   └── (same structure as phase1)
├── phase3-soak-baseline-20241028-143500/           # Phase 3 Prometheus analysis
│   └── (same structure as phase1)
├── deploy-pa-20241028-150000/                      # Full-test Prometheus analysis
│   └── (same structure as phase directories)
├── install-data/                                   # Post-test snapshots
│   ├── agentclusterinstalls.yaml
│   ├── imageclusterinstalls.yaml
│   ├── clusterinstances.yaml
│   ├── clustergroupupgrades.yaml
│   ├── managedclusters.yaml
│   ├── events.yaml
│   ├── pods.yaml
│   └── ...
├── cluster-20241028-150030.png                     # Monitor data graph
├── policy-20241028-150031.png                      # Monitor data graph
└── pa-phase1-idle-baseline.log                     # Prometheus analysis logs
```

---

## Extension Points

### Adding a New Workload Script

**Template**: Copy `acm-deploy-load.py` or `acm-telco-core-load.py`.

**Required Components**:
1. **Argument parser**: Define CLI args for your workload
2. **Version detection**: Call `get_mch_version()`, `get_ocp_version()`, etc.
3. **Result directory creation**: Use timestamped naming convention
4. **Phase structure**:
   - Phase 1: Idle baseline (sleep `--start-delay`)
   - Launch Prometheus analysis for Phase 1
   - Phase 2: Execute workload
   - Launch Prometheus analysis for Phase 2
   - Phase 3: Soak baseline (sleep `--end-delay`)
   - Launch Prometheus analysis for Phase 3
5. **ZTPMonitor thread**: Start before workload, stop after completion
6. **Report generation**: Call `generate_deploy_load_report()` or equivalent
7. **versions.json**: Write version metadata to result directory

### Adding a New Analysis Script

**Template**: Copy `analyze-imageclusterinstalls.py` or `analyze-clustergroupupgrades.py`.

**Required Components**:
1. **Argument parser**: Accept result directory as positional arg
2. **Resource query**: Query OpenShift for relevant resources
3. **Timing calculation**: Extract timestamps, compute durations
4. **Statistics**: Use `assemble_stats()` or pandas `describe()`
5. **Output**: Write `.csv` (raw data) and `.stats` (percentiles) files

**Integration**: Add script invocation to orchestration script (`interval-ztp-install-all.sh`).

### Adding Prometheus Queries for New Components

**Location**: `analyze-prometheus.py` → `<component>_queries()` function

**Steps**:
1. **Detect component**: Check for namespace presence in `namespaces` list
2. **Define queries**: Create PromQL queries for CPU, memory, network
3. **Call `query_thanos()`**: Execute query and write CSV/stats files
4. **Add to `q_names` dict**: Track query metadata

**Example**:
```python
def my_component_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "my-component")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()
  
  # CPU query
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='my-component'})"
  query_thanos(route, q, "my-component", token, end_ts, duration, sub_report_dir, 
               "cpu-my-component", "My Component CPU Cores Usage", "CPU", w, h, q_names)
  
  # Memory query
  q = "sum(container_memory_working_set_bytes{cluster='',container!='',namespace='my-component'})"
  query_thanos(route, q, "my-component", token, end_ts, duration, sub_report_dir, 
               "mem-my-component", "My Component Memory Usage", "MEM", w, h, q_names)
  
  return q_names
```

### Adding New Graph Types

**Location**: `graph-acm-deploy.py` or `graph-acm-compare.py`

**Steps**:
1. **Define data columns**: Extract columns from `monitor_data.csv` or CSV files
2. **Create Plotly figure**: Use `px.line()`, `go.Scatter()`, or `ff.create_annotated_heatmap()`
3. **Apply styling**: Set title, labels, legend, colors
4. **Export to PNG**: Call `fig.write_image()`

**Example** (monitor data graph):
```python
y_custom = ["metric1", "metric2", "metric3"]
title_custom = "Custom Metric Graph"
labels = {"value": "# units", "date": ""}

fig_custom = px.line(df, x="date", y=y_custom, labels=labels, width=1000, height=700)
fig_custom.update_layout(title=title_custom, legend_orientation="v")
fig_custom.write_image("{}/custom-{}.png".format(results_directory, ts), width=1000, height=700)
```

---

## Technology Stack

**Languages**:
- Python 3 (workload, analysis, graphing)
- Bash (orchestration, automation)

**Python Libraries**:
- `argparse` — CLI argument parsing
- `pandas` — Data analysis, statistics
- `plotly` — Visualization (time-series graphs)
- `jinja2` — Template rendering (kustomization, manifests)
- `requests` — Prometheus/Thanos HTTP queries
- `numpy` — Numerical operations (percentiles)
- `subprocess` — Command execution
- `threading` — Background monitoring

**External Tools**:
- `oc` (OpenShift CLI) — Kubernetes API access
- `git` — GitOps manifest management
- Chrome/Kaleido — PNG export from Plotly graphs

**Infrastructure**:
- OpenShift Container Platform (OCP) — Hub and managed clusters
- Advanced Cluster Management (ACM) — Multi-cluster management
- Multicluster Engine (MCE) — Cluster lifecycle
- Prometheus/Thanos — Metrics collection and querying
- ArgoCD — GitOps deployment (optional)

---

## Design Principles

1. **Separation of Concerns**: Each layer has a single responsibility (orchestration, workload, monitoring, analysis, utilities)
2. **Modularity**: Tools are standalone scripts, composable into workflows
3. **Observability**: Comprehensive logging, time-series monitoring, resource consumption tracking
4. **Reproducibility**: Timestamped results, version capture, structured output
5. **Extensibility**: Clean interfaces for adding workloads, analyzers, graphs
6. **Fail-Safe**: Dry-run mode, retry logic, error handling, graceful degradation
7. **Performance**: Background processing, parallel analysis, minimal main-thread blocking
8. **Usability**: Self-documenting directories, human-readable reports, CLI help

---

## Conclusion

The **acm-deploy-load** architecture is designed for **scalability**, **modularity**, and **extensibility**. The layered design separates orchestration, workload execution, monitoring, and analysis into independent components that compose into comprehensive test workflows. Background monitoring and deferred analysis minimize main-thread blocking, enabling efficient large-scale testing. Structured result directories, version capture, and multi-format reports ensure reproducibility and traceability. The framework's modular design makes it straightforward to add new workloads, analyzers, and visualizations as ACM/MCE evolve.

For detailed usage instructions, see `CLAUDE.md`. For contribution guidelines, see `CONTRIBUTING.md`.
