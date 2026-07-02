# acm-deploy-load

Tools, Ansible playbooks, and scripts to prepare, load, and analyze a large-scale OCP cluster with ACM (Advanced Cluster Management) for cluster deployments, upgrades, and policy workloads. Supports deploying SNO (Single Node OpenShift), Compact, and Standard (MNO) clusters via Assisted Installer (AI) or Image-Based Installer (IBI), using direct manifest apply, ClusterInstance API, or ArgoCD/ZTP GitOps workflows.

_**Table of Contents**_

<!-- TOC -->
- [Workflow Overview](#workflow-overview)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Configuration Files](#configuration-files)
- [Documentation](#documentation)
- [Workload Scripts](#workload-scripts)
- [Manifest Generation Scripts](#manifest-generation-scripts)
- [Analysis Scripts](#analysis-scripts)
- [Graphing Scripts](#graphing-scripts)
- [Other Scripts](#other-scripts)
- [Patch Scripts](#patch-scripts)
<!-- /TOC -->

## Workflow Overview

Every scale test generally follows three phases:

```
Phase 1: Setup            Phase 2: Run               Phase 3: Analyze
──────────────────        ──────────────────         ─────────────────────
Generate manifests  →     Deploy clusters at    →    Prometheus metrics
Setup ZTP/ArgoCD          scale via workload         Cluster install stats
Deploy ACM hub            scripts                    Timing analysis
Prep Seed Image                                      Graphs and reports
```

1. **Setup** — Use Ansible playbooks to generate deployment manifests, configure ZTP, and deploy ACM/MCE on the hub cluster
2. **Run** — Execute Python workload scripts to deploy managed clusters in batches at configurable intervals
3. **Analyze** — Run analysis scripts to query Prometheus, compute timing statistics, and generate graphs

## Prerequisites

- **Jetlag** has provisioned your infrastructure — OCP hub cluster installed, bastion accessible, hypervisor nodes configured. See [jetlag](https://github.com/redhat-performance/jetlag) for provisioning guides.
- **`oc` CLI** installed and authenticated against the hub cluster
- **Python 3** on the bastion machine
- **Chrome** (for static plotly graph export via kaleido)

## Setup

Bootstrap the Python virtual environment and install dependencies:

```console
[root@<bastion> acm-deploy-load]# ./bootstrap.sh
[root@<bastion> acm-deploy-load]# source .venv/bin/activate
(.venv) [root@<bastion> acm-deploy-load]#
```

Then follow the quickstart guides in [Documentation](#documentation) to set up and run your test.

## Configuration Files

| File | Description |
| - | - |
| `ansible/vars/all.yml` | Primary Ansible variables file (sample at `ansible/vars/all.sample.yml`) |
| `ansible/vars/telco-core.yml` | Telco Core-specific variables (sample at `ansible/vars/telco-core.sample.yml`) |
| `ansible/inventory/<cloudname>.local` | Ansible inventory (sample at `ansible/inventory/hosts.sample`) |

## Documentation

| Document | Description |
| - | - |
| [Ansible Playbook Reference](docs/ansible-playbook-reference.md) | Complete reference for all playbooks, roles, variables, and patch scripts |
| [Deploy SNO via AI](docs/deploy-sno-ai.md) | Deploy SNO clusters at scale using Assisted Installer |
| [Deploy SNO via IBI](docs/deploy-sno-ibi.md) | Deploy SNO clusters at scale using Image-Based Installer |
| [Deploy Telco Hub via ArgoCD](docs/deploy-telco-hub.md) | Deploy Telco Hub using ArgoCD/GitOps RDS |
| [ZTP DU Profile Setup](docs/ztp-du-profile-setup.md) | DU profile policy configuration — PolicyGenerator vs PolicyGenTemplate, variables reference |

## Workload Scripts

### acm-deploy-load.py

Deploys SNO, Compact, or Standard clusters via Assisted Installer or Image-Based Installer in configurable batches at timed intervals.

**Deployment Methods:**

| Method | Description |
| - | - |
| `ai-manifest` | AI clusters via direct `oc apply` YAML manifests |
| `ai-clusterinstance` | AI clusters via `oc apply` ClusterInstance |
| `ai-clusterinstance-gitops` | AI clusters via ClusterInstances in ArgoCD/ZTP GitOps |
| `ai-siteconfig-gitops` | AI clusters via SiteConfigs in ArgoCD/ZTP GitOps |
| `ibi-manifest` | IBI clusters via direct `oc apply` YAML manifests |
| `ibi-clusterinstance` | IBI clusters via `oc apply` ClusterInstance |
| `ibi-clusterinstance-gitops` | IBI clusters via ClusterInstances in ArgoCD/ZTP GitOps |

**Workload Phases:**

1. Phase 1 / Idle Baseline — Pre-deployment delay for baseline resource measurements (`--start-delay`)
2. Phase 2 / Cluster Deployment — Apply manifests or push to GitOps to deploy clusters
   - Wait for Cluster Install Completion
   - Wait for DU Profile Completion (optional)
   - Wait for Playbook Completion (optional)
3. Phase 3 / Soak Baseline — Post-deployment delay for steady-state resource measurements (`--end-delay`)

Optional per-phase Prometheus analysis runs automatically at phase boundaries (disable with `--no-prometheus-analysis`).

### acm-telco-core-load.py

Deploys Telco Core MNO clusters via GitOps in configurable batches, and runs a policy churn workload that periodically updates a ConfigMap triggering policy re-enforcement across managed clusters. Used for capacity guidelines testing with two test profiles:

**Three Phase Run** — Full capacity guidelines test with certificate rotation measurement:

1. Cert Rotation / Quiesce — 25-hour quiet period to capture certificate rotation resource spikes as a baseline before deployment begins
2. Deployment Batches and Policy Churn — Deploy 1 batch per 12-hour period with concurrent policy ConfigMap updates. Prometheus measurements are taken between phase and batch boundaries to determine resource requirements as cluster count and workload increases.
3. Steady State Measurement — Post-deployment measurement period with all clusters managed and policy churn continuing

**Two Phase Accelerated Run** — Faster test that completes before certificate rotation:

1. Deployment Batches and Policy Churn — Deploy 1 batch per 10-minute period with concurrent policy churn. After the last batch deploys, policy churn continues for 6 hours while clusters finish deploying and applying policies.
2. Steady State Measurement — Resource consumption levels off as policy churn ends and the hub cluster reaches steady state

### acm-mc-load.py

Imports (manages) previously deployed clusters into ACM in batches on an interval while running a concurrent policy churn workload. Updates a ConfigMap on interval, causing policies to cycle between compliant and non-compliant states across the managed clusters.

## Manifest Generation Scripts

| Script | Description |
| - | - |
| `hub-policy-generator.py` | Generate policy manifests (namespaces, ConfigMaps, and policy templates) used by the policy churn workload in `acm-telco-core-load.py` and `acm-mc-load.py` |
| `mc-workload.py` | Generate and apply managed cluster workload manifests (namespaces, deployments, pods, configmaps, secrets) to load a target cluster with objects |

## Analysis Scripts

| Script | Description |
| - | - |
| `analyze-prometheus.py` | Query Prometheus/Thanos for hub resource consumption metrics and generate time-series graphs |
| `analyze-agentclusterinstalls.py` | AI cluster install timing — count, min/avg/max, 50/95/99 percentiles |
| `analyze-imageclusterinstalls.py` | IBI cluster install timing — count, min/avg/max, 50/95/99 percentiles |
| `analyze-clusterinstances.py` | ClusterInstance resource timing analysis |
| `analyze-clustergroupupgrades.py` | CGU/TALM completion timing for ZTP install |
| `analyze-acm-deploy-time.py` | Deployment duration metrics and peak concurrency from monitoring data |
| `analyze-ansiblejobs.py` | AAP AnsibleJob timing analysis |
| `analyze-single-cluster-time.py` | Individual cluster deploy and DU profile timing |

See each script's `--help` output for detailed usage.

## Graphing Scripts

| Script | Description |
| - | - |
| `graph-acm-deploy.py` | Deployment timeline visualization from `monitor_data.csv` |

## Other Scripts

| Script | Description |
| - | - |
| `ocp-health.py` | Verify OCP cluster health (ClusterVersion, ClusterOperators, nodes, MCPs, etcd) |
| `acm-health.py` | Verify ACM health (MCH, MCE, MCO availability) |
| `benchmark-search.py` | Benchmark ACM Search API performance |
| `etcd-defrag.py` | Trigger etcd defragmentation |
| `report-per-cluster.py` | Generate per-cluster timing reports |

## Patch Scripts

Version-specific scripts in the [`patch/`](patch) directory provide memory limits tuning or image patches generally used with experimental builds of specific versions to test fixes during scale testing.
