#!/usr/bin/env bash
# Script to collect post data artifacts for ACM Telco Core Load or ACM MC Load
#set -e
set -o pipefail

results_dir=$(ls -td results/*/ | head -1)
output_dir=${results_dir}/post-run-data
mkdir -p ${output_dir}

echo "$(date -u) :: Collecting managedcluster kubeconfigs"
oc get managedcluster --no-headers | grep -v local | awk '{print $1}' | xargs -I % sh -c "mkdir -p /root/hv-vm/kc/% ;oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/kc/%/kubeconfig"

echo "$(date -u) :: Collecting clusterversion, csv, nodes, namespaces and pod/event data"

oc get clusterversion > ${output_dir}/clusterversion
oc get clusterversion -o yaml > ${output_dir}/clusterversion.yaml
oc describe clusterversion > ${output_dir}/clusterversion.describe

oc get clusteroperators > ${output_dir}/clusteroperators
oc get clusteroperators -o yaml > ${output_dir}/clusteroperators.yaml
oc describe clusteroperators > ${output_dir}/clusteroperators.describe

# Get hub cluster install config
oc get cm -n kube-system cluster-config-v1 -o yaml > ${output_dir}/cluster-config-v1

oc get csv -A > ${output_dir}/csv

oc get no > ${output_dir}/nodes
oc get no -o yaml > ${output_dir}/nodes.yaml
oc describe no > ${output_dir}/nodes.describe
oc get ns > ${output_dir}/namespaces
oc get ns -o yaml > ${output_dir}/namespaces.yaml
oc describe ns > ${output_dir}/namespaces.describe
oc get pods -A -o wide > ${output_dir}/pods
oc get pods -A -o yaml > ${output_dir}/pods.yaml
oc describe pods -A > ${output_dir}/pods.describe
oc get ev -A > ${output_dir}/events
oc get ev -A -o yaml > ${output_dir}/events.yaml

echo "$(date -u) :: Collecting managedcluster data"

oc get managedcluster -A > ${output_dir}/managedcluster
oc get managedcluster -A -o yaml > ${output_dir}/managedcluster.yaml
oc describe managedcluster -A > ${output_dir}/managedcluster.describe

echo "$(date -u) :: Collecting mch/mce/mco data"

oc get mch -A > ${output_dir}/mch
oc get mch -A -o yaml > ${output_dir}/mch.yaml
oc describe mch -A > ${output_dir}/mch.describe

oc get mce > ${output_dir}/mce
oc get mce -o yaml > ${output_dir}/mce.yaml
oc describe mce > ${output_dir}/mce.describe

oc get mco > ${output_dir}/mco
oc get mco -o yaml > ${output_dir}/mco.yaml
oc describe mco > ${output_dir}/mco.describe

echo "$(date -u) :: Collecting policy data"

oc get policy -A > ${output_dir}/policy
oc get policy -A -o yaml > ${output_dir}/policy.yaml

oc get placementrules -A > ${output_dir}/placementrules
oc get placementrules -A -o yaml > ${output_dir}/placementrules.yaml
oc describe placementrules -A > ${output_dir}/placementrules.describe

oc get placementbinding -A > ${output_dir}/placementbinding
oc get placementbinding -A -o yaml > ${output_dir}/placementbinding.yaml
oc describe placementbinding -A > ${output_dir}/placementbinding.describe

echo "$(date -u) :: Done collecting data"
