#!/usr/bin/env bash
# Test to apply
set -e
set -o pipefail

# 24 hour interval to manage each cluster
interval_manage=86400
# interval_manage=3600

# Every 12 minutes update 1/5 of the policies (all policies updated every hour)
interval_policy=720

# Start delay of 1 hour
start_delay=3600
# start_delay=180

# End delay of 1 hour
end_delay=3600
# end_delay=180

ts="$(date -u +%Y%m%d-%H%M%S)"
log_file="mc-load-${ts}.log"

time ./acm-deploy-load/acm-mc-load.py -i ${interval_manage} -p ${interval_policy} -s ${start_delay} -e ${end_delay} 2>&1 | tee ${log_file}

results_dir=$(grep "Results data captured in:" $log_file | awk '{print $NF}')

echo "################################################################################" 2>&1 | tee -a ${log_file}

start_time=$(grep -m 1 "Start Time:" ${results_dir}/report.txt | awk '{print $4}')
end_time=$(grep "End Time:" ${results_dir}/report.txt | awk '{print $4}')
time ./acm-deploy-load/analyze-prometheus.py -p "mc-load" -s "${start_time}" -e "${end_time}" ${results_dir} 2>&1 | tee -a ${log_file}
echo "time ./acm-deploy-load/analyze-prometheus.py -p mc-load -s ${start_time} -e ${end_time} ${results_dir}" | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./scripts/post-acm-load-data-collection.sh -k 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

oc adm must-gather --dest-dir="${results_dir}/must-gather-${ts}" 2>&1 | tee -a ${log_file}
tar caf ${results_dir}/must-gather-${ts}.tar.gz --remove-files ${results_dir}/must-gather-${ts} 2>&1 | tee -a ${log_file}

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

echo "Finished" 2>&1 | tee -a ${log_file}

cat ${log_file} | grep -v WARNING > ${results_dir}/${log_file}.nowarn

mv ${log_file} ${results_dir}

gzip ${results_dir}/${log_file}
