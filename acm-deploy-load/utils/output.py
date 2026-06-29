#!/usr/bin/env python3
#  Copyright 2022 Red Hat
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from datetime import datetime, timezone
from datetime import timedelta
import logging
import numpy as np

logger = logging.getLogger("acm-deploy-load")


def assemble_stats(the_list, seconds=True):
  stats_min = 0
  stats_avg = 0
  stats_p50 = 0
  stats_p95 = 0
  stats_p99 = 0
  stats_max = 0
  if len(the_list) > 0:
    if seconds:
      stats_min = np.min(the_list)
      stats_avg = round(np.mean(the_list), 1)
      stats_p50 = round(np.percentile(the_list, 50), 1)
      stats_p95 = round(np.percentile(the_list, 95), 1)
      stats_p99 = round(np.percentile(the_list, 99), 1)
      stats_max = np.max(the_list)
    else:
      stats_min = str(timedelta(seconds=np.min(the_list)))
      stats_avg = str(timedelta(seconds=round(np.mean(the_list))))
      stats_p50 = str(timedelta(seconds=round(np.percentile(the_list, 50))))
      stats_p95 = str(timedelta(seconds=round(np.percentile(the_list, 95))))
      stats_p99 = str(timedelta(seconds=round(np.percentile(the_list, 99))))
      stats_max = str(timedelta(seconds=np.max(the_list)))
  return "{} :: {} :: {} :: {} :: {} :: {}".format(stats_min, stats_avg, stats_p50, stats_p95, stats_p99, stats_max)


