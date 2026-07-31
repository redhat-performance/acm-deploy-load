#!/usr/bin/env bash
# Test consumes all available cluster capacity
set -e
set -o pipefail

iteration=1

# Method to deploy clusters (AI = Assisted Installer, IBI = Image Based Installer)
# method="ai-clusterinstance-gitops"
method="ibi-clusterinstance-gitops"

# Phase 1 (Idle baseline) delay in seconds
# Idle baseline for 15 seconds for faster test run
start_delay=15
# Idle baseline for 2 hours for long duration comparison
# start_delay=7200

# Phase 2 (Cluster deployment) rate in clusters per interval
# Rate 500 clusters every 30 minutes
interval_period=1800
batch=500
# Rate 80 clusters every 5 minutes
# interval_period=300
# batch=80

# Phase 3 (Soak baseline) delay in seconds
# Soak baseline for 2 minutes for faster test run
end_delay=120
# Soak baseline for 6 hours for long duration comparison
# end_delay=21600

# SNO or Mixed SNOs and MNOs
clusters_per_app=100

# Prometheus analysis per phase (uncomment to enable)
# Use with longer idle and soak baselines to produce capacity guideline measurements
prometheus_analysis_arg="--no-prometheus-analysis"
# prometheus_analysis_arg=""

# WAN Emulation can only be run with SNOs
wan_em="(None)"
# wan_em="(50ms/0.02)"
# wan_em="(50ms/0.02) / 100Mbps"
# wan_em="(50ms/0.02) / 20Mbps"

# Location of ArgoCD cluster and cluster application directories:
# 4.20+ and newer will use telco-reference repo/location
argocd_arg="--argocd-directory /root/rhacm-ztp/telco-reference/telco-ran/configuration/argocd"
# 4.20 and earlier versions use cnf-features-deploy repo/location
# argocd_arg="--argocd-directory /root/rhacm-ztp/cnf-features-deploy/ztp/gitops-subscriptions/argocd"

ts="$(date -u +%Y%m%d-%H%M%S)"
log_file="iz-all-${ts}.log"
test_ver="ZTP Scale Run ${iteration}"

time ./acm-deploy-load/acm-deploy-load.py --test-version "${test_ver}" --wan-emulation "${wan_em}" -m "${method}" --clusters-per-app ${clusters_per_app} ${argocd_arg} --start-delay ${start_delay} --end-delay ${end_delay} ${prometheus_analysis_arg} -w -i 60 -t ${clusters_per_app}cpa-${batch}b-${interval_period}i-${iteration} interval -b ${batch} -i ${interval_period} 2>&1 | tee ${log_file}

results_dir=$(grep "Results data captured in:" $log_file | awk '{print $NF}')

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/graph-acm-deploy.py ${results_dir} 2>&1 | tee -a ${log_file}

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

# Complete Prometheus analysis for entire workload period
start_time=$(grep "Start Time:" ${results_dir}/report.txt | awk '{print $4}')
end_time=$(grep "End Time:" ${results_dir}/report.txt | awk '{print $4}')
echo "time ./acm-deploy-load/analyze-prometheus.py -p deploy-pa -s ${start_time} -e ${end_time} ${results_dir}" | tee -a ${log_file}
time ./acm-deploy-load/analyze-prometheus.py -p "deploy-pa" -s "${start_time}" -e "${end_time}" ${results_dir} 2>&1 | tee -a ${log_file}

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

time ./acm-deploy-load/benchmark-search.py ${results_dir} --sample-count 3 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

echo "Finished" 2>&1 | tee -a ${log_file}

cat ${log_file} | grep -v WARNING > ${results_dir}/${log_file}.nowarn

mv ${log_file} ${results_dir}

gzip ${results_dir}/${log_file}
