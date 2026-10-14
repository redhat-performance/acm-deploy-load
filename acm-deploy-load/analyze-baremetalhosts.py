#!/usr/bin/env python3
#
# Analyze BareMetalHost data on a hub cluster to determine count/min/avg/max/50p/95p/99p timings
# for registration, inspection, and provisioning across inspect-only, IBI, and AI scenarios
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
      description="Analyze BareMetalHost data",
      prog="analyze-baremetalhosts.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-o", "--offline-process", action="store_true", default=False,
                      help="Uses previously stored raw data")
  parser.add_argument("-r", "--raw-data-file", type=str, default="",
                    help="Set raw json data file for offline processing. Empty finds last file")
  parser.add_argument("-s", "--skip-namespaces", type=str, default="openshift-machine-api",
                    help="Comma-separated namespaces to skip (e.g. hub nodes). Empty string to skip none")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  logger.info("Analyze baremetalhosts")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")

  skip_ns = set()
  if cliargs.skip_namespaces:
    skip_ns = set(ns.strip() for ns in cliargs.skip_namespaces.split(",") if ns.strip())

  raw_data_file = "{}/baremetalhosts-{}.json".format(cliargs.results_directory, ts)
  if cliargs.offline_process:
    if cliargs.raw_data_file == "":
      dir_scan = sorted([ f.path for f in os.scandir(cliargs.results_directory) if f.is_file() and f.name.startswith("baremetalhosts-") and f.name.endswith(".json") ])
      if len(dir_scan) == 0:
        logger.error("No previous offline file found. Exiting")
        sys.exit(1)
      raw_data_file = dir_scan[-1]
    else:
      raw_data_file = cliargs.raw_data_file
    logger.info("Reading raw data from: {}".format(raw_data_file))
  else:
    logger.info("Storing raw data file at: {}".format(raw_data_file))

  bmh_csv_file = "{}/baremetalhosts-{}.csv".format(cliargs.results_directory, ts)
  bmh_stats_file = "{}/baremetalhosts-{}.stats".format(cliargs.results_directory, ts)

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "baremetalhosts", "-A", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-baremetalhosts, oc get baremetalhosts rc: {}".format(rc))
      sys.exit(1)
    with open(raw_data_file, "w") as bmh_data_file:
      bmh_data_file.write(output)
  with open(raw_data_file, "r") as bmh_file_data:
    bmh_data = json.load(bmh_file_data)

  logger.info("Writing CSV: {}".format(bmh_csv_file))
  with open(bmh_csv_file, "w") as csv_file:
    csv_file.write("namespace,name,scenario,provisioning_state,creationTimestamp,"
        "register_start,register_end,inspect_start,inspect_end,"
        "provision_start,provision_end,deprovision_start,deprovision_end,"
        "lastUpdated,"
        "Ready_ltt,AvailableForProvisioning_ltt,Healthy_ltt,"
        "Manageable_ltt,Progressing_ltt,Provisioned_ltt,"
        "register_duration,inspect_duration,provision_duration,deprovision_duration,"
        "ct_register_start,register_inspect_gap,inspect_provision_gap,"
        "total_duration\n")

  register_durations = []
  inspect_durations = []
  ct_inspected_durations = []
  ai_provision_durations = []
  ai_total_durations = []
  ibi_total_durations = []
  fleet_earliest_creation = None
  fleet_latest_completion = None
  total_count = 0
  inspect_count = 0
  ibi_count = 0
  ai_count = 0
  skipped_count = 0

  for item in bmh_data["items"]:
    bmh_namespace = item["metadata"]["namespace"]
    bmh_name = item["metadata"]["name"]

    if bmh_namespace in skip_ns:
      skipped_count += 1
      continue

    total_count += 1

    ct_raw = item.get("metadata", {}).get("creationTimestamp", "")
    if ct_raw == "":
      logger.warning("BMH: {}/{}, missing creationTimestamp, skipping".format(bmh_namespace, bmh_name))
      continue
    bmh_ct = parse_ts(ct_raw)
    if bmh_ct == "":
      logger.warning("BMH: {}/{}, malformed creationTimestamp '{}', skipping".format(bmh_namespace, bmh_name, ct_raw))
      continue

    provisioning_state = item.get("status", {}).get("provisioning", {}).get("state", "unknown")

    op_hist = item.get("status", {}).get("operationHistory", {})
    register_start = parse_ts(op_hist.get("register", {}).get("start"))
    register_end = parse_ts(op_hist.get("register", {}).get("end"))
    inspect_start = parse_ts(op_hist.get("inspect", {}).get("start"))
    inspect_end = parse_ts(op_hist.get("inspect", {}).get("end"))
    provision_start = parse_ts(op_hist.get("provision", {}).get("start"))
    provision_end = parse_ts(op_hist.get("provision", {}).get("end"))
    deprovision_start = parse_ts(op_hist.get("deprovision", {}).get("start"))
    deprovision_end = parse_ts(op_hist.get("deprovision", {}).get("end"))

    last_updated = item.get("status", {}).get("lastUpdated", "")

    # Extract condition lastTransitionTimes
    condition_ltts = {
      "Ready": "",
      "AvailableForProvisioning": "",
      "Healthy": "",
      "Manageable": "",
      "Progressing": "",
      "Provisioned": "",
    }
    if "status" in item and "conditions" in item["status"]:
      for condition in item["status"]["conditions"]:
        c_type = condition.get("type", "")
        if c_type in condition_ltts:
          condition_ltts[c_type] = condition.get("lastTransitionTime", "")

    provisioned_ltt = parse_ts(condition_ltts["Provisioned"])

    # Auto-detect scenario
    if provision_start != "":
      scenario = "ai"
      ai_count += 1
    elif item.get("spec", {}).get("externallyProvisioned", False):
      scenario = "ibi"
      ibi_count += 1
    else:
      scenario = "inspect"
      inspect_count += 1

    # Compute durations
    register_duration = compute_duration(register_end, register_start)
    inspect_duration = compute_duration(inspect_end, inspect_start)
    provision_duration = compute_duration(provision_end, provision_start)
    deprovision_duration = compute_duration(deprovision_end, deprovision_start)
    ct_register_start_duration = compute_duration(register_start, bmh_ct)
    register_inspect_gap = compute_duration(inspect_start, register_end)
    inspect_provision_gap = compute_duration(provision_start, inspect_end)

    total_duration = 0
    if scenario == "ai" and provisioning_state == "provisioned" and provision_end != "":
      total_duration = compute_duration(provision_end, bmh_ct)
    elif scenario == "ibi" and provisioning_state == "externally provisioned" and provisioned_ltt != "":
      total_duration = compute_duration(provisioned_ltt, bmh_ct)
    elif scenario == "inspect" and provisioning_state == "available" and inspect_end != "":
      total_duration = compute_duration(inspect_end, bmh_ct)

    # Fleet tracking
    if fleet_earliest_creation is None or bmh_ct < fleet_earliest_creation:
      fleet_earliest_creation = bmh_ct

    completion_ts = ""
    if scenario == "ai" and provisioning_state == "provisioned" and provision_end != "":
      completion_ts = provision_end
    elif scenario == "ibi" and provisioning_state == "externally provisioned" and provisioned_ltt != "":
      completion_ts = provisioned_ltt
    elif scenario == "inspect" and provisioning_state == "available" and inspect_end != "":
      completion_ts = inspect_end
    if completion_ts != "":
      if fleet_latest_completion is None or completion_ts > fleet_latest_completion:
        fleet_latest_completion = completion_ts

    # Collect durations for stats
    if register_duration > 0:
      register_durations.append(register_duration)
    if inspect_duration > 0:
      inspect_durations.append(inspect_duration)
    ct_inspected = compute_duration(inspect_end, bmh_ct)
    if ct_inspected > 0:
      ct_inspected_durations.append(ct_inspected)
    if scenario == "ai" and provisioning_state == "provisioned" and provision_duration > 0:
      ai_provision_durations.append(provision_duration)
    if scenario == "ai" and provisioning_state == "provisioned" and total_duration > 0:
      ai_total_durations.append(total_duration)
    if scenario == "ibi" and provisioning_state == "externally provisioned" and total_duration > 0:
      ibi_total_durations.append(total_duration)

    logger.info("{}/{}, {}, {}, {}".format(bmh_namespace, bmh_name, scenario, provisioning_state, bmh_ct))

    with open(bmh_csv_file, "a") as csv_file:
      csv_file.write(
          "{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
          bmh_namespace, bmh_name, scenario, provisioning_state, bmh_ct,
          register_start, register_end, inspect_start, inspect_end,
          provision_start, provision_end, deprovision_start, deprovision_end,
          last_updated,
          condition_ltts["Ready"], condition_ltts["AvailableForProvisioning"],
          condition_ltts["Healthy"], condition_ltts["Manageable"],
          condition_ltts["Progressing"], condition_ltts["Provisioned"],
          register_duration, inspect_duration, provision_duration, deprovision_duration,
          ct_register_start_duration, register_inspect_gap, inspect_provision_gap,
          total_duration))

  logger.info("Writing Stats: {}".format(bmh_stats_file))

  with open(bmh_stats_file, "w") as stats_file:
    log_write(stats_file, "Fleet BareMetalHost Summary")
    if fleet_earliest_creation is not None:
      log_write(stats_file, "Earliest creationTimestamp: {}".format(fleet_earliest_creation))
    if fleet_earliest_creation is not None and fleet_latest_completion is not None:
      log_write(stats_file, "Latest completion: {}".format(fleet_latest_completion))
      fleet_duration = (fleet_latest_completion - fleet_earliest_creation).total_seconds()
      log_write(stats_file, "Fleet Duration: {}s :: {}".format(fleet_duration, timedelta(seconds=fleet_duration)))
    log_write(stats_file, "Total BareMetalHosts: {}".format(total_count))
    log_write(stats_file, "Skipped (hub namespaces): {}".format(skipped_count))
    log_write(stats_file, "Inspect-only: {}".format(inspect_count))
    log_write(stats_file, "IBI: {}".format(ibi_count))
    log_write(stats_file, "AI: {}".format(ai_count))
    write_stats_block(stats_file,
        "Registration Duration Stats on BareMetalHosts", register_durations)
    write_stats_block(stats_file,
        "Inspection Duration Stats on BareMetalHosts", inspect_durations)
    write_stats_block(stats_file,
        "Creation to Inspected Duration Stats on BareMetalHosts", ct_inspected_durations)
    if len(ai_provision_durations) > 0:
      write_stats_block(stats_file,
          "Provisioning Duration Stats (AI) on BareMetalHosts", ai_provision_durations)
      write_stats_block(stats_file,
          "Total Duration Stats (AI) on BareMetalHosts (creationTimestamp to provision.end)", ai_total_durations)
    if len(ibi_total_durations) > 0:
      write_stats_block(stats_file,
          "Total Duration Stats (IBI) on BareMetalHosts (creationTimestamp to Provisioned condition)", ibi_total_durations)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
