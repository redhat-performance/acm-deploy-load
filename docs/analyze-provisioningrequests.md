# Analyzing ProvisioningRequest Results

This guide covers interpreting the output of `analyze-provisioningrequests.py`, which extracts timing data from O-Cloud Manager `ProvisioningRequest` custom resources (`clcm.openshift.io/v1alpha1`). The script produces a detailed per-cluster CSV with every measurable step-to-step interval, a stats file summarizing the most operationally significant durations, and a raw JSON snapshot for offline re-analysis.

_**Table of Contents**_

<!-- TOC -->
- [Overview](#overview)
- [Running the Script](#running-the-script)
- [ProvisioningRequest Condition Timeline](#provisioningrequest-condition-timeline)
- [CSV Output Reference](#csv-output-reference)
  - [Identification and Status Columns](#identification-and-status-columns)
  - [Condition Timestamp Columns](#condition-timestamp-columns)
  - [Duration Columns](#duration-columns)
- [Stats Output Reference](#stats-output-reference)
- [Interpreting Failures](#interpreting-failures)
<!-- /TOC -->

## Overview

When O-Cloud Manager processes a `ProvisioningRequest`, it progresses through 9 condition stages — from request validation through hardware provisioning, cluster installation, and day-2 configuration. Each condition records a `lastTransitionTime` when it completes, creating a timeline that reveals exactly where time is spent.

The analysis script captures all 9 condition timestamps and computes 9 step-to-step interval durations plus a total duration. The **CSV** exposes every measured interval for detailed analysis. The **stats file** summarizes the 5 most operationally significant durations as percentile breakdowns.

## Running the Script

**Online** (queries live cluster):

```bash
export KUBECONFIG=/root/mno/kubeconfig
./acm-deploy-load/analyze-provisioningrequests.py <results_directory>
```

Ensure `KUBECONFIG` is set to the hub cluster's kubeconfig before running. This runs `oc get provisioningrequests.clcm.openshift.io -o json`, saves the raw JSON to `<results_directory>/provisioningrequests-<timestamp>.json`, then produces the CSV and stats files.

**Offline** (re-analyze previously captured data):

```bash
# Auto-detect the last JSON file in the results directory
./acm-deploy-load/analyze-provisioningrequests.py -o <results_directory>

# Use a specific JSON file
./acm-deploy-load/analyze-provisioningrequests.py -o -r <path/to/provisioningrequests.json> <results_directory>
```

Offline mode is useful for re-analyzing data after script updates or when debugging failures against saved snapshots.

## ProvisioningRequest Condition Timeline

The 9 conditions progress in this order:

| # | Condition | Description |
|---|---|---|
| 1 | `ProvisioningRequestValidated` | Template and parameter validation passed |
| 2 | `ClusterInstanceRendered` | ClusterInstance CR rendered from template and passed dry-run validation |
| 3 | `ClusterResourcesCreated` | Cluster resources (namespace, secrets, etc.) applied to the hub |
| 4 | `NodeAllocationRequestRendered` | Node allocation request built for the hardware manager |
| 5 | `HardwareProvisioned` | Hardware provisioning completed (BMC boot, firmware config on bare metal) |
| 6 | `HardwareNodeConfigApplied` | Node configuration applied to the rendered ClusterInstance |
| 7 | `ClusterInstanceProcessed` | ClusterInstance applied and processed — cluster install begins |
| 8 | `ClusterProvisioned` | OpenShift cluster installation completed |
| 9 | `ConfigurationApplied` | Day-2 configuration policies are compliant (ZTP Done) |

## CSV Output Reference

The CSV contains one row per ProvisioningRequest with 23 columns. Every step-to-step interval is included, making it the primary artifact for detailed timing analysis.

### Identification and Status Columns

| Column | Description |
|---|---|
| `name` | ProvisioningRequest metadata.name (UUID) |
| `cluster_name` | Cluster name from status.extensions.clusterDetails.name |
| `status` | Provisioning phase: `fulfilled`, `progressing`, `failed`, or `unknown` |
| `creationTimestamp` | When the ProvisioningRequest was created |

### Condition Timestamp Columns

9 columns, one per condition, containing the `lastTransitionTime` when the condition became `True`. Empty if the condition has not completed successfully.

| Column |
|---|
| `ProvisioningRequestValidated.lastTransitionTime` |
| `ClusterInstanceRendered.lastTransitionTime` |
| `ClusterResourcesCreated.lastTransitionTime` |
| `NodeAllocationRequestRendered.lastTransitionTime` |
| `HardwareProvisioned.lastTransitionTime` |
| `HardwareNodeConfigApplied.lastTransitionTime` |
| `ClusterInstanceProcessed.lastTransitionTime` |
| `ClusterProvisioned.lastTransitionTime` |
| `ConfigurationApplied.lastTransitionTime` |

### Duration Columns

10 columns measuring time in seconds between consecutive conditions. These are the step-to-step intervals that reveal where time is spent.

| Column | Interval | What It Measures |
|---|---|---|
| `pr_ct_prv_duration` | creationTimestamp → ProvisioningRequestValidated | Request validation |
| `pr_prv_cir_duration` | ProvisioningRequestValidated → ClusterInstanceRendered | ClusterInstance rendering |
| `pr_cir_crc_duration` | ClusterInstanceRendered → ClusterResourcesCreated | Hub resource creation |
| `pr_crc_nar_duration` | ClusterResourcesCreated → NodeAllocationRequestRendered | Node allocation request setup |
| `pr_nar_hp_duration` | NodeAllocationRequestRendered → HardwareProvisioned | Hardware provisioning |
| `pr_hp_hnca_duration` | HardwareProvisioned → HardwareNodeConfigApplied | Node configuration |
| `pr_hnca_cip_duration` | HardwareNodeConfigApplied → ClusterInstanceProcessed | ClusterInstance processing |
| `pr_cip_cp_duration` | ClusterInstanceProcessed → ClusterProvisioned | OpenShift cluster installation |
| `pr_cp_ca_duration` | ClusterProvisioned → ConfigurationApplied | Day-2 policy configuration |
| `total_duration` | creationTimestamp → ConfigurationApplied | End-to-end provisioning |

A duration of `0` means either the interval was instantaneous or one of the required condition timestamps is missing (see [Interpreting Failures](#interpreting-failures)).

## Stats Output Reference

The stats file begins with a **Fleet Provisioning Summary** showing the earliest `creationTimestamp` across all ProvisioningRequests, the latest `ConfigurationApplied` timestamp among fulfilled PRs, and the wall-clock duration between them. This captures how long the entire fleet took to provision end-to-end.

Following the fleet summary are 5 per-cluster duration categories as percentile breakdowns. These are a curated subset of the 10 CSV duration columns, chosen for their operational significance. Only successfully fulfilled ProvisioningRequests with duration > 0 contribute to the stats.

| Stats Block | CSV Duration Source | What It Captures |
|---|---|---|
| Total Duration | `total_duration` | End-to-end provisioning time |
| O-Cloud Preprocessing | creationTimestamp → ClusterInstanceProcessed | Everything before cluster install begins |
| Hardware Provisioning | `pr_nar_hp_duration` | Time to provision hardware (BMC operations) |
| Cluster Provisioning | `pr_cip_cp_duration` | OpenShift cluster installation time |
| Configuration Applied | `pr_cp_ca_duration` | Day-2 policy compliance time |

Each block contains: Count, Min, Average, 50 percentile, 95 percentile, 99 percentile, Max.

**Why the CSV has more columns than the stats file:** The CSV preserves all 9 step-to-step intervals because some are only meaningful in specific environments or for debugging specific issues. The stats file focuses on the 5 durations that are consistently useful for capacity planning and performance regression detection. For detailed step-level analysis (e.g., investigating why `pr_prv_cir_duration` spiked for a subset of clusters), use the CSV directly.

## Interpreting Failures

ProvisioningRequests that have not reached `fulfilled` status still appear in the CSV with partial data:

- **Status column** shows the current phase (e.g., `progressing`, `failed`)
- **Condition timestamps** are populated for conditions that completed successfully (`status: "True"`)
- **Duration columns** for intervals involving incomplete conditions are `0`
- **`total_duration`** is `0` (requires `ConfigurationApplied` to be True)

Example: A cluster where `ClusterProvisioned` succeeded but `ConfigurationApplied` did not (policy timeout) will show:
- All timestamps through `ClusterProvisioned` populated
- `ConfigurationApplied.lastTransitionTime` empty
- `pr_cp_ca_duration` = 0, `total_duration` = 0
- All earlier interval durations (e.g., `pr_cip_cp_duration`) populated normally

These partial rows are excluded from the stats file percentile calculations. Use the CSV to investigate failures — the populated intervals show how far the provisioning progressed and where it stalled.
