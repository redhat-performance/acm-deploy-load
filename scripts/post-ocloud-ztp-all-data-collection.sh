#!/usr/bin/env bash
# Post ocloud-deploy-load data collection script
#set -e
set -o pipefail

results_dir=$(ls -td results/*/ | head -1)
output_dir=${results_dir}/ocloud-data
mkdir -p ${output_dir}

echo "$(date -u) :: Collecting managed cluster kubeconfigs"
oc get managedcluster --no-headers | grep -v local | awk '{print $1}' | \
  xargs -I % sh -c "mkdir -p /root/hv-vm/kc/% ; oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/kc/%/kubeconfig"

echo "$(date -u) :: Collecting hub clusterversion, clusteroperators, featuregate, etcd, csv, nodes, namespaces, pods, events"

oc get clusterversion > ${output_dir}/clusterversion
oc get clusterversion -o yaml > ${output_dir}/clusterversion.yaml
oc describe clusterversion > ${output_dir}/clusterversion.describe

oc get clusteroperators > ${output_dir}/clusteroperators
oc get clusteroperators -o yaml > ${output_dir}/clusteroperators.yaml
oc describe clusteroperators > ${output_dir}/clusteroperators.describe

oc describe featuregate cluster > ${output_dir}/featuregate.cluster.describe
oc get featuregate cluster -o yaml > ${output_dir}/featuregate.cluster.yaml

oc describe etcd cluster > ${output_dir}/etcd.describe
oc get etcd cluster -o yaml > ${output_dir}/etcd.yaml

oc get cm -n kube-system cluster-config-v1 -o yaml > ${output_dir}/cluster-config-v1

oc get csv -A > ${output_dir}/csv
oc get subscriptions.operators.coreos.com -A > ${output_dir}/subscriptions.operators.coreos.com
oc get installplan -A > ${output_dir}/installplan

oc get no > ${output_dir}/nodes
oc get no -o yaml > ${output_dir}/nodes.yaml
oc describe no > ${output_dir}/nodes.describe
oc get ns > ${output_dir}/namespaces
oc get ns -o yaml > ${output_dir}/namespaces.yaml
oc get pods -A -o wide > ${output_dir}/pods
oc get pods -A -o yaml > ${output_dir}/pods.yaml
oc get ev -A > ${output_dir}/events

echo "$(date -u) :: Collecting storage data"

oc get sc > ${output_dir}/storageclasses
oc get sc -o yaml > ${output_dir}/storageclasses.yaml
oc get pv > ${output_dir}/pv
oc get pvc -A > ${output_dir}/pvc

echo "$(date -u) :: Collecting baremetalhost data"

oc get baremetalhost -A > ${output_dir}/baremetalhosts
oc get baremetalhost -A -o yaml > ${output_dir}/baremetalhosts.yaml
oc get baremetalhost -A --no-headers \
  -o custom-columns=NAMESPACE:'.metadata.namespace',NAME:'.metadata.name',STATE:'.status.provisioning.state' \
  > ${output_dir}/baremetalhosts.state

oc get baremetalhost -A --no-headers \
  -o custom-columns=NAMESPACE:'.metadata.namespace',NAME:'.metadata.name',STATE:'.status.provisioning.state' \
  | awk '{print $3}' | sort | uniq -c > ${output_dir}/baremetalhosts.state_count

echo "$(date -u) :: Collecting provisioningrequest data"

oc get provisioningrequests.clcm.openshift.io > ${output_dir}/provisioningrequests
oc get provisioningrequests.clcm.openshift.io | sort -k 2 > ${output_dir}/provisioningrequests.sorted
oc get provisioningrequests.clcm.openshift.io -o yaml > ${output_dir}/provisioningrequests.yaml

cat ${output_dir}/provisioningrequests.sorted | grep -v "PROVISIONDETAILS" | awk '{print $4}' \
  | sort | uniq -c > ${output_dir}/provisioningrequests.status_count
cat ${output_dir}/provisioningrequests.sorted | grep "failed" | awk '{print $2}' \
  > ${output_dir}/provisioningrequests.failed

echo "$(date -u) :: Collecting imagebasedgroupupgrade data"

oc get imagebasedgroupupgrades -A > ${output_dir}/imagebasedgroupupgrades
oc get imagebasedgroupupgrades -A -o yaml > ${output_dir}/imagebasedgroupupgrades.yaml

echo "$(date -u) :: Collecting clusterinstance data"

oc get clusterinstance -A > ${output_dir}/clusterinstance
oc get clusterinstance -A -o yaml > ${output_dir}/clusterinstance.yaml

echo "$(date -u) :: Collecting imageclusterinstall data"

oc get imageclusterinstall -A --no-headers \
  -o custom-columns=NAME:'.metadata.name',COMPLETED:'.status.conditions[?(@.type=="Completed")].reason' \
  > ${output_dir}/ici.status
oc get imageclusterinstall -A -o yaml > ${output_dir}/ici.yaml

cat ${output_dir}/ici.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/ici.status_count
cat ${output_dir}/ici.status | grep "ClusterInstallationTimedOut" | awk '{print $1}' \
  > ${output_dir}/ici.ClusterInstallationTimedOut
cat ${output_dir}/ici.status | grep "ClusterInstallationInProgress" | awk '{print $1}' \
  > ${output_dir}/ici.ClusterInstallationInProgress
cat ${output_dir}/ici.status | grep "ClusterInstallationSucceeded" | awk '{print $1}' \
  > ${output_dir}/ici.ClusterInstallationSucceeded

echo "$(date -u) :: Collecting agentclusterinstall data"

oc get agentclusterinstall -A --no-headers \
  -o custom-columns=NAME:'.metadata.name',COMPLETED:'.status.conditions[?(@.type=="Completed")].reason' \
  > ${output_dir}/aci.status
oc get agentclusterinstall -A -o yaml > ${output_dir}/aci.yaml

cat ${output_dir}/aci.status | grep -v local-agent-cluster | grep -v local-cluster | \
  awk '{print $2}' | sort | uniq -c > ${output_dir}/aci.status_count
cat ${output_dir}/aci.status | grep "InstallationCompleted" | grep -v local-agent-cluster | \
  grep -v local-cluster | awk '{print $1}' > ${output_dir}/aci.InstallationCompleted

echo "$(date -u) :: Collecting O-Cloud Manager (oran-o2ims) data"

oc get all -n oran-o2ims > ${output_dir}/oran-o2ims.all
oc get pods -n oran-o2ims -o yaml > ${output_dir}/oran-o2ims.pods.yaml
oc get csv -n oran-o2ims -o yaml > ${output_dir}/oran-o2ims.csv.yaml
oc get deployments -n oran-o2ims -o yaml > ${output_dir}/oran-o2ims.deployments.yaml
oc get ev -n oran-o2ims > ${output_dir}/oran-o2ims.events

for pod in $(oc get pods -n oran-o2ims --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null); do
  oc logs -n oran-o2ims "${pod}" --tail=-1 > "${output_dir}/oran-o2ims.${pod}.log" 2>&1 || true
done

echo "$(date -u) :: Collecting mch/mce data"

oc get mch -A > ${output_dir}/mch
oc get mch -A -o yaml > ${output_dir}/mch.yaml
oc describe mch -A > ${output_dir}/mch.describe

oc get mce > ${output_dir}/mce
oc get mce -o yaml > ${output_dir}/mce.yaml
oc describe mce > ${output_dir}/mce.describe

echo "$(date -u) :: Collecting managedcluster data"

oc get managedcluster -A > ${output_dir}/managedcluster
oc get managedcluster -A -o yaml > ${output_dir}/managedcluster.yaml
oc get managedcluster -A --no-headers \
  -o custom-columns=NAME:'.metadata.name',AVAILABLE:'.status.conditions[?(@.type=="ManagedClusterConditionAvailable")].status' \
  > ${output_dir}/managedcluster.available

echo "$(date -u) :: Collecting openshift-gitops data"

oc get applications.argoproj.io -n openshift-gitops > ${output_dir}/gitops.applications
oc get applications.argoproj.io -n openshift-gitops -o yaml > ${output_dir}/gitops.applications.yaml

# Collect ODF data if ODF is installed
odf_installed=$(oc get storagecluster -n openshift-storage --no-headers 2>/dev/null | wc -l)
if [[ ${odf_installed} -gt 0 ]]; then
  echo "$(date -u) :: Collecting ODF data"

  oc get storagecluster -n openshift-storage > ${output_dir}/odf.storagecluster
  oc get storagecluster -n openshift-storage -o yaml > ${output_dir}/odf.storagecluster.yaml

  oc get cephcluster -n openshift-storage > ${output_dir}/odf.cephcluster
  oc get cephcluster -n openshift-storage -o yaml > ${output_dir}/odf.cephcluster.yaml

  oc get cephblockpool -n openshift-storage -o yaml > ${output_dir}/odf.cephblockpool.yaml
  oc get cephfilesystem -n openshift-storage -o yaml > ${output_dir}/odf.cephfilesystem.yaml
  oc get cephobjectstore -n openshift-storage -o yaml > ${output_dir}/odf.cephobjectstore.yaml

  oc get noobaa -n openshift-storage > ${output_dir}/odf.noobaa
  oc get noobaa -n openshift-storage -o yaml > ${output_dir}/odf.noobaa.yaml
  oc get backingstore -n openshift-storage > ${output_dir}/odf.backingstore
  oc get backingstore -n openshift-storage -o yaml > ${output_dir}/odf.backingstore.yaml

  oc get pods -n openshift-storage -o wide > ${output_dir}/odf.pods
  oc get pvc -n openshift-storage > ${output_dir}/odf.pvc
  oc get ev -n openshift-storage > ${output_dir}/odf.events
fi

echo "$(date -u) :: Collecting sample installed cluster data"
mkdir -p ${output_dir}/cluster-data

for cluster in $(cat ${output_dir}/ici.ClusterInstallationSucceeded ${output_dir}/aci.InstallationCompleted 2>/dev/null | head -n 2); do
  echo "$(date -u) :: Collecting data for cluster ${cluster}"
  mkdir -p ${output_dir}/cluster-data/${cluster}
  oc --kubeconfig /root/hv-vm/kc/${cluster}/kubeconfig get clusterversion \
    > ${output_dir}/cluster-data/${cluster}/clusterversion
  oc --kubeconfig /root/hv-vm/kc/${cluster}/kubeconfig get clusterversion -o yaml \
    > ${output_dir}/cluster-data/${cluster}/clusterversion.yaml
  oc --kubeconfig /root/hv-vm/kc/${cluster}/kubeconfig get nodes \
    > ${output_dir}/cluster-data/${cluster}/nodes
  oc --kubeconfig /root/hv-vm/kc/${cluster}/kubeconfig get clusteroperators \
    > ${output_dir}/cluster-data/${cluster}/clusteroperators
  oc --kubeconfig /root/hv-vm/kc/${cluster}/kubeconfig get pods -A \
    > ${output_dir}/cluster-data/${cluster}/pods
  oc --kubeconfig /root/hv-vm/kc/${cluster}/kubeconfig get csv -A \
    > ${output_dir}/cluster-data/${cluster}/csv
  ping6 -c 2 "${cluster}" > ${output_dir}/cluster-data/${cluster}/ping 2>&1 || true
done

echo "$(date -u) :: Done collecting data"
