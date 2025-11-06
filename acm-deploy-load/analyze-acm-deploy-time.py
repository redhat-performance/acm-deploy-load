#!/usr/bin/env python3
#
# Analyze monitor_data.csv from acm-deploy-load post run in order to determine deployment duration metrics and
# peak concurrencies
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
from csv import reader
from datetime import datetime
from datetime import timedelta
from utils.output import log_write
import logging
import pandas as pd
import pathlib
import sys
import time

# monitor_data.csv
# Index Column
# 0  date
# 1  cluster_applied
# 2  cluster_init
# 3  cluster_notstarted
# 4  node_booted
# 5  node_discovered
# 6  cluster_installing
# 7  cluster_install_failed
# 8  cluster_install_completed
# 9  managed
# 10 policy_init
# 11 policy_notstarted
# 12 policy_applying
# 13 policy_timedout
# 14 policy_compliant
# 15 playbook_notstarted
# 16 playbook_running
# 17 playbook_completed
INDEX_DATE = 0
INDEX_CLUSTER_APPLIED = 1
INDEX_CLUSTER_INSTALLING = 6
INDEX_CLUSTER_INSTALL_COMPLETED = 8
INDEX_POLICY_APPLYING = 12
INDEX_POLICY_TIMEDOUT = 13
INDEX_POLICY_COMPLIANT = 14
INDEX_PLAYBOOK_RUNNING = 16
INDEX_PLAYBOOK_COMPLETED = 17

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze monitor data to determine deployment duration metrics and peak concurrencies",
      prog="analyze-acm-deploy-time.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  # Name of csv file found in results directory
  parser.add_argument("--monitor-data-file-name", type=str, default="monitor_data.csv",
      help="The name of the monitor data csv file.")
  parser.add_argument("results_directory", type=str, help="The location of an acm-deploy-load results")
  cliargs = parser.parse_args()

  logger.info("ACM Deploy Time")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  md_csv_file = "{}/{}".format(cliargs.results_directory, cliargs.monitor_data_file_name)
  deploy_time_file = "{}/deploy-time-{}".format(cliargs.results_directory, ts)
  if not pathlib.Path(md_csv_file).is_file():
    logger.error("File not found: {}".format(md_csv_file))
    sys.exit(1)

  found_start_ts = False
  start_ts = ""
  peak_cluster_installing = 0
  peak_du_applying = 0
  peak_playbook_running = 0
  peak_concurrency = 0
  data = []
  with open(md_csv_file, "r") as cluster_cv_csv:
    csv_reader = reader(cluster_cv_csv)

    # Determine official "start time", peak concurrencies and read entire file into list
    # Remove the csv header first
    header = next(csv_reader)
    if header is not None:
      for row in csv_reader:
        row_ts = datetime.strptime(row[INDEX_DATE], "%Y-%m-%dT%H:%M:%SZ")
        concurrency = int(row[INDEX_CLUSTER_INSTALLING]) + int(row[INDEX_POLICY_APPLYING]) + int(row[INDEX_PLAYBOOK_RUNNING])
        if int(row[INDEX_CLUSTER_INSTALLING]) > peak_cluster_installing:
          peak_cluster_installing = int(row[INDEX_CLUSTER_INSTALLING])
        if int(row[INDEX_POLICY_APPLYING]) > peak_du_applying:
          peak_du_applying = int(row[INDEX_POLICY_APPLYING])
        if int(row[INDEX_PLAYBOOK_RUNNING]) > peak_playbook_running:
          peak_playbook_running = int(row[INDEX_PLAYBOOK_RUNNING])
        if concurrency > peak_concurrency:
          peak_concurrency = concurrency
        if (start_ts == "") and (int(row[INDEX_CLUSTER_APPLIED]) > 0):
          start_ts = row_ts
        data.append(row)

    cluster_installed = int(data[-1][INDEX_CLUSTER_INSTALL_COMPLETED])
    deployment_completed = int(data[-1][INDEX_POLICY_COMPLIANT])
    playbook_completed = int(data[-1][INDEX_PLAYBOOK_COMPLETED])
    cluster_completed = int(data[-1][INDEX_POLICY_TIMEDOUT]) + int(data[-1][INDEX_POLICY_COMPLIANT])

    last_ts = datetime.strptime(data[-1][INDEX_DATE], "%Y-%m-%dT%H:%M:%SZ")
    cluster_installed_ts = datetime.strptime(data[-1][INDEX_DATE], "%Y-%m-%dT%H:%M:%SZ")
    deployment_completed_ts = datetime.strptime(data[-1][INDEX_DATE], "%Y-%m-%dT%H:%M:%SZ")
    playbook_completed_ts = datetime.strptime(data[-1][INDEX_DATE], "%Y-%m-%dT%H:%M:%SZ")
    completed_ts = datetime.strptime(data[-1][INDEX_DATE], "%Y-%m-%dT%H:%M:%SZ")

  # Find when test is considered cluster install completed by first time we reach max clusters installed
  for row in reversed(data):
    if int(row[INDEX_CLUSTER_INSTALL_COMPLETED]) < cluster_installed:
      break
    cluster_installed_ts = datetime.strptime(row[INDEX_DATE], "%Y-%m-%dT%H:%M:%SZ")

  # Find when test is considered deployment completed by first time we reach max du compliant
  for row in reversed(data):
    if int(row[INDEX_POLICY_COMPLIANT]) < deployment_completed:
      break
    deployment_completed_ts = datetime.strptime(row[INDEX_DATE], "%Y-%m-%dT%H:%M:%SZ")

  # Find when test was completed with max du compliant+du_timeout reached
  for row in reversed(data):
    if (int(row[INDEX_POLICY_TIMEDOUT]) + int(row[INDEX_POLICY_COMPLIANT])) < cluster_completed:
      break
    completed_ts = datetime.strptime(row[INDEX_DATE], "%Y-%m-%dT%H:%M:%SZ")

  # Find when test is considered playbook completed by first time we reach max playbook completed
  for row in reversed(data):
    if (int(row[INDEX_PLAYBOOK_COMPLETED])) < playbook_completed:
      break
    playbook_completed_ts = datetime.strptime(row[INDEX_DATE], "%Y-%m-%dT%H:%M:%SZ")

  cluster_install_duration = int((cluster_installed_ts - start_ts).total_seconds())
  deployed_complete_duration = int((deployment_completed_ts - start_ts).total_seconds())
  completed_duration = int((completed_ts - start_ts).total_seconds())
  playbook_duration = int((playbook_completed_ts - start_ts).total_seconds())
  full_duration = int((last_ts - start_ts).total_seconds())

  with open(deploy_time_file, "w") as time_file:
    log_write(time_file, "Start TS: {}".format(start_ts))
    log_write(time_file, "Cluster Install TS: {}".format(cluster_installed_ts))
    log_write(time_file, "Deployment Complete TS: {}".format(deployment_completed_ts))
    log_write(time_file, "Completed TS: {}".format(completed_ts))
    log_write(time_file, "Playbook Completed TS: {}".format(playbook_completed_ts))
    log_write(time_file, "Last TS: {}".format(last_ts))
    log_write(time_file, "################################################################")
    log_write(time_file, "Cluster Install Duration (Cluster Install Completed): {}s :: {}".format(cluster_install_duration, str(timedelta(seconds=cluster_install_duration))))
    log_write(time_file, "Deployment Complete Duration (DU Compliant): {}s :: {}".format(deployed_complete_duration, str(timedelta(seconds=deployed_complete_duration))))
    log_write(time_file, "Completed Duration (DU Timeout+Compliant): {}s :: {}".format(completed_duration, str(timedelta(seconds=completed_duration))))
    log_write(time_file, "Playbook Duration (Playbook Completed): {}s :: {}".format(playbook_duration, str(timedelta(seconds=playbook_duration))))
    log_write(time_file, "Full Duration: {}s :: {}".format(full_duration, str(timedelta(seconds=full_duration))))
    log_write(time_file, "################################################################")
    deployed_installed_time_diff = deployed_complete_duration - cluster_install_duration
    playbook_deployed_time_diff = playbook_duration - deployed_complete_duration
    log_write(time_file, "Deployment Complete - Cluster Install Completed: {}s :: {}".format(deployed_installed_time_diff, str(timedelta(seconds=deployed_installed_time_diff))))
    log_write(time_file, "Playbook Complete - Deployment Complete: {}s :: {}".format(playbook_deployed_time_diff, str(timedelta(seconds=playbook_deployed_time_diff))))
    log_write(time_file, "################################################################")
    log_write(time_file, "Peak Cluster Installing: {}".format(peak_cluster_installing))
    log_write(time_file, "Peak DU Applying: {}".format(peak_du_applying))
    log_write(time_file, "Peak Playbook Running: {}".format(peak_playbook_running))
    log_write(time_file, "Peak Concurrency (cluster_installing + policy_applying + playbook_running): {}".format(peak_concurrency))

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
