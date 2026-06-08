# Deploy SNO Clusters via Assisted Installer (AI)

This guide covers deploying Single Node OpenShift (SNO) clusters at scale using the Assisted Installer (AI) method. AI uses the assisted-service on the hub cluster to orchestrate full cluster installations on target machines via virtual media and agent-based installation.

_**Table of Contents**_

<!-- TOC -->
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Setup and Execution Order](#setup-and-execution-order)
- [Step 1: Generate SNO Manifests](#step-1-generate-sno-manifests)
- [Step 2: Setup ZTP](#step-2-setup-ztp)
- [Step 3: Deploy ACM Hub](#step-3-deploy-acm-hub)
- [Step 4: Run the Workload](#step-4-run-the-workload)
  - [Workload Phases](#workload-phases)
  - [Key Parameters](#key-parameters)
  - [End-to-End Orchestration](#end-to-end-orchestration)
- [Step 5: Analyze Results](#step-5-analyze-results)
<!-- /TOC -->

## Overview

Assisted Installer deploys SNO clusters through the full OpenShift installation process. A discovery ISO boots on each target machine, registers with the assisted-service on the hub, and the installation proceeds through discovery, validation, and installation phases.

Four AI deployment methods are available:

| Method | Description |
| - | - |
| `ai-manifest` | Direct `oc apply` of raw YAML manifests (Namespace, BMH, ACI, etc.) |
| `ai-clusterinstance` | Direct `oc apply` of ClusterInstance custom resources |
| `ai-clusterinstance-gitops` | ClusterInstance CRs deployed via ArgoCD/ZTP GitOps |
| `ai-siteconfig-gitops` | SiteConfig CRs deployed via ArgoCD/ZTP GitOps |

The `ai-clusterinstance-gitops` method is the preferred approach using the ClusterInstance API with the SiteConfig Operator.

> [!NOTE]
> Despite the similar naming, SiteConfig manifests and the SiteConfig Operator are distinct. The `ai-siteconfig-gitops` method uses SiteConfig custom resources processed by the **ztp-site-generator** kustomize plugin in the ZTP GitOps pipeline. The `ai-clusterinstance` and `ai-clusterinstance-gitops` methods use ClusterInstance custom resources processed by the **SiteConfig Operator**. The SiteConfig Operator does not process SiteConfig manifests.

## Prerequisites

Before deploying SNO clusters via AI:

1. **Jetlag has provisioned your infrastructure** — OCP hub cluster installed, bastion accessible, hypervisor nodes with VMs configured. See [jetlag](https://github.com/redhat-performance/jetlag) for provisioning guides.
2. **`oc` CLI** is installed and authenticated against the hub cluster
3. **acm-deploy-load is bootstrapped** on the bastion:

```console
[root@<bastion> acm-deploy-load]# ./bootstrap.sh
[root@<bastion> acm-deploy-load]# source .venv/bin/activate
(.venv) [root@<bastion> acm-deploy-load]#
```

## Setup and Execution Order

The setup steps must be run in this order — manifests are generated first because the ZTP setup copies them into the GitOps repository:

```
1. sno-manifests.yml              # Generate SNO manifests
2. rhacm-ztp-setup.yml            # Setup ZTP policies and ArgoCD (copies manifests into GitOps repo)
3. rhacm-deploy.yml               # Deploy ACM hub
4. (Run the workload)             # Deploy clusters via acm-deploy-load.py
```

> [!NOTE]
> Each playbook step may require different variable settings in `ansible/vars/all.yml`. Copy the sample file (`cp ansible/vars/all.sample.yml ansible/vars/all.yml`) and adjust before each playbook.

## Step 1: Generate SNO Manifests

Generate the appropriate manifest type for your chosen deployment method. Set the following in `ansible/vars/all.yml`:

| Variable | Description | Example |
| - | - | - |
| `rhacm_disconnected_registry` | Disconnected registry hostname | `registry.example.com` |
| `cluster_image_set` | ClusterImageSet name reference | `openshift-4.21.14` |
| `sno_du_profile` | DU profile version | `4.21` |
| `create_ai_siteconfigs` | Generate AI SiteConfig manifests | `true`/`false` |
| `create_ai_clusterinstances` | Generate AI ClusterInstance manifests | `true`/`false` |
| `create_ai_manifests` | Generate AI raw manifests | `true`/`false` |

To save time, set only the manifest type matching your deployment method:

| Method | Required Manifest Variable |
| - | - |
| `ai-siteconfig-gitops` | `create_ai_siteconfigs: true` |
| `ai-clusterinstance-gitops` | `create_ai_clusterinstances: true` |
| `ai-clusterinstance` | `create_ai_clusterinstances: true` |
| `ai-manifest` | `create_ai_manifests: true` |

Then generate the manifests. This playbook requires the `[hv_vm]` group with per-VM variables, so use the jetlag-generated inventory file:

```console
(.venv) [root@<bastion> acm-deploy-load]# ansible-playbook -i ../jetlag/ansible/inventory/<cloudname>.local ansible/sno-manifests.yml --forks 10
```

The `--forks 10` flag parallelizes manifest generation across hypervisor VMs.

## Step 2: Setup ZTP

Configure the ZTP repository, ArgoCD applications, and policy templates. The ZTP setup clones the ZTP repository, copies your generated manifests into it, and pushes everything to the bastion's git server (Gogs Service).

Set ZTP-specific variables in `ansible/vars/all.yml`:

| Variable | Description | Example |
| - | - | - |
| `rhacm_disconnected_registry` | Disconnected registry hostname | `registry.example.com` |
| `setup_ran_du_ztp` | Enable RAN DU ZTP policies | `true` |
| `setup_ztp_sno_policy` | Create SNO cluster policy | `true` |
| `setup_ztp_compact_policy` | Create Compact cluster policy | `false` |
| `setup_ztp_standard_policy` | Create Standard cluster policy | `false` |
| `ztp_repo_type` | ZTP repo type (`telco-reference` for 4.20+) | `telco-reference` |
| `ztp_site_generator_image_tag` | ZTP site generator image tag | `v4.21.0-2` |
| `du_profile_version` | DU profile version | `4.21` |
| `operator_index_tag` | Operator index tag version | `v4.21` |
| `gogs_host` | Gogs git server host (bastion IP) | `198.18.0.1` or `[fc00:198:18:10::1]` |

```console
(.venv) [root@<bastion> acm-deploy-load]# ansible-playbook -i ansible/inventory/<cloudname>.local ansible/rhacm-ztp-setup.yml
```

### Pre-GA content

In order to use preGA builds/content you need additional parameters and overrides in `ansible/vars/all.yml`

| Variable | Value | Description |
| - | - | - |
| `ztp_repo_branch` | `main` | Should be set to main for pulling non-branched version |
| `ztp_repo_type` | `telco-reference` | Old repo no longer supported |
| `telco_core_operator_index` | `<registry>/<namespace>/<catalog>:<build>` | Desired catalog source image |
| `telco_core_clusterinstance_prega_manifests` | `true` | Required to apply Pre-GA configs from `ansible/roles/telco-core-manifests/templates/prega-manifests` and IDMS |
| `telco_core_prega_idms_link` | `<source>/imageDigestMirrorSet.yaml` | Link to the Pre-GA IDMS configuration |
| `pull_secret` | `"{{ lookup('file', '../<pull-secret-file>') }}"` | Path to the pull secret with Pre-GA content access |

Example:
```yaml
# Pre-GA section
ztp_repo_branch: main
ztp_repo_type: telco-reference
telco_core_operator_index: example.com/early/test-operator-index:v4.22.0-latest
telco_core_clusterinstance_prega_manifests: true
telco_core_prega_idms_link: https://example.com/latest_build/imageDigestMirrorSet.yaml
pull_secret: "{{ lookup('file', '../merged-pull-secret.txt') }}"
```

## Step 3: Deploy ACM Hub

Deploy ACM, MCE, TALM, assisted-installer, SiteConfig Operator, and related components and configuration on the hub cluster.

Set ACM deployment variables in `ansible/vars/all.yml`:

| Variable | Description | Example |
| - | - | - |
| `rhacm_disconnected_registry` | Disconnected registry hostname | `registry.example.com` |
| `acm_source` | OLM CatalogSource for ACM operator | `cs-redhat-operator-index-v4-21` |
| `acm_channel` | ACM operator subscription channel | `release-2.16` |
| `rhacm_quay_pullsecret` | Quay pull secret (set to `'{}'` when not needed) | `'{}'` |
| `setup_rhacm_observability` | Enable ACM Observability | `true` |
| `setup_talm_operator` | Deploy TALM via OLM subscription | `true` |
| `talm_operator_source` | CatalogSource for TALM operator | `cs-redhat-operator-index-v4-21` |
| `acm_enable_siteconfig` | Enable the SiteConfig Operator | `true` |
| `mce_assisted_ocp_versions` | OCP release images for assisted installer | (see example below) |
| `mce_clusterimagesets` | ClusterImageSet definitions | (see example below) |

The `mce_assisted_ocp_versions` and `mce_clusterimagesets` variables are YAML lists. Each OCP version you want to deploy needs an entry in both:

```yaml
mce_assisted_ocp_versions:
- quay.io/openshift-release-dev/ocp-release:4.21.14-x86_64

# Connected environment:
mce_clusterimagesets:
- name: openshift-4.21.14
  releaseImage: quay.io/openshift-release-dev/ocp-release:4.21.14-x86_64

# Disconnected environment (reference the local mirror registry):
mce_clusterimagesets:
- name: openshift-4.21.14
  releaseImage: registry.example.com:5000/ocp4/openshift4:4.21.14-x86_64
```

The `mce_assisted_ocp_versions` list always references `quay.io` release images to configure the assisted-service. The `mce_clusterimagesets` list creates ClusterImageSet resources on the hub, which are referenced by `cluster_image_set` in the SNO manifests. In disconnected environments, the ClusterImageSet `releaseImage` must reference the local mirror registry since the hub cluster pulls from it directly.

```console
(.venv) [root@<bastion> acm-deploy-load]# ansible-playbook -i ansible/inventory/<cloudname>.local ansible/rhacm-deploy.yml
```

After deployment, verify the hub components are healthy:

```console
(.venv) [root@<bastion> acm-deploy-load]# oc get mch -n open-cluster-management
NAME              STATUS    AGE   CURRENTVERSION   DESIREDVERSION
multiclusterhub   Running   16h   2.16.0           2.16.0

(.venv) [root@<bastion> acm-deploy-load]# oc get mce
NAME                 STATUS      AGE   CURRENTVERSION   DESIREDVERSION
multiclusterengine   Available   16h   2.11.0           2.11.0

(.venv) [root@<bastion> acm-deploy-load]# oc get clusterimageset
NAME                RELEASE
openshift-4.21.14   registry.example.com:5000/ocp4/openshift4:4.21.14-x86_64

(.venv) [root@<bastion> acm-deploy-load]# oc get po -n multicluster-engine | grep assisted
assisted-image-service-0                               1/1     Running   0          16h
assisted-service-6f69988b7-c96z9                       2/2     Running   0          16h
```

Confirm that MultiClusterHub is `Running`, MultiClusterEngine is `Available`, your ClusterImageSet exists, and the assisted-service pods are `Running`.

## Step 4: Run the Workload

With the hub configured and manifests generated, run the deployment workload:

```console
(.venv) [root@<bastion> acm-deploy-load]# ./acm-deploy-load/acm-deploy-load.py \
  -m ai-clusterinstance-gitops \
  --argocd-directory /root/rhacm-ztp/telco-reference/telco-ran/configuration/argocd \
  --clusters-per-app 100 \
  -w \
  -i 60 \
  -t 100cpa-500b-3600i-1 \
  interval -b 500 -i 3600
```

This example deploys all available SNO clusters in batches of 500 every hour (3600 seconds), with 100 clusters per ArgoCD application, waiting for DU profile completion, and monitoring every 60 seconds. The `--argocd-directory` flag points to the telco-reference ArgoCD directory used with 4.20+ ZTP repos.

> [!NOTE]
> AI installations take significantly longer than IBI. A typical AI SNO installation takes 45-90 minutes per cluster, so batch sizes and intervals should be planned accordingly to avoid overloading the hub.

### Workload Phases

1. **Deploy Phase** - Applies manifests in batches at the configured interval. For GitOps methods, manifests are pushed to the ZTP repository and ArgoCD syncs them. For direct methods, manifests are applied via `oc apply`.
2. **Wait for Cluster Install** - Monitors `AgentClusterInstall` resources until all clusters reach `InstallationCompleted` or timeout
3. **Wait for DU Profile** (if `-w` flag set) - Waits for TALM `ClusterGroupUpgrade` resources to complete
4. **Report Card** - Generates summary report with timing and success/failure data

### Key Parameters

| Parameter | Flag | Description | Default |
| - | - | - | - |
| Method | `-m` | Deployment method | `ai-siteconfig-gitops` |
| Batch size | `-b` | Clusters to deploy per interval | `100` |
| Interval | `-i` (subcommand) | Seconds between batches | `7200` |
| Clusters per app | `--clusters-per-app` | Clusters per ArgoCD application | `100` |
| Wait for DU profile | `-w` | Wait for day-2 policies to complete | `false` |
| Wait for playbook | `-wp` | Wait for AAP ansible playbook to complete | `false` |
| Monitor interval | `-i` (top-level) | Seconds between monitoring samples | `60` |
| Cluster manifests dir | `-cm` | Directory containing cluster manifests | `/root/hv-vm/` |
| ArgoCD directory | `-a` | ArgoCD configuration directory | (auto-detected) |
| Start index | `-s` | Start deploying from cluster index N | `0` |
| End index | `-e` | Stop deploying at cluster index N (0 = all) | `0` |
| No shuffle | `-n` | Deploy clusters in order (default: shuffled) | `false` |
| Start delay | `--start-delay` | Seconds to wait before starting | `15` |
| End delay | `--end-delay` | Seconds to wait after last batch | `120` |
| Results suffix | `-t` | Suffix for results directory name | `int-0` |
| Wait cluster max | `--wait-cluster-max` | Max seconds to wait for cluster install | `10800` |
| Wait DU profile max | `--wait-du-profile-max` | Max seconds to wait for DU profile | `18000` |
| Skip wait install | `-z` | Skip waiting for cluster installation | `false` |

### Metadata Parameters

These parameters set report and graph title metadata:

| Parameter | Flag | Description |
| - | - | - |
| ACM version | `--acm-version` | ACM version string |
| AAP version | `--aap-version` | AAP version string |
| Test version | `--test-version` | Test identifier |
| Hub OCP version | `--hub-version` | Hub cluster OCP version |
| Deploy OCP version | `--deploy-version` | Deployed cluster OCP version |
| WAN emulation | `--wan-emulation` | WAN emulation settings |

### End-to-End Orchestration

For a complete test run including deployment, analysis, graphing, and data collection, use the orchestration script:

> [!NOTE]
> Edit the variables at the top of `interval-ztp-install-all.sh` before running to set the method, batch size, interval, and metadata for your test. Key variables to review:

```bash
method="ai-clusterinstance-gitops"
interval_period=3600
batch=500
clusters_per_app=100
argocd_arg="--argocd-directory /root/rhacm-ztp/telco-reference/telco-ran/configuration/argocd"
```

Run with `nohup` so the workload survives SSH disconnections or tmux crashes:

```console
(.venv) [root@<bastion> acm-deploy-load]# nohup ./scripts/interval-ztp-install-all.sh &>/dev/null &
```

Monitor progress by tailing the log file:

```console
(.venv) [root@<bastion> acm-deploy-load]# tail -f iz-all-<date>-<time>.log
```

The orchestration script runs deployment followed by the full analysis pipeline: graphing, timing analysis, Prometheus metrics collection, data collection, and must-gather.

All output is collected into a timestamped results directory under `results/`.

## Step 5: Analyze Results

After the workload completes (or after the orchestration script finishes), results are written to a timestamped directory under `results/`. The directory name encodes the run configuration, e.g. `results/20260514-005949-ai-clusterinstance-gitops-100cpa-500b-1800i-6/`.

**Report Card** — The `report.txt` file summarizes the run:

```
###############################################################################
acm-deploy-load Report Card
###############################################################################
Versions
 * ACM: v2.16.0
 * Test: ZTP Scale Run 6
 * Hub OCP: 4.21.14
 * Deployed OCP: 4.21.14
Deployed Cluster Results
 * Available Clusters: 324
 * Deployed (Applied/Committed) Clusters: 324
 * Installed Clusters: 324
 * Failed Clusters: 0
 * Cluster Successful Percent: 100.0%
 * Cluster Failed Percent: 0.0%
Managed Cluster Results
 * Installed Clusters: 324
 * Managed Clusters: 324
 * Managed Successful Percent: 100.0%
 * Managed Failed Percent: 0.0%
DU Profile Results
 * DU Profile Initialized: 324
 * DU Profile Compliant: 324
 * DU Profile Timeout: 0
 * DU Profile Successful Percent: 100.0%
 * DU Profile Failed Percent: 0.0%
Overall Results
 * Overall Success (DU Compliant / Deployed): 324 / 324
 * Overall Success Percent: 100.0%
 * Overall Failed Percent: 0.0%
Deployed Cluster Orchestration
 * Method: ai-clusterinstance-gitops
 * Rate: interval
 * Cluster Start: 0 End: 0
 * 100 cluster(s) per ZTP argoCD application
 * 500 cluster(s) per 1800s interval
 * Actual Intervals: 1
 * Wan Emulation: (None)
Workload Duration Results
 * Start Time: 2026-05-14T00:59:49Z 1778720389819
 * End Time: 2026-05-14T01:30:11Z 1778722211407
 * Cluster Deploying duration: 1s :: 0:00:01
 * Cluster Install wait duration: 1141s :: 0:19:01
 * DU Profile wait duration: 661s :: 0:11:01
 * Total duration: 1822s :: 0:30:22
```

**Deployment Timeline Graphs** — The `cluster-*.png`, `policy-*.png` and `share*.png`  graphs visualize combinations of cluster state progressions over time (applied, installing, completed, managed, policy compliant, etc.) and are useful for identifying bottlenecks and ceiling during large deployments.

**Stats Files** — Each `*.stats` file contains percentile breakdowns (count, min, avg, 50p, 95p, 99p, max) for a resource type. For example, `agentclusterinstalls-*.stats` shows agent-based install duration in seconds:

```
Stats only on AgentClusterInstall CRs in InstallationCompleted
Count: 3565
Min: 2626.0
Average: 4005.1
50 percentile: 3979.0
95 percentile: 4895.0
99 percentile: 5352.3
Max: 8444.0
```

**Prometheus Analysis** — The `deploy-pa-*/` directories contain Prometheus/Thanos query results organized by category (`node/`, `etcd/`, `cluster/`, `resource/`) with time-series graphs and stats for hub resource consumption during the test.
