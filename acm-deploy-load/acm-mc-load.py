#!/usr/bin/env python3
#
# Tool to load ACM with previously deployed clusters and on interval update a configmap that maps to policy templates
# triggering re-enforcing policies.
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
import base64
from datetime import datetime, timedelta, timezone
import glob
from jinja2 import Template
from utils.command import command
from utils.output import log_write
from utils.output import phase_break
import json
import logging
import os
import pathlib
import sys
import time


hub_configmap_template = """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
data:
{%- for key in keys %}
  key{{ loop.index - 1 }}: "{{ '%06d' % key }}"
{%- endfor %}
"""

# Scan all three directories for clusters and add to cluster list
cluster_types = ["sno", "compact", "standard"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def manage_clusters(clusters, mc_dir, hub_kc):
  for cluster in clusters:
    logger.info("Managing {}".format(cluster["name"]))
    oc_cmd = ["oc", "--kubeconfig", hub_kc, "apply", "-f", cluster["mc"]]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("oc apply -f {} rc: {}".format(cluster["mc"], rc))
      sys.exit(1)
    logger.debug(output.strip())

    # Many retries as it may not instant create the secret data upon import
    oc_cmd = ["oc", "--kubeconfig", hub_kc, "get", "secret", "-n", cluster["name"], "{}-import".format(cluster["name"]), "-o", "json"]
    rc, output = command(oc_cmd, False, retries=20, no_log=True)
    if rc != 0:
      logger.error("oc get secret -n {1} {1}-import rc: {2}".format(cluster["name"], rc))
      sys.exit(1)

    output_json = json.loads(output)
    decoded_crds_output = (base64.b64decode(output_json["data"]["crds.yaml"])).decode("utf-8")
    cluster_crds_file = "{}/{}-crds.yml".format(mc_dir, cluster["name"])
    with open(cluster_crds_file, "w") as file1:
      file1.writelines(decoded_crds_output)
    decoded_import_output = (base64.b64decode(output_json["data"]["import.yaml"])).decode("utf-8")
    cluster_import_file = "{}/{}-import.yml".format(mc_dir, cluster["name"])
    with open(cluster_import_file, "w") as file1:
      file1.writelines(decoded_import_output)

    # Lastly import the crd and import data into the spoke cluster to complete process of initiating managing a cluster
    oc_cmd = ["oc", "--kubeconfig", cluster["kc"], "apply", "-f", cluster_crds_file]
    rc, output = command(oc_cmd, False, retries=10, no_log=True)
    if rc != 0:
      logger.error("oc --kubeconfig {} apply -f {} rc: {}".format(cluster["kc"], cluster_crds_file, rc))
      sys.exit(1)

    oc_cmd = ["oc", "--kubeconfig", cluster["kc"], "apply", "-f", cluster_import_file]
    rc, output = command(oc_cmd, False, retries=10, no_log=True)
    if rc != 0:
      logger.error("oc --kubeconfig {} apply -f {} rc: {}".format(cluster["kc"], cluster_import_file, rc))
      sys.exit(1)


def update_policy_cm(policy_ns, cm_name, policy_keys, policy_dir, hub_kc):
  t = Template(hub_configmap_template)
  hcm_template_rendered = t.render(
      name=cm_name,
      namespace=policy_ns,
      keys=policy_keys)
  ts = datetime.fromtimestamp(time.time(), tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
  policy_cm_file = "{}/policy-cm-{}.yml".format(policy_dir, ts)
  with open(policy_cm_file, "w") as file1:
    file1.writelines(hcm_template_rendered)
  oc_cmd = ["oc", "--kubeconfig", hub_kc, "apply", "-f", policy_cm_file]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("oc apply -f {} rc: {}".format(policy_cm_file, rc))
    sys.exit(1)
  logger.debug(output.strip())


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Tool to load ACM with previously deployed clusters",
      prog="acm-mc-load.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-m", "--cluster-manifests", type=str, default="/root/hv-vm/",
                      help="The location of the cluster manifest files and kubeconfigs")

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/mno/kubeconfig",
                      help="Changes which kubeconfig to connect to the hub cluster")

  parser.add_argument("--hub-policy-namespace", type=str, default="policies", help="Namespace for the policies")
  parser.add_argument("--hub-policy-cm-name", type=str, default="policy-template-map",
                      help="Name for hub side configmap for policy data keys")
  parser.add_argument("--hub-policy-cm-keys", type=int, default=5, help="Number of keys for the hub side configmap")

  # Workload interval args
  parser.add_argument("-i", "--interval-manage", type=int, default=3600,
                      help="Time in seconds between managing batchsclusters")
  parser.add_argument("-b", "--batch", type=int, default=1, help="Number of clusters to manage per interval")
  parser.add_argument("-p", "--interval-policy", type=int, default=720,
                      help="Interval between updating configmap used in policy templates")

  parser.add_argument("-s", "--start-delay", type=int, default=120, help="Delay on start of script")
  parser.add_argument("-e", "--end-delay", type=int, default=120, help="Delay on end of script")

  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")

  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  phase_break()
  logger.info("ACM Manage Cluster Load")
  phase_break()
  logger.debug("CLI Args: {}".format(cliargs))

  # Determine where the report directory will be located
  base_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
  base_dir_down = os.path.dirname(base_dir)
  base_dir_results = os.path.join(base_dir_down, "results")
  report_dir_name = "{}-mc-load".format(datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y%m%d-%H%M%S"))
  report_dir = os.path.join(base_dir_results, report_dir_name)
  mc_dir = os.path.join(report_dir, "mc")
  policy_dir = os.path.join(report_dir, "policy-cm")
  logger.info("Results data captured in: {}".format("/".join(report_dir.split("/")[-2:])))
  phase_break()

  # Detect and determine count of available clusters to manage via the managedcluster manifests
  available_clusters = 0
  cluster_list = []
  for c_type in cluster_types:
    logger.info("Checking {}{}/manifests/ for manifests".format(cliargs.cluster_manifests, c_type))
    temp_cluster_list = glob.glob("{}{}/manifests/*".format(cliargs.cluster_manifests, c_type))
    temp_cluster_list.sort()
    for manifest_dir in temp_cluster_list:
      cluster_name = os.path.basename(manifest_dir)
      logger.debug("Found cluster directory: {}".format(cluster_name))
      mc_file = "{}/managedcluster.yml".format(manifest_dir)
      kc_file = "{}kc/{}/kubeconfig".format(cliargs.cluster_manifests, cluster_name)
      if pathlib.Path(mc_file).is_file():
        logger.debug("Found {} mc file {}".format(cluster_name, mc_file))
      else:
        logger.error("Directory appears to be missing managedcluster.yml file: {}".format(manifest_dir))
        sys.exit(1)
      if pathlib.Path(kc_file).is_file():
        logger.debug("Found {} kubeconfig at {}".format(cluster_name, kc_file))
      else:
        logger.error("Did not find cluster {} kubeconfig at {}, exiting".format(cluster_name, kc_file))
        sys.exit(1)
      cdata = {"name": cluster_name, "mc": mc_file, "kc": kc_file}
      cluster_list.append(cdata)
    logger.info("Discovered {} available clusters of type {} to manage".format(len(temp_cluster_list), c_type))
    # cluster_list.extend(temp_cluster_list)

  available_clusters = len(cluster_list)
  if available_clusters == 0:
    logger.error("Zero clusters discovered.")
    sys.exit(1)
  logger.info("Total {} available clusters to manage".format(available_clusters))

  # Detect a policy configmap
  logger.info("Detecting configmap {} in namespace {}".format(cliargs.hub_policy_cm_name, cliargs.hub_policy_namespace))
  oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "get", "cm", "-n", cliargs.hub_policy_namespace, cliargs.hub_policy_cm_name, "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("oc get cm {} -n {} rc: {}".format(cliargs.hub_policy_cm_name, cliargs.hub_policy_namespace, rc))
    sys.exit(1)
  else:
    logger.info("Detected configmap {} in namespace {}".format(cliargs.hub_policy_cm_name, cliargs.hub_policy_namespace))

  # Pre-populate the policy configmap keys var for templating
  starting_key_increment = 0
  policy_cm_keys = [i * 100000 for i in range(cliargs.hub_policy_cm_keys)]

  # Create the results directories to store data into
  logger.debug("Creating report directory: {}".format(report_dir))
  os.mkdir(report_dir)
  os.mkdir(mc_dir)
  os.mkdir(policy_dir)

  manage_start_time = time.time()
  phase_break()
  if cliargs.start_delay > 0:
    logger.info("Sleeping {}s for start delay".format(cliargs.start_delay))
    total_start_delay = cliargs.start_delay
    while(total_start_delay > 300):
      time.sleep(300)
      total_start_delay -= 300
      logger.info("{}s remaining in start delay".format(total_start_delay))
    # Sleep remaining less than 5 minutes time
    time.sleep(total_start_delay)
  start_delay_complete_ts = time.time()

  total_clusters_managed = 0
  total_policy_cm_updates = 0
  cluster_managed_timestamps = []

  next_mc_time = manage_start_time + cliargs.start_delay
  next_policy_time = next_mc_time + cliargs.interval_policy
  last_logged = manage_start_time
  phase_break()
  logger.info("Begin managing clusters - {}".format(int(time.time() * 1000)))
  phase_break()
  current_time = time.time()
  while True:
    # Check if we need to manage a cluster
    if current_time >= next_mc_time:
      if total_clusters_managed >= available_clusters:
        # Managing all clusters causes the infinite loop to finally break.
        # This occurs after the last cluster is managed + interval time afterwards
        logger.info("Completed managing all available clusters")
        break
      else:
        if total_clusters_managed + cliargs.batch > available_clusters:
          new_cluster_count = available_clusters - total_clusters_managed
        else:
          new_cluster_count = cliargs.batch
        cnames = [x["name"] for x in cluster_list[total_clusters_managed:total_clusters_managed + new_cluster_count]]
        logger.info("Manage new cluster(s): {}".format(cnames))
        st = time.time()
        manage_clusters(cluster_list[total_clusters_managed:total_clusters_managed + new_cluster_count], mc_dir, cliargs.kubeconfig)
        et = time.time()
        cluster_managed_timestamps.append(et)
        logger.info("Managing took: {}".format(round(et - st, 1)))
        total_clusters_managed += new_cluster_count
      next_mc_time = next_mc_time + cliargs.interval_manage

    # Check if we need to update the policy cm
    if current_time >= next_policy_time:
      logger.info("Apply new policy cm with keys: {}".format(policy_cm_keys))
      policy_cm_keys[starting_key_increment % len(policy_cm_keys)] += 1
      starting_key_increment += 1
      update_policy_cm(cliargs.hub_policy_namespace, cliargs.hub_policy_cm_name, policy_cm_keys, policy_dir, cliargs.kubeconfig)
      next_policy_time = next_policy_time + cliargs.interval_policy
      total_policy_cm_updates += 1

    # Log something to make sure we know this is still alive
    if current_time - 300 > last_logged:
      last_logged = current_time
      remaining_mc_time = round(next_mc_time - current_time)
      remaining_policy_time = round(next_policy_time - current_time)
      logger.info("Total clusters managed: {}".format(total_clusters_managed))
      logger.info("Total policy updates: {}".format(total_policy_cm_updates))
      if total_clusters_managed >= available_clusters:
        logger.info("Last cluster managed, remaining interval time: {}s :: {}".format(remaining_mc_time, str(timedelta(seconds=remaining_mc_time))))
      else:
        logger.info("Time until next cluster to manage: {}s :: {}".format(remaining_mc_time, str(timedelta(seconds=remaining_mc_time))))
      logger.info("Time until next policy update: {}s :: {}".format(remaining_policy_time, str(timedelta(seconds=remaining_policy_time))))

    time.sleep(.1)
    current_time = time.time()
    # End run loop

  end_delay_start_ts = time.time()
  # End of workload delay
  if cliargs.end_delay > 0:
    phase_break()
    logger.info("Sleeping {}s for end delay".format(cliargs.end_delay))
    total_end_delay = cliargs.end_delay
    while(total_end_delay > 300):
      time.sleep(300)
      total_end_delay -= 300
      logger.info("{}s remaining in end delay".format(total_end_delay))
    # Sleep remaining less than 5 minutes time
    time.sleep(total_end_delay)

  manage_end_time = time.time()

  # Make a report card
  with open("{}/report.txt".format(report_dir), "w") as report:
    phase_break(True, report)
    log_write(report, "acm-mc-load Report Card")
    phase_break(True, report)
    log_write(report, "Workload")
    log_write(report, " * Manage {} cluster(s) per {}s interval".format(cliargs.batch, cliargs.interval_manage))
    log_write(report, " * Update cm ({}) in policy namespace ({}) per {}s interval".format(cliargs.hub_policy_cm_name, cliargs.hub_policy_namespace, cliargs.interval_policy))
    log_write(report, " * Start delay: {}".format(cliargs.start_delay))
    log_write(report, " * End delay: {}".format(cliargs.end_delay))
    log_write(report, " * Total cluster(s) managed: {}".format(total_clusters_managed))
    log_write(report, " * Total policy cm updates: {}".format(total_policy_cm_updates))
    log_write(report, "Workload Timestamps")
    log_write(report, " * Start Time: {} {}".format(datetime.fromtimestamp(manage_start_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), int(manage_start_time * 1000)))
    log_write(report, " * Start Delay Complete Time: {}".format(datetime.fromtimestamp(start_delay_complete_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    for i, ts in enumerate(cluster_managed_timestamps):
      log_write(report, " * MC {} event: {}".format(i, datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    log_write(report, " * End Delay Start Time: {}".format(datetime.fromtimestamp(end_delay_start_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    log_write(report, " * End Time: {} {}".format(datetime.fromtimestamp(manage_end_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), int(manage_end_time * 1000)))

    log_write(report, "Workload Duration Results")
    sd_duration = round(start_delay_complete_ts - manage_start_time)
    log_write(report, " * Start until start delay complete: {}s".format(sd_duration))
    last_ts = start_delay_complete_ts
    for i, ts in enumerate(cluster_managed_timestamps):
      next_duration = round(ts - last_ts)
      if i == 0:
        log_write(report, " * Start delay until MC {} event: {}s".format(i, next_duration))
      else:
        log_write(report, " * MC {} until MC {} event: {}s".format(i - 1, i, next_duration))
      last_ts = ts
    next_duration = round(end_delay_start_ts - last_ts)
    log_write(report, " * MC {} event until end delay start time: {}s".format(i, next_duration))
    ed_duration = round(manage_end_time - end_delay_start_ts)
    log_write(report, " * End delay duration: {}s".format(ed_duration))
    total_duration = round(manage_end_time - manage_start_time)
    log_write(report, " * Total duration: {}s :: {}".format(total_duration, str(timedelta(seconds=total_duration))))
    log_write(report, " * Total include start and end delay")

  logger.info("Took {}s".format(round(manage_end_time - start_time, 1)))


if __name__ == "__main__":
  sys.exit(main())
