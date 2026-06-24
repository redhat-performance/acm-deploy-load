# CLAUDE.md

## Project Overview

**acm-deploy-load** is a load testing and analysis framework for Red Hat Advanced Cluster Management (ACM) on OpenShift Container Platform (OCP). It automates large-scale cluster deployments (SNO, Compact, Standard) using Assisted Installer (AI) and Image-Based Installer (IBI), collects timing metrics, and generates reports and visualizations for capacity planning.

## Environment Setup

```bash
./bootstrap.sh          # Creates .venv, installs Python deps and Ansible collections
source .venv/bin/activate
```

Dependencies: Python 3, `oc` CLI with hub cluster access, Chrome (for static plot export).

## Main Workloads

| Tool | Purpose | Orchestration Script |
|---|---|---|
| `acm-deploy-load/acm-deploy-load.py` | Deploy SNO/Compact/MNO clusters via AI or IBI (7 methods) | `scripts/interval-ztp-install-all.sh` |
| `acm-deploy-load/acm-telco-core-load.py` | Deploy Telco Core MNO clusters via GitOps + policy churn | `scripts/acm-telco-core-load.sh` |
| `acm-deploy-load/acm-mc-load.py` | Policy churn workload against existing managed clusters | `scripts/mc-load-24hr.sh` |

Deployment methods: `ai-manifest`, `ai-clusterinstance`, `ai-clusterinstance-gitops`, `ai-siteconfig-gitops`, `ibi-manifest`, `ibi-clusterinstance`, `ibi-clusterinstance-gitops`

Ansible playbooks for hub setup: `ansible/rhacm-ztp-setup.yml`, `rhacm-deploy.yml`, `mce-deploy.yml`, `aap-deploy.yml`. Variables in `ansible/vars/`; inventory in `ansible/inventory/`.

## Code Architecture

When adding or removing files in `acm-deploy-load/`, `acm-deploy-load/utils/`,
`scripts/`, or `.claude/skills/`, update this tree to match. When adding or
removing Ansible roles, update the role count.

```
acm-deploy-load/                        # All Python scripts
├── acm-deploy-load.py                   # Deploy SNO/Compact/MNO clusters via AI or IBI
├── acm-telco-core-load.py               # Deploy Telco Core MNO clusters via GitOps + policy churn
├── acm-mc-load.py                       # Policy churn workload against existing managed clusters
├── mc-workload.py                       # Load existing managed cluster with objects
├── analyze-prometheus.py                # Prometheus/Thanos metrics analysis, generates stats files
├── analyze-acm-deploy-time.py           # Generates deploy-time-* file (durations, peak concurrency)
├── analyze-imageclusterinstalls.py      # ICI per-cluster install timing stats (IBI)
├── analyze-agentclusterinstalls.py      # ACI per-cluster install timing stats (AI)
├── analyze-clusterinstances.py          # ClusterInstance provisioning timing stats
├── analyze-clustergroupupgrades.py      # CGU per-cluster policy timing stats
├── analyze-imagebasedgroupupgrades.py   # IBGU analysis
├── analyze-imagebasedupgrades.py        # IBU analysis
├── analyze-ansiblejobs.py               # AnsibleJob analysis
├── analyze-clusterversion.py            # ClusterVersion analysis
├── analyze-upgrade.py                   # Upgrade analysis
├── analyze-single-cluster-time.py       # Single cluster timing breakdown
├── graph-acm-deploy.py                  # Deployment visualization (plotly → PNG)
├── graph-clusterversion.py              # ClusterVersion visualization
├── graph-upgrade.py                     # Upgrade visualization
├── report-per-cluster.py                # Per-cluster combined report/graph
├── benchmark-search.py                  # ACM search API benchmark
├── hub-policy-generator.py              # Generate hub policy manifests
├── etcd-defrag.py                       # etcd defragmentation utility
├── acm-health.py                        # ACM hub health check
├── ocp-health.py                        # OCP cluster health check
└── utils/
    ├── analysis.py                      # launch_prometheus_analysis() helper
    ├── command.py                       # subprocess wrapper around `oc` with retry and dry-run
    ├── common_ocp.py                    # OCP utilities: namespace lists, Prometheus token, Thanos routing
    ├── output.py                        # Report card generation (report.txt), CSV/stats formatting
    ├── ztp_monitor.py                   # Background thread sampling cluster install state every N seconds
    └── talm.py                          # Detects TALM minor version
scripts/
├── interval-ztp-install-all.sh          # Orchestrates acm-deploy-load.py + post-test analysis + deploy-pa
├── acm-telco-core-load.sh               # Orchestrates acm-telco-core-load.py + acm-telco-load-hub analysis
├── dry-run-ztp-install.sh               # Dry-run orchestration variant
├── mc-load-24hr.sh                      # 24-hour managed cluster load test
├── post-acm-load-data-collection.sh     # Post-test data collection (pods, events, CRs)
├── post-ztp-install-data-collection.sh  # Post-ZTP install data collection
├── post-ztp-upgrade-data-collection.sh  # Post-ZTP upgrade data collection
└── post-ztp-gen-day1-csv.sh             # Generate day-1 per-cluster CSV
ansible/
├── roles/                               # 38 roles (ACM, MCE, IBI, IBU, AAP, ZTP, telco-core, etc.)
└── vars/                                # Sample variable files for all cluster types
results/                                 # Timestamped test output directories (excluded from git)
.claude/skills/
├── acm-load-analysis/                   # Skill: test result analysis and comparison
├── prometheus-sizing-report/            # Skill: hub cluster sizing reports
└── shared-references/                   # Shared reference files used by multiple skills
```

