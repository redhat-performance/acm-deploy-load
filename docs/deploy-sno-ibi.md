# Deploy SNO Clusters via Image-Based Installer (IBI)

This guide covers deploying Single Node OpenShift (SNO) clusters at scale using the Image-Based Installer (IBI) method. IBI uses a pre-built disk image from a seed cluster to rapidly install SNOs, making it significantly faster than traditional Assisted Installer deployments.

_**Table of Contents**_

<!-- TOC -->
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Setup and Execution Order](#setup-and-execution-order)
- [Phase 1: Create Seed Image](#phase-1-create-seed-image)
- [Phase 2: IBI Scale Test](#phase-2-ibi-scale-test)
  - [Step 1: Generate SNO Manifests](#step-1-generate-sno-manifests)
  - [Step 2: Setup ZTP](#step-2-setup-ztp)
  - [Step 3: Deploy ACM Hub](#step-3-deploy-acm-hub)
  - [Step 4: Prepare SNO Disk Images](#step-4-prepare-sno-disk-images)
  - [Step 5: Run the Workload](#step-5-run-the-workload)
    - [Workload Phases](#workload-phases)
    - [Key Parameters](#key-parameters)
    - [End-to-End Orchestration](#end-to-end-orchestration)
  - [Step 6: Analyze Results](#step-6-analyze-results)
<!-- /TOC -->

## Overview

IBI deploys SNO clusters by writing a pre-built disk image (created from a seed cluster) to each target machine's disk, then customizing it with cluster-specific configuration on first boot. This avoids the full installation process that Assisted Installer uses, making the actual cluster install significantly faster.

However, IBI requires two preparation steps before the scale test can begin: creating a seed image from an existing AI-deployed SNO cluster (one-time per OCP version), and preparing the disk of every target machine with that seed image. These preparation steps are not part of the scale test itself but add considerable setup time compared to AI deployments which can begin immediately after hub configuration.

Three IBI deployment methods are available:

| Method | Description |
| - | - |
| `ibi-manifest` | Direct `oc apply` of raw YAML manifests for each cluster |
| `ibi-clusterinstance` | Direct `oc apply` of ClusterInstance custom resources |
| `ibi-clusterinstance-gitops` | ClusterInstance CRs deployed via ArgoCD/ZTP GitOps |

The `ibi-clusterinstance-gitops` method is used for scale tests, as it exercises the full GitOps ZTP pipeline.

## Prerequisites

Before deploying SNO clusters via IBI:

1. **Jetlag has provisioned your infrastructure** — OCP hub cluster installed, bastion accessible, hypervisor nodes with VMs configured. See [jetlag](https://github.com/redhat-performance/jetlag) for provisioning guides.
2. **`oc` CLI** is installed and authenticated against the hub cluster
3. **acm-deploy-load is bootstrapped** on the bastion:

```console
[root@<bastion> acm-deploy-load]# ./bootstrap.sh
[root@<bastion> acm-deploy-load]# source .venv/bin/activate
(.venv) [root@<bastion> acm-deploy-load]#
```

## Setup and Execution Order

IBI requires a seed image generated from an existing SNO cluster. The full workflow has two phases:

```
Phase 1 — Seed Image (one-time)                    Phase 2 — IBI Scale Test
────────────────────────────────                    ────────────────────────────
1. Deploy SNOs via AI (see AI guide)                1. sno-manifests.yml (IBI manifests)
2. ibu-prepare-seed-cluster.yml (create seed)       2. rhacm-ztp-setup.yml
                                                    3. rhacm-deploy.yml (with IBIO)
                                                    4. ibi-prepare-snos.yml (disk images)
                                                    5. Run the workload
```

Phase 1 creates the seed image from an existing managed SNO cluster. If you already have a verified seed image, skip to Phase 2.

Phase 2 rebuilds the environment for IBI and runs the scale test.

> [!NOTE]
> Each playbook step may require different variable settings in `ansible/vars/all.yml`. Copy the sample file (`cp ansible/vars/all.sample.yml ansible/vars/all.yml`) and adjust before each playbook. See the [Ansible Playbook Reference](ansible-playbook-reference.md) for complete variable documentation.

## Phase 1: Create Seed Image

If this is your first IBI test and you do not have a seed image, you must first deploy a small number of SNOs (4-5) via Assisted Installer to create a seed image from. Follow Steps 1-3 of the [Deploy SNO via AI](deploy-sno-ai.md) guide to generate manifests, setup ZTP, and deploy the ACM hub, then return here.

Instead of running the full workload script, manually add 4-5 clusters to the `kustomization.yaml` in the ZTP repo's cluster application directory:

```console
(.venv) [root@<bastion> acm-deploy-load]# cd /root/rhacm-ztp/telco-reference/telco-ran/configuration/argocd/cluster/ztp-clusters-01
(.venv) [root@<bastion> ztp-clusters-01]# cat kustomization.yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
generators:

resources:
- ./vm00001-clusterinstance.yml
- ./vm00002-clusterinstance.yml
- ./vm00003-clusterinstance.yml
- ./vm00004-clusterinstance.yml
```

The ClusterInstance manifest files referenced in `kustomization.yaml` (e.g. `vm00001-clusterinstance.yml`) must already exist in the same directory. These are generated by Step 1 of Phase 2 (`sno-manifests.yml`) and copied into the ZTP repo by Step 2 (`rhacm-ztp-setup.yml`).

Commit and push the change to Gogs:

```console
(.venv) [root@<bastion> ztp-clusters-01]# git add kustomization.yaml
(.venv) [root@<bastion> ztp-clusters-01]# git commit -m "Add seed cluster candidates"
(.venv) [root@<bastion> ztp-clusters-01]# git push
```

> [!TIP]
> You can open the Gogs web UI on the bastion to verify your changes were pushed. Navigate to the repo, select the correct branch, and browse to the `cluster/ztp-clusters-01/` directory to confirm the `kustomization.yaml` update is present.

Refresh the ArgoCD application to trigger deployment. Monitor the `AgentClusterInstall` resources for each cluster until they reach `InstallationCompleted`, then watch the associated `ClusterGroupUpgrade` objects complete. Once the clusters are labeled `ztp-done=`, they are ready to be used as a seed cluster.

Once you have a few managed SNO clusters deployed via AI, extract their kubeconfigs to verify they are healthy and have the expected DU profile operators installed:

```console
(.venv) [root@<bastion> acm-deploy-load]# oc get managedcluster --no-headers | grep -v local | awk '{print $1}' | xargs -I % sh -c "mkdir -p /root/hv-vm/kc/% ; oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/kc/%/kubeconfig"
```

Verify the seed cluster candidates are healthy and have all DU profile operators before proceeding:

```console
(.venv) [root@<bastion> acm-deploy-load]# export KUBECONFIG=/root/hv-vm/kc/<seed-cluster>/kubeconfig
(.venv) [root@<bastion> acm-deploy-load]# oc get clusterversion
(.venv) [root@<bastion> acm-deploy-load]# oc get co | grep -v "True.*False.*False"
(.venv) [root@<bastion> acm-deploy-load]# oc get csv -A | grep -i succeeded
```

Once verified, configure the seed cluster variables in `ansible/vars/all.yml`:

| Variable | Description | Example |
| - | - | - |
| `rhacm_disconnected_registry` | Disconnected registry hostname | `registry.example.com` |
| `seed_cluster` | Name of the managed cluster to use as seed | `vm00001` |
| `ibu_seed_image_version` | OCP version of the seed image | `4.21.14` |
| `seedgenerator_apiversion` | SeedGenerator API version | `v1` |
| `ibu_prepare_unmanage_cluster` | Whether to unmanage the seed cluster | `true` |
| `ibu_generate_seed_image` | Whether to generate the seed image | `true` |

Then run:

```console
(.venv) [root@<bastion> acm-deploy-load]# ansible-playbook -i ansible/inventory/<cloudname>.local ansible/ibu-prepare-seed-cluster.yml
```

This playbook:
1. Unmanages the seed cluster from ACM by removing it from the ZTP ArgoCD applications
2. Generates a seed image from the cluster using the SeedGenerator API

> [!NOTE]
> Seed image generation takes approximately 10 minutes. The playbook waits for completion automatically.

After the seed image is generated and verified, rebuild the environment for the full IBI scale test and proceed to Phase 2.

## Phase 2: IBI Scale Test

Before beginning, rebuild the hub cluster and VMs that were used during Phase 1 so the scale test starts from a fully clean environment. Re-provision the infrastructure with jetlag to get a fresh hub cluster and replace all hypervisor VMs.

### Step 1: Generate SNO Manifests

Generate IBI ClusterInstance manifests for all target SNO VMs. Set the following in `ansible/vars/all.yml`:

| Variable | Description | Example |
| - | - | - |
| `rhacm_disconnected_registry` | Disconnected registry hostname | `registry.example.com` |
| `cluster_image_set` | ClusterImageSet name reference | `openshift-4.21.14` |
| `create_ibi_clusterinstances` | Generate IBI ClusterInstance manifests | `true`/`false` |
| `create_ibi_manifests` | Generate IBI raw manifests | `true`/`false` |

To save time, set only the manifest type matching your deployment method:

| Method | Required Manifest Variable |
| - | - |
| `ibi-clusterinstance-gitops` | `create_ibi_clusterinstances: true` |
| `ibi-clusterinstance` | `create_ibi_clusterinstances: true` |
| `ibi-manifest` | `create_ibi_manifests: true` |

Then generate the manifests. This playbook requires the `[hv_vm]` group with per-VM variables, so use the jetlag-generated inventory file:

```console
(.venv) [root@<bastion> acm-deploy-load]# ansible-playbook -i ../jetlag/ansible/inventory/<cloudname>.local ansible/sno-manifests.yml --forks 10
```

The `--forks 10` flag parallelizes manifest generation across hypervisor VMs.

### Step 2: Setup ZTP

Configure the ZTP repository, ArgoCD applications, and DU profile policy templates. The ZTP setup clones the upstream ZTP repository, copies your generated manifests into it, templates the DU profile policies, and pushes everything to the bastion's Gogs git server for ArgoCD to consume.

The DU profile policies are generated using **PolicyGenerator (PG)** by default (`acm_policygenerator: true`). The older PolicyGenTemplate (PGT) approach is deprecated but still available by setting `acm_policygenerator: false`. See the [ZTP DU Profile Setup](ztp-du-profile-setup.md) guide for a full explanation of PG vs PGT, policy splitting, hub side templating, and all associated variables.

Set ZTP-specific variables in `ansible/vars/all.yml`:

| Variable | Description | Example |
| - | - | - |
| `rhacm_disconnected_registry` | Disconnected registry hostname | `registry.example.com` |
| `setup_ran_du_ztp` | Enable RAN DU ZTP policies | `true` |
| `setup_ztp_sno_policy` | Create SNO cluster policy | `true` |
| `setup_ztp_compact_policy` | Create Compact cluster policy | `false` |
| `setup_ztp_standard_policy` | Create Standard cluster policy | `false` |
| `acm_policygenerator` | Use ACM PolicyGenerator (`true`, default) | `true` |
| `ztp_repo_type` | ZTP repo type (`telco-reference` for 4.20+) | `telco-reference` |
| `ztp_site_generator_image_tag` | ZTP site generator image tag | `v4.21.0-2` |
| `du_profile_version` | DU profile version | `4.21` |
| `operator_index_tag` | Operator index tag version | `v4.21` |
| `gogs_host` | Gogs git server host (bastion IP) | `198.18.0.1` or `[fc00:198:18:10::1]` |

```console
(.venv) [root@<bastion> acm-deploy-load]# ansible-playbook -i ansible/inventory/<cloudname>.local ansible/rhacm-ztp-setup.yml
```

After the playbook completes, the DU profile policies and cluster siteconfigs are committed to the Gogs repository. You can browse the repository at `http://<gogs_host>:<gogs_port>/testadmin/<repo-name>` to verify the policy templates were generated correctly.

### Step 3: Deploy ACM Hub

Deploy ACM, MCE, TALM, assisted-installer, Image-based Install Operator (IBIO), SiteConfig Operator, and related components and configuration on the hub cluster.

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
| `mce_enable_ibio` | Enable Image-Based Install Operator in MCE | `true` |
| `mce_assisted_ocp_versions` | OCP release images for assisted installer | (see example below) |
| `mce_clusterimagesets` | ClusterImageSet definitions | (see example below) |

> [!IMPORTANT]
> For IBI, both `acm_enable_siteconfig: true` and `mce_enable_ibio: true` must be set. These enable the SiteConfig Operator and Image-Based Install Operator respectively, which are required for IBI cluster deployments.

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

(.venv) [root@<bastion> acm-deploy-load]# oc get po -n multicluster-engine -l app=image-based-install-operator
NAME                                            READY   STATUS    RESTARTS   AGE
image-based-install-operator-6984c848d7-9svlv   2/2     Running   0          18h

(.venv) [root@<bastion> acm-deploy-load]# oc get po -n open-cluster-management -l app.kubernetes.io/component=siteconfig
NAME                                            READY   STATUS    RESTARTS   AGE
siteconfig-controller-manager-55499c95b-x9h68   1/1     Running   0          18h
```

Confirm that MultiClusterHub is `Running`, MultiClusterEngine is `Available`, your ClusterImageSet exists, and the assisted-service, image-based-install-operator, and siteconfig-controller-manager pods are `Running`.

### Step 4: Prepare SNO Disk Images

This step creates a preparation ISO from the seed image, boots a target SNO VM with it to write the disk image, then distributes the prepared disk file to all hypervisors.

Configure the following in `ansible/vars/all.yml`:

| Variable | Description | Example |
| - | - | - |
| `rhacm_disconnected_registry` | Disconnected registry hostname | `registry.example.com` |
| `ocp_ibi_version` | Full OCP release image URI | `quay.io/openshift-release-dev/ocp-release:4.21.14-x86_64` |
| `seed_image_version` | OCP version matching the seed image | `4.21.14` |
| `hv_vm_target` | VM name to use for building the disk file | `vm00010` |
| `ibi_prepare_disk_file` | Whether to create the prep ISO and build disk file | `true` |
| `ibi_hv_copy_disk_file` | Whether to copy disk file from bastion to hypervisors | `true` |
| `ibi_replace_sno_disk_file` | Whether to replace each SNO's disk file | `true` |

For disconnected environments, you may also need to set `ibi_prep_iso_ignitionConfigOverride` with an ignition config that includes registry trust and SSH access configuration for debugging.

```console
(.venv) [root@<bastion> acm-deploy-load]# ansible-playbook -i ../jetlag/ansible/inventory/<cloudname>.local ansible/ibi-prepare-snos.yml --forks 10
```

This playbook:
1. Creates the IBI preparation ISO on the bastion using `openshift-install`
2. Boots a target VM with the prep ISO via Redfish/virtual media to build the disk file
3. Copies the prepared disk file from bastion to all hypervisors
4. Replaces each SNO VM's disk file with the prepared image

> [!TIP]
> If you have already prepared the disk file and just need to redistribute it, set `ibi_prepare_disk_file: false` and `ibi_hv_copy_disk_file: false` to skip those steps.

### Step 5: Run the Workload

With the hub configured and SNO disk images prepared, run the deployment workload:

```console
(.venv) [root@<bastion> acm-deploy-load]# ./acm-deploy-load/acm-deploy-load.py \
  -m ibi-clusterinstance-gitops \
  --clusters-per-app 100 \
  -w \
  -i 60 \
  -t 100cpa-500b-1800i-1 \
  interval -b 500 -i 1800
```

This example deploys all available SNO clusters in batches of 500 every 30 minutes (1800 seconds), with 100 clusters per ArgoCD application, waiting for DU profile completion, and monitoring every 60 seconds.

#### Workload Phases

1. **Deploy Phase** - Applies ClusterInstance manifests in batches at the configured interval, pushing them to the ZTP GitOps repository
2. **Wait for Cluster Install** - Monitors `ImageClusterInstall` resources until all clusters reach `ClusterInstallationSucceeded` or timeout
3. **Wait for DU Profile** (if `-w` flag set) - Waits for TALM `ClusterGroupUpgrade` resources to complete, indicating day-2 policy enforcement is done
4. **Report Card** - Generates a summary report with timing data, success/failure counts, and writes results to the output directory

#### Key Parameters

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
| Results suffix | `-t` | Suffix for results directory name | `int-0` |
| Wait cluster max | `--wait-cluster-max` | Max seconds to wait for cluster install | `10800` |
| Wait DU profile max | `--wait-du-profile-max` | Max seconds to wait for DU profile | `18000` |

#### Metadata Parameters

These parameters are used for report and graph titles:

| Parameter | Flag | Description |
| - | - | - |
| ACM version | `--acm-version` | ACM version string for reports |
| AAP version | `--aap-version` | AAP version string for reports |
| Test version | `--test-version` | Test identifier for graph titles |
| Hub OCP version | `--hub-version` | Hub cluster OCP version for reports |
| Deploy OCP version | `--deploy-version` | Deployed cluster OCP version for reports |
| WAN emulation | `--wan-emulation` | WAN emulation settings for graph titles |

#### End-to-End Orchestration

For a complete test run including deployment, analysis, graphing, and data collection, use the orchestration script:

> [!NOTE]
> Edit the variables at the top of `interval-ztp-install-all.sh` before running to set the method, batch size, interval, and metadata for your test. Key variables to review:

```bash
method="ibi-clusterinstance-gitops"
interval_period=1800
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

### Step 6: Analyze Results

After the workload completes (or after the orchestration script finishes), results are written to a timestamped directory under `results/`. The directory name encodes the run configuration, e.g. `results/20260514-005949-ibi-clusterinstance-gitops-100cpa-500b-1800i-6/`.

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
 * Method: ibi-clusterinstance-gitops
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

**Deployment Timeline Graphs** — The `cluster-*.png`, `policy-*.png` and `share*.png`  graphs visualize combinations of cluster state progressions over time (applied, installing, completed, managed, policy compliant, etc.) and are useful for identifying bottlenecks and ceilings during large deployments.

**Stats Files** — Each `*.stats` file contains percentile breakdowns (count, min, avg, 50p, 95p, 99p, max) for a resource type. For example, `imageclusterinstalls-*.stats` shows IBI install duration in seconds:

```
Stats only on ImageClusterInstalls CRs in ClusterInstallationSucceeded
Count: 324
Min: 351.0
Average: 591.9
50 percentile: 576.0
95 percentile: 677.8
99 percentile: 715.8
Max: 759.0
```

**Prometheus Analysis** — The `deploy-pa-*/` directories contain Prometheus/Thanos query results organized by category (`node/`, `etcd/`, `cluster/`, `resource/`) with time-series graphs and stats for hub resource consumption during the test.
