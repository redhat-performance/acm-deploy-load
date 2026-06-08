# Deploy a Telco Hub Cluster via ArgoCD GitOps (RDS)

This guide covers deploying the Telco Hub Reference Design Spec (RDS) using ArgoCD/GitOps on a 3-node OpenShift Cluster. The playbook clones the [telco-reference](https://github.com/openshift-kni/telco-reference) repository, templates Kustomize overlays with environment-specific values, pushes to Gogs, installs the GitOps operator, and creates an ArgoCD Application that triggers the full hub deployment — including ACM, MCE, ODF, LSO, TALM, OADP, cluster monitoring, and ZTP configuration.

_**Table of Contents**_

<!-- TOC -->
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Setup and Execution Order](#setup-and-execution-order)
- [Step 1: Generate SNO Manifests](#step-1-generate-sno-manifests)
- [Step 2: Setup ZTP](#step-2-setup-ztp)
- [Step 3: Deploy Telco Hub](#step-3-deploy-telco-hub)
  - [Component Toggles](#component-toggles)
  - [GitOps Operator Settings](#gitops-operator-settings)
  - [LSO Overlay Options](#lso-overlay-options)
  - [ODF Overlay Options](#odf-overlay-options)
  - [ACM Overlay Options](#acm-overlay-options)
  - [Registry Overlay Options](#registry-overlay-options)
  - [Cluster Monitoring Options](#cluster-monitoring-options)
  - [Verification](#verification)
- [Step 4: Run the Workload](#step-4-run-the-workload)
<!-- /TOC -->

## Overview

The `telco-hub-deploy.yml` playbook replaces the traditional `rhacm-deploy.yml` approach by deploying the entire hub stack through a single ArgoCD Application (`hub-config`). Instead of sequentially applying individual operators and CRs, ArgoCD syncs a Kustomize overlay tree that installs all required hub components in the correct order via sync-waves.

The upstream [telco-reference/telco-hub/configuration](https://github.com/openshift-kni/telco-reference/tree/main/telco-hub/configuration) provides reference CRs for each component. The playbook templates a `custom-overlays-config/` directory alongside the upstream `example-overlays-config/`, applying environment-specific patches (storage classes, operator sources, registry mirrors, etc.) without modifying the upstream reference CRs directly.

**What gets deployed:**

| Component | Description |
| - | - |
| OpenShift GitOps | ArgoCD operator and hub-config Application |
| Local Storage Operator (LSO) | Local disk provisioning for ODF |
| OpenShift Data Foundation (ODF) | Ceph-based storage (CephFS, RBD, NooBaa) |
| Advanced Cluster Management (ACM) | MultiClusterHub, Observability, AgentServiceConfig, SiteConfig Operator |
| MultiCluster Engine (MCE) | Assisted Installer, Image-Based Install Operator (IBIO) |
| TALM | Topology Aware Lifecycle Manager |
| OADP | OpenShift API for Data Protection |
| Cluster Monitoring | Prometheus retention and persistent storage |
| Registry Mirrors | CatalogSource, IDMS, ITMS for disconnected environments |
| ZTP | ArgoCD plugin configuration and AppProjects for cluster/policy apps |

## Prerequisites

Before deploying the telco hub:

1. **Jetlag has provisioned a plain 3-node OCP cluster** — The cluster must be a 3-node compact (MNO with 0 workers) to support ODF, which requires 3 nodes for Ceph replication. Jetlag should only deploy the base cluster — do **not** install LSO, ODF, GitOps, or apply a cluster monitoring config during jetlag provisioning, as all of these are deployed by the telco-hub playbook via ArgoCD. Key jetlag settings:
   - `cluster_type: mno` with `worker_node_count: 0`
   - `setup_bastion_gogs: true` (required for GitOps repo)
   - `setup_bastion_registry: true` and `use_bastion_registry: true` (disconnected)
   - `controlplane_etcd_on_nvme: true` (recommended for performance)
   - Label nodes for ODF: `post_install_node_labels: ["cluster.ocs.openshift.io/openshift-storage="]`
   - Configure `controlplane_localstorage_disk_devices` with the disk paths for ODF storage — jetlag uses this to generate ignition config that cleanly wipes these disks during installation, which is required for ODF/Ceph to claim them
   - Do **not** set `setup_lso`, `setup_odf`, `setup_openshift_gitops`, or `apply_cluster_monitoring_config`

2. **Operators are synced into the disconnected registry** — For disconnected environments, the following operators must be mirrored into your CatalogSource:

   **Hub operators** (required for the telco-hub deployment):

   | Operator | Description |
   | - | - |
   | `advanced-cluster-management` | ACM hub operator |
   | `multicluster-engine` | MCE operator |
   | `openshift-gitops-operator` | ArgoCD/GitOps operator |
   | `local-storage-operator` | LSO for local disk provisioning |
   | `odf-operator` | OpenShift Data Foundation |
   | `ocs-operator` | OpenShift Container Storage |
   | `mcg-operator` | MultiCloud Object Gateway (NooBaa) |
   | `odf-csi-addons-operator` | ODF CSI add-ons |
   | `ocs-client-operator` | OCS client |
   | `odf-prometheus-operator` | ODF Prometheus |
   | `rook-ceph-operator` | Rook Ceph storage |
   | `cephcsi-operator` | Ceph CSI driver |
   | `odf-dependencies` | ODF dependency operator |
   | `odf-external-snapshotter-operator` | ODF external snapshotter |
   | `recipe` | ODF recipe operator |
   | `topology-aware-lifecycle-manager` | TALM operator |
   | `redhat-oadp-operator` | OADP operator |

   **RAN/DU and Telco Core RDS operators** (required for managed clusters deployed via RAN DU or Telco Core RDS profiles):

   | Operator | Description |
   | - | - |
   | `ptp-operator` | Precision Time Protocol |
   | `sriov-network-operator` | SR-IOV network operator |
   | `cluster-logging` | Cluster logging |
   | `lifecycle-agent` | Lifecycle Agent (for IBI/IBU) |
   | `kubernetes-nmstate-operator` | NMState network configuration |
   | `numaresources-operator` | NUMA-aware scheduling |
   | `metallb-operator` | MetalLB load balancer |

3. **`oc` CLI** is installed and authenticated against the hub cluster
4. **acm-deploy-load is bootstrapped** on the bastion:

```console
[root@<bastion> acm-deploy-load]# ./bootstrap.sh
[root@<bastion> acm-deploy-load]# source .venv/bin/activate
(.venv) [root@<bastion> acm-deploy-load]#
```

## Setup and Execution Order

The telco hub deployment replaces the `rhacm-deploy.yml` step in the traditional workflow. Manifests are generated first because the ZTP setup copies them into the GitOps repository:

```
1. sno-manifests.yml              # Generate SNO manifests (for scale testing)
2. rhacm-ztp-setup.yml            # Setup ZTP policies and ArgoCD repo
3. telco-hub-deploy.yml           # Deploy hub via ArgoCD GitOps (replaces rhacm-deploy.yml)
4. (Run the workload)             # Deploy clusters via acm-deploy-load.py
```

The `telco-hub-deploy.yml` playbook runs four roles:

| Role | Purpose |
| - | - |
| `telco-hub-prepare` | Clones telco-reference, templates Kustomize overlays, pushes to Gogs |
| `telco-hub-deploy` | Installs GitOps operator, applies ArgoCD Application, waits for ODF and MCH |
| `mce-add-clusterimagesets` | Creates ClusterImageSet resources for assisted installer |
| `rhacm-ztp-patches` | Configures ZTP cluster and policy ArgoCD applications (ArgoCD patching disabled) |

> [!NOTE]
> Each playbook step may require different variable settings in `ansible/vars/all.yml`. Copy the sample file (`cp ansible/vars/all.sample.yml ansible/vars/all.yml`) and adjust before each playbook. See the [Ansible Playbook Reference](ansible-playbook-reference.md) for complete variable documentation.

## Step 1: Generate SNO Manifests

If you plan to run a scale test after hub deployment, generate the SNO manifests first. See [Deploy SNO via AI](deploy-sno-ai.md) Step 1 or [Deploy SNO via IBI](deploy-sno-ibi.md) Step 1 for manifest generation instructions.

## Step 2: Setup ZTP

Configure the ZTP repository, ArgoCD applications, and policy templates. Set ZTP-specific variables in `ansible/vars/all.yml`:

| Variable | Description | Example |
| - | - | - |
| `rhacm_disconnected_registry` | Disconnected registry hostname | `registry.example.com` |
| `setup_ran_du_ztp` | Enable RAN DU ZTP policies | `true` |
| `ztp_repo_type` | ZTP repo type (`telco-reference` for 4.20+) | `telco-reference` |
| `ztp_site_generator_image_tag` | ZTP site generator image tag | `v4.21.0-2` |
| `du_profile_version` | DU profile version | `4.21` |
| `operator_index_tag` | Operator index tag version | `v4.21` |
| `gogs_host` | Gogs git server host (bastion IP) | `198.18.0.1` or `[fc00:198:18:10::1]` |

```console
(.venv) [root@<bastion> acm-deploy-load]# ansible-playbook -i ansible/inventory/<cloudname>.local ansible/rhacm-ztp-setup.yml
```

## Step 3: Deploy Telco Hub

This is the main step that deploys the full hub stack via ArgoCD. The `telco-hub-prepare` role templates all Kustomize overlays, and `telco-hub-deploy` applies the ArgoCD Application and waits for components to become healthy.

### Component Toggles

These variables control which overlay directories are included in the root Kustomize configuration. All default to `true`:

| Variable | Description | Default |
| - | - | - |
| `setup_lso` | Include LSO overlay (Local Storage Operator) | `true` |
| `setup_odf` | Include ODF overlay (OpenShift Data Foundation) | `true` |
| `setup_registry_mirror` | Include registry mirror overlay (CatalogSource, IDMS, ITMS) | `true` |
| `setup_ztp` | Include ZTP overlay (ArgoCD plugins and AppProjects) | `true` |
| `setup_cluster_monitoring` | Include cluster monitoring overlay (Prometheus storage) | `true` |
| `setup_gitops_operator` | Install GitOps operator manifests during deploy | `true` |

### GitOps Operator Settings

| Variable | Description | Default |
| - | - | - |
| `gitops_operator_source` | OLM CatalogSource for GitOps operator | `redhat-operators-disconnected` |
| `gitops_operator_channel` | GitOps operator subscription channel | `gitops-1.20` |
| `setup_argocd_tls_cert` | Include TLS certificate patch for ArgoCD | `false` |

### LSO Overlay Options

| Variable | Description | Default |
| - | - | - |
| `lso_device_paths` | List of device paths for local storage | `[/dev/nvme1n1]` |

### ODF Overlay Options

| Variable | Description | Default |
| - | - | - |
| `odf_storage_size` | PV size for OSD devices | `400Gi` |
| `odf_storage_class_name` | Storage class for local volumes | `local-sc` |
| `odf_device_set_count` | Number of device sets | `1` |
| `odf_device_set_replica` | Replica count per device set | `3` |
| `odf_osd_cpu` | CPU request for OSD pods | `2` |
| `odf_osd_memory` | Memory request for OSD pods | `5Gi` |
| `odf_mds_cpu` | CPU request for MDS pods | `3` |
| `odf_mds_memory` | Memory request for MDS pods | `8Gi` |

### ACM Overlay Options

| Variable | Description | Default |
| - | - | - |
| `acm_operator_source` | OLM CatalogSource for ACM operator | `redhat-operators-disconnected` |
| `acm_operator_channel` | ACM operator subscription channel | `release-2.16` |
| `mco_storage_class` | Storage class for MCO (filesystem type) | `ocs-storagecluster-cephfs` |
| `mco_obc_storage_class` | Storage class for MCO OBC (object type) | `openshift-storage.noobaa.io` |
| `asc_db_storage_class` | AgentServiceConfig database storage class | `ocs-storagecluster-cephfs` |
| `asc_fs_storage_class` | AgentServiceConfig filesystem storage class | `ocs-storagecluster-cephfs` |
| `asc_image_storage_class` | AgentServiceConfig image storage class | `ocs-storagecluster-cephfs` |
| `asc_remove_mirror_registry_ref` | Remove mirrorRegistryRef (connected environments) | `false` |
| `setup_asc_disable_image_policy` | Disable container image policy checks in assisted-service | `false` |
| `setup_acm_mch_fix` | Apply MCH/MCE component name fix patches | `true` |
| `mce_assisted_ocp_versions` | OCP release images for assisted installer | (see `vars/all.sample.yml`) |
| `mce_clusterimagesets` | ClusterImageSet definitions | (see `vars/all.sample.yml`) |

### Registry Overlay Options

| Variable | Description | Default |
| - | - | - |
| `registry_catalog_source_image` | CatalogSource image for disconnected operator index | (see defaults) |
| `setup_registry_idms_itms` | Include IDMS/ITMS mirror sets and registry-ca resources | `false` |

> [!NOTE]
> Set `setup_registry_idms_itms: false` when the cluster already has mirror registry configuration applied (e.g., via install-time configuration). Set to `true` to have the overlay apply IDMS, ITMS, registry CA, operator hub, and image config resources.

### Cluster Monitoring Options

| Variable | Description | Default |
| - | - | - |
| `monitoring_retention_period` | Prometheus data retention period | `15d` |
| `monitoring_storage_class` | Storage class for Prometheus PVs | `ocs-storagecluster-cephfs` |
| `monitoring_storage_size` | PV size for Prometheus storage | `100Gi` |

### Running the Playbook

```console
(.venv) [root@<bastion> acm-deploy-load]# ansible-playbook -i ansible/inventory/<cloudname>.local ansible/telco-hub-deploy.yml
```

The playbook will:
1. Clone the `telco-reference` repository (branch configurable via `telco_hub_repo_branch`)
2. Create (or reuse) a Gogs repository and push the source
3. Template all Kustomize overlays into `custom-overlays-config/`
4. Commit and push the overlay configuration to Gogs
5. Install the GitOps operator and wait for the ArgoCD instance to be `Available`
6. Apply the ArgoCD `hub-config` Application via `oc apply -k`
7. Wait for the `hub-config` ArgoCD Application to reach `Synced`
8. Wait for ODF StorageCluster to reach `Ready` and MultiClusterHub to reach `Running`
9. Verify MCE is `Available`, MCO is `Ready`, TALM and assisted-service pods are `Running`
10. Create ClusterImageSet resources for the assisted installer
11. Apply the ZTP cluster and policy ArgoCD applications for managed cluster deployment


### Verification

After the playbook completes, verify the hub components are healthy:

**ArgoCD Application:**

```console
(.venv) [root@<bastion> acm-deploy-load]# oc get application hub-config -n openshift-gitops
NAME         SYNC STATUS   HEALTH STATUS
hub-config   Synced        Healthy
```

**ODF StorageCluster:**

```console
(.venv) [root@<bastion> acm-deploy-load]# oc get storagecluster -n openshift-storage
NAME                 AGE   PHASE   EXTERNAL   CREATED AT             VERSION
ocs-storagecluster   1h    Ready              2026-05-19T00:00:00Z   4.21.0
```

**ACM MultiClusterHub and MultiClusterEngine:**

```console
(.venv) [root@<bastion> acm-deploy-load]# oc get mch -n open-cluster-management
NAME              STATUS    AGE   CURRENTVERSION   DESIREDVERSION
multiclusterhub   Running   1h    2.16.0           2.16.0

(.venv) [root@<bastion> acm-deploy-load]# oc get mce
NAME                 STATUS      AGE   CURRENTVERSION   DESIREDVERSION
multiclusterengine   Available   1h    2.11.0           2.11.0
```

**ClusterImageSets:**

```console
(.venv) [root@<bastion> acm-deploy-load]# oc get clusterimageset
NAME                RELEASE
openshift-4.21.14   registry.example.com:5000/ocp4/openshift4:4.21.14-x86_64
```

**Assisted Service and Operators:**

```console
(.venv) [root@<bastion> acm-deploy-load]# oc get po -n multicluster-engine | grep assisted
assisted-image-service-0                               1/1     Running   0          1h
assisted-service-6f69988b7-c96z9                       2/2     Running   0          1h

(.venv) [root@<bastion> acm-deploy-load]# oc get po -n multicluster-engine -l app=image-based-install-operator
NAME                                            READY   STATUS    RESTARTS   AGE
image-based-install-operator-6984c848d7-9svlv   2/2     Running   0          1h

(.venv) [root@<bastion> acm-deploy-load]# oc get po -n open-cluster-management -l app.kubernetes.io/component=siteconfig
NAME                                            READY   STATUS    RESTARTS   AGE
siteconfig-controller-manager-55499c95b-x9h68   1/1     Running   0          1h
```

**TALM:**

```console
(.venv) [root@<bastion> acm-deploy-load]# oc get csv -n openshift-operators | grep -i talm
topology-aware-lifecycle-manager.v4.21.0   TALM   4.21.0   Succeeded
```

**Cluster Monitoring (Prometheus):**

```console
(.venv) [root@<bastion> acm-deploy-load]# oc get pvc -n openshift-monitoring
NAME                                 STATUS   VOLUME       CAPACITY   ACCESS MODES   STORAGECLASS
localpvc-prometheus-k8s-0            Bound    pvc-...      100Gi      RWO            ocs-storagecluster-cephfs
localpvc-prometheus-k8s-1            Bound    pvc-...      100Gi      RWO            ocs-storagecluster-cephfs
```

Confirm that:
- ArgoCD `hub-config` Application is `Synced` and `Healthy`
- ODF StorageCluster is `Ready`
- MultiClusterHub is `Running` and MultiClusterEngine is `Available`
- ClusterImageSets exist for your target OCP versions
- Assisted-service, IBIO, and SiteConfig operator pods are `Running`
- TALM CSV is `Succeeded`
- Prometheus PVCs are `Bound` (if cluster monitoring is enabled)

## Step 4: Run the Workload

With the hub fully deployed, proceed to run the scale test workload. See [Deploy SNO via AI](deploy-sno-ai.md) Step 4 or [Deploy SNO via IBI](deploy-sno-ibi.md) Step 5 for workload execution instructions.
