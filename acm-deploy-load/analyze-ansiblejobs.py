#!/usr/bin/env python3
#
# Analyze AnsibleJobs data on a hub cluster to determine durations and graph jobs status
#
#  Copyright 2023 Red Hat
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
from utils.common_ocp import get_ocp_namespace_list
from utils.output import log_write
import logging
import numpy as np
import pandas as pd
import plotly.express as px
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze AnsibleJobs data",
      prog="analyze-ansiblejobs.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/bm/kubeconfig",
                      help="Changes which kubeconfig to connect to a cluster")

  # Graph size
  parser.add_argument("-w", "--width", type=int, default=1000, help="Sets width of all graphs")
  parser.add_argument("-t", "--height", type=int, default=700, help="Sets height of all graphs")

  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  # Detect which queries to make based on namespaces present
  namespaces = get_ocp_namespace_list(cliargs.kubeconfig)
  if "ansible-automation-platform" not in namespaces:
      logger.info("ansible-automation-platform namespace not found, skipping ansiblejob analysis")
      return 0

  logger.info("Analyze ansiblejobs")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  aj_csv_file = "{}/ansiblejobs-{}.csv".format(cliargs.results_directory, ts)
  aj_stats_file = "{}/ansiblejobs-{}.stats".format(cliargs.results_directory, ts)
  aj_samples_file = "{}/ansiblejobs-{}-samples.csv".format(cliargs.results_directory, ts)
  aj_graph_file = "{}/ansiblejobs-{}.png".format(cliargs.results_directory, ts)

  oc_cmd = ["oc", "get", "ansiblejobs", "-A", "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-ansiblejobs, oc get ansiblejobs rc: {}".format(rc))
    sys.exit(1)
  aj_data = json.loads(output)

  aj_analyzed = len(aj_data["items"])
  aj_status_total = {}
  create_started_durations = []
  started_finished_durations = []
  complete_durations = []

  # For use with creating the status graph
  aj_graph_start_time = ""
  aj_graph_end_time = ""
  aj_graph_timestamps = {}

  if aj_analyzed == 0:
    logger.info("No AnsibleJobs to analyze. Exiting")
  else:
    logger.info("Writing CSV: {}".format(aj_csv_file))
    with open(aj_csv_file, "w") as csv_file:
      csv_file.write("name,tower_id,target_count,status,changed,failed,elapsed,creationTimestamp,started,finished,complete_duration,create_started_duration,started_finished_duration\n")

    for item in aj_data["items"]:
      aj_name = item["metadata"]["name"]
      aj_creationTimestamp = item["metadata"]["creationTimestamp"]
      aj_tower_id = ""
      if "labels" in item["metadata"] and "tower_job_id" in item["metadata"]["labels"]:
        aj_tower_id = item["metadata"]["labels"]["tower_job_id"]
      aj_target_count = len(item["spec"]["extra_vars"]["target_clusters"])

      aj_result_changed = ""
      aj_result_status = ""
      aj_result_failed = ""
      aj_result_started = ""
      aj_result_finished = ""
      aj_result_elapsed = ""

      if "status" in item and "ansibleJobResult" in item["status"]:
        if "changed" in item["status"]["ansibleJobResult"]:
          aj_result_changed = item["status"]["ansibleJobResult"]["changed"]
        if "status" in item["status"]["ansibleJobResult"]:
          aj_result_status = item["status"]["ansibleJobResult"]["status"]
          if aj_result_status in aj_status_total:
            aj_status_total[aj_result_status] += 1
          else:
            aj_status_total[aj_result_status] = 1
        if "failed" in item["status"]["ansibleJobResult"]:
          aj_result_failed = item["status"]["ansibleJobResult"]["failed"]
        if "started" in item["status"]["ansibleJobResult"]:
          aj_result_started = item["status"]["ansibleJobResult"]["started"]
        if "finished" in item["status"]["ansibleJobResult"]:
          aj_result_finished = item["status"]["ansibleJobResult"]["finished"]
        if "elapsed" in item["status"]["ansibleJobResult"]:
          aj_result_elapsed = item["status"]["ansibleJobResult"]["elapsed"]

      created_dt = datetime.strptime(aj_creationTimestamp, "%Y-%m-%dT%H:%M:%SZ")
      created_dt_no_seconds = datetime.strptime(aj_creationTimestamp, "%Y-%m-%dT%H:%M:%SZ").replace(second=0, microsecond=0)
      # Set earliest created timestamp
      if aj_graph_start_time == "":
        aj_graph_start_time = created_dt_no_seconds
      else:
        if created_dt_no_seconds < aj_graph_start_time:
          aj_graph_start_time = created_dt_no_seconds

      create_started_duration = ""
      started_finished_duration = ""
      complete_duration = ""
      if aj_result_started != "":
        started_dt = datetime.strptime(aj_result_started, "%Y-%m-%dT%H:%M:%S.%fZ")
        started_dt_no_seconds = datetime.strptime(aj_result_started, "%Y-%m-%dT%H:%M:%S.%fZ").replace(second=0, microsecond=0)
        create_started_duration = (started_dt - created_dt).total_seconds()
        create_started_durations.append(create_started_duration)
      if aj_result_finished != "":
        finished_dt = datetime.strptime(aj_result_finished, "%Y-%m-%dT%H:%M:%S.%fZ")
        finished_dt_no_seconds = datetime.strptime(aj_result_finished, "%Y-%m-%dT%H:%M:%S.%fZ").replace(second=0, microsecond=0)
        # Set latest finished timestamp
        if aj_graph_end_time == "":
          aj_graph_end_time = finished_dt_no_seconds
        else:
          if finished_dt_no_seconds > aj_graph_end_time:
            aj_graph_end_time = finished_dt_no_seconds
        aj_graph_timestamps[aj_name] = {
            "create": created_dt_no_seconds,
            "started": started_dt_no_seconds,
            "finished": finished_dt_no_seconds}
        started_finished_duration = (finished_dt - started_dt).total_seconds()
        complete_duration = (finished_dt - created_dt).total_seconds()
        started_finished_durations.append(started_finished_duration)
        complete_durations.append(complete_duration)

      with open(aj_csv_file, "a") as csv_file:
        csv_file.write("{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
            aj_name, aj_tower_id, aj_target_count, aj_result_status, aj_result_changed, aj_result_failed,
            aj_result_elapsed, aj_creationTimestamp, aj_result_started, aj_result_finished, complete_duration,
            create_started_duration, started_finished_duration))


    if aj_graph_start_time != "" and aj_graph_end_time != "":
      # Create 1 minute buckets for series data of ansiblejobs
      data_buckets = {}
      # Add 5 buffer minutes to buckets, at least 2 before start time
      bucket_count = int((aj_graph_end_time - aj_graph_start_time).total_seconds() / 60) + 5
      for i in range(bucket_count):
        data_bk_ts = (aj_graph_start_time - timedelta(minutes=2)) + timedelta(minutes=i)
        data_buckets[data_bk_ts] = {"queued": 0, "running": 0, "completed": 0}
        # logger.info("Bucket: {}".format(data_bk_ts))

      # Now populate each bucket series with data between timestamps for each job:
      for aj in aj_graph_timestamps:
        # logger.info(aj_graph_timestamps[aj])
        queued_start_time = (aj_graph_timestamps[aj]["create"]).replace(second=0, microsecond=0)
        queued_end_time = (aj_graph_timestamps[aj]["started"]).replace(second=0, microsecond=0)
        running_start_time = (aj_graph_timestamps[aj]["started"]).replace(second=0, microsecond=0)
        running_end_time = (aj_graph_timestamps[aj]["finished"]).replace(second=0, microsecond=0)
        queued_bucket_count = int((queued_end_time - queued_start_time).total_seconds() / 60)
        running_bucket_count = int((running_end_time - running_start_time).total_seconds() / 60)
        completed_bucket_count = int((aj_graph_end_time - running_end_time).total_seconds() / 60) + 3
        for i in range(queued_bucket_count):
          data_bk_ts = queued_start_time + timedelta(minutes=i)
          data_buckets[data_bk_ts]["queued"] += 1
        for i in range(running_bucket_count):
          data_bk_ts = running_start_time + timedelta(minutes=i)
          data_buckets[data_bk_ts]["running"] += 1
        for i in range(completed_bucket_count):
          data_bk_ts = running_end_time + timedelta(minutes=i)
          data_buckets[data_bk_ts]["completed"] += 1

      # Write the samples csv file which contains:
      # datetime, queued, running, completed
      with open(aj_samples_file, "w") as csv_file:
        csv_file.write("datetime,queued,running,completed\n")
        for sample in data_buckets:
          csv_file.write("{},{},{},{}\n".format(sample.strftime("%Y-%m-%dT%H:%M:%SZ"), data_buckets[sample]["queued"], data_buckets[sample]["running"], data_buckets[sample]["completed"]))

      # Read in samples csv file to generate a png graph
      df = pd.read_csv(aj_samples_file)

      aj_graph_title = "AnsibleJobs - Status "
      aj_graph_y = ["queued", "running", "completed"]
      l = {"value" : "# ansiblejobs", "date" : ""}

      logger.info("Creating Graph - {}".format(aj_graph_file))
      fig_graph = px.line(df, x="datetime", y=aj_graph_y, labels=l, width=cliargs.width, height=cliargs.height)
      fig_graph.update_layout(title=aj_graph_title, legend_orientation="v")
      fig_graph.write_image(aj_graph_file)

    logger.info("Writing Stats: {}".format(aj_stats_file))
    with open(aj_stats_file, "w") as stats_file:
      log_write(stats_file, "Analyzed {} ansiblejobs".format(aj_analyzed))
      for status in sorted(aj_status_total.keys()):
        log_write(stats_file, "AnsibleJobs with {} status: {}".format(status, aj_status_total[status]))
      log_write(stats_file, "#############################################")
      log_write(stats_file, "Created to Started Duration Stats")
      log_write(stats_file, "Count: {}".format(len(create_started_durations)))
      if len(create_started_durations) > 0:
        log_write(stats_file, "Min: {}".format(round(np.min(create_started_durations), 1)))
        log_write(stats_file, "Average: {}".format(round(np.mean(create_started_durations), 1)))
        log_write(stats_file, "50 percentile: {}".format(round(np.percentile(create_started_durations, 50), 1)))
        log_write(stats_file, "95 percentile: {}".format(round(np.percentile(create_started_durations, 95), 1)))
        log_write(stats_file, "99 percentile: {}".format(round(np.percentile(create_started_durations, 99), 1)))
        log_write(stats_file, "Max: {}".format(round(np.max(create_started_durations), 1)))
      log_write(stats_file, "#############################################")
      log_write(stats_file, "Started to Finished Duration Stats")
      log_write(stats_file, "Count: {}".format(len(started_finished_durations)))
      if len(create_started_durations) > 0:
        log_write(stats_file, "Min: {}".format(round(np.min(started_finished_durations), 1)))
        log_write(stats_file, "Average: {}".format(round(np.mean(started_finished_durations), 1)))
        log_write(stats_file, "50 percentile: {}".format(round(np.percentile(started_finished_durations, 50), 1)))
        log_write(stats_file, "95 percentile: {}".format(round(np.percentile(started_finished_durations, 95), 1)))
        log_write(stats_file, "99 percentile: {}".format(round(np.percentile(started_finished_durations, 99), 1)))
        log_write(stats_file, "Max: {}".format(round(np.max(started_finished_durations), 1)))
      log_write(stats_file, "#############################################")
      log_write(stats_file, "Complete Duration Stats")
      log_write(stats_file, "Count: {}".format(len(complete_durations)))
      if len(create_started_durations) > 0:
        log_write(stats_file, "Min: {}".format(round(np.min(complete_durations), 1)))
        log_write(stats_file, "Average: {}".format(round(np.mean(complete_durations), 1)))
        log_write(stats_file, "50 percentile: {}".format(round(np.percentile(complete_durations, 50), 1)))
        log_write(stats_file, "95 percentile: {}".format(round(np.percentile(complete_durations, 95), 1)))
        log_write(stats_file, "99 percentile: {}".format(round(np.percentile(complete_durations, 99), 1)))
        log_write(stats_file, "Max: {}".format(round(np.max(complete_durations), 1)))

  end_time = time.time()
  logger.info("Analysis Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
