#!/usr/bin/env python3
#
# Analyze ImageClusterInstalls data on a hub cluster to determine count/min/avg/max/50p/95p/99p timings
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
      description="Analyze ImageClusterInstalls data",
      prog="analyze-imageclusterinstalls.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-o", "--offline-process", action="store_true", default=False,
                      help="Uses previously stored raw data")
  parser.add_argument("-r", "--raw-data-file", type=str, default="",
                    help="Set raw json data file for offline processing. Empty finds last file")
  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  logger.info("Analyze imageclusterinstalls")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")

  raw_data_file = "{}/imageclusterinstalls-{}.json".format(cliargs.results_directory, ts)
  if cliargs.offline_process:
    if cliargs.raw_data_file == "":
      dir_scan = sorted([ f.path for f in os.scandir(cliargs.results_directory) if f.is_file() and f.name.startswith("imageclusterinstalls-") and f.name.endswith(".json") ])
      if len(dir_scan) == 0:
        logger.error("No previous offline file found. Exiting")
        sys.exit(1)
      raw_data_file = dir_scan[-1]
    else:
      raw_data_file = cliargs.raw_data_file
    logger.info("Reading raw data from: {}".format(raw_data_file))
  else:
    logger.info("Storing raw data file at: {}".format(raw_data_file))

  ici_csv_file = "{}/imageclusterinstalls-{}.csv".format(cliargs.results_directory, ts)
  ici_stats_file = "{}/imageclusterinstalls-{}.stats".format(cliargs.results_directory, ts)

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "imageclusterinstalls", "-A", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-imageclusterinstalls, oc get imageclusterinstalls rc: {}".format(rc))
      sys.exit(1)
    with open(raw_data_file, "w") as ici_data_file:
      ici_data_file.write(output)
  with open(raw_data_file, "r") as ici_file_data:
    ici_data = json.load(ici_file_data)

  logger.info("Writing CSV: {}".format(ici_csv_file))
  with open(ici_csv_file, "w") as csv_file:
    csv_file.write("name,status,creationTimestamp,bootTime,RequirementsMet.lastTransitionTime,"
        "completed.lastTransitionTime,ct_boot_duration,boot_rm_duration,rm_completed_duration,"
        "total_duration\n")

  ici_installcompleted_values = []
  fleet_earliest_creation = None
  fleet_latest_completion = None
  total_count = 0

  for item in ici_data["items"]:
    ici_name = item["metadata"]["name"]
    total_count += 1

    ici_status = "unknown"
    ct_raw = item.get("metadata", {}).get("creationTimestamp", "")
    ici_creationTimestamp = parse_ts(ct_raw)
    if ici_creationTimestamp == "":
      logger.warning("ICI: {}, missing or invalid creationTimestamp '{}', skipping".format(ici_name, ct_raw))
      continue

    # Fleet start tracks all hosts with a valid creationTimestamp, even those skipped for missing bootTime
    if fleet_earliest_creation is None or ici_creationTimestamp < fleet_earliest_creation:
      fleet_earliest_creation = ici_creationTimestamp

    boot_raw = item.get("status", {}).get("bootTime", "")
    ici_boot_ts = parse_ts(boot_raw)
    if ici_boot_ts == "":
      logger.warning("ICI: {}, missing or invalid bootTime '{}', skipping".format(ici_name, boot_raw))
      continue

    ici_requirements_met_ts = ""
    ici_completed_ts = ""
    for condition in item.get("status", {}).get("conditions", []):
      if condition.get("type") == "RequirementsMet" and condition.get("status") == "True":
        ici_requirements_met_ts = parse_ts(condition.get("lastTransitionTime", ""))
      elif condition.get("type") == "Completed" and condition.get("status") == "True":
        ici_completed_ts = parse_ts(condition.get("lastTransitionTime", ""))
        ici_status = condition.get("reason", "unknown")
        break

    ici_ct_boot_duration = compute_duration(ici_boot_ts, ici_creationTimestamp)
    ici_boot_rm_duration = compute_duration(ici_requirements_met_ts, ici_boot_ts)
    ici_rm_completed_duration = compute_duration(ici_completed_ts, ici_requirements_met_ts)
    ici_total_duration = compute_duration(ici_completed_ts, ici_creationTimestamp)

    if ici_status == "ClusterInstallationSucceeded" and ici_completed_ts != "":
      if fleet_latest_completion is None or ici_completed_ts > fleet_latest_completion:
        fleet_latest_completion = ici_completed_ts
      # Include durations of 0, those are installs completing within timestamp granularity
      if has_duration(ici_completed_ts, ici_creationTimestamp) and ici_total_duration >= 0:
        ici_installcompleted_values.append(ici_total_duration)

    logger.debug("{}, {}, {}, {}, {}, {}".format(ici_name, ici_status, ici_creationTimestamp,
        ici_boot_ts, ici_requirements_met_ts, ici_completed_ts))

    with open(ici_csv_file, "a") as csv_file:
      csv_file.write(
          "{},{},{},{},{},{},{},{},{},{}\n".format(ici_name, ici_status, ici_creationTimestamp,
          ici_boot_ts, ici_requirements_met_ts, ici_completed_ts, ici_ct_boot_duration,
          ici_boot_rm_duration, ici_rm_completed_duration, ici_total_duration))

  logger.info("Writing Stats: {}".format(ici_stats_file))

  with open(ici_stats_file, "w") as stats_file:
    log_write(stats_file, "Fleet ImageClusterInstall Summary")
    if fleet_earliest_creation is not None:
      log_write(stats_file, "Earliest creationTimestamp: {}".format(fleet_earliest_creation))
    if fleet_earliest_creation is not None and fleet_latest_completion is not None:
      log_write(stats_file, "Latest completion: {}".format(fleet_latest_completion))
      fleet_duration = (fleet_latest_completion - fleet_earliest_creation).total_seconds()
      log_write(stats_file, "Fleet Duration: {}s :: {}".format(fleet_duration, timedelta(seconds=fleet_duration)))
    log_write(stats_file, "Total ImageClusterInstalls: {}".format(total_count))
    log_write(stats_file, "ClusterInstallationSucceeded: {}".format(len(ici_installcompleted_values)))
    write_stats_block(stats_file,
        "Stats only on ImageClusterInstalls CRs in ClusterInstallationSucceeded", ici_installcompleted_values)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
