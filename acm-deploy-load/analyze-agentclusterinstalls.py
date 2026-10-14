#!/usr/bin/env python3
#
# Analyze AgentClusterInstalls data on a hub cluster to determine count/min/avg/max/50p/95p/99p timings
#
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

import argparse
from datetime import datetime, timedelta
import json
from utils.command import command
from utils.output import log_write, write_stats_block
from utils.time_utils import parse_ts, compute_duration
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
      description="Analyze AgentClusterInstalls data",
      prog="analyze-agentclusterinstalls.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-o", "--offline-process", action="store_true", default=False,
                      help="Uses previously stored raw data")
  parser.add_argument("-r", "--raw-data-file", type=str, default="",
                    help="Set raw json data file for offline processing. Empty finds last file")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  logger.info("Analyze agentclusterinstalls")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")

  raw_data_file = "{}/agentclusterinstalls-{}.json".format(cliargs.results_directory, ts)
  if cliargs.offline_process:
    if cliargs.raw_data_file == "":
      dir_scan = sorted([ f.path for f in os.scandir(cliargs.results_directory) if f.is_file() and f.name.startswith("agentclusterinstalls-") and f.name.endswith(".json") ])
      if len(dir_scan) == 0:
        logger.error("No previous offline file found. Exiting")
        sys.exit(1)
      raw_data_file = dir_scan[-1]
    else:
      raw_data_file = cliargs.raw_data_file
    logger.info("Reading raw data from: {}".format(raw_data_file))
  else:
    logger.info("Storing raw data file at: {}".format(raw_data_file))

  aci_csv_file = "{}/agentclusterinstalls-{}.csv".format(cliargs.results_directory, ts)
  aci_stats_file = "{}/agentclusterinstalls-{}.stats".format(cliargs.results_directory, ts)

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "agentclusterinstalls", "-A", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-agentclusterinstalls, oc get agentclusterinstalls rc: {}".format(rc))
      sys.exit(1)
    with open(raw_data_file, "w") as aci_data_file:
      aci_data_file.write(output)
  with open(raw_data_file, "r") as aci_file_data:
    aci_data = json.load(aci_file_data)

  logger.info("Writing CSV: {}".format(aci_csv_file))
  with open(aci_csv_file, "w") as csv_file:
    csv_file.write("name,status,creationTimestamp,completed.lastTransitionTime,duration\n")

  aci_installcompleted_values = []
  fleet_earliest_creation = None
  fleet_latest_completion = None
  total_count = 0
  skipped_count = 0

  for item in aci_data["items"]:
    aci_name = item["metadata"]["name"]
    if aci_name == "local-agent-cluster-cluster-install":
      logger.info("analyze-agentclusterinstalls, Skipping local-agent-cluster-cluster-install")
      skipped_count += 1
      continue
    if aci_name == "local-cluster":
      logger.info("analyze-agentclusterinstalls, Skipping local-cluster")
      skipped_count += 1
      continue

    total_count += 1

    aci_status = "unknown"
    ct_raw = item.get("metadata", {}).get("creationTimestamp", "")
    aci_creationTimestamp = parse_ts(ct_raw)
    if aci_creationTimestamp == "":
      logger.warning("ACI: {}, missing or invalid creationTimestamp '{}', skipping".format(aci_name, ct_raw))
      continue

    aci_completed_ltt = ""
    for condition in item.get("status", {}).get("conditions", []):
      if condition.get("type") == "Completed":
        if condition.get("status") == "True":
          aci_completed_ltt = parse_ts(condition.get("lastTransitionTime", ""))
        aci_status = condition.get("reason", "unknown")
        break

    aci_duration = compute_duration(aci_completed_ltt, aci_creationTimestamp)

    # Fleet tracking
    if fleet_earliest_creation is None or aci_creationTimestamp < fleet_earliest_creation:
      fleet_earliest_creation = aci_creationTimestamp

    if aci_status == "InstallationCompleted" and aci_completed_ltt != "":
      if fleet_latest_completion is None or aci_completed_ltt > fleet_latest_completion:
        fleet_latest_completion = aci_completed_ltt
      # Exclude values of 0
      if aci_duration > 0:
        aci_installcompleted_values.append(aci_duration)

    logger.info("{}, {}, {}, {}, {}".format(aci_name, aci_status, aci_creationTimestamp, aci_completed_ltt, aci_duration))

    with open(aci_csv_file, "a") as csv_file:
      csv_file.write("{},{},{},{},{}\n".format(aci_name, aci_status, aci_creationTimestamp, aci_completed_ltt, aci_duration))

  logger.info("Writing Stats: {}".format(aci_stats_file))

  with open(aci_stats_file, "w") as stats_file:
    log_write(stats_file, "Fleet AgentClusterInstall Summary")
    if fleet_earliest_creation is not None:
      log_write(stats_file, "Earliest creationTimestamp: {}".format(fleet_earliest_creation))
    if fleet_earliest_creation is not None and fleet_latest_completion is not None:
      log_write(stats_file, "Latest completion: {}".format(fleet_latest_completion))
      fleet_duration = (fleet_latest_completion - fleet_earliest_creation).total_seconds()
      log_write(stats_file, "Fleet Duration: {}s :: {}".format(fleet_duration, timedelta(seconds=fleet_duration)))
    log_write(stats_file, "Total AgentClusterInstalls: {}".format(total_count))
    log_write(stats_file, "Skipped (local-cluster, local-agent-cluster-cluster-install): {}".format(skipped_count))
    log_write(stats_file, "InstallationCompleted: {}".format(len(aci_installcompleted_values)))
    write_stats_block(stats_file,
        "Stats only on AgentClusterInstall CRs in InstallationCompleted", aci_installcompleted_values)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
