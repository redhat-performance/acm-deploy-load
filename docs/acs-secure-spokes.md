# ACS Secure Spokes Setup and Cleanup

This document describes how to use the ACS (Advanced Cluster Security) playbooks to register managed clusters with ACS Central, deploy sensors, and perform cleanup.

## Overview

Two main playbooks are available:

1. **`ansible/acs-secure-spokes.yml`** — Register clusters with ACS Central and deploy sensors
2. **`ansible/acs-spokes-sensor-cleanup.yml`** — Delete sensors and unregister clusters from ACS Central

## Prerequisites

- Deployed ACM hub cluster with managed clusters in the inventory
- ACS Central deployed and accessible
- `roxctl` CLI installed and in PATH
- Environment variables set:
  - `ROX_API_TOKEN` — API token for ACS Central authentication
  - `ROX_CENTRAL_ADDRESS` — ACS Central URL (e.g., `https://central-rhacs-operator.apps.example.com`)
    - Can be obtained with: `https://$(oc get route central -n rhacs-operator -o jsonpath='{.spec.host}')`
  - `RH_REGISTRY_IO_USERNAME` — Red Hat registry username (for pulling ACS images)
  - `RH_REGISTRY_IO_PASSWORD` — Red Hat registry password
- **Ansible inventory with `managed_clusters` group**: You must add a `managed_clusters` group to your Ansible inventory containing the names of the managed cluster instances. Example:
  ```ini
  [managed_clusters]
  standard-00001
  standard-00002
  standard-00003
  ```
- Kubeconfig secrets on the hub cluster at `<namespace>/<namespace>-admin-kubeconfig`
   - these are usually created by the ACM cluster instance manifests

## ACS Secure Spokes Registration

### Playbook: `ansible/acs-secure-spokes.yml`

This playbook performs the following operations on all managed clusters:

1. **Refresh Vulnerability Definitions** (optional, tagged `refresh-vulns`)
   - Downloads latest vulnerability database from ACS Central
   - Uploads to ACS Central

2. **Register Spokes with ACS Central** (main operation)
   - Generates a Cluster Registration Secret (CRS) if needed
   - Caches CRS across spoke namespaces on the hub
   - Detects mismatches and regenerates if necessary
   - For each spoke:
     - Creates `stackrox` namespace
     - Creates docker registry secrets for pulling ACS images
     - Applies CRS to register with Central

3. **Deploy Sensors** (main operation)
   - Generates sensor deployment scripts for each cluster
   - Deploys sensors to spokes
   - Preserves sensor generation directories for later cleanup

### Usage

#### Basic Setup (Register and Deploy Sensors)

```bash
export ROX_API_TOKEN="<your-api-token>"
export ROX_CENTRAL_ADDRESS="https://$(oc get route central -n rhacs-operator -o jsonpath='{.spec.host}')"
export RH_REGISTRY_IO_USERNAME="<your-username>"
export RH_REGISTRY_IO_PASSWORD="<your-password>"

time ansible-playbook -i ansible/inventory/cloud30.local ansible/acs-secure-spokes.yml
```

#### Refresh Vulnerability Definitions Only

```bash
export ROX_API_TOKEN="<your-api-token>"
export ROX_CENTRAL_ADDRESS="https://$(oc get route central -n rhacs-operator -o jsonpath='{.spec.host}')"

time ansible-playbook -i ansible/inventory/cloud30.local ansible/acs-secure-spokes.yml --tags refresh-vulns
```

#### Force Sensor Regeneration and Redeployment

Useful if sensors need to be updated after cluster changes:

```bash
export ROX_API_TOKEN="<your-api-token>"
export ROX_CENTRAL_ADDRESS="https://$(oc get route central -n rhacs-operator -o jsonpath='{.spec.host}')"
export RH_REGISTRY_IO_USERNAME="<your-username>"
export RH_REGISTRY_IO_PASSWORD="<your-password>"

time ansible-playbook -i ansible/inventory/cloud30.local ansible/acs-secure-spokes.yml -e force_sensor_regeneration=true
```

### Playbook Roles

#### `refresh-vulnerabilities-definition`
- **Default**: Disabled (tagged `refresh-vulns`)
- Generates new vulnerability database from Central
- Updates all spoke namespaces with new CRS if regenerated
- Cleans up temporary work directory

#### `acs-spokes-registration`
- Validates required environment variables
- Manages CRS as secrets in spoke namespaces
- Detects and handles mismatches
- Creates stackrox namespace and docker secrets on each spoke
- Applies CRS to register spoke with Central
- Idempotent: skips if already registered

#### `acs-spokes-sensor-setup`
- Generates sensor deployment scripts per cluster
- Deploys sensors to spokes
- Preserves sensor generation directories in `/root/secured_clusters/`
- Skips clusters already registered in Central (unless `force_sensor_regeneration=true`)
- Prints per-cluster setup summary

### Output

The playbook produces a summary showing:
- Total clusters processed
- Successfully configured count
- Per-cluster timestamp

Example:
```
TASK [acs-spokes-sensor-setup : Display sensor setup summary footer]
ok: [localhost] => {
    "msg": "============================================\nTotal clusters processed: 5\nSuccessfully configured: 5\n============================================"
}
```

## ACS Secure Spokes Cleanup

### Playbook: `ansible/acs-spokes-sensor-cleanup.yml`