## Key Concepts

- **Deployment methods**: `ai-*` = Assisted Installer, `ibi-*` = Image-Based Installer; `-manifest` = direct apply, `-clusterinstance` = ClusterInstance API, `-gitops` = ArgoCD/ZTP GitOps
- **ZTPMonitor**: Background thread in `utils/ztp_monitor.py` that continuously samples `AgentClusterInstall` and `ImageClusterInstall` resources, tracking state transitions and recording timestamps for analysis
- **Thanos routing**: `common_ocp.py` dynamically determines whether to query Prometheus directly or route through the Thanos querier based on cluster configuration
- **Stats output**: Analysis scripts produce `.stats` files with percentile breakdowns (50p, 95p, 99p) alongside raw `.csv` files
- **Dry-run support**: `command.py` supports a dry-run mode that logs `oc` commands without executing them

## OCP Resources Monitored

`AgentClusterInstall`, `ImageClusterInstall`, `ClusterInstance`, `ClusterGroupUpgrade`, `ImageClusterGroupUpgrade`, `ClusterVersion`, `Policy`/`PolicyTemplate`, `AnsibleJob`, `MultiClusterHub`, `MultiClusterEngine`, `MultiClusterObservability`

## Skill Maintenance

Claude Code skills under `.claude/skills/` document conventions derived from the
scripts and tools listed below. When modifying any of these source files, check
whether the corresponding skill references need updating.

| Source File | What Skills Reference From It |
|---|---|
| `acm-deploy-load/analyze-prometheus.py` | `-p` prefix flag, `y_unit` conversions, component namespace detection, stats file layout (`{component}/stats/{metric}.stats`), pandas describe output format |
| `acm-deploy-load/acm-deploy-load.py` | Phase directory naming (`phase1-idle-baseline`, `phase2-cluster-deployment`, `phase3-soak-baseline`), result directory naming |
| `acm-deploy-load/acm-telco-core-load.py` | Phase directory naming (`phase1-idle-baseline`, `phase2-batch-{N}`, `phase3-soak-baseline`), result directory naming, batch phase structure |
| `acm-deploy-load/utils/output.py` | `report.txt` format and report card title (`acm-deploy-load Report Card`, `acm-telco-core-load Report Card`) |
| `acm-deploy-load/analyze-acm-deploy-time.py` | `deploy-time-*` file format (durations, peak concurrency) |
| `acm-deploy-load/analyze-imageclusterinstalls.py` | ICI `.stats` file format (plaintext percentiles) |
| `acm-deploy-load/analyze-agentclusterinstalls.py` | ACI `.stats` file format (plaintext percentiles) |
| `acm-deploy-load/analyze-clusterinstances.py` | CI `.stats` file format (plaintext percentiles, two stat blocks) |
| `acm-deploy-load/analyze-clustergroupupgrades.py` | CGU `.stats` file format (header + plaintext percentiles) |
| `scripts/interval-ztp-install-all.sh` | Full-test Prometheus analysis prefix (`deploy-pa`) |
| `scripts/acm-telco-core-load.sh` | Full-test Prometheus analysis prefix (`acm-telco-load-hub`) |

**Skills that depend on the above:**
- `.claude/skills/acm-load-analysis/` — result directory layout, metrics/units, comparison methodology
- `.claude/skills/prometheus-sizing-report/` — Prometheus queries, stats format
- `.claude/skills/shared-references/` — stats file format, unit conversions (shared by both skills above)
