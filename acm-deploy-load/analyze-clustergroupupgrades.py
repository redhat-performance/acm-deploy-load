#!/usr/bin/env python3
#
# Analyze ClusterGroupUpgrades data on a hub cluster to determine count/min/avg/max/50p/95p/99p timings
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
from datetime import datetime
from datetime import timedelta
import json
from utils.command import command
from utils.output import log_write
from utils.talm import detect_talm_minor
import logging
import numpy as np
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze ClusterGroupUpgrades data",
      prog="analyze-clustergroupupgrades.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/mno/kubeconfig",
                      help="Changes which kubeconfig to connect to the hub cluster")
  parser.add_argument("-n", "--namespace", type=str, default="ztp-install", help="Namespace of the CGUs to analyze")
  parser.add_argument("-p", "--display-precache", action="store_true", default=False, help="Display each CGU precache duration")
  parser.add_argument("-b", "--display-backup", action="store_true", default=False, help="Display each CGU backup duration")
  parser.add_argument("--talm-version", type=str, default="4.14",
                      help="The version of talm to fall back on in event we can not detect the talm version")
  cliargs = parser.parse_args()

  logger.info("Analyze clustergroupupgrades")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  cgu_csv_file = "{}/clustergroupupgrades-{}-{}.csv".format(cliargs.results_directory, cliargs.namespace, ts)
  cgu_stats_file = "{}/clustergroupupgrades-{}-{}.stats".format(cliargs.results_directory, cliargs.namespace, ts)

  # Detect TALM version
  talm_minor = int(detect_talm_minor(cliargs.kubeconfig, cliargs.talm_version))
  logger.info("Using TALM cgu analysis based on TALM minor version: {}".format(talm_minor))

  oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "get", "clustergroupupgrades", "-n", cliargs.namespace, "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-clustergroupupgrades, oc get clustergroupupgrades -n {} rc: {}".format(cliargs.namespace, rc))
    sys.exit(1)
  cgu_data = json.loads(output)

  cgus_total = 0
  cgu_lc_skipped = False
  cgu_conditions = {}
  cgus_create_time = ""
  cgus_precache_time = ""
  cgus_started_time = ""
  cgus_completed_time = ""
  cgu_precaching_durations = []
  cgu_backup_durations = []
  cgu_succeeded_durations = []

  logger.info("Writing CSV: {}".format(cgu_csv_file))
  with open(cgu_csv_file, "w") as csv_file:
    csv_file.write("name,status,creationTimestamp,precacheCompleted,precacheDuration,startedAt,backupCompleted,backupDuration,completedAt,duration\n")

  for item in cgu_data["items"]:
    cgu_name = item["metadata"]["name"]
    if cgu_name.lower() == "local-cluster":
      logger.info("Skipping local-cluster")
      cgu_lc_skipped = True
      continue
    cgus_total += 1
    cgu_status = "unknown"

    # Determine earliest creationTimestamp for the cgus in this namespace
    cgu_created = datetime.strptime(item["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    if cgus_create_time == "":
      cgus_create_time = cgu_created
    elif cgus_create_time > cgu_created:
      logger.info("Replacing cgu created time {} with earlier time {}".format(cgus_create_time, cgu_created))
      cgus_create_time = cgu_created

    precache_ltt = ""
    backup_ltt = ""
    cgu_startedAt = ""
    cgu_completedAt = ""
    cgu_precache_duration = 0
    cgu_backup_duration = 0
    cgu_duration = 0
    if "startedAt" in item["status"]["status"]:
      # Determine earliest startedAt time for the cgus in this namespace
      cgu_startedAt = datetime.strptime(item["status"]["status"]["startedAt"], "%Y-%m-%dT%H:%M:%SZ")
      if cgus_started_time == "":
        cgus_started_time = cgu_startedAt
      elif cgus_started_time > cgu_startedAt:
        logger.info("Replacing cgu started time {} with earlier time {}".format(cgus_started_time, cgu_startedAt))
        cgus_started_time = cgu_startedAt
    if "completedAt" in item["status"]["status"]:
      # Determine latest populated completed time
      cgu_completedAt = datetime.strptime(item["status"]["status"]["completedAt"], "%Y-%m-%dT%H:%M:%SZ")
      if cgus_completed_time == "":
        cgus_completed_time = cgu_completedAt
      elif cgus_completed_time < cgu_completedAt:
        logger.info("Replacing cgu completed time {} with later time {}".format(cgus_completed_time, cgu_completedAt))
        cgus_completed_time = cgu_completedAt
      cgu_duration = (cgu_completedAt - cgu_startedAt).total_seconds()

    if "conditions" in item["status"]:
      for condition in item["status"]["conditions"]:
        if talm_minor >= 12:
          if "type" in condition:
            if (condition["type"] == "Progressing" and condition["status"] == "False"
                and condition["reason"] != "Completed" and condition["reason"] != "TimedOut"):
              cgu_status = "NotStarted"
            if (condition["type"] == "PrecachingSuceeded" and condition["status"] == "True" and
                (condition["reason"] == "PrecachingCompleted" or condition["reason"] == "PartiallyDone")):
              precache_ltt = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
              if cgus_precache_time == "":
                cgus_precache_time = precache_ltt
              elif cgus_precache_time < precache_ltt:
                logger.info("Replacing cgu precaching succeeded time {} with later time {}".format(cgus_precache_time, precache_ltt))
                cgus_precache_time = precache_ltt
              cgu_precache_duration = (precache_ltt - cgu_created).total_seconds()
              cgu_precaching_durations.append(cgu_precache_duration)

            if (condition["type"] == "BackupSuceeded" and condition["status"] == "True" and
                (condition["reason"] == "BackupCompleted" or condition["reason"] == "PartiallyDone")):
              backup_ltt = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
              cgu_backup_duration = (backup_ltt - cgu_startedAt).total_seconds()
              cgu_backup_durations.append(cgu_backup_duration)

            if condition["type"] == "Progressing" and condition["status"] == "True" and condition["reason"] == "InProgress":
              cgu_status = "InProgress"
            if condition["type"] == "Succeeded" and condition["status"] == "False" and condition["reason"] == "TimedOut":
              cgu_status = "TimedOut"
            if condition["type"] == "Succeeded" and condition["status"] == "True" and condition["reason"] == "Completed":
              cgu_status = "Completed"
              cgu_succeeded_durations.append(cgu_duration)
            if cgu_status != "unknown":
              if cgu_status not in cgu_conditions:
                cgu_conditions[cgu_status] = 1
              else:
                cgu_conditions[cgu_status] += 1
              break
        else:
          if condition["reason"] not in cgu_conditions:
            cgu_conditions[condition["reason"]] = 1
          else:
            cgu_conditions[condition["reason"]] += 1
          if condition["type"] == "Ready":
            if condition["status"] == "True":
              if "completedAt" in item["status"]["status"]:
                # Determine latest populated completed time
                cgu_completedAt = datetime.strptime(item["status"]["status"]["completedAt"], "%Y-%m-%dT%H:%M:%SZ")
                if cgus_completed_time == "":
                  cgus_completed_time = cgu_completedAt
                elif cgus_completed_time < cgu_completedAt:
                  logger.info("Replacing cgu completed time {} with later time {}".format(cgus_completed_time, cgu_completedAt))
                  cgus_completed_time = cgu_completedAt
            cgu_status = condition["reason"]
          elif condition["type"] == "PrecachingDone":
            precache_ltt = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
            if cgus_precache_time == "":
              cgus_precache_time = precache_ltt
            elif cgus_precache_time < precache_ltt:
              logger.info("Replacing cgu precaching done time {} with later time {}".format(cgus_precache_time, precache_ltt))
              cgus_precache_time = precache_ltt
            cgu_precache_duration = (cgus_precache_time - cgu_created).total_seconds()
            cgu_precaching_durations.append(cgu_precache_duration)

          if cgu_status == "UpgradeCompleted" and cgu_startedAt != "" and cgu_completedAt != "":
            cgu_duration = (cgu_completedAt - cgu_startedAt).total_seconds()
            cgu_succeeded_durations.append(cgu_duration)
    else:
      logger.warning("Missing conditions from status in CGU {}".format(cgu_name))
    # logger.info("{},{},{},{},{}".format(cgu_name, cgu_status, cgu_startedAt, cgu_completedAt, cgu_duration))

    with open(cgu_csv_file, "a") as csv_file:
      csv_file.write("{},{},{},{},{},{},{},{},{},{}\n".format(cgu_name, cgu_status, cgu_created, precache_ltt, cgu_precache_duration, cgu_startedAt, backup_ltt, cgu_backup_duration, cgu_completedAt, cgu_duration))

  logger.info("Writing Stats: {}".format(cgu_stats_file))

  duration_create_start = (cgus_started_time - cgus_create_time).total_seconds()
  if cgus_precache_time != "":
    duration_create_precache = (cgus_precache_time - cgus_create_time).total_seconds()
  if cgus_completed_time == "":
    duration_start_completed = 0
    duration_create_completed = 0
  else:
    duration_start_completed = (cgus_completed_time - cgus_started_time).total_seconds()
    duration_create_completed = (cgus_completed_time - cgus_create_time).total_seconds()

  with open(cgu_stats_file, "w") as stats_file:
    log_write(stats_file, "#############################################")
    log_write(stats_file, "Stats on clustergroupupgrades CRs in namespace {}".format(cliargs.namespace))
    log_write(stats_file, "Total CGUs - {}".format(cgus_total))
    if cgu_lc_skipped:
      log_write(stats_file, "Skipped local-cluster CGU")
    for condition in cgu_conditions:
      log_write(stats_file, "CGUs with {}: {} - {}%".format(condition, cgu_conditions[condition], round((cgu_conditions[condition] / cgus_total) * 100, 1)))
    log_write(stats_file, "Earliest CGU creationTimestamp: {}".format(cgus_create_time))
    if cgus_precache_time != "":
      log_write(stats_file, "Latest PrecachingSuceeded / PrecachingDone lastTransitionTime: {}".format(cgus_precache_time))
    log_write(stats_file, "Earliest CGU startedAt Timestamp: {}".format(cgus_started_time))
    log_write(stats_file, "Latest CGU completedAt Timestamp: {}".format(cgus_completed_time))
    log_write(stats_file, "Duration between creation and startedAt: {}s :: {}".format(duration_create_start, str(timedelta(seconds=duration_create_start))))
    if cgus_precache_time != "":
      log_write(stats_file, "Duration between creation and precaching succeeded/done: {}s :: {}".format(duration_create_precache, str(timedelta(seconds=duration_create_precache))))
    log_write(stats_file, "Duration between startedAt and completedAt: {}s :: {}".format(duration_start_completed, str(timedelta(seconds=duration_start_completed))))
    log_write(stats_file, "Duration between creation and completedAt: {}s :: {}".format(duration_create_completed, str(timedelta(seconds=duration_create_completed))))

    if len(cgu_precaching_durations) > 0:
      log_write(stats_file, "#############################################")
      log_write(stats_file, "Stats on clustergroupupgrades CRs with PrecachingSuceeded / PrecachingDone condition")
      log_write(stats_file, "Count: {}".format(len(cgu_precaching_durations)))
      log_write(stats_file, "Min: {}".format(np.min(cgu_precaching_durations)))
      log_write(stats_file, "Average: {}".format(round(np.mean(cgu_precaching_durations), 1)))
      log_write(stats_file, "50 percentile: {}".format(round(np.percentile(cgu_precaching_durations, 50), 1)))
      log_write(stats_file, "95 percentile: {}".format(round(np.percentile(cgu_precaching_durations, 95), 1)))
      log_write(stats_file, "99 percentile: {}".format(round(np.percentile(cgu_precaching_durations, 99), 1)))
      log_write(stats_file, "Max: {}".format(np.max(cgu_precaching_durations)))
      if cliargs.display_precache:
        for index, duration in enumerate(cgu_precaching_durations):
          log_write(stats_file, "Collected CGU {}, Precache Duration: {}s :: {}".format(index, duration, str(timedelta(seconds=duration))))

    if len(cgu_backup_durations) > 0:
      log_write(stats_file, "#############################################")
      log_write(stats_file, "Stats on clustergroupupgrades CRs with BackupSuceeded condition")
      log_write(stats_file, "Count: {}".format(len(cgu_backup_durations)))
      log_write(stats_file, "Min: {}".format(np.min(cgu_backup_durations)))
      log_write(stats_file, "Average: {}".format(round(np.mean(cgu_backup_durations), 1)))
      log_write(stats_file, "50 percentile: {}".format(round(np.percentile(cgu_backup_durations, 50), 1)))
      log_write(stats_file, "95 percentile: {}".format(round(np.percentile(cgu_backup_durations, 95), 1)))
      log_write(stats_file, "99 percentile: {}".format(round(np.percentile(cgu_backup_durations, 99), 1)))
      log_write(stats_file, "Max: {}".format(np.max(cgu_backup_durations)))
      if cliargs.display_backup:
        for index, duration in enumerate(cgu_backup_durations):
          log_write(stats_file, "Collected CGU {}, Backup Duration: {}s :: {}".format(index, duration, str(timedelta(seconds=duration))))

    log_write(stats_file, "#############################################")
    log_write(stats_file, "Stats only on clustergroupupgrades CRs with Succeeded / UpgradeCompleted condition")
    log_write(stats_file, "Count: {}".format(len(cgu_succeeded_durations)))
    if len(cgu_succeeded_durations) > 0:
      log_write(stats_file, "Min: {}".format(np.min(cgu_succeeded_durations)))
      log_write(stats_file, "Average: {}".format(round(np.mean(cgu_succeeded_durations), 1)))
      log_write(stats_file, "50 percentile: {}".format(round(np.percentile(cgu_succeeded_durations, 50), 1)))
      log_write(stats_file, "95 percentile: {}".format(round(np.percentile(cgu_succeeded_durations, 95), 1)))
      log_write(stats_file, "99 percentile: {}".format(round(np.percentile(cgu_succeeded_durations, 99), 1)))
      log_write(stats_file, "Max: {}".format(np.max(cgu_succeeded_durations)))

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