def generate_deploy_load_report(start_time, end_time, deploy_start_time, deploy_end_time, wait_cluster_start_time,
    wait_cluster_end_time, wait_du_profile_start_time, wait_du_profile_end_time, wait_playbook_start_time,
    wait_playbook_end_time, soak_start_time, available_clusters, monitor_data, cliargs, versions, total_intervals, report_dir):
  # Timestamps define three workload phases:
  #   Phase 1 (Idle Baseline):      start_time -> deploy_start_time
  #   Phase 2 (Cluster Deployment): deploy_start_time -> soak_start_time
  #     - Manifest apply:             deploy_start_time -> deploy_end_time
  #     - Wait cluster install:        wait_cluster_start_time -> wait_cluster_end_time
  #     - Wait DU profile:             wait_du_profile_start_time -> wait_du_profile_end_time
  #     - Wait playbook:               wait_playbook_start_time -> wait_playbook_end_time
  #   Phase 3 (Soak Baseline):      soak_start_time -> end_time

  # Determine result data
  total_idle_baseline_time = round(deploy_start_time - start_time)
  total_phase2_time = round(soak_start_time - deploy_start_time)
  total_deploy_time = round(deploy_end_time - deploy_start_time)
  total_cluster_install_time = round(wait_cluster_end_time - wait_cluster_start_time)
  total_duprofile_time = round(wait_du_profile_end_time - wait_du_profile_start_time)
  total_playbook_time = round(wait_playbook_end_time - wait_playbook_start_time)
  total_soak_baseline_time = round(end_time - soak_start_time)
  total_time = round(end_time - start_time)
  success_cluster_percent = 0
  failed_cluster_percent = 0
  success_managed_percent = 0
  failed_managed_percent = 0
  success_du_percent = 0
  failed_du_percent = 0
  success_playbook_percent = 0
  failed_playbook_percent = 0
  success_overall_percent = 0
  failed_overall_percent = 0
  if monitor_data["cluster_applied_committed"] > 0:
    success_cluster_percent = round((monitor_data["cluster_install_completed"] / monitor_data["cluster_applied_committed"]) * 100, 1)
    failed_cluster_percent = round(100 - success_cluster_percent, 1)
  if monitor_data["cluster_install_completed"] > 0:
    success_managed_percent = round((monitor_data["managed"] / monitor_data["cluster_install_completed"]) * 100, 1)
    failed_managed_percent = round(100 - success_managed_percent, 1)
  if monitor_data["policy_init"] > 0:
    success_du_percent = round((monitor_data["policy_compliant"] / monitor_data["policy_init"]) * 100, 1)
    failed_du_percent = round(100 - success_du_percent, 1)
    success_overall_percent = round((monitor_data["policy_compliant"] / monitor_data["cluster_applied_committed"]) * 100, 1)
    failed_overall_percent = round(100 - success_overall_percent, 1)
  if cliargs.wait_playbook:
    success_playbook_percent = round((monitor_data["playbook_completed"] / monitor_data["policy_compliant"]) * 100, 1)
    failed_playbook_percent = round(100 - success_playbook_percent, 1)
    success_overall_percent = round((monitor_data["playbook_completed"] / monitor_data["cluster_applied_committed"]) * 100, 1)
    failed_overall_percent = round(100 - success_overall_percent, 1)

  # Log the report and output to report.txt in results directory
  with open("{}/report.txt".format(report_dir), "w") as report:
    phase_break(True, report)
    log_write(report, "acm-deploy-load Report Card")
    phase_break(True, report)
    log_write(report, "Versions")
    if versions["acm_version"]:
      log_write(report, " * ACM: {}".format(versions["acm_version"]))
    if versions["mce_version"]:
      log_write(report, " * MCE: {}".format(versions["mce_version"]))
    if versions["aap_version"]:
      log_write(report, " * AAP: {}".format(versions["aap_version"]))
    log_write(report, " * Test: {}".format(versions["test_version"]))
    log_write(report, " * Hub OCP: {}".format(versions["hub_version"]))
    log_write(report, " * Deployed OCP: {}".format(versions["deploy_version"]))
    log_write(report, "Deployed Cluster Results")
    log_write(report, " * Available Clusters: {}".format(available_clusters))
    log_write(report, " * Deployed (Applied/Committed) Clusters: {}".format(monitor_data["cluster_applied_committed"]))
    log_write(report, " * Installed Clusters: {}".format(monitor_data["cluster_install_completed"]))
    log_write(report, " * Failed Clusters: {}".format(monitor_data["cluster_install_failed"]))
    if monitor_data["cluster_notstarted"] > 0:
      log_write(report, " * InstallationNotStarted Clusters: {}".format(monitor_data["cluster_notstarted"]))
    if monitor_data["cluster_installing"] > 0:
      log_write(report, " * InstallationInProgress Clusters: {}".format(monitor_data["cluster_installing"]))
    log_write(report, " * Cluster Successful Percent: {}%".format(success_cluster_percent))
    log_write(report, " * Cluster Failed Percent: {}%".format(failed_cluster_percent))
    log_write(report, "Managed Cluster Results")
    log_write(report, " * Installed Clusters: {}".format(monitor_data["cluster_install_completed"]))
    log_write(report, " * Managed Clusters: {}".format(monitor_data["managed"]))
    log_write(report, " * Managed Successful Percent: {}%".format(success_managed_percent))
    log_write(report, " * Managed Failed Percent: {}%".format(failed_managed_percent))
    log_write(report, "DU Profile Results")
    log_write(report, " * DU Profile Initialized: {}".format(monitor_data["policy_init"]))
    log_write(report, " * DU Profile Compliant: {}".format(monitor_data["policy_compliant"]))
    log_write(report, " * DU Profile Timeout: {}".format(monitor_data["policy_timedout"]))
    log_write(report, " * DU Profile Successful Percent: {}%".format(success_du_percent))
    log_write(report, " * DU Profile Failed Percent: {}%".format(failed_du_percent))
    if cliargs.wait_playbook:
      log_write(report, "ZTP Day2 Playbook Results")
      log_write(report, " * ZTP Day2 Targets: {}".format(monitor_data["policy_compliant"]))
      log_write(report, " * ZTP Day2 Not Started: {}".format(monitor_data["playbook_notstarted"]))
      log_write(report, " * ZTP Day2 Running: {}".format(monitor_data["playbook_running"]))
      log_write(report, " * ZTP Day2 Completed: {}".format(monitor_data["playbook_completed"]))
      log_write(report, " * ZTP Day2 Successful Percent: {}%".format(success_playbook_percent))
      log_write(report, " * ZTP Day2 Failed Percent: {}%".format(failed_playbook_percent))
    log_write(report, "Overall Results")
    if cliargs.wait_playbook:
      log_write(report, " * Overall Success (Playbook Completed / Deployed): {} / {}".format(monitor_data["playbook_completed"], monitor_data["cluster_applied_committed"]))
    else:
      log_write(report, " * Overall Success (DU Compliant / Deployed): {} / {}".format(monitor_data["policy_compliant"], monitor_data["cluster_applied_committed"]))
    log_write(report, " * Overall Success Percent: {}%".format(success_overall_percent))
    log_write(report, " * Overall Failed Percent: {}%".format(failed_overall_percent))
    log_write(report, "Workload Parameters")
    log_write(report, " * Method: {}".format(cliargs.method))
    log_write(report, " * Rate: {}".format(cliargs.rate))
    log_write(report, " * Phase 1 / Idle Baseline (Start delay): {}s :: {}".format(
        cliargs.start_delay, str(timedelta(seconds=cliargs.start_delay))))
    log_write(report, " * Phase 2 (Cluster Deployment):")
    if cliargs.rate == "interval":
      log_write(report, "  * Deploy {} cluster(s) per {}s :: {} interval".format(
          cliargs.batch, cliargs.interval, str(timedelta(seconds=cliargs.interval))))
      log_write(report, "   * Cluster range: {} to {}".format(cliargs.start, cliargs.end))
      log_write(report, "   * Clusters per ZTP argoCD application: {}".format(cliargs.clusters_per_app))
      log_write(report, "   * Actual intervals: {}".format(total_intervals))
      if cliargs.skip_wait_install:
        log_write(report, "  * Skip waiting for cluster install completion")
      else:
        if cliargs.wait_cluster_max > 0:
          log_write(report, "  * Wait for cluster install completion (Max {}s :: {})".format(
              cliargs.wait_cluster_max, str(timedelta(seconds=cliargs.wait_cluster_max))))
        else:
          log_write(report, "  * Wait for cluster install completion (Infinite wait)")
    if not cliargs.wait_du_profile:
      log_write(report, "  * Skip waiting for DU Profile completion")
    else:
      if cliargs.wait_du_profile_max > 0:
        log_write(report, "  * Wait for DU Profile completion (Max {}s :: {})".format(
            cliargs.wait_du_profile_max, str(timedelta(seconds=cliargs.wait_du_profile_max))))
      else:
        log_write(report, "  * Wait for DU Profile completion (Infinite wait)")
    if not cliargs.wait_playbook:
      log_write(report, "  * Skip waiting for Playbook completion")
    else:
      if cliargs.wait_playbook_max > 0:
        log_write(report, "  * Wait for Playbook completion (Max {}s :: {})".format(
            cliargs.wait_playbook_max, str(timedelta(seconds=cliargs.wait_playbook_max))))
      else:
        log_write(report, "  * Wait for Playbook completion (Infinite wait)")
    log_write(report, " * Phase 3 / Soak Baseline (End delay): {}s :: {}".format(
        cliargs.end_delay, str(timedelta(seconds=cliargs.end_delay))))
    log_write(report, " * Monitor interval: {}s".format(cliargs.monitor_interval))
    if versions["wan_emulation"]:
      log_write(report, " * Wan Emulation: {}".format(versions["wan_emulation"]))
    log_write(report, "Workload Phases")
    log_write(report, " * Start Time: {} {}".format(
        datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), int(start_time * 1000)))
    log_write(report, " * End Time: {} {}".format(
        datetime.fromtimestamp(end_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), int(end_time * 1000)))
    log_write(report, " * Total duration: {}s :: {}".format(total_time, str(timedelta(seconds=total_time))))
    log_write(report, " * Phase 1 (Idle Baseline): {} to {} :: {}s :: {}".format(
        datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        datetime.fromtimestamp(deploy_start_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_idle_baseline_time, str(timedelta(seconds=total_idle_baseline_time))))
    log_write(report, " * Phase 2 (Cluster Deployment): {} to {} :: {}s :: {}".format(
        datetime.fromtimestamp(deploy_start_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        datetime.fromtimestamp(soak_start_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_phase2_time, str(timedelta(seconds=total_phase2_time))))
    log_write(report, "  * Cluster Deploying duration: {}s :: {}".format(total_deploy_time, str(timedelta(seconds=total_deploy_time))))
    if not cliargs.skip_wait_install:
      log_write(report, "  * Cluster Install wait duration: {}s :: {}".format(total_cluster_install_time, str(timedelta(seconds=total_cluster_install_time))))
    if cliargs.wait_du_profile:
      log_write(report, "  * DU Profile wait duration: {}s :: {}".format(total_duprofile_time, str(timedelta(seconds=total_duprofile_time))))
    if cliargs.wait_playbook:
      log_write(report, "  * Playbook wait duration: {}s :: {}".format(total_playbook_time, str(timedelta(seconds=total_playbook_time))))
    log_write(report, " * Phase 3 (Soak Baseline): {} to {} :: {}s :: {}".format(
        datetime.fromtimestamp(soak_start_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        datetime.fromtimestamp(end_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_soak_baseline_time, str(timedelta(seconds=total_soak_baseline_time))))


def generate_telco_core_load_report(workload_start_time, end_time, start_delay_complete_ts,
    end_delay_start_ts, cluster_deployed_timestamps, total_clusters_deployed,
    total_policy_cm_updates, available_clusters, deploy_batch_count, cliargs, versions, report_dir):

  total_elapsed_time = round(end_time - workload_start_time)
  total_idle_baseline_time = round(start_delay_complete_ts - workload_start_time)
  total_phase2_time = round(end_delay_start_ts - start_delay_complete_ts)
  total_soak_baseline_time = round(end_time - end_delay_start_ts)

  with open("{}/report.txt".format(report_dir), "w") as report:
    phase_break(True, report)
    log_write(report, "acm-telco-core-load Report Card")
    phase_break(True, report)
    log_write(report, "Versions")
    if versions["acm_version"]:
      log_write(report, " * ACM: {}".format(versions["acm_version"]))
    if versions["mce_version"]:
      log_write(report, " * MCE: {}".format(versions["mce_version"]))
    if versions["test_version"]:
      log_write(report, " * Test: {}".format(versions["test_version"]))
    if versions["hub_version"]:
      log_write(report, " * Hub OCP: {}".format(versions["hub_version"]))
    if versions["deploy_version"]:
      log_write(report, " * Deployed OCP: {}".format(versions["deploy_version"]))
    log_write(report, "Workload Parameters")
    if cliargs.no_deploy == False and cliargs.no_policy == False:
      phase2_label = "Cluster Deployment + Policy Updates"
      log_write(report, " * Mode: Deploy+Policy")
      log_write(report, " * Phase 1 / Idle Baseline (Start delay): {}s :: {}".format(
          cliargs.start_delay, str(timedelta(seconds=cliargs.start_delay))))
      log_write(report, " * Phase 2 ({}):".format(phase2_label))
      log_write(report, "  * Deploy {} cluster(s) per {}s :: {} interval".format(
          cliargs.batch, cliargs.interval_deploy, str(timedelta(seconds=cliargs.interval_deploy))))
      log_write(report, "   * Available clusters: {}".format(available_clusters))
      log_write(report, "   * Total batches: {}".format(deploy_batch_count))
      log_write(report, "   * Last deploy runtime: {}s :: {}".format(
          cliargs.last_deploy_runtime, str(timedelta(seconds=cliargs.last_deploy_runtime))))
      log_write(report, "  * Update policy configmap ({} keys) in namespace {} per {}s interval".format(
          cliargs.hub_policy_cm_keys, cliargs.hub_policy_namespace, cliargs.interval_policy))
      log_write(report, " * Phase 3 / Soak Baseline (End delay): {}s :: {}".format(
          cliargs.end_delay, str(timedelta(seconds=cliargs.end_delay))))
    elif cliargs.no_deploy == False and cliargs.no_policy == True:
      phase2_label = "Cluster Deployment"
      log_write(report, " * Mode: Deploy Clusters only")
      log_write(report, " * Phase 1 / Idle Baseline (Start delay): {}s :: {}".format(
          cliargs.start_delay, str(timedelta(seconds=cliargs.start_delay))))
      log_write(report, " * Phase 2 ({}):".format(phase2_label))
      log_write(report, "  * Deploy {} cluster(s) per {}s :: {} interval".format(
          cliargs.batch, cliargs.interval_deploy, str(timedelta(seconds=cliargs.interval_deploy))))
      log_write(report, "   * Available clusters: {}".format(available_clusters))
      log_write(report, "   * Total batches: {}".format(deploy_batch_count))
      log_write(report, "   * Last deploy runtime: {}s :: {}".format(
          cliargs.last_deploy_runtime, str(timedelta(seconds=cliargs.last_deploy_runtime))))
      log_write(report, " * Phase 3 / Soak Baseline (End delay): {}s :: {}".format(
          cliargs.end_delay, str(timedelta(seconds=cliargs.end_delay))))
    elif cliargs.no_deploy == True and cliargs.no_policy == False:
      phase2_label = "Policy Updates"
      log_write(report, " * Mode: Policy configmap updates only")
      log_write(report, " * Phase 1 / Idle Baseline (Start delay): {}s :: {}".format(
          cliargs.start_delay, str(timedelta(seconds=cliargs.start_delay))))
      log_write(report, " * Phase 2 ({}):".format(phase2_label))
      log_write(report, "  * Update policy configmap ({} keys) in namespace {} per {}s interval".format(
          cliargs.hub_policy_cm_keys, cliargs.hub_policy_namespace, cliargs.interval_policy))
      log_write(report, "   * Maximum number of policy intervals to run: {}".format(cliargs.max_policy_intervals))
      log_write(report, " * Phase 3 / Soak Baseline (End delay): {}s :: {}".format(
          cliargs.end_delay, str(timedelta(seconds=cliargs.end_delay))))
    log_write(report, "Workload Results")
    log_write(report, " * Total elapsed time: {}s :: {}".format(total_elapsed_time, str(timedelta(seconds=total_elapsed_time))))
    log_write(report, " * Total cluster(s) deployed: {}".format(total_clusters_deployed))
    log_write(report, " * Total policy cm updates: {}".format(total_policy_cm_updates))
    log_write(report, "Workload Phases")
    log_write(report, " * Start Time: {} {}".format(
        datetime.fromtimestamp(workload_start_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        int(workload_start_time * 1000)))
    log_write(report, " * End Time: {} {}".format(
        datetime.fromtimestamp(end_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        int(end_time * 1000)))
    log_write(report, " * Total duration: {}s :: {}".format(total_elapsed_time, str(timedelta(seconds=total_elapsed_time))))
    log_write(report, " * Phase 1 (Idle Baseline): {} to {} :: {}s :: {}".format(
        datetime.fromtimestamp(workload_start_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        datetime.fromtimestamp(start_delay_complete_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_idle_baseline_time, str(timedelta(seconds=total_idle_baseline_time))))
    log_write(report, " * Phase 2 ({}): {} to {} :: {}s :: {}".format(phase2_label,
        datetime.fromtimestamp(start_delay_complete_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        datetime.fromtimestamp(end_delay_start_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_phase2_time, str(timedelta(seconds=total_phase2_time))))
    for i, ts in enumerate(cluster_deployed_timestamps):
      log_write(report, "  * Cluster(s) Batch {} deployed: {}".format(
          i, datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    log_write(report, " * Phase 3 (Soak Baseline): {} to {} :: {}s :: {}".format(
        datetime.fromtimestamp(end_delay_start_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        datetime.fromtimestamp(end_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_soak_baseline_time, str(timedelta(seconds=total_soak_baseline_time))))


def log_write(file, message):
  logger.info(message)
  file.write(message + "\n")


def phase_break(lw=False, file=None):
  if lw:
    log_write(file, "###############################################################################")
  else:
    logger.info("###############################################################################")
