# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**acm-deploy-load** is a load testing and analysis framework for Red Hat Advanced Cluster Management (ACM) on OpenShift Container Platform (OCP). It automates large-scale cluster deployments (SNO, Compact, Standard) using Assisted Installer (AI) and Image-Based Installer (IBI), collects timing metrics, and generates reports and visualizations for capacity planning.

## Environment Setup

```bash
./bootstrap.sh          # Creates .venv, installs Python deps and Ansible collections
source .venv/bin/activate
```

Dependencies: Python 3, `oc` CLI with hub cluster access, Chrome (for static plot export).

## Running the Main Workloads

### acm-deploy-load.py — Cluster Deployment Loader

Deploys SNO, Compact, or Standard (MNO) clusters via Assisted Installer (AI,
agent-based) or Image-Based Installer (IBI), using either direct manifest apply
or ArgoCD/ZTP GitOps. Supports 7 deployment methods:

```bash
./acm-deploy-load/acm-deploy-load.py -m <method> interval -b <batch> -i <interval>
# methods: ai-manifest, ai-clusterinstance, ai-clusterinstance-gitops,
#          ai-siteconfig-gitops, ibi-manifest, ibi-clusterinstance, ibi-clusterinstance-gitops
```

### acm-telco-core-load.py — Telco Core MNO Workload

Deploys Telco Core MNO clusters via GitOps in configurable batches, then triggers
a policy configmap churn workload across the managed clusters once deployed.

```bash
./acm-deploy-load/acm-telco-core-load.py
```

### acm-mc-load.py — Managed Cluster Load Workload

Targets existing managed clusters (no deployment) and drives the same policy churn
workload as acm-telco-core-load.py: a configmap is updated on a regular interval,
changing values that policies enforce, causing managed clusters to cycle between
compliant and noncompliant states.

```bash
./acm-deploy-load/acm-mc-load.py
```

### End-to-end orchestration

```bash
# Orchestrates acm-deploy-load.py followed by post-test data collection and analysis scripts
./scripts/interval-ztp-install-all.sh

# Orchestrates acm-telco-core-load.py followed by post-test data collection
./scripts/acm-telco-core-load.sh
```

## Analysis and Graphing

```bash
# Prometheus/Thanos metrics analysis (largest script, 1451 lines)
./acm-deploy-load/analyze-prometheus.py

# Other analyzers follow the pattern analyze-<resource>.py:
./acm-deploy-load/analyze-upgrade.py
./acm-deploy-load/analyze-clustergroupupgrades.py
./acm-deploy-load/analyze-imagebasedupgrades.py

# Graphing (outputs PNG via plotly/matplotlib)
./acm-deploy-load/graph-acm-deploy.py
./acm-deploy-load/graph-upgrade.py
```

## Ansible Playbooks for ZTP/ACM/MCE Deployment and configuration

```bash
# Deploy ACM hub, MCE, ZTP, AAP
ansible-playbook ansible/rhacm-ztp-setup.yml
ansible-playbook ansible/rhacm-deploy.yml
ansible-playbook ansible/mce-deploy.yml
ansible-playbook ansible/aap-deploy.yml
```

Variables live in `ansible/vars/`; inventory in `ansible/inventory/`.

## Code Architecture

```
acm-deploy-load/          # All Python scripts
├── acm-deploy-load.py    # Deploys SNO/Compact/MNO clusters via AI or IBI (manifest or GitOps)
├── acm-telco-core-load.py  # Deploys Telco Core MNO clusters via GitOps in batches + policy churn workload
├── acm-mc-load.py        # Policy churn workload against existing managed clusters (no deployment)
├── mc-workload.py        # Load existing Managed cluster with objects
├── analyze-*.py          # Post-run analysis tools (Prometheus, upgrades, CGU, IBI, etc.)
├── graph-*.py            # Visualization scripts (plotly/matplotlib → PNG)
├── acm-health.py / ocp-health.py
└── utils/
    ├── command.py        # subprocess wrapper around `oc` with retry logic and dry-run support
    ├── common_ocp.py     # OCP utilities: namespace lists, Prometheus token retrieval, Thanos routing
    ├── output.py         # Report/CSV generation, percentile stats formatting
    ├── ztp_monitor.py    # Background thread sampling cluster install state every N seconds
    └── talm.py           # Detects TALM minor version
ansible/
├── roles/                # 38+ roles (ACM, MCE, IBI, IBU, AAP, ZTP, etc.)
└── vars/                 # Sample variable files for all cluster types
scripts/                  # Shell wrappers for end-to-end test workflows
results/                  # Timestamped test output directories (excluded from git)
```

## Key Concepts

- **Deployment methods**: `ai-*` = Assisted Installer, `ibi-*` = Image-Based Installer; `-manifest` = direct apply, `-clusterinstance` = ClusterInstance API, `-gitops` = ArgoCD/ZTP GitOps
- **ZTPMonitor**: Background thread in `utils/ztp_monitor.py` that continuously samples `AgentClusterInstall` and `ImageClusterInstall` resources, tracking state transitions and recording timestamps for analysis
- **Thanos routing**: `common_ocp.py` dynamically determines whether to query Prometheus directly or route through the Thanos querier based on cluster configuration
- **Stats output**: Analysis scripts produce `.stats` files with percentile breakdowns (50p, 95p, 99p) alongside raw `.csv` files
- **Dry-run support**: `command.py` supports a dry-run mode that logs `oc` commands without executing them

## OCP Resources Monitored

`AgentClusterInstall`, `ImageClusterInstall`, `ClusterInstance`, `ClusterGroupUpgrade`, `ImageClusterGroupUpgrade`, `ClusterVersion`, `Policy`/`PolicyTemplate`, `AnsibleJob`, `MultiClusterHub`, `MultiClusterEngine`, `MultiClusterObservability`
