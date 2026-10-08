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
from datetime import datetime
from datetime import timedelta
import json
from utils.command import command
from utils.output import log_write
import logging
import numpy as np
import os
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def write_stats_block(stats_file, label, durations):
  stats_count = len(durations)
  stats_min = 0
  stats_avg = 0
  stats_50p = 0
  stats_95p = 0
  stats_99p = 0
  stats_max = 0
  if stats_count > 0:
    stats_min = np.min(durations)
    stats_avg = round(np.mean(durations), 1)
    stats_50p = round(np.percentile(durations, 50), 1)
    stats_95p = round(np.percentile(durations, 95), 1)
    stats_99p = round(np.percentile(durations, 99), 1)
    stats_max = np.max(durations)
  log_write(stats_file, label)
  log_write(stats_file, "Count: {}".format(stats_count))
  log_write(stats_file, "Min: {}".format(stats_min))
  log_write(stats_file, "Average: {}".format(stats_avg))
  log_write(stats_file, "50 percentile: {}".format(stats_50p))
  log_write(stats_file, "95 percentile: {}".format(stats_95p))
  log_write(stats_file, "99 percentile: {}".format(stats_99p))
  log_write(stats_file, "Max: {}".format(stats_max))


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze ProvisioningRequest data",
      prog="analyze-provisioningrequests.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-o", "--offline-process", action="store_true", default=False,
                      help="Uses previously stored raw data")
  parser.add_argument("-r", "--raw-data-file", type=str, default="",
                    help="Set raw json data file for offline processing. Empty finds last file")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

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
    oc_cmd = ["oc", "get", "provisioningrequests.clcm.openshift.io", "-o", "json"]
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
        "pr_ct_prv_duration,pr_prv_cir_duration,pr_cir_crc_duration,"
        "pr_crc_nar_duration,pr_nar_hp_duration,pr_hp_hnca_duration,"
        "pr_hnca_cip_duration,pr_cip_cp_duration,pr_cp_ca_duration,"
        "total_duration\n")

  pr_total_durations = []
  pr_preprocessing_durations = []
  pr_hw_provisioning_durations = []
  pr_cluster_provisioning_durations = []
  pr_configuration_durations = []
  fleet_earliest_creation = None
  fleet_latest_fulfilled = None

  for item in pr_data["items"]:
    pr_name = item["metadata"]["name"]
    ct_raw = item.get("metadata", {}).get("creationTimestamp", "")
    if ct_raw == "":
      logger.warning("PR: {}, missing creationTimestamp, skipping".format(pr_name))
      continue
    try:
      pr_creationTimestamp = datetime.strptime(ct_raw, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
      logger.warning("PR: {}, malformed creationTimestamp '{}', skipping".format(pr_name, ct_raw))
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

    if "status" in item and "conditions" in item["status"]:
      for condition in item["status"]["conditions"]:
        if "type" in condition and "status" in condition:
          ltt = condition.get("lastTransitionTime", "")
          if condition["status"] != "True" or ltt == "":
            continue
          try:
            parsed_ts = datetime.strptime(ltt, "%Y-%m-%dT%H:%M:%SZ")
          except ValueError:
            logger.warning("PR: {}, malformed lastTransitionTime '{}' in condition {}".format(
                pr_name, ltt, condition["type"]))
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
        else:
          logger.warning("PR: {}, 'type' or 'status' missing in condition: {}".format(pr_name, condition))
    else:
      logger.warning("status or conditions not found in provisioningrequest object: {}".format(pr_name))

    logger.info("{}, {}, {}, {}".format(pr_name, pr_cluster_name, pr_status, pr_creationTimestamp))

    # Compute interval durations
    if pr_validated_ts != "":
      pr_ct_prv_duration = (pr_validated_ts - pr_creationTimestamp).total_seconds()
    else:
      pr_ct_prv_duration = 0
    if pr_validated_ts != "" and pr_ci_rendered_ts != "":
      pr_prv_cir_duration = (pr_ci_rendered_ts - pr_validated_ts).total_seconds()
    else:
      pr_prv_cir_duration = 0
    if pr_ci_rendered_ts != "" and pr_resources_created_ts != "":
      pr_cir_crc_duration = (pr_resources_created_ts - pr_ci_rendered_ts).total_seconds()
    else:
      pr_cir_crc_duration = 0
    if pr_resources_created_ts != "" and pr_nar_rendered_ts != "":
      pr_crc_nar_duration = (pr_nar_rendered_ts - pr_resources_created_ts).total_seconds()
    else:
      pr_crc_nar_duration = 0
    if pr_nar_rendered_ts != "" and pr_hw_provisioned_ts != "":
      pr_nar_hp_duration = (pr_hw_provisioned_ts - pr_nar_rendered_ts).total_seconds()
    else:
      pr_nar_hp_duration = 0
    if pr_hw_provisioned_ts != "" and pr_hw_config_applied_ts != "":
      pr_hp_hnca_duration = (pr_hw_config_applied_ts - pr_hw_provisioned_ts).total_seconds()
    else:
      pr_hp_hnca_duration = 0
    if pr_hw_config_applied_ts != "" and pr_ci_processed_ts != "":
      pr_hnca_cip_duration = (pr_ci_processed_ts - pr_hw_config_applied_ts).total_seconds()
    else:
      pr_hnca_cip_duration = 0
    if pr_ci_processed_ts != "" and pr_cluster_provisioned_ts != "":
      pr_cip_cp_duration = (pr_cluster_provisioned_ts - pr_ci_processed_ts).total_seconds()
    else:
      pr_cip_cp_duration = 0
    if pr_cluster_provisioned_ts != "" and pr_config_applied_ts != "":
      pr_cp_ca_duration = (pr_config_applied_ts - pr_cluster_provisioned_ts).total_seconds()
    else:
      pr_cp_ca_duration = 0
    if pr_config_applied_ts != "":
      total_duration = (pr_config_applied_ts - pr_creationTimestamp).total_seconds()
    else:
      total_duration = 0

    if fleet_earliest_creation is None or pr_creationTimestamp < fleet_earliest_creation:
      fleet_earliest_creation = pr_creationTimestamp
    if pr_status == "fulfilled" and pr_config_applied_ts != "":
      if fleet_latest_fulfilled is None or pr_config_applied_ts > fleet_latest_fulfilled:
        fleet_latest_fulfilled = pr_config_applied_ts

    if pr_status == "fulfilled" and total_duration > 0:
      pr_total_durations.append(total_duration)
    if pr_ci_processed_ts != "" and pr_validated_ts != "":
      preprocessing_duration = (pr_ci_processed_ts - pr_creationTimestamp).total_seconds()
      if pr_status == "fulfilled" and preprocessing_duration > 0:
        pr_preprocessing_durations.append(preprocessing_duration)
    if pr_nar_hp_duration > 0 and pr_status == "fulfilled":
      pr_hw_provisioning_durations.append(pr_nar_hp_duration)
    if pr_cip_cp_duration > 0 and pr_status == "fulfilled":
      pr_cluster_provisioning_durations.append(pr_cip_cp_duration)
    if pr_cp_ca_duration > 0 and pr_status == "fulfilled":
      pr_configuration_durations.append(pr_cp_ca_duration)

    with open(pr_csv_file, "a") as csv_file:
      csv_file.write(
          "{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
          pr_name, pr_cluster_name, pr_status, pr_creationTimestamp,
          pr_validated_ts, pr_ci_rendered_ts, pr_resources_created_ts,
          pr_nar_rendered_ts, pr_hw_provisioned_ts, pr_hw_config_applied_ts,
          pr_ci_processed_ts, pr_cluster_provisioned_ts, pr_config_applied_ts,
          pr_ct_prv_duration, pr_prv_cir_duration, pr_cir_crc_duration,
          pr_crc_nar_duration, pr_nar_hp_duration, pr_hp_hnca_duration,
          pr_hnca_cip_duration, pr_cip_cp_duration, pr_cp_ca_duration,
          total_duration))

  logger.info("Writing Stats: {}".format(pr_stats_file))

  with open(pr_stats_file, "w") as stats_file:
    if fleet_earliest_creation is not None and fleet_latest_fulfilled is not None:
      fleet_duration = (fleet_latest_fulfilled - fleet_earliest_creation).total_seconds()
      log_write(stats_file, "Fleet Provisioning Summary")
      log_write(stats_file, "Earliest creationTimestamp: {}".format(fleet_earliest_creation))
      log_write(stats_file, "Latest fulfilled ConfigurationApplied: {}".format(fleet_latest_fulfilled))
      log_write(stats_file, "Fleet Duration: {}s :: {}".format(fleet_duration, timedelta(seconds=fleet_duration)))
      log_write(stats_file, "Total ProvisioningRequests: {}".format(len(pr_data["items"])))
      log_write(stats_file, "Fulfilled: {}".format(len(pr_total_durations)))
    write_stats_block(stats_file,
        "Total Duration Stats on ProvisioningRequests in fulfilled", pr_total_durations)
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

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
