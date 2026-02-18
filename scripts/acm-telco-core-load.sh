#!/usr/bin/env bash
# Script to orchestrate ACM Telco Core Load testing
set -e
set -o pipefail

# 24 hour interval to deploy each cluster
deploy_interval=86400
# deploy_interval=300

# Last deploy runtime of 24 hours
last_deploy_runtime=86400
# last_deploy_runtime=3600

# Every 12 minutes update 1/5 of the policies (all policies updated every hour)
policy_interval=720

# Number of clusters to deploy per interval
deploy_batch=1

# Start delay of 1 hour
start_delay=3600
# start_delay=180

# End delay of 2 hours
end_delay=7200
# end_delay=180

ts="$(date -u +%Y%m%d-%H%M%S)"
log_file="acm-telco-core-load-${ts}.log"

echo "time ./acm-deploy-load/acm-telco-core-load.py -k /root/mno/kubeconfig -i ${deploy_interval} -l ${last_deploy_runtime} -b ${deploy_batch} -p ${policy_interval} -s ${start_delay} -e ${end_delay}" | tee ${log_file}
time ./acm-deploy-load/acm-telco-core-load.py -k /root/mno/kubeconfig -i ${deploy_interval} -l ${last_deploy_runtime} -b ${deploy_batch} -p ${policy_interval} -s ${start_delay} -e ${end_delay} 2>&1 | tee -a ${log_file}

results_dir=$(grep "Results data captured in:" $log_file | awk '{print $NF}')

echo "################################################################################" 2>&1 | tee -a ${log_file}

start_time=$(grep -m 1 "Start Time:" ${results_dir}/report.txt | awk '{print $4}')
end_time=$(grep "End Time:" ${results_dir}/report.txt | awk '{print $4}')
echo "time ./acm-deploy-load/analyze-prometheus.py -k /root/mno/kubeconfig -p acm-telco-load-hub -s ${start_time} -e ${end_time} ${results_dir}" | tee -a ${log_file}
time ./acm-deploy-load/analyze-prometheus.py -k /root/mno/kubeconfig -p "acm-telco-load-hub" -s "${start_time}" -e "${end_time}" ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./scripts/post-acm-load-data-collection.sh -k 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

oc adm must-gather --dest-dir="${results_dir}/must-gather-${ts}" 2>&1 | tee -a ${log_file}
tar caf ${results_dir}/must-gather-${ts}.tar.gz --remove-files ${results_dir}/must-gather-${ts} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

echo "Finished" 2>&1 | tee -a ${log_file}

mv ${log_file} ${results_dir}
