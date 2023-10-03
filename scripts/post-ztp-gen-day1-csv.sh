#!/bin/bash
# Generates a day1.csv file with the following fields
# name, cluster_name, aci_creation, aci_installed, assisted_cluster_registration, assisted_host_registration, assisted_installed, bmh_provision_start, bmh_provision_end

output_file=/dev/fd/1
if [[ -d "$1" ]]; then
  output_file="$1/day1-$(date +%Y%m%d-%H%M%S).csv"
fi

bmh_tmp=$(mktemp)
agent_tmp=$(mktemp)
aci_tmp=$(mktemp)
events_tmp=$(mktemp)
trap _cleanup exit
_cleanup(){
  rm -f "$bmh_tmp"
  rm -f "$agent_tmp"
  rm -f "$aci_tmp"
  rm -f "$events_tmp"
}

(
echo name,cluster_name,aci_creation,aci_installed,assisted_cluster_registration,assisted_host_registration,assisted_installed,bmh_provision_start,bmh_provision_end,managedcluster_imported

oc get aci -A -ojson \
| jq -r '.items[] | select(.status.conditions[] | select(.type == "Completed" and .status == "True")) | .metadata.name' \
| sort \
| while read -r cluster_name; do

    oc get bmh -n $cluster_name -ojson > "$bmh_tmp"
    oc get agent -n $cluster_name -ojson > "$agent_tmp"
    oc get aci -n $cluster_name $cluster_name -ojson > "$aci_tmp"
    aci_creation=$(jq -r '.metadata.creationTimestamp' "$aci_tmp")
    aci_installed=$(jq -r '.status.conditions[] | select(.type=="Completed") | .lastTransitionTime' "$aci_tmp")
    managedcluster_imported=$(oc get managedcluster $cluster_name -ojsonpath='{range .status.conditions[?(@.type=="ManagedClusterImportSucceeded")]}{.lastTransitionTime}{end}')
    events_url=$(jq -r '.status.debugInfo.eventsURL' "$aci_tmp")
    curl -sk "$events_url" > "$events_tmp"
    cluster_reg=$(jq -r '.[] | select(.name=="cluster_registration_succeeded") | .event_time' "$events_tmp")
    assisted_installed=$(jq -r '.[] | select(.name=="cluster_installation_completed") | .event_time' "$events_tmp")

    jq -r .items[].metadata.name "$agent_tmp" \
    | while read -r host_id; do
      host=$(jq '.items[] | select(.metadata.name=="'"$host_id"'") | .spec.hostname' "$agent_tmp" -r)
      bmh_provision_start=$(jq '.items[] | select(.metadata.name=="'"$host"'") | .status.operationHistory.provision.start' "$bmh_tmp" -r)
      bmh_provision_end=$(jq '.items[] | select(.metadata.name=="'"$host"'") | .status.operationHistory.provision.end' "$bmh_tmp" -r)
      host_reg=$(jq -r '.[] | select(.name=="host_registration_succeeded") | select(.host_id=="'"$host_id"'")| .event_time' "$events_tmp")
      echo "$host,$cluster_name,$aci_creation,$aci_installed,$cluster_reg,$host_reg,$assisted_installed,$bmh_provision_start,$bmh_provision_end,$managedcluster_imported"
    done
done
) > "$output_file"
