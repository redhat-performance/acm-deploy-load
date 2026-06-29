#!/usr/bin/env bash
# Purpose of this script is to run a quick dry-run to verify everything is set to run the actual test
set -e
set -o pipefail

iteration=1
interval_period=7200
batch=100
clusters_per_app=100

wan_em="(None)"
# wan_em="(50ms/0.02)"
# wan_em="(50ms/0.02) / 100Mbps"
# wan_em="(50ms/0.02) / 20Mbps"

ts="$(date -u +%Y%m%d-%H%M%S)"
log_file="dr-${ts}.log"
test_ver="ZTP Scale Run ${iteration}"
interval_period=1

time ./acm-deploy-load/acm-deploy-load.py --dry-run --start-delay 1 --end-delay 1 --test-version "${test_ver}" --wan-emulation "${wan_em}" --clusters-per-app ${clusters_per_app} -w --ztp-client-templates -i 10 -t dry-run interval -b ${batch} -i ${interval_period} 2>&1 | tee ${log_file}

results_dir=$(grep "Results data captured in:" $log_file | awk '{print $NF}')

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/graph-acm-deploy.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-acm-deploy-time.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./scripts/post-ztp-install-data-collection.sh -k 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-agentclusterinstalls.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-clustergroupupgrades.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

oc adm must-gather --dest-dir="${results_dir}/must-gather-${ts}" 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

start_time=$(grep "Start Time:" ${results_dir}/report.txt | awk '{print $4}')
end_time=$(grep "End Time:" ${results_dir}/report.txt | awk '{print $4}')
time ./acm-deploy-load/analyze-prometheus.py -p "deploy-pa" -s "${start_time}" -e "${end_time}" ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

# meta=$(kubectl promdump meta -n openshift-monitoring -p prometheus-k8s-0 -c prometheus -d /prometheus </dev/null 2>&1 | tee -a ${log_file})
# kubectl promdump -n openshift-monitoring -p prometheus-k8s-0 -c prometheus -d /prometheus --min-time "$(echo $meta | cut -d \| -f 5 | cut -d \  -f 2,3)" --max-time "$(echo $meta | cut -d \| -f 6 | cut -d \  -f 2,3)" > ${results_dir}/promdump-${ts}.tar.gz

echo "################################################################################" 2>&1 | tee -a ${log_file}

echo "Finished" 2>&1 | tee -a ${log_file}

cat ${log_file} | grep -v WARNING > ${results_dir}/${log_file}.nowarn

mv ${log_file} ${results_dir}

gzip ${results_dir}/${log_file}
