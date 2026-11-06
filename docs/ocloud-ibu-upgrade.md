# O-Cloud Manager IBU Upgrade (ProvisioningRequest-driven)

This document covers upgrading O-Cloud-managed SNOs via the ProvisioningRequest (PR)
API, including the instrumented workflow used to capture detailed per-SNO Image Based
Upgrade (IBU) timing.

_**Table of Contents**_

<!-- TOC -->
- [Test flow](#test-flow)
- [ClusterTemplate revisions](#clustertemplate-revisions)
- [Normal upgrade (v2)](#normal-upgrade-v2)
- [Instrumented upgrade for timing (v3)](#instrumented-upgrade-for-timing-v3)
- [Finalize the IBU](#finalize-the-ibu)
<!-- /TOC -->

## Test flow

A complete O-Cloud IBU upgrade test with timing analysis follows these steps:

1. **Install** — O-Cloud Manager provisions SNOs using the `v1` ClusterTemplate. Run
   `analyze-provisioningrequests.py` after the fleet reaches `fulfilled` to capture
   install timing.

2. **Patch PRs for upgrade** — Update each PR's `templateVersion` to the `v3`
   ClusterTemplate (or `v2` for a normal upgrade) and record the patch time in the
   `ibu-patch-time` annotation (see [Instrumented upgrade for timing (v3)](#instrumented-upgrade-for-timing-v3)).

3. **Wait for completion** — O-Cloud Manager drives Prep → Upgrade per cluster. Monitor
   the fleet until all PRs report `UpgradeCompleted`.

4. **Analyze** — Run both analysis scripts for the most complete picture:

   `analyze-provisioningrequests.py` captures hub-side upgrade duration (patch time →
   `UpgradeCompleted`) and fleet totals:

   ```bash
   export KUBECONFIG=/root/mno/kubeconfig
   ./acm-deploy-load/analyze-provisioningrequests.py <results_directory>
   ```

   `analyze-ocloud-ibu.py` fetches per-SNO IBU objects from the spokes and produces
   per-stage timing stats (Prep/Stateroot/Precache, Upgrade/PrePivot/PostPivot,
   and totals):

   ```bash
   export KUBECONFIG=/root/mno/kubeconfig
   ./acm-deploy-load/analyze-ocloud-ibu.py <ocp_version> <results_directory>
   ```

5. **Finalize** — If a follow-on IBU is needed on the same clusters, finalize each
   spoke IBU to return it to `Idle` before the next upgrade cycle (see
   [Finalize the IBU](#finalize-the-ibu)).

## ClusterTemplate revisions

The `ocloud-ztp-templates` role generates these ClusterTemplate revisions per OCP
version (both `ai` and `ibi` types). A PR selects one through its
`spec.templateVersion`, formatted `<version>-<type>-<revision>` (e.g.
`v4-22-3-ibi-v2`):

| Revision | Plan | Use |
| - | - | - |
| `v1` | install (no `upgradeDefaults`) | Day-1 install |
| `v2` | Prep + AbortOnFailure + Upgrade + AbortOnFailure + FinalizeUpgrade | Normal single-shot upgrade |
| `v3` | Prep + Upgrade | Instrumented upgrade: stops before finalize and omits `AbortOnFailure`, so each spoke's IBU `status.history` survives for analysis |

A v3 instrumented upgrade leaves each spoke IBU in the `Upgrade` (completed) state
rather than finalizing it. Finalize it manually before running any follow-on IBU on
the same SNO (see [Finalize the IBU](#finalize-the-ibu)).

The plan is phase-driven in `clustertemplate.yaml.j2` solely via `item.upgrade_phase`
(`full` for v2, `upgrade` for v3; absent for v1).

## Normal upgrade (v2)

Patch each PR's `templateVersion` to the `v2` revision for the target release, recording
the per-PR patch time in the `ibu-patch-time` annotation (read by
`analyze-provisioningrequests.py` for the upgrade duration):

```console
oc get pr --no-headers | sort -k 2 | awk '{print $1}' | xargs -I{} bash -c \
 'TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); oc patch provisioningrequests {} --type merge \
  -p "{\"spec\":{\"templateName\":\"sno-ran-du\",\"templateVersion\":\"v4-22-3-ibi-v2\"},\"metadata\":{\"annotations\":{\"ibu-patch-time\":\"$TS\"}}}"'
```

O-Cloud drives Prep → Upgrade → FinalizeUpgrade; each spoke IBU returns to `Idle`
when complete.

## Instrumented upgrade for timing (v3)

Use `v3` to measure per-SNO Prep/Upgrade timing. `FinalizeUpgrade` returns the IBU to
`Idle` and **wipes `status.history`**, so you must collect the IBU data *before*
finalizing.

1. Trigger the upgrade and record the per-PR patch time in the `ibu-patch-time`
   annotation:

```console
oc get pr --no-headers | sort -k 2 | awk '{print $1}' | xargs -I{} bash -c \
 'TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); oc patch provisioningrequests {} --type merge \
  -p "{\"spec\":{\"templateName\":\"sno-ran-du\",\"templateVersion\":\"v4-22-3-ibi-v3\"},\"metadata\":{\"annotations\":{\"ibu-patch-time\":\"$TS\"}}}"'
```

2. After the fleet reports `UpgradeCompleted`, run `analyze-ocloud-ibu.py` to fetch
   each spoke's IBU object and produce per-cluster timing stats. The script queries
   `status.history` for `Prep` and `Upgrade` stages and their nested phases
   (`Stateroot`, `Precache`, `PrePivot`, `PostPivot`):

```bash
export KUBECONFIG=/root/mno/kubeconfig
./acm-deploy-load/analyze-ocloud-ibu.py <ocp_version> <results_directory>
```

3. Finalize the IBU (next section) before running any follow-on IBU on the same SNOs.

## Finalize the IBU

A v3 instrumented upgrade leaves each spoke IBU in the `Upgrade` (completed) state. An
IBU must be finalized (returned to `Idle`) before another IBU can run on that SNO, so
close it out once you have collected the timing data, or whenever you need to run a
follow-on IBU. Set each spoke IBU's stage to `Idle` directly (the LCA-native finalize;
an already-`Idle` IBU is a harmless no-op):

```console
ls /root/hv-vm/kc/ | xargs -P 16 -I% sh -c \
 'oc --kubeconfig /root/hv-vm/kc/%/kubeconfig patch ibu upgrade --type merge \
  -p "{\"spec\":{\"stage\":\"Idle\"}}" 2>/dev/null'
```

Verify the fleet finalized (expect all `Idle`):

```console
ls /root/hv-vm/kc/ | xargs -I% sh -c \
 "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get ibu --no-headers" | awk '{print $3, $4}' | sort | uniq -c
```
