#!/usr/bin/env python3
#
# Analyze ProvisioningRequest data on a hub cluster to determine count/min/avg/max/50p/95p/99p timings
#
#  Copyright 2026 Red Hat
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

import argparse
from datetime import datetime, timedelta
import json
from utils.command import command
from utils.output import log_write, write_stats_block
from utils.time_utils import parse_ts, compute_duration, has_duration
import logging
import os
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze ProvisioningRequest data",
      prog="analyze-provisioningrequests.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-o", "--offline-process", action="store_true", default=False,
                      help="Uses previously stored raw data")
  parser.add_argument("-r", "--raw-data-file", type=str, default="",
                    help="Set raw json data file for offline processing. Empty finds last file")
  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  logger.info("Analyze provisioningrequests")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")

  raw_data_file = "{}/provisioningrequests-{}.json".format(cliargs.results_directory, ts)
  if cliargs.offline_process:
    if cliargs.raw_data_file == "":
      dir_scan = sorted([ f.path for f in os.scandir(cliargs.results_directory) if f.is_file() and f.name.startswith("provisioningrequests") and f.name.endswith(".json") ])
      if len(dir_scan) == 0:
        logger.error("No previous offline file found. Exiting")
        sys.exit(1)
      raw_data_file = dir_scan[-1]
    else:
      raw_data_file = cliargs.raw_data_file
    logger.info("Reading raw data from: {}".format(raw_data_file))
  else:
    logger.info("Storing raw data file at: {}".format(raw_data_file))

  pr_csv_file = "{}/provisioningrequests-{}.csv".format(cliargs.results_directory, ts)
  pr_stats_file = "{}/provisioningrequests-{}.stats".format(cliargs.results_directory, ts)

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "provisioningrequests.clcm.openshift.io", "--show-managed-fields=true", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-provisioningrequests, oc get provisioningrequests rc: {}".format(rc))
      sys.exit(1)
    with open(raw_data_file, "w") as pr_data_file:
      pr_data_file.write(output)
  with open(raw_data_file, "r") as pr_file_data:
    pr_data = json.load(pr_file_data)

  logger.info("Writing CSV: {}".format(pr_csv_file))
  with open(pr_csv_file, "w") as csv_file:
    csv_file.write("name,cluster_name,status,creationTimestamp,"
        "ProvisioningRequestValidated.lastTransitionTime,"
        "ClusterInstanceRendered.lastTransitionTime,"
        "ClusterResourcesCreated.lastTransitionTime,"
        "NodeAllocationRequestRendered.lastTransitionTime,"
        "HardwareProvisioned.lastTransitionTime,"
        "HardwareNodeConfigApplied.lastTransitionTime,"
        "ClusterInstanceProcessed.lastTransitionTime,"
        "ClusterProvisioned.lastTransitionTime,"
        "ConfigurationApplied.lastTransitionTime,"
        "UpgradeCompleted.lastTransitionTime,"
        "templateVersion.patch.time,"
        "pr_ct_prv_duration,pr_prv_cir_duration,pr_cir_crc_duration,"
        "pr_crc_nar_duration,pr_nar_hp_duration,pr_hp_hnca_duration,"
        "pr_hnca_cip_duration,pr_cip_cp_duration,pr_cp_ca_duration,"
        "pr_patch_uc_duration,total_duration\n")

  pr_total_durations = []
  pr_preprocessing_durations = []
  pr_hw_provisioning_durations = []
  pr_cluster_provisioning_durations = []
  pr_configuration_durations = []
  pr_upgrade_durations = []
  fleet_earliest_creation = None
  fleet_latest_fulfilled = None
  fleet_earliest_ibu_patch = None
  fleet_latest_upgrade_completed = None

  for item in pr_data["items"]:
    pr_name = item["metadata"]["name"]
    ct_raw = item.get("metadata", {}).get("creationTimestamp", "")
    pr_creationTimestamp = parse_ts(ct_raw)
    if pr_creationTimestamp == "":
      logger.warning("PR: {}, missing or invalid creationTimestamp '{}', skipping".format(pr_name, ct_raw))
      continue

    # Determine cluster name
    pr_cluster_name = ""
    if "status" in item and "extensions" in item["status"]:
      pr_cluster_name = item["status"]["extensions"].get("clusterDetails", {}).get("name", "")
    if pr_cluster_name == "":
      pr_cluster_name = item.get("spec", {}).get("templateParameters", {}).get(
          "clusterInstanceParameters", {}).get("clusterName", "")

    # Determine status from provisioningPhase
    pr_status = "unknown"
    if "status" in item and "provisioningStatus" in item["status"]:
      pr_status = item["status"]["provisioningStatus"].get("provisioningPhase", "unknown")

    pr_validated_ts = ""
    pr_ci_rendered_ts = ""
    pr_resources_created_ts = ""
    pr_nar_rendered_ts = ""
    pr_hw_provisioned_ts = ""
    pr_hw_config_applied_ts = ""
    pr_ci_processed_ts = ""
    pr_cluster_provisioned_ts = ""
    pr_config_applied_ts = ""
    pr_upgrade_completed_ts = ""
    pr_ibu_patch_ts = ""

    if "status" in item and "conditions" in item["status"]:
      for condition in item["status"]["conditions"]:
        if "type" in condition and "status" in condition:
          ltt = condition.get("lastTransitionTime", "")
          parsed_ts = parse_ts(ltt)
          if parsed_ts == "":
            logger.warning("PR: {}, malformed lastTransitionTime '{}' in condition {}".format(
                pr_name, ltt, condition["type"]))
            continue
          if condition["status"] != "True":
            continue
          if condition["type"] == "ProvisioningRequestValidated":
            pr_validated_ts = parsed_ts
          elif condition["type"] == "ClusterInstanceRendered":
            pr_ci_rendered_ts = parsed_ts
          elif condition["type"] == "ClusterResourcesCreated":
            pr_resources_created_ts = parsed_ts
          elif condition["type"] == "NodeAllocationRequestRendered":
            pr_nar_rendered_ts = parsed_ts
          elif condition["type"] == "HardwareProvisioned":
            pr_hw_provisioned_ts = parsed_ts
          elif condition["type"] == "HardwareNodeConfigApplied":
            pr_hw_config_applied_ts = parsed_ts
          elif condition["type"] == "ClusterInstanceProcessed":
            pr_ci_processed_ts = parsed_ts
          elif condition["type"] == "ClusterProvisioned":
            pr_cluster_provisioned_ts = parsed_ts
          elif condition["type"] == "ConfigurationApplied":
            pr_config_applied_ts = parsed_ts
          elif condition["type"] == "UpgradeCompleted":
            pr_upgrade_completed_ts = parsed_ts
        else:
          logger.warning("PR: {}, 'type' or 'status' missing in condition: {}".format(pr_name, condition))
    else:
      logger.warning("status or conditions not found in provisioningrequest object: {}".format(pr_name))

    # IBU trigger timestamp: annotation (preferred) > kubectl-patch managedField on f:spec.templateVersion
    # Recommended one-liner to trigger O-Cloud IBU and record the per-PR patch time as an annotation:
    #   oc get pr --no-headers | sort -k 2 | awk '{print $1}' | \
    #     xargs -I{} bash -c 'TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); \
    #     oc patch provisioningrequests {} --type merge -p \
    #     "{\"spec\":{\"templateName\":\"sno-ran-du\",\"templateVersion\":\"v4-22-3-ibi-v2\"},\
    #\"metadata\":{\"annotations\":{\"ibu-patch-time\":\"$TS\"}}}"'
    annotation_patch_ts = parse_ts(item.get("metadata", {}).get("annotations", {}).get("ibu-patch-time", ""))
    if annotation_patch_ts != "":
      pr_ibu_patch_ts = annotation_patch_ts
    else:
      for mf in item.get("metadata", {}).get("managedFields", []):
        if mf.get("manager") == "kubectl-patch" and mf.get("operation") == "Update":
          if "f:templateVersion" in mf.get("fieldsV1", {}).get("f:spec", {}):
            parsed = parse_ts(mf.get("time", ""))
            if parsed != "":
              pr_ibu_patch_ts = parsed

    logger.debug("{}, {}, {}, {}".format(pr_name, pr_cluster_name, pr_status, pr_creationTimestamp))

    # Compute interval durations
    pr_ct_prv_duration = compute_duration(pr_validated_ts, pr_creationTimestamp)
    pr_prv_cir_duration = compute_duration(pr_ci_rendered_ts, pr_validated_ts)
    pr_cir_crc_duration = compute_duration(pr_resources_created_ts, pr_ci_rendered_ts)
    pr_crc_nar_duration = compute_duration(pr_nar_rendered_ts, pr_resources_created_ts)
    pr_nar_hp_duration = compute_duration(pr_hw_provisioned_ts, pr_nar_rendered_ts)
    pr_hp_hnca_duration = compute_duration(pr_hw_config_applied_ts, pr_hw_provisioned_ts)
    pr_hnca_cip_duration = compute_duration(pr_ci_processed_ts, pr_hw_config_applied_ts)
    pr_cip_cp_duration = compute_duration(pr_cluster_provisioned_ts, pr_ci_processed_ts)
    pr_cp_ca_duration = compute_duration(pr_config_applied_ts, pr_cluster_provisioned_ts)
    pr_patch_uc_duration = compute_duration(pr_upgrade_completed_ts, pr_ibu_patch_ts)
    total_duration = compute_duration(pr_config_applied_ts, pr_creationTimestamp)

    if fleet_earliest_creation is None or pr_creationTimestamp < fleet_earliest_creation:
      fleet_earliest_creation = pr_creationTimestamp
    if pr_config_applied_ts != "":
      if fleet_latest_fulfilled is None or pr_config_applied_ts > fleet_latest_fulfilled:
        fleet_latest_fulfilled = pr_config_applied_ts
    if pr_ibu_patch_ts != "":
      if fleet_earliest_ibu_patch is None or pr_ibu_patch_ts < fleet_earliest_ibu_patch:
        fleet_earliest_ibu_patch = pr_ibu_patch_ts
    if pr_upgrade_completed_ts != "":
      if fleet_latest_upgrade_completed is None or pr_upgrade_completed_ts > fleet_latest_upgrade_completed:
        fleet_latest_upgrade_completed = pr_upgrade_completed_ts

    # Include durations of 0, those are intervals completing within timestamp granularity.
    # Install metrics gate on timestamps only — a failed IBU changes pr_status away from
    # "fulfilled" even though the cluster installed successfully.
    if has_duration(pr_config_applied_ts, pr_creationTimestamp) and total_duration >= 0:
      pr_total_durations.append(total_duration)
    preprocessing_duration = compute_duration(pr_ci_processed_ts, pr_creationTimestamp)
    if has_duration(pr_ci_processed_ts, pr_creationTimestamp) and preprocessing_duration >= 0:
      pr_preprocessing_durations.append(preprocessing_duration)
    if has_duration(pr_hw_provisioned_ts, pr_nar_rendered_ts) and pr_nar_hp_duration >= 0:
      pr_hw_provisioning_durations.append(pr_nar_hp_duration)
    if has_duration(pr_cluster_provisioned_ts, pr_ci_processed_ts) and pr_cip_cp_duration >= 0:
      pr_cluster_provisioning_durations.append(pr_cip_cp_duration)
    if has_duration(pr_config_applied_ts, pr_cluster_provisioned_ts) and pr_cp_ca_duration >= 0:
      pr_configuration_durations.append(pr_cp_ca_duration)
    if has_duration(pr_upgrade_completed_ts, pr_ibu_patch_ts) and pr_patch_uc_duration >= 0:
      pr_upgrade_durations.append(pr_patch_uc_duration)
    elif pr_upgrade_completed_ts != "" and pr_ibu_patch_ts == "":
      logger.warning("PR: {}, UpgradeCompleted found but no IBU patch timestamp (annotation or kubectl-patch managedField), skipping from upgrade stats".format(pr_name))
    with open(pr_csv_file, "a") as csv_file:
      csv_file.write(
          "{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
          pr_name, pr_cluster_name, pr_status, pr_creationTimestamp,
          pr_validated_ts, pr_ci_rendered_ts, pr_resources_created_ts,
          pr_nar_rendered_ts, pr_hw_provisioned_ts, pr_hw_config_applied_ts,
          pr_ci_processed_ts, pr_cluster_provisioned_ts, pr_config_applied_ts,
          pr_upgrade_completed_ts, pr_ibu_patch_ts,
          pr_ct_prv_duration, pr_prv_cir_duration, pr_cir_crc_duration,
          pr_crc_nar_duration, pr_nar_hp_duration, pr_hp_hnca_duration,
          pr_hnca_cip_duration, pr_cip_cp_duration, pr_cp_ca_duration,
          pr_patch_uc_duration, total_duration))

  logger.info("Writing Stats: {}".format(pr_stats_file))

  with open(pr_stats_file, "w") as stats_file:
    log_write(stats_file, "Fleet Provisioning Summary")
    if fleet_earliest_creation is not None:
      log_write(stats_file, "Earliest creationTimestamp: {}".format(fleet_earliest_creation))
    if fleet_earliest_creation is not None and fleet_latest_fulfilled is not None:
      log_write(stats_file, "Latest fulfilled ConfigurationApplied: {}".format(fleet_latest_fulfilled))
      fleet_duration = compute_duration(fleet_latest_fulfilled, fleet_earliest_creation)
      log_write(stats_file, "Fleet Install Duration: {}s :: {}".format(fleet_duration, timedelta(seconds=fleet_duration)))
    if fleet_earliest_ibu_patch is not None and fleet_latest_upgrade_completed is not None:
      log_write(stats_file, "Earliest templateVersion kubectl-patch: {}".format(fleet_earliest_ibu_patch))
      log_write(stats_file, "Latest fulfilled UpgradeCompleted: {}".format(fleet_latest_upgrade_completed))
      fleet_upgrade_duration = compute_duration(fleet_latest_upgrade_completed, fleet_earliest_ibu_patch)
      log_write(stats_file, "Fleet Upgrade Duration: {}s :: {}".format(
          fleet_upgrade_duration, timedelta(seconds=fleet_upgrade_duration)))
    log_write(stats_file, "Total ProvisioningRequests: {}".format(len(pr_data["items"])))
    log_write(stats_file, "Fulfilled (Installed): {}".format(len(pr_total_durations)))
    log_write(stats_file, "Fulfilled (Upgraded): {}".format(len(pr_upgrade_durations)))
    write_stats_block(stats_file,
        "Total Install and Configuration Duration Stats (creationTimestamp to ConfigurationApplied) on fulfilled ProvisioningRequests",
        pr_total_durations)
    write_stats_block(stats_file,
        "O-Cloud Preprocessing Stats (creationTimestamp to ClusterInstanceProcessed) on fulfilled ProvisioningRequests",
        pr_preprocessing_durations)
    write_stats_block(stats_file,
        "Hardware Provisioning Stats (NodeAllocationRequestRendered to HardwareProvisioned) on fulfilled ProvisioningRequests",
        pr_hw_provisioning_durations)
    write_stats_block(stats_file,
        "Cluster Provisioning Stats (ClusterInstanceProcessed to ClusterProvisioned) on fulfilled ProvisioningRequests",
        pr_cluster_provisioning_durations)
    write_stats_block(stats_file,
        "Configuration Applied Stats (ClusterProvisioned to ConfigurationApplied) on fulfilled ProvisioningRequests",
        pr_configuration_durations)
    write_stats_block(stats_file,
        "IBU Upgrade Stats (templateVersion kubectl-patch to UpgradeCompleted) on fulfilled ProvisioningRequests",
        pr_upgrade_durations)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
