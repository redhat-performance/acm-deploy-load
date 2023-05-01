#!/usr/bin/env bash
# 3500 MC support

export KUBECONFIG=/root/bm/kubeconfig

echo "Create searchscale configmap"

oc create cm -n open-cluster-management searchscale --from-literal POSTGRESQL_SHARED_BUFFERS=512MB --from-literal POSTGRESQL_EFFECTIVE_CACHE_SIZE=1024MB --from-literal WORK_MEM=128MB
echo "Add searchscale configmap to ACM search-v2-operator"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "replace", "path": "/spec/dbConfig", "value": "searchscale"}]'
echo "Sleep 10"
sleep 10

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

echo "Applying ACM observability tuning"
echo "Applying ACM observability memcache tuning"
oc patch mco -n open-cluster-management-observability observability --type json -p '[{"op": "add", "path": "/spec/advanced", "value": {"queryFrontendMemcached": {"connectionLimit": 10240, "maxItemSize": "10m", "memoryLimitMb": 10240}, "storeMemcached": {"connectionLimit": 10240, "maxItemSize": "10m", "memoryLimitMb": 10240}}}]'
echo "Sleep 10"
sleep 10
# echo "Applying ACM observability store replicas 6 tuning"
# oc patch mco -n open-cluster-management-observability observability --type json -p '[{"op": "add", "path": "/spec/advanced/store", "value": {"replicas": "6"}}]'
# echo "Sleep 10"
# sleep 10
echo "Applying ACM observability route timeout tuning"
oc annotate route -n open-cluster-management-observability rbac-query-proxy --overwrite haproxy.router.openshift.io/timeout=300s
oc annotate route -n open-cluster-management-observability observatorium-api --overwrite haproxy.router.openshift.io/timeout=300s
echo "Sleep 10"
sleep 10

echo "Done Patching"
