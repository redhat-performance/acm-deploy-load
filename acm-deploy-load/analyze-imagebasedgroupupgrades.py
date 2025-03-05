#!/usr/bin/env python3
#
# Analyze ImageBaseGroupUpgrade and ImageBasedUpgrade data on hub and spoke clusters to determine
# upgrade count/min/avg/max/50p/95p/99p timings and success rate
#
#  Copyright 2024 Red Hat
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
from collections import OrderedDict
from datetime import datetime
from datetime import timedelta
import json
import logging
import os
from pathlib import Path
from utils.command import command
from utils.output import assemble_stats
from utils.output import log_write
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze ImageBasedGroupUpgrade data",
      prog="analyze-imagebasedgroupupgrades.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("ocp_version", type=str, help="The expected version for clusters to have been upgraded to")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  parser.add_argument("-n", "--namespace", type=str, default="ztp-platform-upgrade", help="Namespace of the IBGUs to analyze")

  # IBGU analysis options only
  parser.add_argument("-i", "--ibgu-label", type=str, default="ibgu", help="Expected label to equal expected version for ibgu(s)")

  parser.add_argument("--offline-process", action="store_true", default=False, help="Uses previously stored raw data")
  parser.add_argument("--raw-data-directory", type=str, default="",
                    help="Set raw data directory for offline processing. Empty finds last directory")
  parser.add_argument("-k", "--kubeconfigs", type=str, default="/root/hv-vm/kc",
                      help="The location of the kubeconfigs, nested under each cluster's directory")
  parser.add_argument("-ni", "--no-ibu-analysis", action="store_true", default=False, help="Skip analyzing individual IBU objects")
  cliargs = parser.parse_args()

  ibu_analysis = not cliargs.no_ibu_analysis

  logger.info("Analyze imagebasedgroupupgrades")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  raw_data_dir = "{}/ibu-{}-ibgu-{}".format(cliargs.results_directory, cliargs.ocp_version, ts)
  if cliargs.offline_process:
    if cliargs.raw_data_directory == "":
      # Detect last raw data directory
      dir_scan = sorted([ f.path for f in os.scandir(cliargs.results_directory) if f.is_dir() and "ibu-{}-ibgu".format(cliargs.ocp_version) in f.path ])
      if len(dir_scan) == 0:
        logger.error("No previous offline directories found. Exiting")
        sys.exit(1)
      raw_data_dir = dir_scan[-1]
    else:
      raw_data_dir = cliargs.raw_data_directory
    logger.info("Reading raw data from: {}".format(raw_data_dir))
  else:
    Path(raw_data_dir).mkdir(parents=True, exist_ok=True)
    logger.info("Storing raw data in: {}".format(raw_data_dir))

  ibu_ibgu_csv_file = "{}/ibu-{}-ibgus-{}.csv".format(cliargs.results_directory, cliargs.ocp_version, ts)
  ibu_ibu_csv_file = "{}/ibu-{}-ibus-{}.csv".format(cliargs.results_directory, cliargs.ocp_version, ts)
  ibu_ibgu_stats_file = "{}/ibu-{}-ibgus-{}.stats".format(cliargs.results_directory, cliargs.ocp_version, ts)

  if not cliargs.offline_process:
    label_selector = "{}={}".format(cliargs.ibgu_label, cliargs.ocp_version)
    oc_cmd = ["oc", "get", "imagebasedgroupupgrades", "-n", cliargs.namespace, "-l", label_selector, "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-imagebasedgroupupgrade, oc get clustergroupupgrades -n {} -l {} rc: {}".format(cliargs.namespace, label_selector, cliargs.ocp_version, rc))
      sys.exit(1)
    with open("{}/ibgus.json".format(raw_data_dir), "w") as ibgu_data_file:
      ibgu_data_file.write(output)

  logger.info("Reading {}/ibgus.json".format(raw_data_dir))
  with open("{}/ibgus.json".format(raw_data_dir), "r") as ibgu_data_file:
    ibgu_data = json.load(ibgu_data_file)

  if len(ibgu_data["items"]) == 0:
    logger.error("No ibgu(s) to examine")
    sys.exit(1)

  earliest_PrepStartTime = ""
  latest_PrepCompletionTime = ""
  earliest_UpgradeStartTime = ""
  latest_UpgradeCompletionTime = ""
  ibgus = OrderedDict()
  ibus = []

  for item in ibgu_data["items"]:
    ibgu_name = item["metadata"]["name"]
    ibgus[ibgu_name] = {}
    ibgus[ibgu_name]["creationTimestamp"] = datetime.strptime(item["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    ibgus[ibgu_name]["completed_time"] = ""
    ibgus[ibgu_name]["completed_duration"] = 0
    ibgus[ibgu_name]["clusters"] = {}
    ibgus[ibgu_name]["prepDurations"] = []
    ibgus[ibgu_name]["upgradeDurations"] = []
    ibgus[ibgu_name]["rollbackDurations"] = []
    ibgus[ibgu_name]["earliestPrepStartTime"] = ""
    ibgus[ibgu_name]["latestPrepCompletionTime"] = ""
    ibgus[ibgu_name]["earliestUpgradeStartTime"] = ""
    ibgus[ibgu_name]["latestUpgradeCompletionTime"] = ""
    logger.info("Found: {}, {}".format(ibgu_name, ibgus[ibgu_name]["creationTimestamp"]))
    for cluster in item["status"]["clusters"]:
      cluster_name = cluster["name"]
      if cluster_name not in ibus:
        ibus.append(cluster_name)
      ibgus[ibgu_name]["clusters"][cluster_name] = {}
      ibgus[ibgu_name]["clusters"][cluster_name]["status"] = "Unknown"
      ibgus[ibgu_name]["clusters"][cluster_name]["prepStartTime"] = ""
      ibgus[ibgu_name]["clusters"][cluster_name]["prepCompletionTime"] = ""
      ibgus[ibgu_name]["clusters"][cluster_name]["prepDuration"] = 0
      ibgus[ibgu_name]["clusters"][cluster_name]["upgradeStartTime"] = ""
      ibgus[ibgu_name]["clusters"][cluster_name]["upgradeCompletionTime"] = ""
      ibgus[ibgu_name]["clusters"][cluster_name]["upgradeDuration"] = 0
      ibgus[ibgu_name]["clusters"][cluster_name]["rollbackStartTime"] = ""
      ibgus[ibgu_name]["clusters"][cluster_name]["rollbackCompletionTime"] = ""
      ibgus[ibgu_name]["clusters"][cluster_name]["rollbackDuration"] = 0
      if "completedActions" in cluster:
        for action in cluster["completedActions"]:
          if action["action"] == "Prep" and ibgus[ibgu_name]["clusters"][cluster_name]["status"] == "Unknown":
            ibgus[ibgu_name]["clusters"][cluster_name]["status"] = "prepared"
          elif action["action"] == "Upgrade":
            ibgus[ibgu_name]["clusters"][cluster_name]["status"] = "upgraded"
          elif action["action"] == "Rollback":
            ibgus[ibgu_name]["clusters"][cluster_name]["status"] = "rollback"
          else:
            logger.warning("New completed action: {}".format(action["action"]))
    for condition in item["status"]["conditions"]:
      # logger.info("Condition: {}".format(condition))
      if condition["type"] == "Progressing" and condition["status"] == "False" and condition["reason"] == "Completed":
        ibgus[ibgu_name]["completed_time"] = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
    if ibgus[ibgu_name]["completed_time"] != "":
      ibgus[ibgu_name]["completed_duration"] = (ibgus[ibgu_name]["completed_time"] - ibgus[ibgu_name]["creationTimestamp"]).total_seconds()

  ibus = sorted(ibus)

  if ibu_analysis:
    # Get individual cluster IBU data here
    for cluster in ibus:
      kubeconfig = "{}/{}/kubeconfig".format(cliargs.kubeconfigs, cluster)
      if not cliargs.offline_process:
        oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "ibu", "upgrade", "-o", "json"]
        rc, output = command(oc_cmd, False, retries=2, no_log=True)
        if rc != 0:
          logger.error("analyze-imagebasedgroupupgrade, oc get ibu rc: {}".format(rc))
          output = ""
        with open("{}/{}-ibu.json".format(raw_data_dir, cluster), "w") as ibu_data_file:
          ibu_data_file.write(output)

      if os.stat("{}/{}-ibu.json".format(raw_data_dir, cluster)).st_size == 0:
        ibu_data = ""
      else:
        with open("{}/{}-ibu.json".format(raw_data_dir, cluster), "r") as ibu_data_file:
          ibu_data = json.load(ibu_data_file)

      # Determine timestamps from conditions in IBU data
      ibu_prep_started_time = ""
      ibu_prep_completed_time = ""
      ibu_upgrade_started_time = ""
      ibu_upgrade_completed_time = ""
      ibu_rollback_started_time = ""
      ibu_rollback_completed_time = ""
      if "status" in ibu_data:
        if "history" in ibu_data["status"]:
          for item in ibu_data["status"]["history"]:
            if item["stage"] == "Prep":
              if "startTime" in item:
                ibu_prep_started_time = datetime.strptime(item["startTime"], "%Y-%m-%dT%H:%M:%SZ")
              if "completionTime" in item:
                ibu_prep_completed_time = datetime.strptime(item["completionTime"], "%Y-%m-%dT%H:%M:%SZ")
            elif item["stage"] == "Upgrade":
              if "startTime" in item:
                ibu_upgrade_started_time = datetime.strptime(item["startTime"], "%Y-%m-%dT%H:%M:%SZ")
              if "completionTime" in item:
                ibu_upgrade_completed_time = datetime.strptime(item["completionTime"], "%Y-%m-%dT%H:%M:%SZ")
            elif item["stage"] == "Rollback":
              if "startTime" in item:
                ibu_rollback_started_time = datetime.strptime(item["startTime"], "%Y-%m-%dT%H:%M:%SZ")
              if "completionTime" in item:
                ibu_rollback_completed_time = datetime.strptime(item["completionTime"], "%Y-%m-%dT%H:%M:%SZ")
        else:
          logger.error("History key missing in ibu, check LCA version (Must be 4.17 or newer)")
          # No longer exit on missing history key
          # sys.exit(1)

      # Match timestamps from IBU data to the correct cluster
      cluster_found = False
      for ibgu in ibgus:
        if cluster in ibgus[ibgu]["clusters"]:
          cluster_found = True
          ibgus[ibgu]["clusters"][cluster]["prepStartTime"] = ibu_prep_started_time
          ibgus[ibgu]["clusters"][cluster]["prepCompletionTime"] = ibu_prep_completed_time
          if ibu_prep_started_time != "" and ibu_prep_completed_time != "":
            ibgus[ibgu]["clusters"][cluster]["prepDuration"] = (ibu_prep_completed_time - ibu_prep_started_time).total_seconds()
            ibgus[ibgu]["prepDurations"].append(ibgus[ibgu]["clusters"][cluster]["prepDuration"])
            if ibgus[ibgu]["earliestPrepStartTime"] == "":
              ibgus[ibgu]["earliestPrepStartTime"] = ibu_prep_started_time
            elif ibu_prep_started_time < ibgus[ibgu]["earliestPrepStartTime"]:
              ibgus[ibgu]["earliestPrepStartTime"] = ibu_prep_started_time
            if ibgus[ibgu]["latestPrepCompletionTime"] == "":
              ibgus[ibgu]["latestPrepCompletionTime"] = ibu_prep_completed_time
            elif ibu_prep_completed_time > ibgus[ibgu]["latestPrepCompletionTime"]:
              ibgus[ibgu]["latestPrepCompletionTime"] = ibu_prep_completed_time
            if earliest_PrepStartTime == "":
              earliest_PrepStartTime = ibu_prep_started_time
              logger.info("Set earliest_PrepStartTime: {}".format(earliest_PrepStartTime))
            elif ibu_prep_started_time < earliest_PrepStartTime:
              earliest_PrepStartTime = ibu_prep_started_time
              logger.info("Adjusted earliest_PrepStartTime: {}".format(earliest_PrepStartTime))
            if latest_PrepCompletionTime == "":
              latest_PrepCompletionTime = ibu_prep_completed_time
              logger.info("Set latest_PrepCompletionTime: {}".format(latest_PrepCompletionTime))
            elif ibu_prep_completed_time > latest_PrepCompletionTime:
              latest_PrepCompletionTime = ibu_prep_completed_time
              logger.info("Adjusted latest_PrepCompletionTime: {}".format(latest_PrepCompletionTime))
          ibgus[ibgu]["clusters"][cluster]["upgradeStartTime"] = ibu_upgrade_started_time
          ibgus[ibgu]["clusters"][cluster]["upgradeCompletionTime"] = ibu_upgrade_completed_time
          if ibu_upgrade_started_time != "" and ibu_upgrade_completed_time != "":
            ibgus[ibgu]["clusters"][cluster]["upgradeDuration"] = (ibu_upgrade_completed_time - ibu_upgrade_started_time).total_seconds()
            ibgus[ibgu]["upgradeDurations"].append(ibgus[ibgu]["clusters"][cluster]["upgradeDuration"])
            if ibgus[ibgu]["earliestUpgradeStartTime"] == "":
              ibgus[ibgu]["earliestUpgradeStartTime"] = ibu_upgrade_started_time
            elif ibu_upgrade_started_time < ibgus[ibgu]["earliestUpgradeStartTime"]:
              ibgus[ibgu]["earliestUpgradeStartTime"] = ibu_upgrade_started_time
            if ibgus[ibgu]["latestUpgradeCompletionTime"] == "":
              ibgus[ibgu]["latestUpgradeCompletionTime"] = ibu_upgrade_completed_time
            elif ibu_upgrade_completed_time > ibgus[ibgu]["latestUpgradeCompletionTime"]:
              ibgus[ibgu]["latestUpgradeCompletionTime"] = ibu_upgrade_completed_time
            if earliest_UpgradeStartTime == "":
              earliest_UpgradeStartTime = ibu_upgrade_started_time
              logger.info("Set earliest_UpgradeStartTime: {}".format(earliest_UpgradeStartTime))
            elif ibu_upgrade_started_time < earliest_UpgradeStartTime:
              earliest_UpgradeStartTime = ibu_upgrade_started_time
              logger.info("Adjusted earliest_UpgradeStartTime: {}".format(earliest_UpgradeStartTime))
            if latest_UpgradeCompletionTime == "":
              latest_UpgradeCompletionTime = ibu_upgrade_completed_time
              logger.info("Set latest_UpgradeCompletionTime: {}".format(latest_UpgradeCompletionTime))
            elif ibu_upgrade_completed_time > latest_UpgradeCompletionTime:
              latest_UpgradeCompletionTime = ibu_upgrade_completed_time
              logger.info("Adjusted latest_UpgradeCompletionTime: {}".format(latest_UpgradeCompletionTime))
          ibgus[ibgu]["clusters"][cluster]["rollbackStartTime"] = ibu_rollback_started_time
          ibgus[ibgu]["clusters"][cluster]["rollbackCompletionTime"] = ibu_rollback_completed_time
          if ibu_rollback_started_time != "" and ibu_rollback_completed_time != "":
            ibgus[ibgu]["clusters"][cluster]["rollbackDuration"] = (ibu_rollback_completed_time - ibu_rollback_started_time).total_seconds()
            ibgus[ibgu]["rollbackDurations"].append(ibgus[ibgu]["clusters"][cluster]["rollbackDuration"])
        if cluster_found:
          break

  # Write the IBGU data to a CSV
  logger.info("Writing CSV: {}".format(ibu_ibgu_csv_file))
  with open(ibu_ibgu_csv_file, "a") as csv_file:
    csv_file.write("name,creationTimestamp,completed_time,completed_duration,clusters,prepared,upgraded,rollbacked\n")
    for ibgu in ibgus:
      clusters = len(ibgus[ibgu]["clusters"])
      prepared = len(ibgus[ibgu]["prepDurations"])
      upgraded = len(ibgus[ibgu]["upgradeDurations"])
      rollbacked = len(ibgus[ibgu]["rollbackDurations"])
      csv_file.write("{},{},{},{},{},{},{},{}\n".format(ibgu, ibgus[ibgu]["creationTimestamp"], ibgus[ibgu]["completed_time"], ibgus[ibgu]["completed_duration"], clusters, prepared, upgraded, rollbacked))

  # Write the IBU data to a CSV
  logger.info("Writing CSV: {}".format(ibu_ibu_csv_file))
  with open(ibu_ibu_csv_file, "a") as csv_file:
    csv_file.write("name,ibgu,status,prepStartTime,prepCompletionTime,prepDuration,upgradeStartTime,upgradeCompletionTime,upgradeDuration,rollbackStartTime,rollbackCompletionTime,rollbackDuration,\n")
    for ibgu in ibgus:
      for cluster in ibgus[ibgu]["clusters"]:
        c_data = ibgus[ibgu]["clusters"][cluster]
        csv_file.write("{},{},{},{},{},{},{},{},{},{},{},{}\n".format(cluster, ibgu, c_data["status"], c_data["prepStartTime"], c_data["prepCompletionTime"], c_data["prepDuration"], c_data["upgradeStartTime"], c_data["upgradeCompletionTime"], c_data["upgradeDuration"], c_data["rollbackStartTime"], c_data["rollbackCompletionTime"], c_data["rollbackDuration"]))

  # Display summary of the collected IBGU and IBU data
  logger.info("Writing Stats: {}".format(ibu_ibgu_stats_file))
  with open(ibu_ibgu_stats_file, "w") as stats_file:
    log_write(stats_file, "##########################################################################################")
    log_write(stats_file, "Stats on imagebasedgroupupgrade CRs in namespace {}".format(cliargs.namespace))
    log_write(stats_file, "Expected OCP Version {}".format(cliargs.ocp_version))
    log_write(stats_file, "Total IBGUs: {}".format(len(ibgus)))
    total_clusters = 0
    total_prep_duration = 0
    total_upgrade_duration = 0
    if earliest_PrepStartTime != "" and latest_PrepCompletionTime != "":
      total_prep_duration = (latest_PrepCompletionTime - earliest_PrepStartTime).total_seconds()
    if earliest_UpgradeStartTime != "" and latest_UpgradeCompletionTime != "":
      total_upgrade_duration = (latest_UpgradeCompletionTime - earliest_UpgradeStartTime).total_seconds()
    all_prepDurations = []
    all_upgradeDurations = []
    all_rollbackDurations = []
    for ibgu in ibgus:
      total_clusters += len(ibgus[ibgu]["clusters"])
      all_prepDurations.extend(ibgus[ibgu]["prepDurations"])
      all_upgradeDurations.extend(ibgus[ibgu]["upgradeDurations"])
      all_rollbackDurations.extend(ibgus[ibgu]["rollbackDurations"])
    log_write(stats_file, "Total Clusters: {}, Prepared: {}, Upgraded: {}, Rollbacks: {}".format(total_clusters, len(all_prepDurations), len(all_upgradeDurations), len(all_rollbackDurations)))
    log_write(stats_file, "(IBU) All IBGU Prepare Actions")
    log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(all_prepDurations)))
    log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(all_prepDurations, False)))
    log_write(stats_file, "(IBU) Earliest Prep Start Time: {}".format(earliest_PrepStartTime))
    log_write(stats_file, "(IBU) Latest Prep Completion Time: {}".format(latest_PrepCompletionTime))
    log_write(stats_file, "(IBU) Total Prep Duration Time: {}s :: {}".format(total_prep_duration, str(timedelta(seconds=total_prep_duration))))
    log_write(stats_file, "(IBU) All IBGU Upgrade Actions")
    log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(all_upgradeDurations)))
    log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(all_upgradeDurations, False)))
    log_write(stats_file, "(IBU) Earliest Upgrade Start Time: {}".format(earliest_UpgradeStartTime))
    log_write(stats_file, "(IBU) Latest Upgrade Completion Time: {}".format(latest_UpgradeCompletionTime))
    log_write(stats_file, "(IBU) Total Upgrade Duration Time: {}s :: {}".format(total_upgrade_duration, str(timedelta(seconds=total_upgrade_duration))))
    log_write(stats_file, "(IBU) All IBGU Rollback Actions")
    log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(all_rollbackDurations)))
    log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(all_rollbackDurations, False)))
    log_write(stats_file, "##########################################################################################")
    for ibgu in ibgus:
      ibgu_prep_duration = 0
      ibgu_upgrade_duration = 0
      if ibgus[ibgu]["earliestPrepStartTime"] != "" and ibgus[ibgu]["latestPrepCompletionTime"] != "":
        ibgu_prep_duration = (ibgus[ibgu]["latestPrepCompletionTime"] - ibgus[ibgu]["earliestPrepStartTime"]).total_seconds()
      if ibgus[ibgu]["earliestUpgradeStartTime"] != "" and ibgus[ibgu]["latestUpgradeCompletionTime"] != "":
        ibgu_upgrade_duration = (ibgus[ibgu]["latestUpgradeCompletionTime"] - ibgus[ibgu]["earliestUpgradeStartTime"]).total_seconds()
      log_write(stats_file, "IBGU: {}".format(ibgu))
      log_write(stats_file, "Clusters: {}, Prepared: {}, Upgraded: {}, Rollbacks: {}".format(len(ibgus[ibgu]["clusters"]), len(ibgus[ibgu]["prepDurations"]), len(ibgus[ibgu]["upgradeDurations"]), len(ibgus[ibgu]["rollbackDurations"])))
      log_write(stats_file, "creationTimestamp: {}".format(ibgus[ibgu]["creationTimestamp"]))
      log_write(stats_file, "completed_time: {}".format(ibgus[ibgu]["completed_time"]))
      log_write(stats_file, "Duration: {}s :: {}".format(ibgus[ibgu]["completed_duration"], str(timedelta(seconds=ibgus[ibgu]["completed_duration"]))))
      log_write(stats_file, "(IBU) Prepare Action")
      log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(ibgus[ibgu]["prepDurations"])))
      log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(ibgus[ibgu]["prepDurations"], False)))
      log_write(stats_file, "(IBU) Earliest Prepare Action Start Time: {}".format(ibgus[ibgu]["earliestPrepStartTime"]))
      log_write(stats_file, "(IBU) Latest Prepare Action Completion Time: {}".format(ibgus[ibgu]["latestPrepCompletionTime"]))
      log_write(stats_file, "(IBU) Total Prepare Action Duration Time: {}s :: {}".format(ibgu_prep_duration, str(timedelta(seconds=ibgu_prep_duration))))
      log_write(stats_file, "(IBU) Upgrade Action")
      log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(ibgus[ibgu]["upgradeDurations"])))
      log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(ibgus[ibgu]["upgradeDurations"], False)))
      log_write(stats_file, "(IBU) Earliest Upgrade Action Start Time: {}".format(ibgus[ibgu]["earliestUpgradeStartTime"]))
      log_write(stats_file, "(IBU) Latest Upgrade Action Completion Time: {}".format(ibgus[ibgu]["latestUpgradeCompletionTime"]))
      log_write(stats_file, "(IBU) Total Upgrade Action Duration Time: {}s :: {}".format(ibgu_upgrade_duration, str(timedelta(seconds=ibgu_upgrade_duration))))
      log_write(stats_file, "(IBU) Rollback Action")
      log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(ibgus[ibgu]["rollbackDurations"])))
      log_write(stats_file, "(IBU) Recorded Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(ibgus[ibgu]["rollbackDurations"], False)))
      log_write(stats_file, "##########################################################################################")

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
