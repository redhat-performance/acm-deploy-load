# ocloud-deploy-load.py

Phased orchestrator for O-Cloud (oran-o2ims) workloads: BMH inspection via
GitOps, SNO install via ProvisioningRequests, and IBU upgrade via `oc patch`.
Produces `report.txt`, `versions.json`, `monitor_data.csv`, and per-phase
Prometheus analysis.

## Prerequisites

**Hub cluster**

- ACM and O-Cloud Manager (oran-o2ims) installed on the hub
- GitOps repo containing ClusterTemplates, ProvisioningRequest manifests, and
  the resource pool `kustomization.yaml` (see `--argocd-directory`)
- ProvisioningRequest manifests generated and placed at
  `--provisioningrequest-manifests`

**Seed images**

Two seed images are required for IBI-based testing:

1. An install seed image (e.g. 4.22.0) used to pre-stage each target SNO's
   disk ahead of the test run.
2. An upgrade seed image (e.g. 4.22.3) used as the IBU upgrade target.

**GitOps / ClusterTemplate setup**

When testing IBU upgrade, two ClusterTemplates must be deployed on the hub —
one for installation and one for upgrade. Run both setup playbooks:

```bash
ansible-playbook ansible/rhacm-ztp-setup.yml       # install ClusterTemplate
ansible-playbook ansible/ocloud-ztp-ibu-setup.yml  # upgrade ClusterTemplate
```

## Phase Model

| # | Phase | Action | Done when |
|---|---|---|---|
| 1 | Idle Baseline | sleep `--start-delay` | elapsed |
| 2 | Inspection | uncomment BMH entries in `resourcepool-lab` `kustomization.yaml`, git push | `bmh_inspect_complete + bmh_inspect_failed >= committed` or `--inspect-timeout` |
| 3 | Install | `oc apply -f` PR manifests | `pr_fulfilled + pr_failed >= applied` or `--install-timeout` |
| 4 | Upgrade | `oc patch provisioningrequests` with new `templateVersion` | `pr_upgraded + pr_upgrade_failed >= patched` or `--upgrade-timeout` |
| 5 | Soak Baseline | sleep `--end-delay` | elapsed |

Skip any phase with `--skip-inspection`, `--skip-install`, or `--skip-upgrade`.

## Arguments

| Flag | Default | Description |
|---|---|---|
| `-k/--kubeconfig` | `/root/mno/kubeconfig` | Hub cluster kubeconfig |
| `-m/--method` | `ibi` | Install method: `ai` or `ibi` |
| `--provisioningrequest-manifests` | `/root/hv-vm/sno/ocloud-{method}-provisioningrequest/` | Directory with `*-provisioningrequest.yml` files |
| `--argocd-directory` | `/root/rhacm-ztp/telco-reference/telco-ran/configuration/argocd` | ArgoCD git repository root |
| `--resourcepool-name` | `resourcepool-lab` | Resource pool name (determines kustomization.yaml gate file path) |
| `--inspect-batch` | `100` | Hosts to uncomment per inspection batch |
| `--inspect-interval` | `60` | Seconds between inspection batches (0=back-to-back) |
| `--inspect-timeout` | `1800` | Max seconds to wait for inspection (0=infinite) |
| `--install-batch` | `100` | PRs to apply per install batch |
| `--install-interval` | `60` | Seconds between install batches (0=back-to-back) |
| `--install-timeout` | `1800` | Max seconds to wait for install (0=infinite) |
| `--upgrade-batch` | `100` | PRs to patch per upgrade batch |
| `--upgrade-interval` | `60` | Seconds between upgrade batches (0=back-to-back) |
| `--upgrade-timeout` | `1800` | Max seconds to wait for upgrade (0=infinite) |
| `-n/--no-shuffle` | `false` | Do not shuffle host/PR list |
| `--upgrade-ocp-version` | `""` | Target OCP version for IBU (required unless `--skip-upgrade`) |
| `--upgrade-revision` | `v3` | ClusterTemplate revision (`v3`=Prep+Upgrade only) |
| `--clustertemplate-name` | `sno-ran-du` | ClusterTemplate name |
| `--skip-inspection` | `false` | Skip phase 2 |
| `--skip-install` | `false` | Skip phase 3 |
| `--skip-upgrade` | `false` | Skip phase 4 |
| `--start-delay` | `0` | Phase 1 idle baseline duration (seconds) |
| `--end-delay` | `0` | Phase 5 soak baseline duration (seconds) |
| `-i/--monitor-interval` | `60` | Monitor thread sampling interval (seconds) |
| `--no-prometheus-analysis` | `false` | Skip per-phase Prometheus analysis |
| `-t/--results-dir-suffix` | `test-00` | Suffix appended to results directory name |
| `--test-version` | `""` | Test version label for the report card |
| `-d/--debug` | `false` | Enable debug logging |
| `--dry-run` | `false` | Echo commands without executing them |

## Running the Test

Edit the configuration variables at the top of the orchestration script, then run it:

```bash
# Edit method, batch sizes, timeouts, upgrade version, etc.
vi scripts/ocloud-ztp-inspect-install-upgrade-all.sh

./scripts/ocloud-ztp-inspect-install-upgrade-all.sh
```

The script runs `ocloud-deploy-load.py`, collects post-test hub and spoke data,
runs resource analyzers, and (if upgrade ran) runs `analyze-ocloud-ibu.py`.
Results and logs are saved to `results/{ts}-ocloud-{method}-{suffix}/`.

## templateVersion Format

The upgrade templateVersion is built from `v{ocp_version_dashes}-{method}-{revision}`.

Examples:
- `v4-22-3-ibi-v3` — IBI (Image-based Install), Prep+Upgrade only (recommended; leaves IBU history intact)
- `v4-22-3-ai-v2` — AI (Assisted Installer), full Prep+Upgrade+Finalize flow
