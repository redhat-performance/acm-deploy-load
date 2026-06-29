#!/usr/bin/env bash
# Script to orchestrate ACM Telco Core Load testing
set -e
set -o pipefail

iteration=1

# Phase 1 (Idle baseline) delay in seconds
# 25 hours accounts for initial certificate rotation on hub cluster
start_delay=90000
# start_delay=180

# Phase 2 (Cluster deployment) rate in clusters per interval
# 1 cluster every 12 hours
deploy_batch=1
deploy_interval=43200
# deploy_interval=300

# After the last cluster deployment, continue running for this duration before Phase 3
last_deploy_runtime=43200
# last_deploy_runtime=7200

# Phase 2 (Policy updates) - every 12 minutes updates 1/5 of policies (all updated every hour)
policy_interval=720

# Phase 3 (Soak baseline) delay in seconds
# 6 hours to observe idle workload
end_delay=21600
# end_delay=180

# Prometheus analysis per phase (Use flag to disable)
# Use with longer idle and soak baselines to produce capacity guideline measurements
# prometheus_analysis_arg="--no-prometheus-analysis"
prometheus_analysis_arg=""

ts="$(date -u +%Y%m%d-%H%M%S)"
log_file="acm-telco-core-load-${ts}.log"
test_ver="Telco Core Load ${iteration}"
results_dir_suffix="test-${iteration}"

echo "time ./acm-deploy-load/acm-telco-core-load.py -k /root/mno/kubeconfig --test-version \"${test_ver}\" -t ${results_dir_suffix} -s ${start_delay} -b ${deploy_batch} -i ${deploy_interval} -l ${last_deploy_runtime} -p ${policy_interval} -e ${end_delay} ${prometheus_analysis_arg}" | tee ${log_file}
time ./acm-deploy-load/acm-telco-core-load.py -k /root/mno/kubeconfig --test-version "${test_ver}" -t ${results_dir_suffix} -s ${start_delay} -b ${deploy_batch} -i ${deploy_interval} -l ${last_deploy_runtime} -p ${policy_interval} -e ${end_delay} ${prometheus_analysis_arg} 2>&1 | tee -a ${log_file}

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
