#!/usr/bin/env bash
# 3500 MC support

export KUBECONFIG=/root/mno/kubeconfig

# Patches in this file:
# - Patch the search-collector deployment
# - Patch the search-postgres deployment
# - Patch the search-indexer deployment
# - Patch the search-api deployment
# - Patch the console-mce to reduce the frequency requests to search
# - Patch the multicluster-integrations-config configmap to disable the basic pull model

# Patch the search-collector deployment
echo "Applying patch to search-v2-operator - collector deployment"
echo "  - Increase the memory limit to 8Gi and the request to 64Mi."
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/collector/resources", "value": {"limits": {"memory": "8Gi"}, "requests": {"memory": "64Mi", "cpu": "25m"}}}]'

# Patch the search-postgres deployment
echo "Applying patch to search-v2-operator - database deployment"
echo "  - Increase the memory limit to 16Gi and the request to 4Gi."
echo "  - Set the environment variables for the database."
oc patch search -n open-cluster-management search-v2-operator --type json \
  -p='[
    {"op": "add", "path": "/spec/deployments/database/resources", "value": {"limits": {"memory": "16Gi"}, "requests": {"memory": "4Gi", "cpu": "25m"}}},
    {"op": "add", "path": "/spec/deployments/database/envVar", "value": [{"name": "POSTGRESQL_EFFECTIVE_CACHE_SIZE", "value": "1024MB"}, {"name": "POSTGRESQL_SHARED_BUFFERS", "value": "512MB"}, {"name": "WORK_MEM", "value": "128MB"}]}
  ]'

# Patch the search-indexer deployment
echo "Applying patch to search-v2-operator - indexer deployment"
echo "  - Increase the memory limit to 4Gi and the request to 128Mi."
echo "  - Set the replica count to 3."
echo "  - Set the environment variable REQUEST_LIMIT to 75."
oc patch search -n open-cluster-management search-v2-operator --type json \
  -p='[
    {"op": "add", "path": "/spec/deployments/indexer/resources", "value": {"limits": {"memory": "4Gi"}, "requests": {"memory": "128Mi", "cpu": "25m"}}},
    {"op": "add", "path": "/spec/deployments/indexer/replicaCount", "value": 3},
    {"op": "add", "path": "/spec/deployments/indexer/envVar", "value": [{"name": "REQUEST_LIMIT", "value": "75"}]}
  ]'

# Patch the search-api deployment
echo "Applying patch to search-v2-operator - queryapi deployment"
echo "  - Increase the memory limit to 4Gi and the request to 1Gi."
echo "  - Set the replica count to 2."
oc patch search -n open-cluster-management search-v2-operator --type json \
  -p='[
    {"op": "add", "path": "/spec/deployments/queryapi/resources", "value": {"limits": {"memory": "4Gi"}, "requests": {"memory": "1Gi", "cpu": "25m"}}}, {"op": "add", "path": "/spec/deployments/queryapi/replicaCount", "value": 2}
  ]'
echo "Sleep 10"
sleep 10

# Patch the console to reduce the frequency of search requests
echo "Applying patch to console-mce-config configmap." 
echo "  - Reduce frequency of search requests to 5 minutes and limit the number of results to 500."
oc -n multicluster-engine patch configmap console-mce-config \
  --type=merge \
  -p '{"data":{"APP_SEARCH_INTERVAL":"300000","APP_SEARCH_LIMIT":"500"}}'

# Patch the multicluster-integrations-config configmap to disable the basic pull model
echo "Applying patch to multicluster-integrations-config configmap."
echo "  - Disable the basic pull model."
oc -n open-cluster-management patch configmap multicluster-integrations-config \
  --type=merge \
  -p='{"data":{"config.yaml":"pullModel:\n  basic:\n    disabled: true\n"}}'

echo "Sleep 10"
sleep 10

echo "Done Patching"
