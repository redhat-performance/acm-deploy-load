#!/usr/bin/env bash
#set -e
set -o pipefail

results_dir=$(ls -td results/*/ | head -1)
output_dir=${results_dir}/install-data
mkdir -p ${output_dir}

if [ "$1" == "-k" ]; then
  echo "$(date -u) :: Getting sno cluster kubeconfigs"
  ls /root/hv-vm/sno/ai-manifest/ | sed 's/-manifest.yml//g' | xargs -I % sh -c "mkdir -p /root/hv-vm/kc/% ;oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/kc/%/kubeconfig"
  echo "$(date -u) :: Getting compact cluster kubeconfigs"
  ls /root/hv-vm/compact/manifests/ | xargs -I % sh -c "mkdir -p /root/hv-vm/kc/%; oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/kc/%/kubeconfig"
  echo "$(date -u) :: Getting standard cluster kubeconfigs"
  ls /root/hv-vm/standard/manifests/ | xargs -I % sh -c "mkdir -p /root/hv-vm/kc/%; oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/kc/%/kubeconfig"
fi

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
# Takes too much space:
# oc get csv -A -o yaml > ${output_dir}/csv.yaml
# oc describe csv -A > ${output_dir}/csv.describe

oc get no > ${output_dir}/nodes
oc get no -o yaml > ${output_dir}/nodes.yaml
oc describe no > ${output_dir}/nodes.describe
oc get ns > ${output_dir}/namespaces
oc get ns -o yaml > ${output_dir}/namespaces.yaml
oc get pods -A -o wide > ${output_dir}/pods
oc get pods -A -o yaml > ${output_dir}/pods.yaml
oc describe pods -A > ${output_dir}/pods.describe
oc get ev -A > ${output_dir}/events
oc get ev -A -o yaml > ${output_dir}/events.yaml

echo "$(date -u) :: Collecting clusterinstance data"

oc get clusterinstance -A > ${output_dir}/clusterinstance.get_default
oc get clusterinstance -A -o yaml > ${output_dir}/clusterinstance.yaml
oc describe clusterinstance -A > ${output_dir}/clusterinstance.describe

echo "$(date -u) :: Collecting agentclusterinstall data"

oc get agentclusterinstall -A --no-headers -o custom-columns=NAME:'.metadata.name',COMPLETED:'.status.conditions[?(@.type=="Completed")].reason' > ${output_dir}/aci.status
oc describe agentclusterinstall -A > ${output_dir}/aci.describe
oc get agentclusterinstall -A -o yaml > ${output_dir}/aci.yaml

cat ${output_dir}/aci.status | grep -v local-agent-cluster | grep -v local-cluster | awk '{print $2}' | sort | uniq -c > ${output_dir}/aci.status_count
cat ${output_dir}/aci.status | grep "InstallationFailed" | awk '{print $1}' > ${output_dir}/aci.InstallationFailed
cat ${output_dir}/aci.status | grep "InstallationNotStarted" | awk '{print $1}' > ${output_dir}/aci.InstallationNotStarted
cat ${output_dir}/aci.status | grep "InstallationInProgress" | awk '{print $1}' > ${output_dir}/aci.InstallationInProgress

echo "$(date -u) :: Collecting imageclusterinstall data"

oc get imageclusterinstall -A --no-headers -o custom-columns=NAME:'.metadata.name',COMPLETED:'.status.conditions[?(@.type=="Completed")].reason' > ${output_dir}/ici.status
oc describe imageclusterinstall -A > ${output_dir}/ici.describe
oc get imageclusterinstall -A -o yaml > ${output_dir}/ici.yaml

cat ${output_dir}/ici.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/ici.status_count
cat ${output_dir}/ici.status | grep "ClusterInstallationTimedOut" | awk '{print $1}' > ${output_dir}/ici.ClusterInstallationTimedOut
cat ${output_dir}/ici.status | grep "ClusterInstallationInProgress" | awk '{print $1}' > ${output_dir}/ici.ClusterInstallationInProgress

echo "$(date -u) :: Collecting openshift-gitops data"

oc get applications.argoproj.io -n openshift-gitops > ${output_dir}/gitops.applications

echo "$(date -u) :: Collecting installed clusters data"

# Get 2 Deployed cluster's install-configs
cat ${output_dir}/aci.status | grep InstallationCompleted | grep -v local-agent-cluster | grep -v local-cluster | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get cm -n kube-system cluster-config-v1 -o yaml > ${output_dir}/%.cluster-config-v1"
cat ${output_dir}/ici.status | grep ClusterInstallationSucceeded | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get cm -n kube-system cluster-config-v1 -o yaml > ${output_dir}/%.cluster-config-v1"
# Copy two SiteConfigs/ClusterInstances
ls  /root/hv-vm/*/ai-siteconfig/*-siteconfig.yml | head -n 2 | xargs -I % sh -c "cp % ${output_dir}/"
ls  /root/hv-vm/*/ai-siteconfig/*-resources.yml | head -n 2 | xargs -I % sh -c "cp % ${output_dir}/"
ls  /root/hv-vm/*/ai-clusterinstance/*-clusterinstance.yml | head -n 2 | xargs -I % sh -c "cp % ${output_dir}/"
ls  /root/hv-vm/*/ibi-clusterinstance/*-clusterinstance.yml | head -n 2 | xargs -I % sh -c "cp % ${output_dir}/"
# Ping 2 deployed clusters
cat ${output_dir}/aci.status | grep InstallationCompleted | grep -v local-agent-cluster | grep -v local-cluster | head -n 2 | awk '{print $1}' | xargs -I % sh -c "ping6 -c 2 % > ${output_dir}/%.ping"
cat ${output_dir}/ici.status | grep ClusterInstallationSucceeded | head -n 2 | awk '{print $1}' | xargs -I % sh -c "ping6 -c 2 % > ${output_dir}/%.ping"
# Get 2 Deployed cluster's clusterversion objects
cat ${output_dir}/aci.status | grep InstallationCompleted | grep -v local-agent-cluster | grep -v local-cluster | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get clusterversion version > ${output_dir}/%.clusterversion"
cat ${output_dir}/ici.status | grep ClusterInstallationSucceeded | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get clusterversion version > ${output_dir}/%.clusterversion"
# Get 2 Deployed cluster's clusterversion objects yaml
cat ${output_dir}/aci.status | grep InstallationCompleted | grep -v local-agent-cluster | grep -v local-cluster | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get clusterversion version -o yaml > ${output_dir}/%.clusterversion.yaml"
cat ${output_dir}/ici.status | grep ClusterInstallationSucceeded | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get clusterversion version -o yaml > ${output_dir}/%.clusterversion.yaml"
# Get 2 Deployed cluster's clusterserviceversion objects
cat ${output_dir}/aci.status | grep InstallationCompleted | grep -v local-agent-cluster | grep -v local-cluster | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get csv -A > ${output_dir}/%.clusterserviceversion"
cat ${output_dir}/ici.status | grep ClusterInstallationSucceeded | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get csv -A > ${output_dir}/%.clusterserviceversion"
# Get 2 Deployed cluster's clusteroperators objects
cat ${output_dir}/aci.status | grep InstallationCompleted | grep -v local-agent-cluster | grep -v local-cluster | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get co -A > ${output_dir}/%.clusteroperators"
cat ${output_dir}/ici.status | grep ClusterInstallationSucceeded | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get co -A > ${output_dir}/%.clusteroperators"
# Get 2 Deployed cluster's clusteroperators objects yaml
cat ${output_dir}/aci.status | grep InstallationCompleted | grep -v local-agent-cluster | grep -v local-cluster | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get co -A -o yaml > ${output_dir}/%.clusteroperators.yaml"
cat ${output_dir}/ici.status | grep ClusterInstallationSucceeded | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get co -A -o yaml > ${output_dir}/%.clusteroperators.yaml"
# Get 2 Deployed cluster's pods
cat ${output_dir}/aci.status | grep InstallationCompleted | grep -v local-agent-cluster | grep -v local-cluster | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get po -A > ${output_dir}/%.pods"
cat ${output_dir}/ici.status | grep ClusterInstallationSucceeded | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get po -A > ${output_dir}/%.pods"

echo "$(date -u) :: Collecting managedcluster data"

oc get managedcluster -A > ${output_dir}/managedcluster.get_default
oc describe managedcluster -A > ${output_dir}/managedcluster.describe
oc get managedcluster -A --no-headers -o custom-columns=NAME:'.metadata.name',AVAILABLE:'.status.conditions[?(@.type=="ManagedClusterConditionAvailable")].status' > ${output_dir}/managedcluster.available

cat ${output_dir}/managedcluster.available | grep "Unknown" > ${output_dir}/mc.Unknown

oc get observabilityaddon -A -o json | jq -r '.items[] | "\(.metadata.namespace) Available: \(.status.conditions[] | select(.type=="Available" and .status=="True").status), lastTransitionTime: \(.status.conditions[] | select(.type=="Available" and .status=="True").lastTransitionTime), message: \(.status.conditions[] | select(.type=="Available" and .status=="True").message)"' > ${output_dir}/obs.available.clusters
oc get observabilityaddon -A -o json | jq -r '.items[] | "\(.metadata.namespace) Degraded: \(.status.conditions[] | select(.type=="Degraded" and .status=="True").status), lastTransitionTime: \(.status.conditions[] | select(.type=="Degraded" and .status=="True").lastTransitionTime), message: \(.status.conditions[] | select(.type=="Degraded" and .status=="True").message)"' > ${output_dir}/obs.degraded.clusters

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
# Also takes too much space
# oc describe policy -A > ${output_dir}/policy.describe

echo "$(date -u) :: Collecting clustergroupupgrades data"

oc get clustergroupupgrades -n ztp-install --no-headers -o custom-columns=NAME:'.metadata.name',READY:'.status.conditions[?(@.type=="Succeeded")].reason' > ${output_dir}/cgu.status
oc describe clustergroupupgrades -n ztp-install > ${output_dir}/cgu.describe
oc get clustergroupupgrades -n ztp-install -o yaml > ${output_dir}/cgu.yaml

cat ${output_dir}/cgu.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/cgu.status_count
cat ${output_dir}/cgu.status | grep "TimedOut"  | awk '{print $1}' > ${output_dir}/cgu.TimedOut


# Only collect AAP data if automation hub exists
ztp_day2_ns_exists=$(oc get aap -A --no-headers | wc -l)
if [[ $ztp_day2_ns_exists > 0 ]]; then
  echo "$(date -u) :: Collecting ACM application hook data"

  # AAP without EDA Data
  # oc get applications.app.k8s.io -n ztp-day2-automation > ${output_dir}/applications.app.k8s.io
  # oc get applications.app.k8s.io -n ztp-day2-automation -o yaml > ${output_dir}/applications.app.k8s.io.yaml
  # oc describe applications.app.k8s.io -n ztp-day2-automation > ${output_dir}/applications.app.k8s.io.describe

  # oc get subscriptions.apps.open-cluster-management.io -n ztp-day2-automation > ${output_dir}/subscriptions.apps.open-cluster-management.io
  # oc get subscriptions.apps.open-cluster-management.io -n ztp-day2-automation -o yaml > ${output_dir}/subscriptions.apps.open-cluster-management.io.yaml
  # oc describe subscriptions.apps.open-cluster-management.io -n ztp-day2-automation > ${output_dir}/subscriptions.apps.open-cluster-management.io.describe

  # oc get placementrules -n ztp-day2-automation > ${output_dir}/placementrules
  # oc get placementrules -n ztp-day2-automation -o yaml > ${output_dir}/placementrules.yaml
  # oc describe placementrules -n ztp-day2-automation > ${output_dir}/placementrules.describe

  # oc get ansiblejobs -A > ${output_dir}/ansiblejobs
  # oc get ansiblejobs -A --no-headers | wc -l > ${output_dir}/ansiblejobs.count
  # oc get ansiblejobs -A -o yaml > ${output_dir}/ansiblejobs.yaml
  # oc describe ansiblejobs -A > ${output_dir}/ansiblejobs.describe

  echo "$(date -u) :: Collecting aap data"

  oc get aap -n ansible-automation-platform > ${output_dir}/aap
  oc get aap -n ansible-automation-platform -o yaml > ${output_dir}/aap.yaml
  oc describe aap -n ansible-automation-platform > ${output_dir}/aap.describe

  oc get automationhub -n ansible-automation-platform > ${output_dir}/aap.automationhub
  oc get automationhub -n ansible-automation-platform -o yaml > ${output_dir}/aap.automationhub.yaml
  oc describe automationhub -n ansible-automation-platform  > ${output_dir}/aap.automationhub.describe

  oc get automationcontroller -n ansible-automation-platform > ${output_dir}/aap.automationcontroller
  oc get automationcontroller -n ansible-automation-platform -o yaml > ${output_dir}/aap.automationcontroller.yaml
  oc describe automationcontroller -n ansible-automation-platform  > ${output_dir}/aap.automationcontroller.describe

  oc get eda -n ansible-automation-platform > ${output_dir}/aap.eda
  oc get eda -n ansible-automation-platform -o yaml > ${output_dir}/aap.eda.yaml
  oc describe eda -n ansible-automation-platform > ${output_dir}/aap.eda.describe

  oc get managedclusters -l ztp-ansible=running > ${output_dir}/aap.mc.ztp-ansible-running
  oc get managedclusters -l ztp-ansible=completed > ${output_dir}/aap.mc.ztp-ansible-completed
  oc get managedclusters -l ztp-ansible=running --no-headers | wc -l > ${output_dir}/aap.mc.ztp-ansible-running.count
  oc get managedclusters -l ztp-ansible=completed --no-headers | wc -l > ${output_dir}/aap.mc.ztp-ansible-completed.count

fi

echo "$(date -u) :: Inspecting failed cluster installs"
truncate -s 0 ${output_dir}/cluster-install-failures
for cluster in $(cat ${output_dir}/aci.InstallationFailed ${output_dir}/ici.ClusterInstallationTimedOut); do
  echo "$(date -u) :: Checking cluster ${cluster}"
  export KUBECONFIG=/root/hv-vm/kc/${cluster}/kubeconfig
  if ! oc get pods 2>/dev/null >/dev/null; then
    # needs adjustment for compact/standard
    if ssh core@${cluster} uptime 2>/dev/null >/dev/null; then
        echo "$cluster APIDown" | tee -a ${output_dir}/cluster-install-failures
        continue
    fi
    echo "$cluster Offline/Unreachable" | tee -a ${output_dir}/cluster-install-failures
    continue
  fi
  cluster_installed=$(oc get clusterversion version -o json | jq '.status.conditions[] | select(.type=="Available").status' -r)
  if [ $cluster_installed == "True" ]; then
    # No bug (yet) - Cluster Appears Installed
    echo "$cluster ClusterVersionAvailable " | tee -a ${output_dir}/cluster-install-failures
    continue
  fi
  if oc get clusterversion version -o json | jq '.status.conditions[] | select(.status=="True") | select(.type=="Progressing").message ' | egrep "Working towards|some cluster operators are not available|MultipleErrors" -q; then
    # https://issues.redhat.com/browse/OCPBUGS-12881
    echo "$cluster ManyOperatorsIncomplete" | tee -a ${output_dir}/cluster-install-failures
    continue
  fi
  failure_found=false
  echo -n "$cluster " | tee -a ${output_dir}/cluster-install-failures
  autoscaler_degraded=$(oc get co cluster-autoscaler -o json | jq -r '.status.conditions==null')
  ceo_available=$(oc get co etcd -o json | jq -r '.status.conditions[] | select(.type=="Available").status')
  ceo_degraded=$(oc get co etcd -o json | jq -r '.status.conditions[] | select(.type=="Degraded").status')
  image_registry_degraded=$(oc get co image-registry -o json | jq -r '.status.conditions[] | select(.type=="Degraded").status')
  machine_api_notready=$(oc get co machine-api -o json | jq -r '.status.conditions==null')
  mco_degraded=$(oc get co machine-config -o json | jq -r '.status.conditions[] | select(.type=="Degraded").status')
  ks_degraded=$(oc get co kube-scheduler -o json | jq -r '.status.conditions[] | select(.type=="Degraded").status')
  olm_degraded=$(oc get co operator-lifecycle-manager -o json | jq -r '.status.conditions[] | select(.type=="Degraded").status')
  if [ $autoscaler_degraded == "true" ]; then
    # https://issues.redhat.com/browse/OCPBUGS-18954
    echo -n "ClusterAutoScalerDegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $ceo_available == "False" ]; then
    # https://issues.redhat.com/browse/OCPBUGS-12475
    echo -n "EtcdOperatorUnavailable " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $ceo_degraded == "True" ]; then
    # https://issues.redhat.com/browse/OCPBUGS-12853
    echo -n "EtcdOperatorDegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $image_registry_degraded == "True" ]; then
    # https://issues.redhat.com/browse/OCPBUGS-18969
    echo -n "ImageRegistryDegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $machine_api_notready == "true" ]; then
    # https://issues.redhat.com/browse/OCPBUGS-19505
    echo -n "MachineAPINotReady " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $mco_degraded == "True" ]; then
    # https://issues.redhat.com/browse/OCPBUGS-12741
    # https://issues.redhat.com/browse/OCPBUGS-18964 (Also detected as this)
    echo -n "MCODegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $olm_degraded == "True" ]; then
    echo -n "OLMDegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $ks_degraded == "True" ]; then
    echo -n "KubeSchedulerDegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if $failure_found ; then
    echo "" | tee -a ${output_dir}/cluster-install-failures
  else
    # Sometimes a cluster is actually installed or seems installed by the time this script has completed
    # Alternatively this could be a new install failure type
    echo "Else" | tee -a ${output_dir}/cluster-install-failures
  fi
done
cat ${output_dir}/cluster-install-failures | awk '{$1=""; print $0}' | sort | uniq -c > ${output_dir}/cluster-install-failures.failure_count


echo "$(date -u) :: Inspecting up to 40 TimedOut CGUs"
mkdir -p ${output_dir}/cgu-failures
examined_cgu_failures=0

for cluster in $(cat ${output_dir}/cgu.TimedOut); do
  examined_cgu_failures=$((examined_cgu_failures+1))
  echo "$(date -u) :: Checking cluster ($examined_cgu_failures) - ${cluster}"
  export KUBECONFIG=/root/hv-vm/kc/${cluster}/kubeconfig
  mkdir -p ${output_dir}/cgu-failures/${cluster}

  oc get pods -A > ${output_dir}/cgu-failures/${cluster}/pods
  oc get pods -A -o yaml > ${output_dir}/cgu-failures/${cluster}/pods.yaml
  oc describe pods -A > ${output_dir}/cgu-failures/${cluster}/pods.describe

  oc get clusteroperators -A > ${output_dir}/cgu-failures/${cluster}/clusteroperators
  oc get clusteroperators -A -o yaml > ${output_dir}/cgu-failures/${cluster}/clusteroperators.yaml
  oc describe clusteroperators -A > ${output_dir}/cgu-failures/${cluster}/clusteroperators.describe

  oc get clusterversion -o yaml > ${output_dir}/cgu-failures/${cluster}/clusterversion.yaml

  oc get configurationpolicies -A > ${output_dir}/cgu-failures/${cluster}/configurationpolicies
  oc get configurationpolicies -A -o yaml > ${output_dir}/cgu-failures/${cluster}/configurationpolicies.yaml
  oc describe configurationpolicies -A > ${output_dir}/cgu-failures/${cluster}/configurationpolicies.describe

  oc get policies -A > ${output_dir}/cgu-failures/${cluster}/policies
  oc get policies -A -o yaml > ${output_dir}/cgu-failures/${cluster}/policies.yaml
  oc describe policies -A > ${output_dir}/cgu-failures/${cluster}/policies.describe

  oc get subs -A > ${output_dir}/cgu-failures/${cluster}/subs
  oc get subs -A -o yaml > ${output_dir}/cgu-failures/${cluster}/subs.yaml
  oc describe subs -A > ${output_dir}/cgu-failures/${cluster}/subs.describe

  oc get csvs -A > ${output_dir}/cgu-failures/${cluster}/csvs
  oc get csvs -A -o yaml > ${output_dir}/cgu-failures/${cluster}/csvs.yaml
  oc describe csvs -A > ${output_dir}/cgu-failures/${cluster}/csvs.describe

  oc get installplans -A > ${output_dir}/cgu-failures/${cluster}/installplans
  oc get installplans -A -o yaml > ${output_dir}/cgu-failures/${cluster}/installplans.yaml
  oc describe installplans -A > ${output_dir}/cgu-failures/${cluster}/installplans.describe

  oc get catalogsources -A > ${output_dir}/cgu-failures/${cluster}/catalogsources
  oc get catalogsources -A -o yaml > ${output_dir}/cgu-failures/${cluster}/catalogsources.yaml
  oc describe catalogsources -A > ${output_dir}/cgu-failures/${cluster}/catalogsources.describe

  oc logs -n open-cluster-management-agent-addon -l app=config-policy-controller --tail=-1 > ${output_dir}/cgu-failures/${cluster}/config-policy-controller.log
  oc logs -n open-cluster-management-agent-addon -l app=governance-policy-framework --tail=-1 > ${output_dir}/cgu-failures/${cluster}/governance-policy-framework.log

  if [ "$examined_cgu_failures" -ge "40" ]; then
    break
  fi
done

echo "$(date -u) :: Done collecting data"
