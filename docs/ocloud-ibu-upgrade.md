# O-Cloud Manager IBU Upgrade (ProvisioningRequest-driven)

This document covers upgrading O-Cloud-managed SNOs via the ProvisioningRequest (PR)
API, including the instrumented workflow used to capture detailed per-SNO Image Based
Upgrade (IBU) timing.

_**Table of Contents**_

<!-- TOC -->
- [ClusterTemplate revisions](#clustertemplate-revisions)
- [Normal upgrade (v2)](#normal-upgrade-v2)
- [Instrumented upgrade for timing (v3)](#instrumented-upgrade-for-timing-v3)
- [Finalize the IBU](#finalize-the-ibu)
<!-- /TOC -->

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

2. After the fleet reports `UpgradeCompleted`, collect each spoke's IBU object. It
   holds `status.history` with the `Prep` and `Upgrade` stages and their nested phases
   (`Stateroot`, `Precache`, `PrePivot`, `PostPivot`):

```console
mkdir -p /tmp/ibu-preserve
ls -d /root/hv-vm/kc/*/ | sed 's#.*/kc/##;s#/##' | xargs -P 16 -I{} sh -c \
 'oc --kubeconfig /root/hv-vm/kc/{}/kubeconfig get ibu upgrade -o json > /tmp/ibu-preserve/{}-ibu.json 2>/dev/null'
```

3. Finalize the IBU (next section), then analyze the collected data with
   `analyze-ocloud-imagebasedupgrades.py`.

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
 "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get ibu --no-headers" | awk '{print $2, $3}' | sort | uniq -c
```
