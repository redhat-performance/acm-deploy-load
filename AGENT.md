# AGENT.md — AI Agent Guide for acm-deploy-load

This document provides guidance for AI coding assistants (like Claude Code) working with the **acm-deploy-load** codebase. It complements the human-oriented documentation (README.md, ARCHITECTURE.md, CONTRIBUTING.md) with patterns, conventions, and context optimized for AI agents.

---

## Table of Contents

- [Quick Orientation](#quick-orientation)
- [Navigating the Codebase](#navigating-the-codebase)
- [Common Workflows](#common-workflows)
- [Code Modification Patterns](#code-modification-patterns)
- [Testing and Validation](#testing-and-validation)
- [Analysis and Debugging](#analysis-and-debugging)
- [Conventions and Standards](#conventions-and-standards)
- [Common Pitfalls](#common-pitfalls)
- [Quick Reference](#quick-reference)

---

## Quick Orientation

### Project Purpose

**acm-deploy-load** is a load testing and capacity planning framework for Red Hat Advanced Cluster Management (ACM) at scale. It:
- Deploys 1000+ managed clusters to test ACM hub capacity
- Monitors resource consumption (CPU, memory, network, disk, etcd)
- Analyzes timing (cluster install, policy application, upgrades)
- Generates reports and graphs for capacity planning

### Key Technologies

- **Python 3** — Workload generation, analysis, graphing
- **Bash** — Test orchestration, multi-step workflows
- **OpenShift CLI (`oc`)** — Kubernetes API interaction
- **Prometheus/Thanos** — Metrics collection and querying
- **Plotly** — Time-series visualization
- **Ansible** — Hub cluster setup (not typically modified)

### Project Scope Boundaries

**In scope for AI agent assistance:**
- Python workload scripts (`acm-deploy-load/*.py`)
- Analysis scripts (`analyze-*.py`, `graph-*.py`)
- Utility modules (`utils/*.py`)
- Bash orchestration scripts (`scripts/*.sh`)
- Documentation updates (CLAUDE.md, ARCHITECTURE.md, AGENT.md)

**Out of scope (requires human expertise):**
- Ansible playbooks (complex ACM/OCP deployment logic)
- Test environment provisioning (Jetlag, bare metal)
- ACM/OCP version-specific API changes
- Production deployment decisions

---

## Navigating the Codebase

### File Organization Patterns

The repository follows a **functional directory structure**:

```
acm-deploy-load/           # Python executable scripts (chmod +x, shebang)
├── acm-*.py               # Workload generation (deploy-load, telco-core-load, mc-load)
├── analyze-*.py           # Analysis scripts (prometheus, timing, CRs)
├── graph-*.py             # Visualization scripts (plotly → PNG)
├── benchmark-*.py         # Benchmarking tools
├── *-health.py            # Health check utilities
└── utils/                 # Shared library modules (no shebang)
    ├── command.py         # Subprocess wrapper for `oc` commands
    ├── ztp_monitor.py     # Background monitoring thread
    ├── common_ocp.py      # OpenShift utilities (versions, tokens, namespaces)
    ├── output.py          # Report generation and statistics
    ├── analysis.py        # Prometheus analysis launcher
    └── talm.py            # TALM version detection

scripts/                   # Bash orchestration (test workflows)
├── interval-ztp-install-all.sh        # Main test orchestration
├── acm-telco-core-load.sh             # Telco Core test orchestration
├── post-*-data-collection.sh          # Post-test CR/log snapshots
└── dry-run-*.sh                       # Dry-run test variants

ansible/                   # Hub cluster setup (rarely modified)
├── roles/                 # 38 Ansible roles (ACM, MCE, GitOps, etc.)
└── vars/                  # Variable templates for cluster manifests

results/                   # Test output (git-ignored, timestamped directories)
└── YYYYMMDD-HHMMSS-<method>-<suffix>/
    ├── report.txt         # Test summary
    ├── monitor_data.csv   # Time-series cluster state
    ├── versions.json      # ACM/MCE/OCP versions
    ├── deploy-time-*.txt  # Deployment milestones
    ├── *.stats            # Timing percentiles (plaintext)
    ├── *.csv              # Raw timing data
    ├── *.png              # Graphs
    ├── phase*-*/          # Per-phase Prometheus analysis
    ├── deploy-pa-*/       # Full-test Prometheus analysis
    └── install-data/      # Post-test CR/log snapshots
```

### Key Files by Function

**Workload Generation:**
- `acm-deploy-load.py` — Primary cluster deployment (AI/IBI, 7 methods)
- `acm-telco-core-load.py` — Telco Core MNO deployment with policy churn
- `acm-mc-load.py` — Policy churn workload (no cluster deployment)

**Monitoring:**
- `utils/ztp_monitor.py` — Background thread sampling cluster state every 60s
- Writes `monitor_data.csv` with columns: date, cluster_applied, cluster_init, cluster_notstarted, node_booted, node_discovered, cluster_installing, cluster_install_failed, cluster_install_completed, managed, policy_init, policy_notstarted, policy_applying, policy_timedout, policy_compliant, playbook_notstarted, playbook_running, playbook_completed

**Analysis:**
- `analyze-prometheus.py` — Query Prometheus/Thanos for resource metrics (CPU, memory, network, disk, etcd)
- `analyze-imageclusterinstalls.py` — IBI per-cluster install timing (ICI)
- `analyze-agentclusterinstalls.py` — AI per-cluster install timing (ACI)
- `analyze-clusterinstances.py` — ClusterInstance provisioning timing
- `analyze-clustergroupupgrades.py` — CGU per-cluster policy timing
- `analyze-acm-deploy-time.py` — Deployment milestones and peak concurrency

**Visualization:**
- `graph-acm-deploy.py` — Single test result graphs from `monitor_data.csv`
- `graph-acm-compare.py` — Two-result comparison overlay graphs (resource + deploy)

**Utilities:**
- `utils/command.py` — Subprocess wrapper with retry, dry-run, directory context
- `utils/common_ocp.py` — Version detection, Prometheus token, Thanos routing, namespace lists
- `utils/output.py` — Report card generation, statistics calculation
- `utils/analysis.py` — Background Prometheus analysis launcher

### Understanding Result Directories

**Naming Convention:** `YYYYMMDD-HHMMSS-<method>-<params>-<suffix>`

**Example:** `20261028-041457-ibi-clusterinstance-gitops-1000cpa-500b-1800i-17-mcoa`
- `20261028-041457` — UTC timestamp
- `ibi-clusterinstance-gitops` — Deployment method
- `1000cpa` — 1000 clusters per ArgoCD app
- `500b` — 500 cluster batch size
- `1800i` — 1800 second interval (30 minutes)
- `17-mcoa` — User-provided suffix

**Key Files in Result Directory:**

| File | Purpose | When Created |
|------|---------|--------------|
| `report.txt` | Test summary, success rates, timing | End of workload script |
| `versions.json` | ACM/MCE/OCP versions | End of workload script |
| `monitor_data.csv` | Time-series cluster state (60s samples) | During test (ZTPMonitor thread) |
| `deploy-time-*.txt` | Install duration, DU duration, peak concurrency | By `analyze-acm-deploy-time.py` |
| `imageclusterinstalls-*.csv` | Per-cluster ICI timing (raw) | By `analyze-imageclusterinstalls.py` |
| `imageclusterinstalls-*.stats` | ICI percentiles (p50, p95, p99, max) | By `analyze-imageclusterinstalls.py` |
| `clustergroupupgrades-*.csv` | Per-cluster CGU timing (raw) | By `analyze-clustergroupupgrades.py` |
| `clustergroupupgrades-*.stats` | CGU percentiles (p50, p95, p99, max) | By `analyze-clustergroupupgrades.py` |
| `phase1-idle-baseline-*/` | Idle baseline Prometheus analysis | By workload script (background) |
| `phase2-cluster-deployment-*/` | Deployment Prometheus analysis | By workload script (background) |
| `phase3-soak-baseline-*/` | Soak baseline Prometheus analysis | By workload script (background) |
| `deploy-pa-*/` | Full-test Prometheus analysis | By orchestration script (foreground) |
| `cluster-*.png`, `policy-*.png` | Deployment graphs | By `graph-acm-deploy.py` |

---

## Common Workflows

### 1. Analyzing an Existing Test Result

**User Request:** "Analyze the results in directory XYZ"

**Workflow:**

1. **Locate the result directory** (usually in `results/` or a full path)
2. **Invoke the acm-load-analysis skill** if available:
   ```
   /acm-load-analysis <path-to-result-directory>
   ```
3. **Manual analysis** (if skill not available):
   - Read `report.txt` for test summary
   - Read `deploy-time-*.txt` for timing milestones
   - Read `*.stats` files for per-cluster timing percentiles
   - Check `phase2-cluster-deployment-*/` or `deploy-pa-*/` for resource metrics
   - Look for graphs: `cluster-*.png`, `policy-*.png`

**Key files to check:**
- `report.txt` — Success rates, cluster counts
- `deploy-time-ibi-clusterinstance-gitops.txt` — Install/DU duration, peak concurrency
- `imageclusterinstalls-*.stats` — ICI timing (p50, p95, p99)
- `clustergroupupgrades-*.stats` — CGU timing (p50, p95, p99)
- `deploy-pa-*/cluster/stats/cpu-cluster.stats` — Hub CPU consumption (P95)
- `deploy-pa-*/cluster/stats/mem-cluster.stats` — Hub memory consumption (Max)
- `deploy-pa-*/etcd/stats/backend-commit-etcd.stats` — etcd latency (P99)

### 2. Comparing Two Test Results

**User Request:** "Compare test run A and test run B"

**Workflow:**

1. **Identify both result directories**
2. **Invoke the acm-load-analysis skill** with both directories:
   ```
   /acm-load-analysis <result-dir-A> <result-dir-B>
   ```
3. **Manual comparison** (if skill not available):
   - Read both `report.txt` files
   - Compare `deploy-time-*.txt` files (install duration, DU duration)
   - Compare `*.stats` files (ICI, CGU timing)
   - Use `graph-acm-compare.py` to generate overlay graphs:
     ```bash
     python acm-deploy-load/graph-acm-compare.py \
       results/test-A \
       results/test-B \
       --label-a "No-ODF" \
       --label-b "ODF" \
       -o results/comparison-A-vs-B \
       -p comparison
     ```

**Key metrics to compare:**
- Cluster install success rate (%)
- DU profile compliance rate (%)
- Install duration (p50, p95, p99)
- DU duration (p50, p95, p99)
- Hub CPU P95 (cores)
- Hub memory Max (GiB)
- etcd backend commit P99 (ms)
- etcd DB size Max (GB)

### 3. Running a Small-Scale Test

**User Request:** "Run a test to verify changes"

**Workflow:**

1. **SSH to the test bastion:**
   ```bash
   ssh -i ~/.ssh/id_scale root@<bastion-host>
   export KUBECONFIG=/root/mno/kubeconfig
   cd /root/acmqe/acm-deploy-load
   source .venv/bin/activate
   ```

2. **Run dry-run first** to validate logic:
   ```bash
   scripts/dry-run-ztp-install.sh -c 10 -b 5 -i 60 -t "test-dry"
   ```

3. **Run small-scale functional test:**
   ```bash
   scripts/interval-ztp-install-all.sh \
     -c 10 \              # Deploy 10 clusters
     -b 5 \               # Batch size: 5 clusters
     -i 60 \              # Interval: 60 seconds (1 minute)
     -m ibi-clusterinstance-gitops \
     -t "test-small" \    # Result suffix
     --start-delay 60 \   # 1-minute idle baseline
     --end-delay 120      # 2-minute soak baseline
   ```

4. **Review results:**
   ```bash
   cd results/YYYYMMDD-HHMMSS-ibi-clusterinstance-gitops-*-test-small/
   cat report.txt
   ```

### 4. Debugging Test Failures

**User Request:** "The test failed, help me debug"

**Workflow:**

1. **Check the orchestration log:**
   ```bash
   tail -100 iz-all-*.log  # Main log file in cwd
   ```

2. **Check the result directory:**
   ```bash
   cd results/YYYYMMDD-HHMMSS-*/
   cat report.txt  # Summary with error counts
   ls install-data/  # CR snapshots
   ```

3. **Check cluster state:**
   ```bash
   oc --kubeconfig /root/mno/kubeconfig get imageclusterinstall -A
   oc --kubeconfig /root/mno/kubeconfig get managedcluster
   oc --kubeconfig /root/mno/kubeconfig get clustergroupupgrade -n ztp-install
   ```

4. **Check specific failed cluster:**
   ```bash
   oc --kubeconfig /root/mno/kubeconfig get imageclusterinstall <cluster-name> -n <namespace> -o yaml
   oc --kubeconfig /root/mno/kubeconfig get events -n <namespace> --sort-by='.lastTimestamp'
   ```

5. **Common failure reasons:**
   - **cluster_install_failed > 0** — Check `install-data/imageclusterinstalls.yaml` for failure conditions
   - **managed < cluster_install_completed** — Import failed, check `install-data/managedclusters.yaml`
   - **policy_compliant < policy_init** — DU profile failed, check `install-data/clustergroupupgrades.yaml`
   - **Prometheus analysis missing** — Check `pa-phase*.log` for errors
   - **Graph generation failed** — Check for missing monitor_data.csv

### 5. Adding a New Analysis Script

**User Request:** "Add analysis for XYZ resource"

**Workflow:**

1. **Copy an existing analyzer as template:**
   ```bash
   cp acm-deploy-load/analyze-imageclusterinstalls.py acm-deploy-load/analyze-xyz.py
   ```

2. **Modify the script:**
   - Update argparse description
   - Change `oc get` command to query XYZ resource
   - Extract timestamps from XYZ resource spec/status
   - Compute durations (e.g., creation → completion)
   - Generate `.csv` (raw data) and `.stats` (percentiles)

3. **Test the analyzer:**
   ```bash
   python acm-deploy-load/analyze-xyz.py results/YYYYMMDD-HHMMSS-*/
   cat results/YYYYMMDD-HHMMSS-*/xyz-*.csv
   cat results/YYYYMMDD-HHMMSS-*/xyz-*.stats
   ```

4. **Integrate into orchestration:**
   - Edit `scripts/interval-ztp-install-all.sh`
   - Add analyzer invocation after main workload completes
   - Add separator line `echo "###..." | tee -a ${log_file}`

5. **Update documentation:**
   - Add entry to CLAUDE.md code tree
   - Update ARCHITECTURE.md analysis tools section

### 6. Modifying Prometheus Queries

**User Request:** "Add Prometheus query for component XYZ"

**Workflow:**

1. **Locate component detection in `analyze-prometheus.py`:**
   ```python
   # Around line 200-300, find component detection logic
   if "xyz-namespace" in namespaces:
       xyz_q_names = xyz_queries(report_dir, route, token, end_ts, duration, w, h)
       q_names.update(xyz_q_names)
   ```

2. **Add query function:**
   ```python
   def xyz_queries(report_dir, route, token, end_ts, duration, w, h):
       sub_report_dir = os.path.join(report_dir, "xyz")
       make_report_directories(sub_report_dir)
       q_names = OrderedDict()
       
       # CPU query
       q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='xyz-namespace'})"
       query_thanos(route, q, "xyz", token, end_ts, duration, sub_report_dir, 
                    "cpu-xyz", "XYZ CPU Cores Usage", "CPU", w, h, q_names)
       
       # Memory query
       q = "sum(container_memory_working_set_bytes{cluster='',container!='',namespace='xyz-namespace'})"
       query_thanos(route, q, "xyz", token, end_ts, duration, sub_report_dir, 
                    "mem-xyz", "XYZ Memory Usage", "MEM", w, h, q_names)
       
       return q_names
   ```

3. **Test the query:**
   ```bash
   # Use existing result directory for testing
   python acm-deploy-load/analyze-prometheus.py \
     -s 2024-10-28T04:00:00Z \
     -e 2024-10-28T08:00:00Z \
     -p test-xyz \
     results/existing-test/
   
   # Check output
   ls -lh results/existing-test/test-xyz-*/xyz/
   cat results/existing-test/test-xyz-*/xyz/stats/cpu-xyz.stats
   ```

4. **Verify stats file format:**
   ```
   Unit: cores
   count    240.0
   mean     5.23
   std      1.45
   min      2.10
   25%      4.20
   50%      5.15
   75%      6.10
   95%      7.85    ← Use P95 for CPU
   99%      8.20
   max      9.50
   ```

---

## Code Modification Patterns

### 1. Adding a CLI Argument

**Pattern:** All Python scripts use `argparse` for CLI arguments.

**Example** (from `acm-deploy-load.py`):
```python
parser = argparse.ArgumentParser(
    description="Tool to load ACM with Cluster deployments",
    prog="acm-deploy-load.py",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
)

parser.add_argument("-k", "--kubeconfig", type=str, default="/root/mno/kubeconfig",
                    help="Changes which kubeconfig to connect to the hub cluster")
parser.add_argument("-m", "--method", choices=install_methods, default="ibi-clusterinstance-gitops",
                    help="The method of cluster install")
parser.add_argument("--dry-run", action="store_true", default=False,
                    help="Echos commands instead of executing them")
```

**Best Practices:**
- Use long form (`--arg`) and short form (`-a`) for frequently used args
- Provide `default` value (shown in help via `ArgumentDefaultsHelpFormatter`)
- Write descriptive `help` text (shown in `--help`)
- Use `type=int` for numeric args, `action="store_true"` for flags
- Use `choices=[]` for restricted values

### 2. Querying OpenShift Resources

**Pattern:** Use `utils/command.py` wrapper, not direct `subprocess`.

**Example:**
```python
from utils.command import command

# Query all imageclusterinstalls
oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "imageclusterinstall", "-A", "-o", "json"]
rc, output = command(oc_cmd, dry_run=False, retries=3, no_log=True)
if rc != 0:
    logger.error("oc get imageclusterinstall rc: {}".format(rc))
    sys.exit(1)

try:
    data = json.loads(output)
except json.decoder.JSONDecodeError:
    logger.error("JSON decode error: {}".format(output[:500]))
    sys.exit(1)

# Process data
for item in data["items"]:
    cluster_name = item["metadata"]["name"]
    # ...
```

**Key Points:**
- Always check return code (`rc != 0` means failure)
- Use `retries=3` for transient failures (network, API server load)
- Use `no_log=True` for high-frequency queries (reduces log noise)
- Handle `JSONDecodeError` (malformed JSON from API server under load)
- Use `-A` for all namespaces, `-n <namespace>` for specific namespace
- Use `-o json` for programmatic parsing, `-o yaml` for human reading

### 3. Writing Stats Files

**Pattern:** Analysis scripts write two files: `.csv` (raw) and `.stats` (percentiles).

**Example** (from `analyze-imageclusterinstalls.py`):
```python
import pandas as pd

# Collect timing data
timing_data = []
for cluster in clusters:
    duration = cluster_completed_ts - cluster_created_ts
    timing_data.append({
        "cluster": cluster_name,
        "duration": duration
    })

# Write CSV (raw data)
df = pd.DataFrame(timing_data)
csv_file = "{}/imageclusterinstalls-{}.csv".format(results_dir, ts)
df.to_csv(csv_file, index=False)
logger.info("Wrote CSV: {}".format(csv_file))

# Write stats (percentiles)
stats_file = "{}/imageclusterinstalls-{}.stats".format(results_dir, ts)
with open(stats_file, "w") as f:
    f.write("ImageClusterInstalls: {} clusters\n".format(len(timing_data)))
    if len(timing_data) > 0:
        durations = [d["duration"] for d in timing_data]
        f.write("p50: {:.1f}\n".format(np.percentile(durations, 50)))
        f.write("p95: {:.1f}\n".format(np.percentile(durations, 95)))
        f.write("p99: {:.1f}\n".format(np.percentile(durations, 99)))
        f.write("max: {:.1f}\n".format(np.max(durations)))
logger.info("Wrote stats: {}".format(stats_file))
```

**Stats File Format (plaintext):**
```
ImageClusterInstalls: 2592 clusters
p50: 1018.0
p95: 1158.0
p99: 1193.0
max: 1371.0
```

**Stats File Format (pandas describe):**
```
Unit: cores
count    240.0
mean     5.23
std      1.45
min      2.10
25%      4.20
50%      5.15
75%      6.10
95%      7.85
99%      8.20
max      9.50
```

**Key Points:**
- CSV: One row per cluster, columns: cluster, duration, start_ts, end_ts, etc.
- Stats: Plaintext with p50/p95/p99/max OR pandas `describe()` output
- Use `{:.1f}` for one decimal place (seconds), `{:.2f}` for two (percentages)
- Include header line (e.g., "ImageClusterInstalls: 2592 clusters")

### 4. Launching Background Processes

**Pattern:** Use `subprocess.Popen()` with `start_new_session=True` to detach.

**Example** (from `utils/analysis.py`):
```python
import subprocess
import sys

cmd = [
    sys.executable,  # Use same Python interpreter
    analyzer_script,
    "-k", kubeconfig,
    "-s", start_str,
    "-e", end_str,
    "-p", phase_name,
    report_dir,
]

log_file = os.path.join(report_dir, "pa-{}.log".format(phase_name))
try:
    with open(log_file, "w") as f:
        proc = subprocess.Popen(
            cmd,
            stdout=f,
            stderr=subprocess.STDOUT,
            cwd=base_dir,
            start_new_session=True,  # Detach from parent
        )
    logger.info("Launched prometheus analysis phase '{}' in background (pid {}, log: {})".format(
        phase_name, proc.pid, os.path.basename(log_file)))
except Exception as e:
    logger.warning("Failed to launch prometheus analysis for phase {}: {}".format(phase_name, e))
```

**Key Points:**
- Use `sys.executable` (not hardcoded `python3`) for correct interpreter
- Redirect stdout/stderr to log file
- Use `start_new_session=True` to detach from parent (continues after parent exits)
- Don't wait for completion (`proc.wait()`) — that defeats the purpose
- Log PID and log file path for debugging

### 5. Thread-Based Monitoring

**Pattern:** Subclass `threading.Thread`, use shared dict and signal flag.

**Example** (from `utils/ztp_monitor.py`):
```python
from threading import Thread

class ZTPMonitor(Thread):
    def __init__(self, method, talm_minor, monitor_data, csv_file, dry_run, sample_interval, kubeconfig):
        super(ZTPMonitor, self).__init__()
        self.method = method
        self.monitor_data = monitor_data  # Shared dict
        self.csv_file = csv_file
        self.sample_interval = sample_interval
        self.signal = True  # Stop flag
        
    def run(self):
        while self.signal:
            start_sample_time = time.time()
            
            # Query resources, update monitor_data
            self.monitor_data["cluster_installing"] = ...
            self.monitor_data["cluster_install_completed"] = ...
            
            # Sleep for remaining interval
            elapsed = time.time() - start_sample_time
            sleep_time = max(0, self.sample_interval - elapsed)
            time.sleep(sleep_time)

# Main thread usage:
monitor_data = {"cluster_installing": 0, "cluster_install_completed": 0, ...}
monitor_thread = ZTPMonitor(method, talm_minor, monitor_data, csv_file, dry_run, interval, kubeconfig)
monitor_thread.start()

# ... deploy clusters ...

# Stop monitor
monitor_thread.signal = False
monitor_thread.join()  # Wait for thread to finish
```

**Key Points:**
- Override `run()` method, not `__init__()`
- Use shared dictionary for latest state (thread-safe for dict updates)
- Use signal flag (`self.signal`) to stop thread gracefully
- Sleep for remaining interval (not fixed interval) to maintain cadence
- Always `join()` thread before exiting main process

---

## Testing and Validation

### Dry-Run Testing

**Always run dry-run before executing destructive operations.**

**Example:**
```bash
# Dry-run a deployment
python acm-deploy-load/acm-deploy-load.py \
  --dry-run \
  -m ibi-clusterinstance-gitops \
  interval -b 10 -i 60

# Output will show commands without executing:
# 2024-10-28 12:00:00 : INFO : Command(1): echo oc --kubeconfig /root/mno/kubeconfig get imageclusterinstall -A -o json
# 2024-10-28 12:00:01 : INFO : Command(1): echo git add /root/rhacm-ztp/.../kustomization.yaml
```

**What dry-run tests:**
- Argument parsing
- File path resolution
- Command construction
- Manifest rendering (templates)
- Git operations (add, commit, push)

**What dry-run doesn't test:**
- Actual cluster deployment
- API server responses
- Prometheus queries
- Timing analysis (no real data)

### Small-Scale Functional Testing

**Test with 5-10 clusters before running full-scale test.**

**Example:**
```bash
scripts/interval-ztp-install-all.sh \
  -c 10 \              # 10 clusters (not 2592)
  -b 5 \               # 5 cluster batch
  -i 60 \              # 1-minute interval (not 30 minutes)
  -m ibi-clusterinstance-gitops \
  -t "test-func" \
  --start-delay 60 \   # 1-minute idle (not 15 minutes)
  --end-delay 120      # 2-minute soak (not 6 hours)
```

**What to verify:**
- All 10 clusters install successfully (100% success rate)
- DU profile compliant (100% compliant)
- Prometheus analysis runs without errors
- Graphs generated correctly
- Stats files have expected format

**Duration:** ~15-20 minutes (vs 6-8 hours for full-scale)

### Analyzing Test Results

**Use the acm-load-analysis skill when available:**
```
/acm-load-analysis results/YYYYMMDD-HHMMSS-*/
```

**Manual verification checklist:**
- [ ] `report.txt` exists with summary
- [ ] `monitor_data.csv` has > 0 rows
- [ ] `deploy-time-*.txt` has install duration, DU duration
- [ ] `imageclusterinstalls-*.stats` has p50/p95/p99/max
- [ ] `clustergroupupgrades-*.stats` has p50/p95/p99/max
- [ ] `phase1-idle-baseline-*/` directory exists
- [ ] `phase2-cluster-deployment-*/` directory exists
- [ ] `phase3-soak-baseline-*/` directory exists
- [ ] `deploy-pa-*/cluster/stats/cpu-cluster.stats` exists
- [ ] `cluster-*.png` graph exists
- [ ] `policy-*.png` graph exists

---

## Analysis and Debugging

### Reading Stats Files

**Pandas describe() format** (from `analyze-prometheus.py`):
```
Unit: cores
count    240.0
mean     5.23
std      1.45
min      2.10
25%      4.20
50%      5.15    ← P50 (median)
75%      6.10
95%      7.85    ← P95 (use for CPU, network, disk)
99%      8.20    ← P99 (use for etcd latency)
max      9.50    ← Max (use for memory, disk usage)
```

**Plaintext format** (from timing analyzers):
```
ImageClusterInstalls: 2592 clusters
p50: 1018.0
p95: 1158.0
p99: 1193.0
max: 1371.0
```

**Key statistics by metric type:**
- **CPU**: Use P95 (95th percentile) — captures peak load, filters transient spikes
- **Memory**: Use Max — memory doesn't release quickly, max shows true requirement
- **Network**: Use P95 — filters transient bursts
- **Disk IOPS/Throughput**: Use P95 — filters transient bursts
- **Disk Usage**: Use Max — shows maximum storage requirement
- **etcd Latency**: Use P99 — SLO targets are P99 thresholds
- **etcd DB Size**: Use Max — shows maximum storage consumed
- **Timing (ICI, CGU)**: Report p50, p95, p99, max — p50 = typical, p95/p99 = outliers

### Common Debug Scenarios

#### Scenario 1: Clusters Not Installing

**Symptoms:**
- `cluster_init > 0` but `cluster_install_completed = 0` after 30+ minutes
- `cluster_notstarted` increasing or stuck

**Debug Steps:**
```bash
# Check ICI/ACI status
oc get imageclusterinstall -A  # For IBI
oc get agentclusterinstall -A  # For AI

# Check specific cluster
oc get imageclusterinstall <cluster-name> -n <namespace> -o yaml

# Look for conditions
# status:
#   conditions:
#   - type: Completed
#     status: "False"
#     reason: InstallationInProgress  # OK
#     # OR
#     reason: InstallationFailed      # BAD
#     message: "..."                  # Error details
```

**Common Causes:**
- Insufficient bare metal hosts (check `oc get baremetalhost -A`)
- Seed image not prepared (IBI only)
- Network connectivity issues (check BMC reachability)
- Invalid cluster manifest (check `oc get events -n <namespace>`)

#### Scenario 2: DU Profile Not Compliant

**Symptoms:**
- `policy_init > 0` but `policy_compliant = 0` after 30+ minutes
- `policy_timedout > 0`

**Debug Steps:**
```bash
# Check CGU status
oc get clustergroupupgrade -n ztp-install

# Check specific CGU
oc get clustergroupupgrade <cluster-name> -n ztp-install -o yaml

# Look for status
# status:
#   conditions:
#   - type: Ready
#     status: "True"     # All policies compliant
#     # OR
#     status: "False"    # Some policies non-compliant
#   remediationPlan:
#     - <cluster-name>:
#       - <policy-name>: NonCompliant  # Which policy failed
```

**Common Causes:**
- Policy template not rendered correctly (check policy in `ztp-install` namespace)
- Operator not installed on managed cluster (e.g., SR-IOV, PTP)
- Resource constraints on managed cluster (OOM, disk full)
- Timeout too short (increase `--wait-du-profile-max`)

#### Scenario 3: Prometheus Analysis Failed

**Symptoms:**
- `pa-phase*.log` has errors
- `phase*-*/` directory empty or missing stats files

**Debug Steps:**
```bash
# Check log
cat results/YYYYMMDD-HHMMSS-*/pa-phase2-cluster-deployment.log

# Common errors:
# - "401 Unauthorized" → Prometheus token expired
# - "Connection refused" → Prometheus route not accessible
# - "Empty result" → Time window has no data (check start/end timestamps)
# - "KeyError: '95%'" → Stats file empty (no data points)
```

**Common Causes:**
- Prometheus token expired (re-run with fresh token)
- Thanos route not found (check `oc get route -n open-cluster-management-observability`)
- Phase duration < 15 minutes (analysis skipped, increase `--start-delay` or `--end-delay`)
- Prometheus retention period exceeded (querying data older than retention)

#### Scenario 4: Graph Generation Failed

**Symptoms:**
- `graph-acm-deploy.py` exits with error
- PNG files missing in result directory

**Debug Steps:**
```bash
# Run graph script manually
python acm-deploy-load/graph-acm-deploy.py results/YYYYMMDD-HHMMSS-*/

# Common errors:
# - "FileNotFoundError: monitor_data.csv" → CSV missing (workload didn't complete)
# - "KeyError: 'cluster_applied'" → CSV has wrong columns
# - "kaleido.scopes._base.ScopeError" → Chrome/Chromium not installed
```

**Common Causes:**
- `monitor_data.csv` missing (ZTPMonitor thread crashed)
- CSV corrupted (partial write due to script crash)
- Chrome not installed (required for PNG export via kaleido)

---

## Conventions and Standards

### Naming Conventions

**Python Scripts:**
- Workload: `acm-<purpose>-load.py` (e.g., `acm-deploy-load.py`, `acm-mc-load.py`)
- Analysis: `analyze-<resource>.py` (e.g., `analyze-imageclusterinstalls.py`)
- Graphing: `graph-<purpose>.py` (e.g., `graph-acm-deploy.py`)
- Utilities: `<function>.py` (e.g., `etcd-defrag.py`, `hub-policy-generator.py`)

**Bash Scripts:**
- Orchestration: `<workload>-all.sh` (e.g., `interval-ztp-install-all.sh`)
- Post-test: `post-<workload>-<action>.sh` (e.g., `post-ztp-install-data-collection.sh`)
- Dry-run: `dry-run-<workload>.sh` (e.g., `dry-run-ztp-install.sh`)

**Result Files:**
- CSV: `<resource>-<timestamp>.csv` (e.g., `imageclusterinstalls-20241028-120000.csv`)
- Stats: `<resource>-<timestamp>.stats` (e.g., `imageclusterinstalls-20241028-120000.stats`)
- Graphs: `<type>-<timestamp>.png` (e.g., `cluster-20241028-120000.png`)
- Directories: `<prefix>-<timestamp>/` (e.g., `deploy-pa-20241028-120000/`)

### Logging Standards

**Use the project logger, not print():**
```python
import logging
logger = logging.getLogger("acm-deploy-load")

logger.debug("Detailed debug info (only visible with --debug)")
logger.info("Normal informational message")
logger.warning("Warning message (e.g., missing optional data)")
logger.error("Error message (e.g., API call failed)")
```

**Log Levels:**
- `DEBUG` — Verbose details (variable values, loop iterations)
- `INFO` — Normal operation (commands executed, files written, progress updates)
- `WARNING` — Unexpected but recoverable (missing optional resource, retry triggered)
- `ERROR` — Failure requiring attention (API error, file write failed, invalid data)

**Log Format:**
```
%(asctime)s : %(levelname)s : %(threadName)s : %(message)s
```

**Example:**
```
2024-10-28 12:00:00 : INFO : MainThread : Command(1): oc get imageclusterinstall -A -o json
2024-10-28 12:00:01 : INFO : ZTPMonitor : Sample complete, elapsed: 1.2s
```

### Documentation Standards

**When modifying code, update these files:**

| File | Update When |
|------|-------------|
| `CLAUDE.md` | Add/remove files in `acm-deploy-load/`, `scripts/`, `.claude/skills/` |
| `ARCHITECTURE.md` | Change component architecture, add new patterns, modify workflows |
| `AGENT.md` | Add new common workflows, debugging scenarios, code patterns |
| `CONTRIBUTING.md` | Change development workflow, add new testing guidelines |
| `README.md` | Change setup steps, add new prerequisites, update quick start |

**Code Tree in CLAUDE.md:**
- Keep alphabetically sorted within each directory
- Include one-line description for each file
- Update role count when adding/removing Ansible roles

**Skills Documentation:**
- Update `.claude/skills/acm-load-analysis/` when changing analysis scripts
- Update skill maintenance table in CLAUDE.md when adding new metrics or graph types

---

## Common Pitfalls

### 1. Not Using Dry-Run Before Deploying

**Problem:** Deploy script has typo, deploys 2592 clusters with wrong config.

**Solution:** Always dry-run first:
```bash
python acm-deploy-load/acm-deploy-load.py --dry-run interval -b 500 -i 1800
```

### 2. Forgetting to Activate Virtual Environment

**Problem:** Python dependencies not found, import errors.

**Solution:** Always activate venv:
```bash
source .venv/bin/activate
python --version  # Verify
```

### 3. Using `print()` Instead of `logger.info()`

**Problem:** Output not captured in logs, no timestamps.

**Solution:** Use logger:
```python
import logging
logger = logging.getLogger("acm-deploy-load")
logger.info("Message here")  # NOT print("Message here")
```

### 4. Hardcoding Paths

**Problem:** Script fails when run from different directory.

**Solution:** Use relative paths or CLI args:
```python
# BAD
kubeconfig = "/root/mno/kubeconfig"

# GOOD
parser.add_argument("-k", "--kubeconfig", type=str, default="/root/mno/kubeconfig")
```

### 5. Not Handling JSON Decode Errors

**Problem:** Script crashes when API returns malformed JSON under load.

**Solution:** Always wrap JSON parsing:
```python
try:
    data = json.loads(output)
except json.decoder.JSONDecodeError:
    logger.warning("JSON decode error: {}".format(output[:500]))
    return
```

### 6. Forgetting to Join Threads

**Problem:** Main script exits, ZTPMonitor thread still writing CSV.

**Solution:** Always join threads:
```python
monitor_thread.signal = False
monitor_thread.join()  # Wait for thread to finish
```

### 7. Not Checking `oc` Return Codes

**Problem:** Script continues with invalid data after `oc` command fails.

**Solution:** Always check return code:
```python
rc, output = command(oc_cmd, dry_run=False)
if rc != 0:
    logger.error("oc command failed: rc={}".format(rc))
    sys.exit(1)
```

### 8. Using Wrong Statistic

**Problem:** Report shows "average" CPU, understating peak requirement.

**Solution:** Use correct statistic:
- **CPU**: P95 (not mean/average)
- **Memory**: Max (not mean/average)
- **etcd latency**: P99 (not mean/average)

### 9. Not Converting Units

**Problem:** Report shows "5000000000" instead of "5.0 GB".

**Solution:** Convert to human-readable units:
```python
# Bytes to GiB (binary)
gib = bytes / (1024 ** 3)

# Bytes to GB (decimal)
gb = bytes / (1000 ** 3)

# Bytes to Mbps (network)
mbps = bytes_per_sec * 8 / (1000 ** 2)
```

### 10. Forgetting to Update CLAUDE.md File Tree

**Problem:** CLAUDE.md code tree doesn't match actual files.

**Solution:** Update CLAUDE.md when adding/removing files:
```markdown
acm-deploy-load/
├── acm-deploy-load.py
├── analyze-prometheus.py
├── analyze-xyz.py          # ← ADD THIS LINE
└── utils/
```

---

## Quick Reference

### Result Directory Naming

```
YYYYMMDD-HHMMSS-<method>-<params>-<suffix>
20261028-041457-ibi-clusterinstance-gitops-1000cpa-500b-1800i-17-mcoa

YYYYMMDD-HHMMSS:  Timestamp (UTC)
method:           ibi-clusterinstance-gitops
params:           1000cpa (clusters per app)
                  500b (batch size)
                  1800i (interval in seconds)
suffix:           17-mcoa (user-provided)
```

### Deployment Methods

| Method | Description | Installer | API | GitOps |
|--------|-------------|-----------|-----|--------|
| `ai-manifest` | Assisted Installer, direct manifest apply | AI | ACI | No |
| `ai-clusterinstance` | Assisted Installer, ClusterInstance API | AI | CI | No |
| `ai-clusterinstance-gitops` | Assisted Installer, ClusterInstance via GitOps | AI | CI | Yes |
| `ai-siteconfig-gitops` | Assisted Installer, SiteConfig via GitOps (legacy) | AI | SC | Yes |
| `ibi-manifest` | Image-Based Installer, direct manifest apply | IBI | ICI | No |
| `ibi-clusterinstance` | Image-Based Installer, ClusterInstance API | IBI | CI | No |
| `ibi-clusterinstance-gitops` | Image-Based Installer, ClusterInstance via GitOps | IBI | CI | Yes |

### Key File Locations

| Purpose | Location |
|---------|----------|
| Workload scripts | `acm-deploy-load/*.py` |
| Analysis scripts | `acm-deploy-load/analyze-*.py` |
| Graph scripts | `acm-deploy-load/graph-*.py` |
| Utilities | `acm-deploy-load/utils/*.py` |
| Orchestration | `scripts/*.sh` |
| Test results | `results/YYYYMMDD-HHMMSS-*/` |
| Analysis skills | `.claude/skills/*/` |

### Essential Commands

```bash
# Setup
./bootstrap.sh && source .venv/bin/activate

# Dry-run test
python acm-deploy-load/acm-deploy-load.py --dry-run interval -b 10 -i 60

# Small-scale test
scripts/interval-ztp-install-all.sh -c 10 -b 5 -i 60 -t "test"

# Full-scale test
scripts/interval-ztp-install-all.sh -c 2592 -b 500 -i 1800 -t "run-17"

# Analyze result
/acm-load-analysis results/YYYYMMDD-HHMMSS-*/

# Compare two results
/acm-load-analysis results/test-A/ results/test-B/

# Generate comparison graphs
python acm-deploy-load/graph-acm-compare.py \
  results/test-A results/test-B \
  --label-a "A" --label-b "B" \
  -o results/comparison-A-vs-B \
  -p comparison
```

### Resource Monitoring

```bash
# Check cluster state
oc get imageclusterinstall -A         # IBI clusters
oc get agentclusterinstall -A         # AI clusters
oc get managedcluster                 # All managed clusters
oc get clustergroupupgrade -n ztp-install  # DU profile status

# Check specific cluster
oc get imageclusterinstall <name> -n <ns> -o yaml
oc get managedcluster <name> -o yaml
oc get clustergroupupgrade <name> -n ztp-install -o yaml

# Check events
oc get events -n <namespace> --sort-by='.lastTimestamp'

# Check pod logs
oc logs -n <namespace> <pod-name>
```

### Stats File Interpretation

```bash
# CPU (use P95)
cat deploy-pa-*/cluster/stats/cpu-cluster.stats
# Look for: 95%    XX.XX  ← Hub CPU requirement

# Memory (use Max)
cat deploy-pa-*/cluster/stats/mem-cluster.stats
# Look for: max     XX.XX  ← Hub memory requirement

# etcd latency (use P99)
cat deploy-pa-*/etcd/stats/backend-commit-etcd.stats
# Look for: 99%     XX.XX  ← Should be < 25ms

# ICI timing (report p50, p95, p99, max)
cat imageclusterinstalls-*.stats
# Look for: p50/p95/p99/max
```

---

## Summary

This guide provides AI agents with the context needed to work effectively with the acm-deploy-load codebase. Key principles:

1. **Always dry-run before deploying** — Validate logic without cluster deployment
2. **Use small-scale tests** — 5-10 clusters for functional validation before full-scale
3. **Follow naming conventions** — Consistent file/directory naming for discoverability
4. **Use logger, not print()** — Structured logging with timestamps and levels
5. **Handle errors gracefully** — Check return codes, catch exceptions, log warnings
6. **Update documentation** — CLAUDE.md, ARCHITECTURE.md, AGENT.md when modifying code
7. **Verify stats files** — Use correct statistic (P95 for CPU, Max for memory, P99 for etcd)
8. **Test end-to-end** — Don't just unit test, verify full workflow (workload → analysis → graphs)

For architecture details, see `ARCHITECTURE.md`. For contribution guidelines, see `CONTRIBUTING.md`. For project overview, see `CLAUDE.md`.
