#!/usr/bin/env bash
# Patch SiteConfig Operator maxConcurrentReconciles to 10

export KUBECONFIG=/root/mno/kubeconfig

echo "Applying ACM siteconfig-operator-configuration maxConcurrentReconciles: 10"
oc get cm -n open-cluster-management siteconfig-operator-configuration -o json | jq '.data.maxConcurrentReconciles'
oc patch configmap siteconfig-operator-configuration -n open-cluster-management --type=merge -p '{"data":{"maxConcurrentReconciles":"10"}}'
oc get cm -n open-cluster-management siteconfig-operator-configuration -o json | jq '.data.maxConcurrentReconciles'

echo "Restarting ACM siteconfig-controller-manager"
oc rollout restart deployment -n open-cluster-management siteconfig-controller-manager

echo "Done Patching"
