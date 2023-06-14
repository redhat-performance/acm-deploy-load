#!/bin/bash
# Generates a day1.csv file with the following fields
# name, aci_creation, aci_installed, assisted_cluster_registration, assisted_host_registration, assisted_installed, bmh_provision_start, bmh_provision_end

output_file=/dev/fd/1
if [[ -d "$1" ]]; then
  output_file="$1/$(date +%Y%m%d-%H%M%S)"
fi

bmh_tmp=$(mktemp)
trap _cleanup exit
_cleanup(){
  rm -f "$bmh_tmp"
}

(
echo name,aci_creation,aci_installed,assisted_cluster_registration,assisted_host_registration,assisted_installed,bmh_provision_start,bmh_provision_end,managedcluster_imported

oc get aci -A -ojson \
| jq -r '.items[] | select(.status.conditions[] | select(.type == "Completed" and .status == "True")) | .metadata.name' \
| sort \
| while read -r host; do
    oc get bmh -n $host $host -ojson > "$bmh_tmp"
    bmh_provision_start=$(jq .status.operationHistory.provision.start "$bmh_tmp" -r)
    bmh_provision_end=$(jq .status.operationHistory.provision.end "$bmh_tmp" -r)
    managedcluster_imported=$(oc get managedcluster -n $host $host -ojsonpath='{range .status.conditions[?(@.type=="ManagedClusterImportSucceeded")]}{.lastTransitionTime}{end}')
    oc get aci -n $host $host -ojson \
    | jq -r '(.status.conditions[] | select(.type=="Completed") | .lastTransitionTime) as $completed | [.metadata.creationTimestamp, $completed,.status.debugInfo.eventsURL] | join(" ")' \
    | while read -r aci_creation aci_installed events_url; do
      curl -sk "$events_url" \
      | jq -r '.[] | select(.name=="cluster_registration_succeeded" or .name=="host_registration_succeeded" or .name=="cluster_installation_completed") | .event_time' \
      | xargs -n3 \
      | while read -r cluster_reg host_reg assisted_installed; do
          echo "$host,$aci_creation,$aci_installed,$cluster_reg,$host_reg,$assisted_installed,$bmh_provision_start,$bmh_provision_end,$managedcluster_imported"
      done
    done
done
) > "$output_file"
