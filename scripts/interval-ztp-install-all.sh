#!/usr/bin/env bash
# Test consumes all available cluster capacity
set -e
set -o pipefail

iteration=1

# Method to deploy clusters (AI = Assisted Installer, IBI = Image Based Installer)
# method="ai-siteconfig-gitops"
# method="ai-clusterinstance-gitops"
method="ibi-clusterinstance-gitops"

# Rate 500/1hr
interval_period=3600
batch=500
# Rate 40/5m
# interval_period=300
# batch=40

# SNO or Mixed SNOs and MNOs
clusters_per_app=100

# WAN Emulation can only be run with SNOs
wan_em="(None)"
# wan_em="(50ms/0.02)"
# wan_em="(50ms/0.02) / 100Mbps"
# wan_em="(50ms/0.02) / 20Mbps"

ts="$(date -u +%Y%m%d-%H%M%S)"
log_file="iz-all-${ts}.log"
acm_ver=$(cat /root/snapshot.ver)
aap_csv=$(oc get csv -n ansible-automation-platform -l operators.coreos.com/ansible-automation-platform-operator.ansible-automation-platfor= -o json | jq '.items[0].metadata.name' -r)
test_ver="ZTP Scale Run ${iteration}"
hub_ocp=$(oc version -o json | jq -r '.openshiftVersion')
# grep will cause error code 141 since it prints only the first match
cluster_ocp=$(cat /root/hv-vm/*/*/*.yml | grep "clusterImageSetNameRef:" -m 1 | awk '{print $NF}' | sed 's/openshift-//' || if [[ $? -eq 141 ]]; then true; else exit $?; fi)

time ./acm-deploy-load/acm-deploy-load.py --acm-version "${acm_ver}" --aap-version "${aap_csv}" --test-version "${test_ver}" --hub-version "${hub_ocp}" --deploy-version "${cluster_ocp}" --wan-emulation "${wan_em}" -m "${method}" --clusters-per-app ${clusters_per_app} -w -i 60 -t ${clusters_per_app}cpa-${batch}b-${interval_period}i-${iteration} interval -b ${batch} -i ${interval_period} 2>&1 | tee ${log_file}

results_dir=$(grep "Results data captured in:" $log_file | awk '{print $NF}')

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/graph-acm-deploy.py --acm-version "${acm_ver}" --test-version "${test_ver}" --hub-version "${hub_ocp}" --deploy-version "${cluster_ocp}" --wan-emulation "${wan_em}" ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-acm-deploy-time.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./scripts/post-ztp-install-data-collection.sh -k 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-clusterinstances.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-agentclusterinstalls.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-imageclusterinstalls.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-clustergroupupgrades.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-ansiblejobs.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

start_time=$(grep "Start Time:" ${results_dir}/report.txt | awk '{print $4}')
end_time=$(grep "End Time:" ${results_dir}/report.txt | awk '{print $4}')
time ./acm-deploy-load/analyze-prometheus.py -p "deploy-pa" -s "${start_time}" -e "${end_time}" ${results_dir} 2>&1 | tee -a ${log_file}
echo "time ./acm-deploy-load/analyze-prometheus.py -p deploy-pa -s ${start_time} -e ${end_time} ${results_dir}" | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

oc adm must-gather --dest-dir="${results_dir}/must-gather-${ts}" 2>&1 | tee -a ${log_file}
tar caf ${results_dir}/must-gather-${ts}.tar.gz --remove-files ${results_dir}/must-gather-${ts} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

# Commented out as the default is now IBI
# time ./scripts/post-ztp-gen-day1-csv.sh ${results_dir} 2>&1 | tee -a ${log_file}
#
# echo "################################################################################" 2>&1 | tee -a ${log_file}
#
# time ./acm-deploy-load/report-per-cluster.py ${results_dir}/day1-*.csv ${results_dir}/clustergroupupgrades-ztp-install-*.csv --profile combined --writegraph ${results_dir}/graph-combined-per-cluster.png 2>&1 | tee -a ${log_file}
# time ./acm-deploy-load/report-per-cluster.py ${results_dir}/day1-*.csv ${results_dir}/clustergroupupgrades-ztp-install-*.csv --profile all_stages --writegraph ${results_dir}/graph-per-cluster-stage_breakdown.png 2>&1 | tee -a ${log_file}

# Commented out as promdumps are rarely used and should be migrated to a separate script
# echo "################################################################################" 2>&1 | tee -a ${log_file}
#
# meta=$(kubectl promdump meta -n openshift-monitoring -p prometheus-k8s-0 -c prometheus -d /prometheus </dev/null 2>&1 | tee -a ${log_file})
# kubectl promdump -n openshift-monitoring -p prometheus-k8s-0 -c prometheus -d /prometheus --min-time "$(echo $meta | cut -d \| -f 5 | cut -d \  -f 2,3)" --max-time "$(echo $meta | cut -d \| -f 6 | cut -d \  -f 2,3)" > ${results_dir}/promdump-${ts}.tar.gz

echo "################################################################################" 2>&1 | tee -a ${log_file}
echo "Running ACM-inspector"  2>&1 | tee -a ${log_file}

acm_inspector_image="quay.io/bjoydeep/acm-inspector:2.9.0-SNAPSHOT-2023-10-02-16-51-40"
acm_inspector_token=$(oc create token kubeburner -n default)
acm_inspector_url=$(oc whoami --show-server)
acm_inspector_output_dir="$(pwd)/${results_dir}/acm-inspector-$(date -u +%Y%m%d-%H%M%S)"
mkdir -p ${acm_inspector_output_dir}

podman run --network host -e OC_CLUSTER_URL=${acm_inspector_url} -e OC_TOKEN=${acm_inspector_token} -v ${acm_inspector_output_dir}:/acm-inspector/output ${acm_inspector_image} 2>&1 | tee -a ${log_file}
tar czf ${acm_inspector_output_dir}.tar.gz -C ${acm_inspector_output_dir} .

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/benchmark-search.py ${results_dir} --sample-count 3 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

echo "Finished" 2>&1 | tee -a ${log_file}

cat ${log_file} | grep -v WARNING > ${results_dir}/${log_file}.nowarn

mv ${log_file} ${results_dir}

gzip ${results_dir}/${log_file}
