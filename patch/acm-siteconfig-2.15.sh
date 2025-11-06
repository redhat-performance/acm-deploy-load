#!/usr/bin/env bash
# Patch SiteConfig Operator maxConcurrentReconciles to 10
# Patch SiteConfig Operator container image to the solve ACM-25778

export KUBECONFIG=/root/mno/kubeconfig

# Performed in siteconfig operator role
# echo "Applying ACM siteconfig-operator-configuration maxConcurrentReconciles: 10"
# oc get cm -n open-cluster-management siteconfig-operator-configuration -o json | jq '.data.maxConcurrentReconciles'
# oc patch configmap siteconfig-operator-configuration -n open-cluster-management --type=merge -p '{"data":{"maxConcurrentReconciles":"10"}}'
# oc get cm -n open-cluster-management siteconfig-operator-configuration -o json | jq '.data.maxConcurrentReconciles'

# echo "Restarting ACM siteconfig-controller-manager"
# oc rollout restart deployment -n open-cluster-management siteconfig-controller-manager

echo "Pausing MCH"
oc annotate mch -n open-cluster-management multiclusterhub mch-pause=True
sleep 10

echo "Patching SiteConfig Operator container image"
oc get deploy -n open-cluster-management siteconfig-controller-manager -o json |  jq '.spec.template.spec.containers[] | select(.name=="manager").image'
oc get deploy -n open-cluster-management siteconfig-controller-manager -o json |  jq '.spec.template.spec.containers[] |= (select(.name=="manager").image = "quay.io/acm-d/siteconfig-operator@sha256:a5146ff0d94ad425fb59f1d5d2fdaf3430b3a72df85f19ea59492c63d47fc695")' | oc replace -f -
oc get deploy -n open-cluster-management siteconfig-controller-manager -o json |  jq '.spec.template.spec.containers[] | select(.name=="manager").image'
echo "Sleep 10"
sleep 10

echo "Done Patching"
