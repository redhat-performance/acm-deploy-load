#!/usr/bin/env python3
#
# Analyze per-cluster ImageBasedUpgrade data from O-Cloud Manager SNO upgrades.
#
# Clusters are discovered from ProvisioningRequests on the hub. Per-stage timing
# (Prep / Upgrade and their sub-phases) is read from each spoke's `ibu upgrade`
# object. Produces per-cluster CSV and fleet percentile stats.
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
from collections import OrderedDict
from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path
from utils.command import command
from utils.ibu import fetch_spoke_ibu, parse_ibu_history
from utils.output import log_write, write_stats_block
from utils.time_utils import parse_ts, compute_duration, has_duration
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def get_phase_times(phases, phase_name):
  """Return (start, completion) for a named phase from a parsed history phases list."""
  for p in phases:
    if p["phase"] == phase_name:
      return p["start"], p["completion"]
  return "", ""


def extract_ibu_patch_time(item):
  """Return the IBU trigger timestamp from annotation (preferred) or kubectl-patch managedField."""
  ts = parse_ts(item.get("metadata", {}).get("annotations", {}).get("ibu-patch-time", ""))
  if ts != "":
    return ts
  for mf in item.get("metadata", {}).get("managedFields", []):
    if mf.get("manager") == "kubectl-patch" and mf.get("operation") == "Update":
      if "f:templateVersion" in mf.get("fieldsV1", {}).get("f:spec", {}):
        parsed = parse_ts(mf.get("time", ""))
        if parsed != "":
          return parsed
  return ""


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze O-Cloud IBU upgrade timing from ProvisioningRequests and spoke IBU objects",
      prog="analyze-ocloud-ibu.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("ocp_version", type=str, help="Upgrade target OCP version (e.g. 4.22.3)")
  parser.add_argument("results_directory", type=str, help="Directory to place analyzed data")
  parser.add_argument("-o", "--offline-process", action="store_true", default=False,
                      help="Use previously stored raw data")
  parser.add_argument("-r", "--raw-data-directory", type=str, default="",
                      help="Raw data directory for offline processing; empty = auto-detect last")
  parser.add_argument("-k", "--kubeconfigs", type=str, default="/root/hv-vm/kc",
                      help="Base directory containing per-cluster kubeconfig subdirectories")
  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Enable debug logging")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  logger.info("Analyze O-Cloud IBU upgrades")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  raw_data_dir = "{}/ocloud-ibu-{}-{}".format(cliargs.results_directory, cliargs.ocp_version, ts)

  if cliargs.offline_process:
    if cliargs.raw_data_directory == "":
      dir_scan = sorted([
          f.path for f in os.scandir(cliargs.results_directory)
          if f.is_dir() and "ocloud-ibu-{}-".format(cliargs.ocp_version) in f.path
      ])
      if len(dir_scan) == 0:
        logger.error("No previous raw data directories found. Exiting")
        sys.exit(1)
      raw_data_dir = dir_scan[-1]
    else:
      raw_data_dir = cliargs.raw_data_directory
    logger.info("Reading raw data from: {}".format(raw_data_dir))
  else:
    Path(raw_data_dir).mkdir(parents=True, exist_ok=True)
    logger.info("Storing raw data in: {}".format(raw_data_dir))

  pr_json_file = "{}/provisioningrequests.json".format(raw_data_dir)
  csv_file = "{}/ocloud-ibu-{}-{}.csv".format(cliargs.results_directory, cliargs.ocp_version, ts)
  stats_file = "{}/ocloud-ibu-{}-{}.stats".format(cliargs.results_directory, cliargs.ocp_version, ts)

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "provisioningrequests.clcm.openshift.io", "--show-managed-fields=true", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-ocloud-ibu, oc get provisioningrequests rc: {}".format(rc))
      sys.exit(1)
    with open(pr_json_file, "w") as f:
      f.write(output)

  with open(pr_json_file, "r") as f:
    pr_data = json.load(f)

  # Build ordered cluster map from PRs
  clusters = OrderedDict()
  for item in pr_data["items"]:
    pr_name = item["metadata"]["name"]
    ct_raw = item.get("metadata", {}).get("creationTimestamp", "")
    pr_created = parse_ts(ct_raw)
    if pr_created == "":
      logger.warning("PR: {}, missing or invalid creationTimestamp, skipping".format(pr_name))
      continue

    cluster_name = ""
    if "status" in item and "extensions" in item["status"]:
      cluster_name = item["status"]["extensions"].get("clusterDetails", {}).get("name", "")
    if cluster_name == "":
      cluster_name = item.get("spec", {}).get("templateParameters", {}).get(
          "clusterInstanceParameters", {}).get("clusterName", "")
    if cluster_name == "":
      logger.warning("PR: {}, cannot determine cluster name, skipping".format(pr_name))
      continue

    pr_status = "unknown"
    if "status" in item and "provisioningStatus" in item["status"]:
      pr_status = item["status"]["provisioningStatus"].get("provisioningPhase", "unknown")

    pr_upgrade_completed = ""
    if "status" in item and "conditions" in item["status"]:
      for condition in item["status"]["conditions"]:
        if condition.get("type") == "UpgradeCompleted" and condition.get("status") == "True":
          pr_upgrade_completed = parse_ts(condition.get("lastTransitionTime", ""))

    ibu_patch_time = extract_ibu_patch_time(item)
    pr_upgrade_duration = compute_duration(pr_upgrade_completed, ibu_patch_time)

    clusters[cluster_name] = {
        "pr_name": pr_name,
        "pr_status": pr_status,
        "ibu_patch_time": ibu_patch_time,
        "pr_upgrade_completed": pr_upgrade_completed,
        "pr_upgrade_duration": pr_upgrade_duration,
        # IBU spoke data (populated below)
        "prep_start": "", "prep_completion": "", "prep_duration": 0,
        "prep_stateroot_start": "", "prep_stateroot_completion": "", "prep_stateroot_duration": 0,
        "prep_precache_start": "", "prep_precache_completion": "", "prep_precache_duration": 0,
        "upgrade_start": "", "upgrade_completion": "", "upgrade_duration": 0,
        "upgrade_prepivot_start": "", "upgrade_prepivot_completion": "", "upgrade_prepivot_duration": 0,
        "upgrade_postpivot_start": "", "upgrade_postpivot_completion": "", "upgrade_postpivot_duration": 0,
        "rollback_start": "", "rollback_completion": "", "rollback_duration": 0,
        "ibu_total_duration": 0,
    }
    logger.debug("PR: {}, cluster: {}, status: {}".format(pr_name, cluster_name, pr_status))

  logger.info("ProvisioningRequests: {} total, {} with cluster names".format(
      len(pr_data["items"]), len(clusters)))

  # Fleet accumulators
  fleet_earliest_patch = None
  fleet_latest_pr_upgrade = None
  fleet_earliest_prep_start = None
  fleet_latest_upgrade_completion = None

  pr_upgrade_durations = []
  prep_durations = []
  prep_stateroot_durations = []
  prep_precache_durations = []
  upgrade_durations = []
  upgrade_prepivot_durations = []
  upgrade_postpivot_durations = []
  rollback_durations = []
  ibu_total_durations = []

  logger.info("Querying spoke IBU objects for {} clusters".format(len(clusters)))
  for cluster_name in sorted(clusters):
    c = clusters[cluster_name]
    ibu_data = fetch_spoke_ibu(cluster_name, cliargs.kubeconfigs, raw_data_dir, cliargs.offline_process)
    history = parse_ibu_history(ibu_data)

    c["prep_start"] = history["Prep"]["start"]
    c["prep_completion"] = history["Prep"]["completion"]
    c["prep_duration"] = compute_duration(c["prep_completion"], c["prep_start"])

    ps, pc = get_phase_times(history["Prep"]["phases"], "Stateroot")
    c["prep_stateroot_start"] = ps
    c["prep_stateroot_completion"] = pc
    c["prep_stateroot_duration"] = compute_duration(pc, ps)

    ps, pc = get_phase_times(history["Prep"]["phases"], "Precache")
    c["prep_precache_start"] = ps
    c["prep_precache_completion"] = pc
    c["prep_precache_duration"] = compute_duration(pc, ps)

    c["upgrade_start"] = history["Upgrade"]["start"]
    c["upgrade_completion"] = history["Upgrade"]["completion"]
    c["upgrade_duration"] = compute_duration(c["upgrade_completion"], c["upgrade_start"])

    ps, pc = get_phase_times(history["Upgrade"]["phases"], "PrePivot")
    c["upgrade_prepivot_start"] = ps
    c["upgrade_prepivot_completion"] = pc
    c["upgrade_prepivot_duration"] = compute_duration(pc, ps)

    ps, pc = get_phase_times(history["Upgrade"]["phases"], "PostPivot")
    c["upgrade_postpivot_start"] = ps
    c["upgrade_postpivot_completion"] = pc
    c["upgrade_postpivot_duration"] = compute_duration(pc, ps)

    c["rollback_start"] = history["Rollback"]["start"]
    c["rollback_completion"] = history["Rollback"]["completion"]
    c["rollback_duration"] = compute_duration(c["rollback_completion"], c["rollback_start"])

    c["ibu_total_duration"] = compute_duration(c["upgrade_completion"], c["prep_start"])

    if has_duration(c["prep_completion"], c["prep_start"]) and c["prep_duration"] >= 0:
      prep_durations.append(c["prep_duration"])
    if has_duration(c["prep_stateroot_completion"], c["prep_stateroot_start"]) and c["prep_stateroot_duration"] >= 0:
      prep_stateroot_durations.append(c["prep_stateroot_duration"])
    if has_duration(c["prep_precache_completion"], c["prep_precache_start"]) and c["prep_precache_duration"] >= 0:
      prep_precache_durations.append(c["prep_precache_duration"])
    if has_duration(c["upgrade_completion"], c["upgrade_start"]) and c["upgrade_duration"] >= 0:
      upgrade_durations.append(c["upgrade_duration"])
    if has_duration(c["upgrade_prepivot_completion"], c["upgrade_prepivot_start"]) and c["upgrade_prepivot_duration"] >= 0:
      upgrade_prepivot_durations.append(c["upgrade_prepivot_duration"])
    if has_duration(c["upgrade_postpivot_completion"], c["upgrade_postpivot_start"]) and c["upgrade_postpivot_duration"] >= 0:
      upgrade_postpivot_durations.append(c["upgrade_postpivot_duration"])
    if has_duration(c["rollback_completion"], c["rollback_start"]) and c["rollback_duration"] >= 0:
      rollback_durations.append(c["rollback_duration"])
    if has_duration(c["upgrade_completion"], c["prep_start"]) and c["ibu_total_duration"] >= 0:
      ibu_total_durations.append(c["ibu_total_duration"])

    if c["prep_start"] != "":
      if fleet_earliest_prep_start is None or c["prep_start"] < fleet_earliest_prep_start:
        fleet_earliest_prep_start = c["prep_start"]
    if c["upgrade_completion"] != "":
      if fleet_latest_upgrade_completion is None or c["upgrade_completion"] > fleet_latest_upgrade_completion:
        fleet_latest_upgrade_completion = c["upgrade_completion"]

  for cluster_name, c in clusters.items():
    if has_duration(c["pr_upgrade_completed"], c["ibu_patch_time"]) and c["pr_upgrade_duration"] >= 0:
      pr_upgrade_durations.append(c["pr_upgrade_duration"])
    if c["ibu_patch_time"] != "":
      if fleet_earliest_patch is None or c["ibu_patch_time"] < fleet_earliest_patch:
        fleet_earliest_patch = c["ibu_patch_time"]
    if c["pr_upgrade_completed"] != "":
      if fleet_latest_pr_upgrade is None or c["pr_upgrade_completed"] > fleet_latest_pr_upgrade:
        fleet_latest_pr_upgrade = c["pr_upgrade_completed"]

  logger.info("Writing CSV: {}".format(csv_file))
  with open(csv_file, "w") as f:
    f.write("cluster_name,pr_name,pr_status,"
            "ibu_patch_time,pr_upgrade_completed,pr_upgrade_duration,"
            "prep_start,prep_completion,prep_duration,"
            "prep_stateroot_start,prep_stateroot_completion,prep_stateroot_duration,"
            "prep_precache_start,prep_precache_completion,prep_precache_duration,"
            "upgrade_start,upgrade_completion,upgrade_duration,"
            "upgrade_prepivot_start,upgrade_prepivot_completion,upgrade_prepivot_duration,"
            "upgrade_postpivot_start,upgrade_postpivot_completion,upgrade_postpivot_duration,"
            "rollback_start,rollback_completion,rollback_duration,"
            "ibu_total_duration\n")
    for cluster_name in sorted(clusters):
      c = clusters[cluster_name]
      f.write("{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
          cluster_name, c["pr_name"], c["pr_status"],
          c["ibu_patch_time"], c["pr_upgrade_completed"], c["pr_upgrade_duration"],
          c["prep_start"], c["prep_completion"], c["prep_duration"],
          c["prep_stateroot_start"], c["prep_stateroot_completion"], c["prep_stateroot_duration"],
          c["prep_precache_start"], c["prep_precache_completion"], c["prep_precache_duration"],
          c["upgrade_start"], c["upgrade_completion"], c["upgrade_duration"],
          c["upgrade_prepivot_start"], c["upgrade_prepivot_completion"], c["upgrade_prepivot_duration"],
          c["upgrade_postpivot_start"], c["upgrade_postpivot_completion"], c["upgrade_postpivot_duration"],
          c["rollback_start"], c["rollback_completion"], c["rollback_duration"],
          c["ibu_total_duration"]))

  logger.info("Writing Stats: {}".format(stats_file))
  with open(stats_file, "w") as sf:
    log_write(sf, "O-Cloud IBU Fleet Summary")
    log_write(sf, "Target OCP Version: {}".format(cliargs.ocp_version))
    log_write(sf, "Total ProvisioningRequests: {}".format(len(pr_data["items"])))
    log_write(sf, "Clusters identified: {}".format(len(clusters)))
    log_write(sf, "Clusters with UpgradeCompleted (PR): {}".format(len(pr_upgrade_durations)))
    if fleet_earliest_patch is not None:
      log_write(sf, "Earliest ibu-patch-time: {}".format(fleet_earliest_patch))
    if fleet_latest_pr_upgrade is not None:
      log_write(sf, "Latest UpgradeCompleted (PR): {}".format(fleet_latest_pr_upgrade))
    if fleet_earliest_patch is not None and fleet_latest_pr_upgrade is not None:
      fleet_pr_duration = compute_duration(fleet_latest_pr_upgrade, fleet_earliest_patch)
      if fleet_pr_duration >= 0:
        log_write(sf, "Fleet PR-based Upgrade Duration: {}s :: {}".format(
            fleet_pr_duration, timedelta(seconds=fleet_pr_duration)))
    log_write(sf, "Clusters with Prep timing (spoke IBU): {}".format(len(prep_durations)))
    log_write(sf, "Clusters with Upgrade timing (spoke IBU): {}".format(len(upgrade_durations)))
    log_write(sf, "Clusters with Rollback timing (spoke IBU): {}".format(len(rollback_durations)))
    if fleet_earliest_prep_start is not None:
      log_write(sf, "Earliest Prep startTime (spoke IBU): {}".format(fleet_earliest_prep_start))
    if fleet_latest_upgrade_completion is not None:
      log_write(sf, "Latest Upgrade completionTime (spoke IBU): {}".format(fleet_latest_upgrade_completion))
    if fleet_earliest_prep_start is not None and fleet_latest_upgrade_completion is not None:
      fleet_ibu_duration = compute_duration(fleet_latest_upgrade_completion, fleet_earliest_prep_start)
      if fleet_ibu_duration >= 0:
        log_write(sf, "Fleet Prep+Upgrade Duration (spoke IBU): {}s :: {}".format(
            fleet_ibu_duration, timedelta(seconds=fleet_ibu_duration)))
    write_stats_block(sf,
        "PR-based Upgrade Duration Stats (ibu-patch-time to UpgradeCompleted)",
        pr_upgrade_durations)
    write_stats_block(sf,
        "Prep Stage Stats (IBU startTime to completionTime)",
        prep_durations)
    write_stats_block(sf,
        "Prep Stateroot Phase Stats",
        prep_stateroot_durations)
    write_stats_block(sf,
        "Prep Precache Phase Stats",
        prep_precache_durations)
    write_stats_block(sf,
        "Upgrade Stage Stats (IBU startTime to completionTime)",
        upgrade_durations)
    write_stats_block(sf,
        "Upgrade PrePivot Phase Stats",
        upgrade_prepivot_durations)
    write_stats_block(sf,
        "Upgrade PostPivot Phase Stats",
        upgrade_postpivot_durations)
    if rollback_durations:
      write_stats_block(sf,
          "Rollback Stage Stats (IBU startTime to completionTime)",
          rollback_durations)
    write_stats_block(sf,
        "Total Per-Cluster Duration Stats (Prep startTime to Upgrade completionTime)",
        ibu_total_durations)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))


if __name__ == "__main__":
  sys.exit(main())
