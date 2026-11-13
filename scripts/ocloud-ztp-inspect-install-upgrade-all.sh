#!/usr/bin/env bash
# Orchestrates ocloud-deploy-load.py followed by offline resource analyzers,
# live analyze-ocloud-ibu.py (if upgrade ran), and full-run Prometheus analysis.

set -e
set -o pipefail

################################################################################
# Configuration — edit these before running
################################################################################
method="ibi"                           # ai or ibi
upgrade_ocp_version="4.22.3"           # target OCP version for IBU upgrade
upgrade_revision="v3"                  # v2=full upgrade with AbortOnFailure+Finalize, v3=Prep+Upgrade (no finalize)
test_ver="test-00"
kubeconfig="/root/mno/kubeconfig"
spoke_kc_dir="/root/hv-vm/kc"          # analyze-ocloud-ibu.py -k argument

# Phase 1 - Idle baseline
# Idle baseline for 15 seconds for faster test run
start_delay=15
# Idle baseline for 2 hours for long duration comparison
# start_delay=7200

# Phase 2 — Inspection
inspect_batch=200
inspect_interval=0
inspect_timeout=1800

# Phase 3 — Install
install_batch=200
install_interval=0
# 30 minutes with ibi (image-based installer)
install_timeout=1800
# 1.5 hours with ai (agent-installer)
# install_timeout=5400

# Phase 4 — Upgrade
upgrade_batch=25
# 10 minute interval to throttle stampede of Prep stage container image pulls
upgrade_interval=600
upgrade_timeout=3600

# Phase 5 - Soak baseline
# Soak baseline for 2 minutes for faster test run
end_delay=120
# Soak baseline for 6 hours for long duration comparison
# end_delay=21600

# Set to "false" to skip a phase
run_inspection=true
run_install=true
run_upgrade=true

# Set to "false" to disable shuffling of host/PR lists
shuffle=true

# Set to "false" to skip Prometheus analysis
run_prometheus=true

export KUBECONFIG="${kubeconfig}"

################################################################################
# Build skip flags
################################################################################
skip_flags=""
if [ "${run_inspection}" != "true" ]; then
  skip_flags="${skip_flags} --skip-inspection"
fi
if [ "${run_install}" != "true" ]; then
  skip_flags="${skip_flags} --skip-install"
fi
if [ "${run_upgrade}" != "true" ]; then
  skip_flags="${skip_flags} --skip-upgrade"
fi
if [ "${shuffle}" != "true" ]; then
  skip_flags="${skip_flags} --no-shuffle"
fi

################################################################################
# Main orchestrator
################################################################################
ts="$(date -u +%Y%m%d-%H%M%S)"
log_file="ocloud-all-${ts}.log"

echo "################################################################################" 2>&1 | tee ${log_file}
echo "Starting ocloud-deploy-load at ${ts}" 2>&1 | tee -a ${log_file}
echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/ocloud-deploy-load.py \
  -k "${kubeconfig}" \
  -m "${method}" \
  --test-version "${test_ver}" \
  --inspect-batch ${inspect_batch} \
  --inspect-interval ${inspect_interval} \
  --inspect-timeout ${inspect_timeout} \
  --install-batch ${install_batch} \
  --install-interval ${install_interval} \
  --install-timeout ${install_timeout} \
  --upgrade-batch ${upgrade_batch} \
  --upgrade-interval ${upgrade_interval} \
  --upgrade-timeout ${upgrade_timeout} \
  --upgrade-ocp-version "${upgrade_ocp_version}" \
  --upgrade-revision "${upgrade_revision}" \
  --start-delay ${start_delay} \
  --end-delay ${end_delay} \
  ${skip_flags} \
  -t "${test_ver}" \
  2>&1 | tee -a ${log_file}

results_dir=$(grep "Results data captured in:" "${log_file}" | awk '{print $NF}')

echo "################################################################################" 2>&1 | tee -a ${log_file}
echo "$(date -u) :: Running post-ocloud-ztp-all-data-collection.sh" 2>&1 | tee -a ${log_file}
echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./scripts/post-ocloud-ztp-all-data-collection.sh 2>&1 | tee -a ${log_file}

echo "$(date -u) :: Running graph-ocloud-deploy.py" 2>&1 | tee -a ${log_file}
echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/graph-ocloud-deploy.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

echo "$(date -u) :: Running Post Run Analysis" 2>&1 | tee -a ${log_file}
echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-provisioningrequests.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-baremetalhosts.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-clusterinstances.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-agentclusterinstalls.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-imageclusterinstalls.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

echo "$(date -u) :: Running analyze-ocloud-ibu.py" 2>&1 | tee -a ${log_file}
echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./acm-deploy-load/analyze-ocloud-ibu.py "${upgrade_ocp_version}" ${results_dir} -k "${spoke_kc_dir}" 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

echo "$(date -u) :: Running full-run Prometheus analysis" 2>&1 | tee -a ${log_file}
echo "################################################################################" 2>&1 | tee -a ${log_file}

start_time=$(grep "Start Time:" ${results_dir}/report.txt | awk '{print $4}')
end_time=$(grep "End Time:" ${results_dir}/report.txt | awk '{print $4}')
time ./acm-deploy-load/analyze-prometheus.py -p "ocloud-pa" -s "${start_time}" -e "${end_time}" ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

echo "Finished" 2>&1 | tee -a ${log_file}

################################################################################
# Move and compress log
################################################################################
cat "${log_file}" | grep -v WARNING > "${results_dir}/${log_file}.nowarn"
mv -- "${log_file}" "${results_dir}"
gzip "${results_dir}/${log_file}"
echo "Log saved to ${results_dir}/${log_file}.gz"
