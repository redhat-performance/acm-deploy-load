#!/usr/bin/env bash
# 3500 MC support

export KUBECONFIG=/root/bm/kubeconfig

echo "Applying ACM search-v2-operator collector resources bump"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/collector/resources", "value": {"limits": {"memory": "8Gi"}, "requests": {"memory": "64Mi", "cpu": "25m"}}}]'
echo "Sleep 10"
sleep 10
echo "Applying ACM search-v2-operator database resources bump"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/database/resources", "value": {"limits": {"memory": "16Gi"}, "requests": {"memory": "32Mi", "cpu": "25m"}}}]'
echo "Sleep 10"
sleep 10
echo "Applying ACM search-v2-operator database envvars"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/database/envVar", "value": [{"name": "POSTGRESQL_EFFECTIVE_CACHE_SIZE", "value": "1024MB"}, {"name": "POSTGRESQL_SHARED_BUFFERS", "value": "512MB"}, {"name": "WORK_MEM", "value": "128MB"}]}]'
echo "Sleep 10"
sleep 10
echo "Applying ACM search-v2-operator indexer resources bump"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/indexer/resources", "value": {"limits": {"memory": "4Gi"}, "requests": {"memory": "128Mi", "cpu": "25m"}}}]'
echo "Sleep 10"
sleep 10
echo "Applying ACM search-v2-operator queryapi resources bump"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/queryapi/resources", "value": {"limits": {"memory": "4Gi"}, "requests": {"memory": "1Gi", "cpu": "25m"}}}, {"op": "add", "path": "/spec/deployments/queryapi/replicaCount", "value": 2}]'
echo "Sleep 10"
sleep 10

echo "Done Patching"
