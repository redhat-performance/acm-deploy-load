# Analyzing BareMetalHost Results

This guide covers interpreting the output of `analyze-baremetalhosts.py`, which extracts timing data from Metal3 `BareMetalHost` custom resources (`metal3.io/v1alpha1`). The script auto-detects the deployment scenario for each BMH — inspect-only, IBI (Image-Based Install), or AI (Assisted Install) — and produces a per-BMH CSV with all available timestamps and durations, a stats file with scenario-aware percentile breakdowns, and a raw JSON snapshot for offline re-analysis.

_**Table of Contents**_

<!-- TOC -->
- [Overview](#overview)
- [Running the Script](#running-the-script)
- [Scenario Detection](#scenario-detection)
- [BareMetalHost Lifecycle Timeline](#baremetalhost-lifecycle-timeline)
- [CSV Output Reference](#csv-output-reference)
  - [Identification Columns](#identification-columns)
  - [Timestamp Columns](#timestamp-columns)
  - [Duration Columns](#duration-columns)
- [Stats Output Reference](#stats-output-reference)
- [Interpreting Failures](#interpreting-failures)
<!-- /TOC -->

## Overview

When a BareMetalHost is created on a hub cluster, it progresses through registration, inspection, and (optionally) provisioning. The `status.operationHistory` field records `start`/`end` timestamps for each operation, while `status.conditions` track state transitions with `lastTransitionTime` values.

The analysis script captures all operation history timestamps, all 6 condition timestamps, and computes durations for each lifecycle phase. Because BMHs serve different purposes depending on the deployment method, the script auto-detects the scenario per BMH and adapts its total duration calculation accordingly.

## Running the Script

**Online** (queries live cluster):

```bash
export KUBECONFIG=/root/mno/kubeconfig
./acm-deploy-load/analyze-baremetalhosts.py <results_directory>
```

Ensure `KUBECONFIG` is set to the hub cluster's kubeconfig before running. This runs `oc get baremetalhosts -A -o json`, saves the raw JSON to `<results_directory>/baremetalhosts-<timestamp>.json`, then produces the CSV and stats files.

**Offline** (re-analyze previously captured data):

```bash
# Auto-detect the last JSON file in the results directory
./acm-deploy-load/analyze-baremetalhosts.py -o <results_directory>

# Use a specific JSON file
./acm-deploy-load/analyze-baremetalhosts.py -o -r <path/to/baremetalhosts.json> <results_directory>
```

**Namespace filtering:**

By default, BMHs in the `openshift-machine-api` namespace (hub cluster nodes) are excluded. Override with `--skip-namespaces`:

```bash
# Skip multiple namespaces
./acm-deploy-load/analyze-baremetalhosts.py -s "openshift-machine-api,other-ns" <results_directory>

# Skip no namespaces (process everything)
./acm-deploy-load/analyze-baremetalhosts.py -s "" <results_directory>
```

## Scenario Detection

Each BMH is classified into one of three scenarios based on its current state:

| Scenario | Detection Criteria | What It Represents |
|---|---|---|
| `inspect` | `operationHistory.provision.start` is null, `spec.externallyProvisioned` absent/false | BMH registered and inspected only (O-Cloud inventory) |
| `ibi` | `spec.externallyProvisioned: true` | Image-Based Install — provisioning managed externally |
| `ai` | `operationHistory.provision.start` is not null | Assisted Install — BMO-managed provisioning |

The `provisioning.state` field reflects the terminal state: `available` (inspect), `externally provisioned` (IBI), or `provisioned` (AI).

Mixed captures (e.g., some BMHs inspected, others provisioned) are handled naturally — each BMH is classified independently.

## BareMetalHost Lifecycle Timeline

All BMHs share registration and inspection phases. Provisioning differs by scenario:

**Common phases (all scenarios):**

| Phase | Timing Source |
|---|---|
| Registration | `operationHistory.register.start` → `register.end` |
| Inspection | `operationHistory.inspect.start` → `inspect.end` |

**AI provisioning (Assisted Install):**

| Phase | Timing Source |
|---|---|
| Provisioning | `operationHistory.provision.start` → `provision.end` |

**IBI provisioning (Image-Based Install):**

IBI sets `spec.externallyProvisioned: true` so BMO does not track the provision operation in `operationHistory`. Instead, the `Provisioned` condition `lastTransitionTime` marks when provisioning completed.

## CSV Output Reference

The CSV contains one row per BMH with 28 columns.

### Identification Columns

| Column | Description |
|---|---|
| `namespace` | BMH namespace (cluster name for non-O-Cloud, shared pool for O-Cloud) |
| `name` | BMH metadata.name |
| `scenario` | Auto-detected: `inspect`, `ibi`, or `ai` |
| `provisioning_state` | Raw value from `status.provisioning.state` |

### Timestamp Columns

**Operation history timestamps** (empty if null/not applicable):

| Column | Description |
|---|---|
| `creationTimestamp` | When the BMH object was created |
| `register_start`, `register_end` | Registration operation window |
| `inspect_start`, `inspect_end` | Inspection operation window |
| `provision_start`, `provision_end` | Provisioning operation window (AI only) |
| `deprovision_start`, `deprovision_end` | Deprovisioning operation window (future use) |
| `lastUpdated` | Last status update time |

**Condition lastTransitionTime columns** (raw RFC3339 values):

| Column |
|---|
| `Ready_ltt` |
| `AvailableForProvisioning_ltt` |
| `Healthy_ltt` |
| `Manageable_ltt` |
| `Progressing_ltt` |
| `Provisioned_ltt` |

### Duration Columns

8 columns measuring time in seconds. A value of `0` means the interval is not applicable for the scenario or a required timestamp is missing.

| Column | Interval | Applicable Scenarios |
|---|---|---|
| `register_duration` | register.end − register.start | All |
| `inspect_duration` | inspect.end − inspect.start | All |
| `provision_duration` | provision.end − provision.start | AI only |
| `deprovision_duration` | deprovision.end − deprovision.start | Future use |
| `ct_register_start` | register.start − creationTimestamp | All |
| `register_inspect_gap` | inspect.start − register.end | All |
| `inspect_provision_gap` | provision.start − inspect.end | AI only |
| `total_duration` | Varies by scenario (see below) | All |

**Total duration calculation per scenario:**

| Scenario | Total Duration |
|---|---|
| `inspect` | inspect.end − creationTimestamp |
| `ai` | provision.end − creationTimestamp |
| `ibi` | Provisioned condition lastTransitionTime − creationTimestamp |

## Stats Output Reference

The stats file begins with a **Fleet BareMetalHost Summary** showing the earliest `creationTimestamp`, latest completion timestamp, wall-clock fleet duration, total count, skipped count, and per-scenario breakdown.

Following the fleet summary are percentile breakdowns. The first 3 blocks always appear; scenario-specific blocks appear only when BMHs of that scenario exist in the data.

| Stats Block | What It Captures | When It Appears |
|---|---|---|
| Registration Duration | Time for BMO to register the BMH with the BMC | Always |
| Inspection Duration | Time for hardware inspection | Always |
| Creation to Inspected | End-to-end time from BMH creation to inspection complete | Always |
| Provisioning Duration (AI) | BMO-managed provisioning time | AI BMHs present |
| Total Duration (AI) | Creation to provision complete | AI BMHs present |
| Total Duration (IBI) | Creation to Provisioned condition | IBI BMHs present |

Each block contains: Count, Min, Average, 50 percentile, 95 percentile, 99 percentile, Max.

Registration, Inspection, and Creation to Inspected stats include any BMH with a positive duration for that interval, regardless of terminal state — so in-progress hosts contribute their completed phases. AI and IBI stats blocks only include BMHs that reached their expected terminal `provisioning.state` with duration > 0, and the blocks are omitted entirely if no qualifying BMHs exist.

## Interpreting Failures

BMHs that have not reached their expected terminal state still appear in the CSV with partial data:

- **`provisioning_state`** shows the current state (e.g., `registering`, `inspecting`, `preparing`)
- **Operation history timestamps** are populated for completed operations
- **Duration columns** for incomplete operations are `0`
- **`total_duration`** is `0` unless the BMH reached its expected terminal state

Use the CSV to investigate failures — populated timestamps and durations show how far the BMH progressed and where it stalled. The condition `lastTransitionTime` columns can provide additional context about state changes.
