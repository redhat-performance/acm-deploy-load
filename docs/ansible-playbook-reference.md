# Ansible Playbook Reference

This document provides a reference for acm-deploy-load Ansible playbooks.

_**Table of Contents**_

<!-- TOC -->
- [Inventory Files](#inventory-files)
- [Vars Files](#vars-files)
- [Playbook Summary](#playbook-summary)
- [Playbook Details](#playbook-details)
<!-- /TOC -->

## Inventory Files

Ansible playbooks require an inventory file that defines the target hosts. Copy the sample and fill in your environment details:

```console
(.venv) [root@<bastion> acm-deploy-load]# cp ansible/inventory/hosts.sample ansible/inventory/<cloudname>.local
```

Most playbooks only require the `[bastion]` group — a single entry with your bastion hostname is sufficient for hub deployment playbooks (`rhacm-deploy.yml`, `rhacm-ztp-setup.yml`, etc.).

The `[hv]` and `[hv_vm]` groups are only needed by manifest generation and IBI preparation playbooks (`sno-manifests.yml`, `telco-core-manifests.yml`, `ibi-prepare-snos.yml`). These groups contain per-host variables (IPs, MAC addresses, disk locations, etc.) and are typically provided by the jetlag-generated inventory file at `../jetlag/ansible/inventory/<cloudname>.local`.

| Group | Required By | Description |
| - | - | - |
| `bastion` | All playbooks | The bastion machine where playbooks run and services are hosted |
| `hv` | `ibi-prepare-snos.yml` | Hypervisor nodes that host VMs |
| `hv_vm` | `sno-manifests.yml`, `telco-core-manifests.yml`, `ibi-prepare-snos.yml` | Individual VMs hosted on hypervisors (targets for SNO/MNO deployment) |

> [!TIP]
> The `sno-manifests.yml` and `ibi-prepare-snos.yml` playbooks benefit from `--forks 10` for parallel execution across VMs.

## Vars Files

Playbook variables are set in vars files under `ansible/vars/`. Copy the sample files and adjust for your environment:

```console
(.venv) [root@<bastion> acm-deploy-load]# cp ansible/vars/all.sample.yml ansible/vars/all.yml
(.venv) [root@<bastion> acm-deploy-load]# cp ansible/vars/telco-core.sample.yml ansible/vars/telco-core.yml
```

| File | Used By | Description |
| - | - | - |
| `ansible/vars/all.yml` | All playbooks | Primary variables file covering ACM/MCE operator settings, ZTP configuration, assisted-installer, IBI/IBU, TALM, observability, and registry configuration |
| `ansible/vars/telco-core.yml` | `telco-core-manifests.yml` | Telco Core-specific variables including cluster definitions, t-shirt sizes, and network configuration |

> [!NOTE]
> Different playbooks may require different variable settings in `all.yml`. Review the sample file and the quickstart guides ([Deploy SNO via AI](deploy-sno-ai.md), [Deploy SNO via IBI](deploy-sno-ibi.md)) for the variables needed at each step.

## Playbook Summary

| Playbook | Purpose |
| - | - |
| `aap-2-6-deploy.yml` | Deploy and configure AAP 2.6 specifically |
| `aap-deploy.yml` | Deploy and configure Ansible Automation Platform with ACM integration |
| `ibi-prepare-snos.yml` | Create IBI prep ISO, build disk file, and distribute to hypervisors |
| `ibu-prepare-seed-cluster.yml` | Unmanage a seed cluster and generate a seed image for IBI/IBU |
| `mce-deploy.yml` | Deploy MCE standalone with assisted-installer and ClusterImageSets |
| `rhacm-deploy.yml` | Deploy ACM, MCE, assisted-installer, observability, TALM, SiteConfig operator, and ClusterImageSets |
| `rhacm-downstream-deploy.yml` | Deploy downstream/Konflux ACM builds with mirror setup |
| `rhacm-global-hub-deploy.yml` | Deploy ACM Global Hub for multi-hub management |
| `rhacm-ztp-complete-upgrade-setup.yml` | Setup ZTP platform and operator upgrade process |
| `rhacm-ztp-ibgu-setup.yml` | Setup ZTP Image-Based GroupUpgrade (IBGU) process |
| `rhacm-ztp-ibu-setup.yml` | Setup ZTP Image-Based Upgrade (IBU) process |
| `rhacm-ztp-operator-upgrade-setup.yml` | Setup ZTP operator upgrade process |
| `rhacm-ztp-platform-upgrade-setup.yml` | Setup ZTP platform upgrade process |
| `rhacm-ztp-setup.yml` | Setup ZTP repository, ArgoCD applications, and policy templates |
| `sno-manifests.yml` | Generate SNO cluster deployment manifests (AI and IBI) |
| `telco-core-manifests.yml` | Generate Telco Core MNO cluster manifests |

## Playbook Details

### ibi-prepare-snos.yml

**Target**: bastion, hv (hypervisors), hv_vm (VMs)

**Roles executed** (in order):
1. `ibi-create-prep-iso` (bastion) - Extracts openshift-install, generates IBI prep ISO
2. `ibi-install-prep` (hv_vm) - Boots each VM with prep ISO via Redfish to build disk file
3. `ibi-copy-disk-file` (hv) - Copies prepared disk file from bastion to all hypervisors

### ibu-prepare-seed-cluster.yml

**Target**: bastion

**Roles executed** (in order):
1. `ibu-prepare-unmanage-seed-cluster` - Removes seed cluster from ZTP ArgoCD management
2. `ibu-generate-seed-image` - Creates SeedGenerator manifest on seed cluster and waits for image generation

### rhacm-deploy.yml

**Target**: bastion

**Roles executed** (in order):
1. `rhacm-deploy` - Installs ACM operator and creates MultiClusterHub
2. `rhacm-observability` - Configures ACM Observability (when `setup_rhacm_observability: true`)
3. `talm-deploy` - Deploys TALM operator (when `setup_talm_operator: true` or `setup_talm_repo: true`)
4. `rhacm-ztp-patches` - Applies ZTP ArgoCD patches (when `setup_rhacm_ztp_patches: true`)
5. `rhacm-siteconfig-operator` - Enables SiteConfig Operator (when `acm_enable_siteconfig: true`)
6. `mce-assisted-installer` - Configures assisted-installer in MCE
7. `mce-image-based-install` - Enables IBIO in MCE (when `mce_enable_ibio: true`)
8. `mce-add-clusterimagesets` - Creates ClusterImageSet resources

### rhacm-ztp-setup.yml

**Target**: bastion

**Roles executed** (in order):
1. `rhacm-ztp-setup` - Clones ZTP repo, pushes to Gogs, creates ArgoCD config
2. `telco-core-ztp` - Sets up Telco Core ZTP policies (when `setup_core_ztp: true`)
3. `telco-ran-du-ztp` - Sets up RAN DU ZTP policies (when `setup_ran_du_ztp: true`)

### sno-manifests.yml

**Target**: hv_vm (hypervisor VMs)

**Roles executed**:
1. `sno-create-manifests` - Templates per-VM manifests for all enabled formats (AI SiteConfigs, AI ClusterInstances, AI manifests, IBI ClusterInstances, IBI manifests)

### telco-core-manifests.yml

**Target**: bastion

**Roles executed** (in order):
1. `telco-core-bm-inventory` - Reads baremetal OCP inventory JSON and maps hardware to Telco Core clusters (when `ocp_inventory` is defined)
2. `telco-core-vm-inventory` - Reads VM inventory from jetlag and maps VMs to Telco Core clusters (when using VM inventory)
3. `telco-core-manifests` - Creates ClusterInstance and SiteConfig manifests for each Telco Core cluster
