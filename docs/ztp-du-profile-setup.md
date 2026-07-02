# ZTP DU Profile Setup

This guide covers the `rhacm-ztp-setup.yml` playbook and the RAN DU profile policy templates it deploys. It explains the two policy generation approaches (ACM PolicyGenerator and PolicyGenTemplate), how to choose between them, and documents all associated variables.

_**Table of Contents**_

<!-- TOC -->
- [Overview](#overview)
- [Running the Playbook](#running-the-playbook)
- [ACM PolicyGenerator vs PolicyGenTemplate](#policygenerator-vs-policygenerator-template)
  - [ACM PolicyGenerator (PG)](#policygenerator-pg)
  - [PolicyGenTemplate (PGT) — Deprecated](#policygenerator-template-pgt--deprecated)
- [Repository and Bastion Layout](#repository-and-bastion-layout)
  - [Bastion Paths](#bastion-paths)
  - [Viewing in Gogs](#viewing-in-gogs)
- [Variables Reference](#variables-reference)
  - [Role Toggles](#role-toggles)
  - [Policy Toggles](#policy-toggles)
  - [Repository Configuration](#repository-configuration)
  - [DU Profile Selection](#du-profile-selection)
  - [Policy Content Variables](#policy-content-variables)
  - [Policy Splitting](#policy-splitting)
  - [Hub Side Templating](#hub-side-templating)
  - [Performance Profile](#performance-profile)
  - [Image Based Upgrade (IBU)](#image-based-upgrade-ibu)
  - [ArgoCD and Cluster Applications](#argocd-and-cluster-applications)
  - [Extra Manifests](#extra-manifests)
  - [Gogs Configuration](#gogs-configuration)
  - [ZTP Site Generator](#ztp-site-generator)
- [Template Directory Structure](#template-directory-structure)
<!-- /TOC -->

## Overview

The `rhacm-ztp-setup.yml` playbook prepares the ZTP GitOps pipeline on the bastion. It runs three roles in sequence:

1. **`rhacm-ztp-setup`** — Clones the upstream [telco-reference](https://github.com/openshift-kni/telco-reference) repository, pushes it to the local Gogs instance, and creates ArgoCD configuration
2. **`telco-core-ztp`** — Sets up Telco Core ZTP policies (when `setup_core_ztp: true`)
3. **`telco-ran-du-ztp`** — Generates RAN DU profile policy templates for SNO, compact (3-node), and standard clusters (when `setup_ran_du_ztp: true`)

The `telco-ran-du-ztp` role templates policy manifests, copies source CRs, distributes siteconfigs across ArgoCD applications, and commits everything to the Gogs repository for ArgoCD to reconcile.

## Running the Playbook

```console
(.venv) [root@<bastion> acm-deploy-load]# ansible-playbook -i ansible/inventory/<cloudname>.local ansible/rhacm-ztp-setup.yml
```

Ensure `ansible/vars/all.yml` is configured before running. See [Ansible Playbook Reference](ansible-playbook-reference.md) for inventory and vars file setup.

## ACM PolicyGenerator vs PolicyGenTemplate

Two approaches exist for generating ACM governance policies from DU profile manifests. The `acm_policygenerator` variable controls which one is used.

### ACM PolicyGenerator (PG)

**Default and recommended.** ACM PolicyGenerator uses `apiVersion: policy.open-cluster-management.io/v1` with `kind: PolicyGenerator`. Policies are defined as separate entries in a top-level `policies:` list, each with a `name:` and `manifests:` block.

- Template directories: `pg-du-4.20/` (covers OCP 4.20+) and `pg-du-4.18/` (covers OCP 4.18–4.19)
- Requires source-crs and schema.openapi to be copied alongside the templates (handled automatically by the role)
- Supports policy splitting via separate `policies:` entries controlled by `group_policy_logforwarder_name` and `group_policy_storage_name`

### PolicyGenTemplate (PGT) — Deprecated

PolicyGenTemplate uses `apiVersion: ran.openshift.io/v1` with `kind: PolicyGenTemplate`. Policy splitting is done per-manifest via a `policyName` field.

- Template directories: `pgt-du-4.22/` through `pgt-du-4.12/` (one per OCP minor version)
- Does not require source-crs to be copied

> [!WARNING]
> PolicyGenTemplate is deprecated and will be removed in a future ACM release. Use ACM PolicyGenerator for all new deployments.

## Repository and Bastion Layout

### Bastion Paths

The ZTP repository is cloned and managed at:

```
/root/rhacm-ztp/telco-reference/
```

The DU profile policy templates are placed under the ArgoCD base path within that repo:

```
/root/rhacm-ztp/telco-reference/telco-ran/configuration/argocd/
├── cluster-**/                        # ArgoCD cluster application directories
├── policy/
│   ├── common-ranGen.yaml             # Common policy (subscriptions, catalog sources)
│   ├── common-mno-ranGen.yaml         # Common MNO policy (worker MachineConfig)
│   ├── group-du-sno-ranGen.yaml       # SNO group policy
│   ├── group-du-sno-validator-ranGen.yaml
│   ├── group-du-3node-ranGen.yaml     # Compact (3-node) group policy
│   ├── group-du-3node-validator-ranGen.yaml
│   ├── group-du-standard-ranGen.yaml  # Standard group policy
│   ├── group-du-standard-validator-ranGen.yaml
│   ├── kustomization.yaml             # Kustomization with generator references
│   └── source-crs/                    # Source CRs (PG only)
└── sno-site.yaml                      # SNO site ArgoCD application
```

### Viewing in Gogs

The repository is pushed to the local Gogs git service. Access it at:

```
http://<gogs_host>:<gogs_port>/testadmin/telco-reference
```

The Gogs credentials default to `testadmin`/`testadmin`.

ArgoCD watches this Gogs repository and reconciles any changes pushed to it.

## Variables Reference

Variables are set in two places:
- **`ansible/vars/all.yml`** — Playbook-level variables (policy toggles, performance profile, disconnected registry)
- **`ansible/roles/telco-ran-du-ztp/defaults/main.yml`** — Role defaults (DU profile version, policy splitting, IBU, hub templating)

Role defaults can be overridden in `all.yml` or via `--extra-vars`.

### Role Toggles

These two variables in `ansible/vars/all.yml` control which ZTP roles the playbook executes:

| Variable | Default | Description |
| - | - | - |
| `setup_ran_du_ztp` | `false` | Enable the `telco-ran-du-ztp` role — generates RAN DU profile policies |
| `setup_core_ztp` | `false` | Enable the `telco-core-ztp` role — generates Telco Core policies |

### Policy Toggles

When `setup_ran_du_ztp` is enabled, these variables control which cluster type policies are generated:

| Variable | Default | Description |
| - | - | - |
| `setup_ztp_sno_policy` | `true` | Generate SNO DU profile policies |
| `setup_ztp_compact_policy` | `true` | Generate compact (3-node) DU profile policies |
| `setup_ztp_standard_policy` | `true` | Generate standard DU profile policies |
| `setup_ztp_common_policy` | `true` | Generate common policies (subscriptions, catalog sources) |
| `setup_ztp_sno_site_policy` | `false` | Generate SNO site-level policy |

### Repository Configuration

Set in `ansible/roles/rhacm-ztp-setup/defaults/main.yml` (shared with `telco-ran-du-ztp`):

| Variable | Default | Description |
| - | - | - |
| `ztp_repo_type` | `"telco-reference"` | Repository type. Use `"telco-reference"` for all current deployments |
| `telco_reference_repo` | `https://github.com/openshift-kni/telco-reference.git` | Upstream telco-reference repo URL |
| `telco_reference_branch` | `release-4.21` | Branch to clone from telco-reference |

> [!NOTE]
> The legacy `cnf-features-deploy` repository (`ztp_repo_type: "cnf-features-deploy"`) is still supported for OCP 4.19 and earlier but is no longer maintained. Its gitops-subscriptions were frozen at 4.19 and source-crs were removed at 4.21. Use `telco-reference` for all new work.

### DU Profile Selection

| Variable | Default | Description |
| - | - | - |
| `acm_policygenerator` | `true` | `true` = ACM PolicyGenerator (PG), `false` = deprecated PolicyGenTemplate (PGT) |
| `du_profile_version` | `4.22` | OCP version for DU profile templates. Supported: 4.22–4.12. PG consolidates versions (4.20+ → 4.20, 4.18–4.19 → 4.18); PGT uses the exact version |

### Policy Content Variables

| Variable | Default | Description |
| - | - | - |
| `rhacm_disconnected_registry` | _(empty)_ | Disconnected registry hostname. When set (length > 1), enables DefaultCatsrc, DisconnectedIDMS, and per-subscription catalog source overrides |
| `rhacm_disconnected_registry_port` | `5000` | Disconnected registry port |
| `disconnected_operator_index_name` | `redhat/redhat-operator-index` | Operator index image name in the disconnected registry |
| `operator_index_tag` | `v4.22` | Operator index image tag |
| `common_catalogsource_name` | `rh-du-operators` | Name for the DU profile CatalogSource (avoids conflicts with default catalog names) |
| `manyPolicies` | `false` | SNO only: organize CRs into 13–18 policies instead of the default 5 |

### Policy Splitting

These variables control whether ClusterLogForwarder and StorageLV are included in the main config policy or split into separate policies. This is supported for both PG and PGT SNO templates.

| Variable | Default | Description |
| - | - | - |
| `group_policy_logforwarder_name` | `"config-log-policy"` | Policy name for ClusterLogForwarder. Set to `"config-policy"` to include it in the main policy |
| `group_policy_storage_name` | `"config-storage-policy"` | Policy name for StorageLV. Set to `"config-policy"` to include it in the main policy |

When set to the defaults, the SNO DU profile produces three policies:
- `group-du-sno-latest-config-policy` — main configuration policy (without log forwarder and storage)
- `group-du-sno-latest-config-log-policy` — ClusterLogForwarder only
- `group-du-sno-latest-config-storage-policy` — StorageLV only

To keep everything in a single policy:

```yaml
group_policy_logforwarder_name: "config-policy"
group_policy_storage_name: "config-policy"
```

### Hub Side Templating

These variables add hub-side template annotations to policy manifests, useful for scale testing with per-cluster or per-group ConfigMap lookups.

| Variable | Default | Description |
| - | - | - |
| `extraHubCommonTemplates` | `false` | Add hub side templating annotations in common policy manifests (subscriptions, catalog sources) |
| `extraHubGroupTemplates` | `false` | Add hub side templating annotations in group policy manifests (SriovOperatorConfig, PtpConfigSlave, TunedPerformancePatch, etc.) |
| `extraHubSiteTemplates` | `false` | Add per-site hub side templating annotations from site-specific ConfigMaps |

### Performance Profile

Set in `ansible/vars/all.yml`:

| Variable | Default | Description |
| - | - | - |
| `setup_ztp_enable_performanceprofile` | `false` | Include PerformanceProfile and TunedPerformancePatch in group policies |
| `setup_ztp_perfprofile_isolated_cpus` | `"4-7"` | CPU set for isolated (workload) CPUs |
| `setup_ztp_perfprofile_reserved_cpus` | `"0-3"` | CPU set for reserved (platform) CPUs |
| `setup_ztp_perfprofile_hugepage_count` | `1` | Number of 1G hugepages |
| `setup_ztp_perfprofile_realtime` | `true` | Enable real-time kernel |

### Image Based Upgrade (IBU)

| Variable | Default | Description |
| - | - | - |
| `include_oadp_operator` | `false` | Install OADP operator on SNOs (required for IBU backups) |
| `oadp_s3Url` | `http://minio-minio.apps.bm.example.com` | S3-compatible backend URL for OADP |
| `s3_access_key_id` | `minio` | S3 access key |
| `s3_secret_access_key` | `minio123` | S3 secret key |
| `include_lca_operator` | `false` | Install Lifecycle Agent operator on SNOs (required for IBU) |
| `lifecycle_agent_channel` | `stable` | LCA subscription channel (`alpha` for 4.15, `stable` for 4.16+) |
| `ibu_source_crs_apiversion` | `v1` | IBU source CR API version (`v1alpha1` for alpha, `v1` for stable) |

### ArgoCD and Cluster Applications

| Variable | Default | Description |
| - | - | - |
| `cluster_applications_count` | `40` | Number of ArgoCD cluster application directories to pre-create |
| `siteconfigs_per_application` | `100` | Maximum number of siteconfigs per ArgoCD application |
| `siteconfigs_directories` | `["/root/hv-vm/sno/ai-siteconfig", "/root/hv-vm/compact/ai-siteconfig", "/root/hv-vm/standard/ai-siteconfig"]` | Local directories containing siteconfig YAML files to distribute |

### Extra Manifests

| Variable | Default | Description |
| - | - | - |
| `include_crun_extra_manifests` | `true` | Include crun container runtime MachineConfig with day-0 install |
| `include_synctimeonce_extra_manifests` | `false` | Include modified sync-time-once chronyd manifest (workaround for [OCPBUGS-21740](https://issues.redhat.com/browse/OCPBUGS-21740)) |
| `include_varlibcontainers_partitioned_extra_manifests` | `false` | Include /var/lib/containers partition manifest (required for IBU) |

### Gogs Configuration

Set in `ansible/roles/rhacm-ztp-setup/defaults/main.yml`:

| Variable | Default | Description |
| - | - | - |
| `gogs_host` | `"[fc00:1000::1]"` | Gogs service hostname or IP |
| `gogs_port` | `10880` | Gogs service port |
| `gogs_username` | `testadmin` | Gogs username for git push |
| `gogs_password` | `testadmin` | Gogs password for git push |

### ZTP Site Generator

Set in `ansible/roles/rhacm-ztp-setup/defaults/main.yml`:

| Variable | Default | Description |
| - | - | - |
| `ztp_site_generator_image_tag` | `"4.21"` | Container image tag for the ZTP site generator kustomize plugin |
| `rhacm_policy_generator_image_tag` | `v2.13.4-2` | Container image tag for the ACM PolicyGenerator kustomize plugin |

## Template Directory Structure

The Ansible role contains template directories for both PG and PGT across supported OCP versions:

```
ansible/roles/telco-ran-du-ztp/templates/
├── pg-common/                              # Shared Jinja2 includes for PG templates
│   ├── common-hub-annotations.j2           # Common policy hub annotations (standalone patch item)
│   ├── common-hub-annotations-10.j2        # Common policy hub annotations (10-space indent, no metadata)
│   ├── group-hub-annotations.j2            # Group policy hub annotations (standalone patch item)
│   ├── group-hub-annotations-10.j2         # Group policy hub annotations (10-space indent, no metadata)
│   └── group-hub-annotations-12.j2         # Group policy hub annotations (12-space indent, no metadata)
├── pg-du-4.20/                             # PG templates for OCP 4.20+
│   ├── acm-common-ranGen.yaml
│   ├── acm-common-mno-ranGen.yaml
│   ├── acm-group-du-sno-ranGen.yaml
│   ├── acm-group-du-sno-validator-ranGen.yaml
│   ├── acm-group-du-3node-ranGen.yaml
│   ├── acm-group-du-3node-validator-ranGen.yaml
│   ├── acm-group-du-standard-ranGen.yaml
│   └── acm-group-du-standard-validator-ranGen.yaml
├── pg-du-4.18/                             # PG templates for OCP 4.18–4.19
│   └── (same files as pg-du-4.20)
├── pgt-du-4.22/ through pgt-du-4.12/      # PGT templates (deprecated), one per OCP version
│   ├── common-ranGen.yaml
│   ├── common-mno-ranGen.yaml
│   ├── group-du-sno-ranGen.yaml
│   ├── group-du-sno-validator-ranGen.yaml
│   ├── group-du-3node-ranGen.yaml
│   ├── group-du-3node-validator-ranGen.yaml
│   ├── group-du-standard-ranGen.yaml
│   └── group-du-standard-validator-ranGen.yaml
└── source-crs/                             # Custom source CRs for IBU/OADP/LCA
```
