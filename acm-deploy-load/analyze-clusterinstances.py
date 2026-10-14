#!/usr/bin/env python3
#
# Analyze ClusterInstance data on a hub cluster to determine count/min/avg/max/50p/95p/99p timings
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
      description="Analyze ClusterInstance data",
      prog="analyze-clusterinstances.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-o", "--offline-process", action="store_true", default=False,
                      help="Uses previously stored raw data")
  parser.add_argument("-r", "--raw-data-file", type=str, default="",
                    help="Set raw json data file for offline processing. Empty finds last file")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  logger.info("Analyze clusterinstances")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")

  raw_data_file = "{}/clusterinstances-{}.json".format(cliargs.results_directory, ts)
  if cliargs.offline_process:
    if cliargs.raw_data_file == "":
      dir_scan = sorted([ f.path for f in os.scandir(cliargs.results_directory) if f.is_file() and f.name.startswith("clusterinstances-") and f.name.endswith(".json") ])
      if len(dir_scan) == 0:
        logger.error("No previous offline file found. Exiting")
        sys.exit(1)
      raw_data_file = dir_scan[-1]
    else:
      raw_data_file = cliargs.raw_data_file
    logger.info("Reading raw data from: {}".format(raw_data_file))
  else:
    logger.info("Storing raw data file at: {}".format(raw_data_file))

  ci_csv_file = "{}/clusterinstances-{}.csv".format(cliargs.results_directory, ts)
  ci_stats_file = "{}/clusterinstances-{}.stats".format(cliargs.results_directory, ts)

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "clusterinstances", "-A", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-clusterinstances, oc get clusterinstances rc: {}".format(rc))
      sys.exit(1)
    with open(raw_data_file, "w") as ci_data_file:
      ci_data_file.write(output)
  with open(raw_data_file, "r") as ci_file_data:
    ci_data = json.load(ci_file_data)

  logger.info("Writing CSV: {}".format(ci_csv_file))
  with open(ci_csv_file, "w") as csv_file:
    csv_file.write("name,status,creationTimestamp,ClusterInstanceValidated.lastTransitionTime,"
        "RenderedTemplates.lastTransitionTime,RenderedTemplatesValidated.lastTransitionTime,"
        "RenderedTemplatesApplied.lastTransitionTime,Provisioned.lastTransitionTime,"
        "ci_ct_iv_duration,ci_iv_rt_duration,ci_rt_rtv_duration,ci_rtv_rta_duration,"
        "ci_rta_p_duration,total_duration\n")

  ci_instancevalidated_durations = []
  ci_provisioned_durations = []
  fleet_earliest_creation = None
  fleet_latest_provisioned = None
  total_count = 0

  for item in ci_data["items"]:
    ci_name = item["metadata"]["name"]
    total_count += 1

    ci_status = "unknown"
    ct_raw = item.get("metadata", {}).get("creationTimestamp", "")
    ci_creationTimestamp = parse_ts(ct_raw)
    if ci_creationTimestamp == "":
      logger.warning("CI: {}, missing or invalid creationTimestamp '{}', skipping".format(ci_name, ct_raw))
      continue

    ci_instancevalidated_ts = ""
    ci_renderedtemplates_ts = ""
    ci_renderedtemplatesvalidated_ts = ""
    ci_renderedtemplatesapplied_ts = ""
    ci_provisioned_ts = ""

    if "status" in item and "conditions" in item["status"]:
      for condition in item["status"]["conditions"]:
        if "type" in condition and "status" in condition:
          if condition["type"] == "ClusterInstanceValidated" and condition["status"] == "True":
            ci_instancevalidated_ts = parse_ts(condition.get("lastTransitionTime", ""))
          elif condition["type"] == "RenderedTemplates" and condition["status"] == "True":
            ci_renderedtemplates_ts = parse_ts(condition.get("lastTransitionTime", ""))
          elif condition["type"] == "RenderedTemplatesValidated" and condition["status"] == "True":
            ci_renderedtemplatesvalidated_ts = parse_ts(condition.get("lastTransitionTime", ""))
          elif condition["type"] == "RenderedTemplatesApplied" and condition["status"] == "True":
            ci_renderedtemplatesapplied_ts = parse_ts(condition.get("lastTransitionTime", ""))
          elif condition["type"] == "Provisioned" and condition["status"] == "True":
            ci_provisioned_ts = parse_ts(condition.get("lastTransitionTime", ""))
            ci_status = "Provisioned"
        else:
          logger.warning("CI: {}, 'type' or 'status' missing in condition: {}".format(ci_name, condition))
    else:
      logger.warning("status or conditions not found in clusterinstance object: {}".format(ci_name))

    ci_ct_iv_duration = compute_duration(ci_instancevalidated_ts, ci_creationTimestamp)
    ci_iv_rt_duration = compute_duration(ci_renderedtemplates_ts, ci_instancevalidated_ts)
    ci_rt_rtv_duration = compute_duration(ci_renderedtemplatesvalidated_ts, ci_renderedtemplates_ts)
    ci_rtv_rta_duration = compute_duration(ci_renderedtemplatesapplied_ts, ci_renderedtemplatesvalidated_ts)
    ci_rta_p_duration = compute_duration(ci_provisioned_ts, ci_renderedtemplatesapplied_ts)
    total_duration = compute_duration(ci_provisioned_ts, ci_creationTimestamp)

    # Fleet tracking
    if fleet_earliest_creation is None or ci_creationTimestamp < fleet_earliest_creation:
      fleet_earliest_creation = ci_creationTimestamp

    if ci_instancevalidated_ts != "" and ci_ct_iv_duration > 0:
      ci_instancevalidated_durations.append(ci_ct_iv_duration)

    if ci_status == "Provisioned" and ci_provisioned_ts != "":
      if fleet_latest_provisioned is None or ci_provisioned_ts > fleet_latest_provisioned:
        fleet_latest_provisioned = ci_provisioned_ts
      if total_duration > 0:
        ci_provisioned_durations.append(total_duration)

    logger.info("{}, {}, {}, {}, {}, {}, {}, {}".format(
        ci_name, ci_status, ci_creationTimestamp, ci_instancevalidated_ts, ci_renderedtemplates_ts,
        ci_renderedtemplatesvalidated_ts, ci_renderedtemplatesapplied_ts, ci_provisioned_ts))

    with open(ci_csv_file, "a") as csv_file:
      csv_file.write(
          "{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(ci_name, ci_status,
          ci_creationTimestamp, ci_instancevalidated_ts, ci_renderedtemplates_ts,
          ci_renderedtemplatesvalidated_ts, ci_renderedtemplatesapplied_ts, ci_provisioned_ts,
          ci_ct_iv_duration, ci_iv_rt_duration, ci_rt_rtv_duration, ci_rtv_rta_duration,
          ci_rta_p_duration, total_duration))

  logger.info("Writing Stats: {}".format(ci_stats_file))

  with open(ci_stats_file, "w") as stats_file:
    log_write(stats_file, "Fleet ClusterInstance Summary")
    if fleet_earliest_creation is not None:
      log_write(stats_file, "Earliest creationTimestamp: {}".format(fleet_earliest_creation))
    if fleet_earliest_creation is not None and fleet_latest_provisioned is not None:
      log_write(stats_file, "Latest Provisioned: {}".format(fleet_latest_provisioned))
      fleet_duration = (fleet_latest_provisioned - fleet_earliest_creation).total_seconds()
      log_write(stats_file, "Fleet Duration: {}s :: {}".format(fleet_duration, timedelta(seconds=fleet_duration)))
    log_write(stats_file, "Total ClusterInstances: {}".format(total_count))
    log_write(stats_file, "Provisioned: {}".format(len(ci_provisioned_durations)))
    write_stats_block(stats_file,
        "Stats on ClusterInstances CRs with CreationTimeStamp until InstanceValidated Timestamp",
        ci_instancevalidated_durations)
    write_stats_block(stats_file,
        "Total Duration Stats only on ClusterInstances CRs in Provisioned", ci_provisioned_durations)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