This playbook performs cleanup on all managed clusters:

1. **Delete Sensors** (tagged `sensor-cleanup`)
   - Checks for `delete-sensor.sh` in sensor generation directories
   - Runs the delete script on each spoke
   - Optionally removes sensor generation directories

2. **Unregister Spokes from Central** (tagged `unregister`)
   - Runs `roxctl cluster delete` for each cluster
   - Handles already-deleted clusters gracefully

### Usage

#### Delete Sensors Only (Keep Generation Directories)

```bash
time ansible-playbook -i ansible/inventory/cloud30.local ansible/acs-spokes-sensor-cleanup.yml --tags sensor-cleanup
```

#### Delete Sensors and Clean Up Generation Directories

```bash
time ansible-playbook -i ansible/inventory/cloud30.local ansible/acs-spokes-sensor-cleanup.yml --tags sensor-cleanup -e cleanup_sensor_generation_after_delete=true
```

#### Unregister Clusters from Central Only

```bash
export ROX_API_TOKEN="<your-api-token>"
export ROX_CENTRAL_ADDRESS="https://$(oc get route central -n rhacs-operator -o jsonpath='{.spec.host}')"

time ansible-playbook -i ansible/inventory/cloud30.local ansible/acs-spokes-sensor-cleanup.yml --tags registration
```

#### Full Cleanup (Delete Sensors and Unregister)

```bash
export ROX_API_TOKEN="<your-api-token>"
export ROX_CENTRAL_ADDRESS="https://$(oc get route central -n rhacs-operator -o jsonpath='{.spec.host}')"

time ansible-playbook -i ansible/inventory/cloud30.local ansible/acs-spokes-sensor-cleanup.yml
```

#### Full Cleanup with Generation Directory Removal

```bash
export ROX_API_TOKEN="<your-api-token>"
export ROX_CENTRAL_ADDRESS="https://$(oc get route central -n rhacs-operator -o jsonpath='{.spec.host}')"

time ansible-playbook -i ansible/inventory/cloud30.local ansible/acs-spokes-sensor-cleanup.yml -e cleanup_sensor_generation_after_delete=true
```

### Playbook Roles

#### `acs-spokes-sensor-cleanup`
- Checks for `delete-sensor.sh` in each sensor directory
- Executes delete script with spoke's kubeconfig
- Records SUCCESS or SKIPPED status
- Optionally removes sensor generation directory (controlled by `cleanup_sensor_generation_after_delete`)
- Prints cleanup summary

#### `acs-spokes-registration` (unregister action)
- Set with `acs_spokes_registration_action: unregister` variable
- Validates required environment variables
- Runs `roxctl cluster delete --name <cluster>`
- Gracefully handles "not found" errors
- Records SUCCESS or NOT_FOUND status
- Prints unregister summary

### Output

The playbook produces summaries showing:
- Total clusters processed
- Successfully cleaned up count
- Skipped count (no sensor found)
- Successfully unregistered count
- Not found/already removed count

## File Locations

- **Sensor generation directories**: `/root/secured_clusters/sensor-<cluster-name>/`
- **CRS cache**: Stored as secrets in spoke namespaces on hub
- **Playbooks**: `ansible/acs-secure-spokes.yml`, `ansible/acs-spokes-sensor-cleanup.yml`
- **Roles**: `ansible/roles/acs-*`

## Troubleshooting

### "Cluster already exists" Error

This occurs when a cluster is already registered in ACS Central. Solutions:

1. **Skip regeneration** (normal behavior):
   - The playbook detects this and skips sensor generation
   - Deployment is skipped if no sensor scripts were generated

2. **Force regeneration**:
   ```bash
   ansible-playbook ... -e force_sensor_regeneration=true
   ```
   - Deletes existing cluster from Central
   - Regenerates and redeploys sensor

### "No such file or directory" for delete-sensor.sh

This is expected if:
- Sensors were never deployed
- Sensor directories were cleaned up after deployment
- Use `--tags sensor-cleanup` to skip if not present

### ROX_API_TOKEN Not Recognized

Ensure environment variables are exported before running playbook:

```bash
export ROX_API_TOKEN="<token>"
export ROX_CENTRAL_ADDRESS="<url>"
```

Verify with:
```bash
echo $ROX_API_TOKEN
echo $ROX_CENTRAL_ADDRESS
```

## Best Practices

1. **Always run on managed_clusters group**: Ensure your inventory has clusters under `[managed_clusters]` group
2. **Preserve sensor directories**: Keep directories unless actively cleaning up; useful for redeployment
3. **Use tags for selective operations**: Run specific roles using `--tags` to avoid accidental deletions
4. **Validate environment before cleanup**: Ensure correct ROX_CENTRAL_ADDRESS before unregistering
5. **Check CRS status**: CRS mismatches trigger regeneration automatically; no manual intervention needed

## Idempotency

Both playbooks are largely idempotent:

- **Setup playbook**: Can be safely rerun; skips already-registered clusters
- **Cleanup playbook**: Can be safely rerun; handles missing components gracefully
- **CRS management**: Automatically detects and fixes mismatches

## Related Documentation

- [ACS Integration with ACM](https://access.redhat.com/documentation/en-us/red_hat_advanced_cluster_security_for_kubernetes/)
- [roxctl CLI Reference](https://docs.openshift.com/acs/cli/)
