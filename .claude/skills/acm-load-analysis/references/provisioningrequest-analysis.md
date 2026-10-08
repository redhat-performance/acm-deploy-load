# ProvisioningRequest Analysis Reference

## Output Files

- `provisioningrequests-{TS}.json` — raw `oc get` output
- `provisioningrequests-{TS}.csv` — per-PR row with timestamps + durations
- `provisioningrequests-{TS}.stats` — percentile summary (5 blocks)

## CSV Columns (23 total)

Identification: `name`, `cluster_name`, `status`, `creationTimestamp`

Condition timestamps (9):
`ProvisioningRequestValidated.lastTransitionTime`,
`ClusterInstanceRendered.lastTransitionTime`,
`ClusterResourcesCreated.lastTransitionTime`,
`NodeAllocationRequestRendered.lastTransitionTime`,
`HardwareProvisioned.lastTransitionTime`,
`HardwareNodeConfigApplied.lastTransitionTime`,
`ClusterInstanceProcessed.lastTransitionTime`,
`ClusterProvisioned.lastTransitionTime`,
`ConfigurationApplied.lastTransitionTime`

Duration columns (10, in seconds):
`pr_ct_prv_duration`, `pr_prv_cir_duration`, `pr_cir_crc_duration`,
`pr_crc_nar_duration`, `pr_nar_hp_duration`, `pr_hp_hnca_duration`,
`pr_hnca_cip_duration`, `pr_cip_cp_duration`, `pr_cp_ca_duration`,
`total_duration`

## Stats Blocks

Fleet Provisioning Summary header (earliest creation, latest fulfilled, fleet duration, counts),
followed by 5 per-cluster stats blocks:

1. `Total Duration Stats on ProvisioningRequests in fulfilled`
2. `O-Cloud Preprocessing Stats (creationTimestamp to ClusterInstanceProcessed) on fulfilled ProvisioningRequests`
3. `Hardware Provisioning Stats (NodeAllocationRequestRendered to HardwareProvisioned) on fulfilled ProvisioningRequests`
4. `Cluster Provisioning Stats (ClusterInstanceProcessed to ClusterProvisioned) on fulfilled ProvisioningRequests`
5. `Configuration Applied Stats (ClusterProvisioned to ConfigurationApplied) on fulfilled ProvisioningRequests`

## Success Criteria

- `status.provisioningStatus.provisioningPhase == "fulfilled"` — successfully completed
- Other values: `progressing`, `failed`, `unknown`
- Only `fulfilled` PRs with duration > 0 contribute to stats
