#!/usr/bin/env python3
#
# Tool to load ACM with cluster deployments via manifests or GitOps ZTP
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
from collections import OrderedDict
import datetime
from datetime import timedelta
import glob
from jinja2 import Template
from utils.common_ocp import detect_aap_install
from utils.command import command
from utils.output import generate_report
from utils.output import phase_break
from utils.ztp_monitor import ZTPMonitor
from utils.talm import detect_talm_minor
import logging
import math
import os
import pathlib
import random
import shutil
import sys
import time

# TODO:
# * Discern sno, compact, and standard clusters in monitor data and report individual results
# * Discern sno, compact, and standard clusters in analysis scripts
# * Upgrade script orchestration and monitoring


kustomization_siteconfig_template = """---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
generators:
{%- for cluster in clusters %}
- ./{{ cluster }}-siteconfig.yml
{%- endfor %}

resources:
{%- for cluster in clusters %}
- ./{{ cluster }}-resources.yml
{%- endfor %}

"""

kustomization_clusterinstance_template = """---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
generators:

resources:
{%- for cluster in clusters %}
- ./{{ cluster }}-clusterinstance.yml
{%- endfor %}

"""

ns_file = """---
apiVersion: v1
kind: Namespace
metadata:
  name: test-config
"""

test_cm_template = """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-cm
  namespace: test-config
data:
  key1: "true"
  network-1-vlan: "123"
  pfname1: "ens1f1"
  network-1-ns: {{ clusterName }}-sriov-ns

"""


# Scan all three directories for clusters and add to cluster list
cluster_types = ["sno", "compact", "standard"]

install_methods = [
    "ai-manifest",
    "ai-clusterinstance",
    "ai-clusterinstance-gitops",
    "ai-siteconfig-gitops",
    "ibi-manifest",
    "ibi-clusterinstance",
    "ibi-clusterinstance-gitops"
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def deploy_ztp_clusters(clusters, manifest_type, ztp_deploy_apps, start_index, end_index, clusters_per_app, argocd_dir, dry_run, ztp_client_templates):
  git_files = []
  last_ztp_app_index = math.floor((start_index) / clusters_per_app)
  for idx, cluster in enumerate(clusters[start_index:end_index]):
    ztp_app_index = math.floor((start_index + idx) / clusters_per_app)

    # If number of clusters batched rolls into the next application, render the kustomization file
    if last_ztp_app_index < ztp_app_index:
      logger.info("Rendering {}/kustomization.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"]))
      if manifest_type == "siteconfig":
        t = Template(kustomization_siteconfig_template)
      else:
        t = Template(kustomization_clusterinstance_template)
      kustomization_rendered = t.render(
          clusters=ztp_deploy_apps[last_ztp_app_index]["clusters"])
      if not dry_run:
        with open("{}/kustomization.yaml".format(ztp_deploy_apps[last_ztp_app_index]["location"]), "w") as file1:
          file1.writelines(kustomization_rendered)
      git_files.append("{}/kustomization.yaml".format(ztp_deploy_apps[last_ztp_app_index]["location"]))
      last_ztp_app_index = ztp_app_index

    if manifest_type == "siteconfig":
      siteconfig_name = os.path.basename(cluster)
      siteconfig_dir = os.path.dirname(cluster)
      cluster_name = siteconfig_name.replace("-siteconfig.yml", "")
      ztp_deploy_apps[ztp_app_index]["clusters"].append(cluster_name)
      logger.debug("Clusters: {}".format(ztp_deploy_apps[ztp_app_index]["clusters"]))

      logger.debug("Copying {}-siteconfig.yml and {}-resources.yml from {} to {}".format(
          cluster_name, cluster_name, siteconfig_dir, ztp_deploy_apps[last_ztp_app_index]["location"]))
      if not dry_run:
        shutil.copy2(
            "{}/{}-siteconfig.yml".format(siteconfig_dir, cluster_name),
            "{}/{}-siteconfig.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"], cluster_name))
        shutil.copy2(
            "{}/{}-resources.yml".format(siteconfig_dir, cluster_name),
            "{}/{}-resources.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"], cluster_name))
      git_files.append("{}/{}-siteconfig.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"], cluster_name))
      git_files.append("{}/{}-resources.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"], cluster_name))
    else:
      # clusterinstance deployment
      clusterinstance_name = os.path.basename(cluster)
      clusterinstance_dir = os.path.dirname(cluster)
      cluster_name = clusterinstance_name.replace("-clusterinstance.yml", "")
      ztp_deploy_apps[ztp_app_index]["clusters"].append(cluster_name)
      logger.debug("Clusters: {}".format(ztp_deploy_apps[ztp_app_index]["clusters"]))

      logger.debug("Copying {}-clusterinstance.yml from {} to {}".format(
          cluster_name, clusterinstance_dir, ztp_deploy_apps[last_ztp_app_index]["location"]))
      if not dry_run:
        shutil.copy2(
            "{}/{}-clusterinstance.yml".format(clusterinstance_dir, cluster_name),
            "{}/{}-clusterinstance.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"], cluster_name))
      git_files.append("{}/{}-clusterinstance.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"], cluster_name))


    if ztp_client_templates:
      extra_manifests_dir = "{}/extra-manifests/{}".format(ztp_deploy_apps[last_ztp_app_index]["location"], cluster_name)
      logger.debug("Creating directory: {}".format(extra_manifests_dir))
      logger.info("Writing {}/01-ns.yaml".format(extra_manifests_dir))
      logger.info("Rendering {}/test-cm.yaml".format(extra_manifests_dir))
      t = Template(test_cm_template)
      test_cm_rendered = t.render(clusterName=cluster_name)
      if not dry_run:
        os.makedirs(extra_manifests_dir, exist_ok=True)
        with open("{}/01-ns.yaml".format(extra_manifests_dir), "w") as file1:
          file1.writelines(ns_file)
        with open("{}/test-cm.yaml".format(extra_manifests_dir), "w") as file1:
          file1.writelines(test_cm_rendered)
      git_files.append("{}/01-ns.yaml".format(extra_manifests_dir))
      git_files.append("{}/test-cm.yaml".format(extra_manifests_dir))

  # Always render a kustomization.yaml file at conclusion of the enumeration
  logger.info("Rendering {}/kustomization.yaml".format(ztp_deploy_apps[ztp_app_index]["location"]))
  if manifest_type == "siteconfig":
    t = Template(kustomization_siteconfig_template)
  else:
    t = Template(kustomization_clusterinstance_template)
  kustomization_rendered = t.render(
      clusters=ztp_deploy_apps[ztp_app_index]["clusters"])
  if not dry_run:
    with open("{}/kustomization.yaml".format(ztp_deploy_apps[ztp_app_index]["location"]), "w") as file1:
      file1.writelines(kustomization_rendered)
  git_files.append("{}/kustomization.yaml".format(ztp_deploy_apps[ztp_app_index]["location"]))

  # Git Process:
  for file in git_files:
    logger.debug("git add {}".format(file))
    git_add = ["git", "add", file]
    rc, output = command(git_add, dry_run, retries=3, cmd_directory=argocd_dir)
    if rc != 0:
      logger.error("acm-deploy-load, git add rc: {}, Output: {}".format(rc, output))
      sys.exit(1)
  logger.info("Added {} files in git".format(len(git_files)))
  git_commit = ["git", "commit", "-m", "Deploying Clusters {} to {}".format(start_index, end_index)]
  rc, output = command(git_commit, dry_run, cmd_directory=argocd_dir)
  rc, output = command(["git", "push"], dry_run, cmd_directory=argocd_dir)


def log_monitor_data(data, elapsed_seconds, cliargs):
  logger.info("Elapsed total time: {}s :: {}".format(elapsed_seconds, str(timedelta(seconds=elapsed_seconds))))
  logger.info("Applied/Committed Clusters: {}".format(data["cluster_applied_committed"]))
  logger.info("Initialized Clusters: {}".format(data["cluster_init"]))
  logger.info("Not Started Clusters: {}".format(data["cluster_notstarted"]))
  logger.info("Booted Nodes: {}".format(data["node_booted"]))
  logger.info("Discovered Nodes: {}".format(data["node_discovered"]))
  logger.info("Installing Clusters: {}".format(data["cluster_installing"]))
  logger.info("Failed Clusters: {}".format(data["cluster_install_failed"]))
  logger.info("Completed Clusters: {}".format(data["cluster_install_completed"]))
  logger.info("Managed Clusters: {}".format(data["managed"]))
  logger.info("Initialized Policy Clusters: {}".format(data["policy_init"]))
  logger.info("Policy Not Started Clusters: {}".format(data["policy_notstarted"]))
  logger.info("Policy Applying Clusters: {}".format(data["policy_applying"]))
  logger.info("Policy Timedout Clusters: {}".format(data["policy_timedout"]))
  logger.info("Policy Compliant Clusters: {}".format(data["policy_compliant"]))
  if cliargs.wait_playbook:
    logger.info("Playbook Not Started Clusters: {}".format(data["playbook_notstarted"]))
    logger.info("Playbook Running Clusters: {}".format(data["playbook_running"]))
    logger.info("Playbook Completed Clusters: {}".format(data["playbook_completed"]))


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Tool to load ACM with Cluster deployments via manifests or GitOps ZTP",
      prog="acm-deploy-load.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-m", "--method", choices=install_methods, default="ai-siteconfig-gitops",
                      help="The method of cluster install, ai - Assisted-Installer, ibi - Image-Based-Installer")

  # "Global" args
  parser.add_argument("-cm", "--cluster-manifests", type=str, default="/root/hv-vm/",
                      help="The location of the cluster manifests, siteconfigs and resource files")
  parser.add_argument("-a", "--argocd-directory", type=str,
                      default="/root/rhacm-ztp/cnf-features-deploy/ztp/gitops-subscriptions/argocd",
                      help="The location of the ArgoCD cluster and cluster applications directories")
  parser.add_argument("-s", "--start", type=int, default=0,
                      help="Cluster start index, follows array logic starting at 0 for '00001'")
  parser.add_argument("-e", "--end", type=int, default=0, help="Cluster end index (0 = total manifest count)")
  parser.add_argument("-n", "--no-shuffle", action="store_true", default=False,
                      help="Do not shuffle the list of discovered installable clusters")
  parser.add_argument("--start-delay", type=int, default=15,
                      help="Delay to starting deploys, allowing monitor thread to gather data (seconds)")
  parser.add_argument("--end-delay", type=int, default=120,
                      help="Delay on end, allows monitor thread to gather additional data points (seconds)")
  parser.add_argument("--clusters-per-app", type=int, default=100,
                      help="Maximum number of clusters per cluster application")
  parser.add_argument("--wait-cluster-max", type=int, default=10800,
                      help="Maximum amount of time to wait for cluster install completion (seconds)")
  parser.add_argument("--wait-du-profile-max", type=int, default=18000,
                      help="Maximum amount of time to wait for DU Profile completion (seconds)")
  parser.add_argument("--wait-playbook-max", type=int, default=1200,
                      help="Maximum amount of time to wait for Playbook completion (seconds)")
  parser.add_argument("-w", "--wait-du-profile", action="store_true", default=False,
                      help="Waits for du profile to complete after all expected clusters installed")
  parser.add_argument("-wp", "--wait-playbook", action="store_true", default=False,
                      help="Waits for playbook to complete after DU Profile completion")
  parser.add_argument("--ztp-client-templates", action="store_true", default=False,
                      help="If ztp method, include client templates")

  # Monitor Thread Options
  parser.add_argument("-i", "--monitor-interval", type=int, default=60,
                      help="Interval to collect monitoring data (seconds)")
  # The version of talm determines how we monitor for du profile applying/compliant/timeout
  parser.add_argument("--talm-version", type=str, default="4.16",
                      help="The version of talm to fall back on in event we can not detect the talm version")

  # Report options
  parser.add_argument("-t", "--results-dir-suffix", type=str, default="int-0",
                      help="Suffix to be appended to results directory name")
  parser.add_argument("--acm-version", type=str, default="", help="Sets ACM version for report")
  parser.add_argument("--aap-version", type=str, default="", help="Sets AAP version for report")
  parser.add_argument("--test-version", type=str, default="ZTP Scale Run 1", help="Sets test version for graph title")
  parser.add_argument("--hub-version", type=str, default="", help="Sets OCP Hub version for report")
  parser.add_argument("--deploy-version", type=str, default="", help="Sets OCP deployed version for report")
  parser.add_argument("--wan-emulation", type=str, default="", help="Sets WAN emulation for graph title")

  # Debug and dry-run options
  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  parser.add_argument("--dry-run", action="store_true", default=False, help="Echos commands instead of executing them")

  subparsers = parser.add_subparsers(dest="rate")

  parser_interval = subparsers.add_parser("interval", help="Interval rate method of deploying clusters",
                                          formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser_interval.add_argument("-b", "--batch", type=int, default=100, help="Number of clusters to apply per interval")
  parser_interval.add_argument("-i", "--interval", type=int, default=7200,
                               help="Time in seconds between deploying clusters")
  parser_interval.add_argument("-z", "--skip-wait-install", action="store_true", default=False,
                               help="Skips waiting for cluster install completion phase")

  parser.set_defaults(rate="interval", batch=100, interval=7200, start=0, end=0, skip_wait_install=False)
  cliargs = parser.parse_args()

  # # From laptop for debugging, should be commented out before commit
  # logger.info("Replacing directories for testing purposes#############################################################")
  # cliargs.cluster_manifests = "/home/akrzos/akrh/project-things/20240820-ibi-install-on-lta/hv-vm/"
  # cliargs.argocd_directory = "/home/akrzos/akrh/project-things/20240820-ibi-install-on-lta/argocd/"
  # cliargs.dry_run = True
  # cliargs.start_delay = 1
  # cliargs.end_delay = 1

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  phase_break()
  if cliargs.dry_run:
    logger.info("ACM Deploy Load - Dry Run")
  else:
    logger.info("ACM Deploy Load")
  phase_break()
  logger.debug("CLI Args: {}".format(cliargs))

  # Detect TALM version
  talm_minor = int(detect_talm_minor(cliargs.talm_version, cliargs.dry_run))
  logger.info("Using TALM cgu monitoring based on TALM minor version: {}".format(talm_minor))

  # Detect AAP install
  if detect_aap_install(dry_run=cliargs.dry_run):
    logger.info("AAP install detected, waiting for playbook completion")
    cliargs.wait_playbook = True
  else:
    logger.info("AAP install not detected")

  # Validate parameters and display rate and method plan
  logger.info("Deploying Clusters rate: {}".format(cliargs.rate))
  logger.info("Deploying Clusters method: {}".format(cliargs.method))
  if (cliargs.start < 0):
    logger.error("Cluster start index must be equal to or greater than 0")
    sys.exit(1)
  if (cliargs.end < 0):
    logger.error("Cluster end index must be equal to or greater than 0")
    sys.exit(1)
  if (cliargs.end > 0 and (cliargs.start >= cliargs.end)):
    logger.error("Cluster start index must be greater than the end index, when end index is not 0")
    sys.exit(1)
  if (cliargs.monitor_interval < 10):
    logger.error("Monitor interval must be equal to or greater than 10")
    sys.exit(1)
  if cliargs.rate == "interval":
    if not (cliargs.batch >= 1):
      logger.error("Batch size must be equal to or greater than 1")
      sys.exit(1)
    if not (cliargs.interval >= 0):
      logger.error("Interval must be equal to or greater than 0")
      sys.exit(1)
    logger.info(" * {} Cluster(s) per {}s interval".format(cliargs.batch, cliargs.interval))
    logger.info(" * Start Index: {}, End Index: {}".format(cliargs.start, cliargs.end))
    if cliargs.skip_wait_install:
      logger.info(" * Skip waiting for cluster install completion")
    else:
      if cliargs.wait_cluster_max > 0:
        logger.info(" * Wait for cluster install completion (Max {}s)".format(cliargs.wait_cluster_max))
      else:
        logger.info(" * Wait for cluster install completion (Infinite wait)")
  if not cliargs.wait_du_profile:
    logger.info(" * Skip waiting for DU Profile completion")
  else:
    if cliargs.wait_du_profile_max > 0:
      logger.info(" * Wait for DU Profile completion (Max {}s)".format(cliargs.wait_du_profile_max))
    else:
      logger.info(" * Wait for DU Profile completion (Infinite wait)")
  if not cliargs.wait_playbook:
    logger.info(" * Skip waiting for Playbook completion")
  else:
    if cliargs.wait_playbook_max > 0:
      logger.info(" * Wait for Playbook completion (Max {}s)".format(cliargs.wait_playbook_max))
    else:
      logger.info(" * Wait for Playbook completion (Infinite wait)")

  # Determine where the report directory will be located
  base_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
  base_dir_down = os.path.dirname(base_dir)
  base_dir_results = os.path.join(base_dir_down, "results")
  report_dir_name = "{}-{}-{}".format(datetime.datetime.utcfromtimestamp(start_time).strftime("%Y%m%d-%H%M%S"), cliargs.method, cliargs.results_dir_suffix)
  report_dir = os.path.join(base_dir_results, report_dir_name)
  logger.info("Results data captured in: {}".format("/".join(report_dir.split("/")[-2:])))

  monitor_data_csv_file = "{}/monitor_data.csv".format(report_dir)

  logger.info("Monitoring data captured to: {}".format("/".join(monitor_data_csv_file.split("/")[-3:])))
  logger.info(" * Monitoring interval: {}".format(cliargs.monitor_interval))
  phase_break()

  # Get starting data and list directories for manifests/siteconfigs/cluster applications
  available_clusters = 0
  cluster_list = []
  available_ztp_apps = 0
  ztp_deploy_apps = OrderedDict()
  if "manifest" in cliargs.method or "clusterinstance" in cliargs.method:
    for c_type in cluster_types:
      dir_to_check = cliargs.method.replace("-gitops", "")
      manifest_suffix = dir_to_check.split("-")[1]
      logger.info("Checking {}{}/{} for {}".format(cliargs.cluster_manifests, c_type, dir_to_check, manifest_suffix))
      temp_cluster_list = glob.glob("{}{}/{}/*-{}.yml".format(cliargs.cluster_manifests, c_type, dir_to_check, manifest_suffix))
      temp_cluster_list.sort()
      for manifests_file in temp_cluster_list:
        if pathlib.Path(manifests_file).is_file():
          logger.debug("Found {}".format(manifests_file))
        else:
          logger.error("{} is not a file".format(manifests_file))
          sys.exit(1)
      logger.info("Discovered {} available clusters of type {} for deployment".format(len(temp_cluster_list), c_type))
      cluster_list.extend(temp_cluster_list)
  elif cliargs.method == "ai-siteconfig-gitops":
    for c_type in cluster_types:
      siteconfig_dir = "{}{}/ai-siteconfig".format(cliargs.cluster_manifests, c_type)
      logger.info("Checking {} for siteconfigs".format(siteconfig_dir))
      temp_cluster_list = glob.glob("{}/*-siteconfig.yml".format(siteconfig_dir))
      temp_cluster_list.sort()
      for siteconfig_file in temp_cluster_list:
        siteconfig_name = os.path.basename(siteconfig_file)
        resources_name = siteconfig_name.replace("-siteconfig", "-resources")
        if pathlib.Path("{}/{}".format(siteconfig_dir, resources_name)).is_file():
          logger.debug("Found {}".format("{}/{}".format(siteconfig_dir, resources_name)))
        else:
          logger.error("Directory appears to be missing {} file: {}".format(resources_name, siteconfig_dir))
          sys.exit(1)
      logger.info("Discovered {} available clusters of type {} for deployment".format(len(temp_cluster_list), c_type))
      cluster_list.extend(temp_cluster_list)

  if "gitops" in cliargs.method:
    ztp_apps = glob.glob("{}/cluster/ztp-*".format(cliargs.argocd_directory))
    ztp_apps.sort()
    for idx, ztp_app in enumerate(ztp_apps):
      ztp_deploy_apps[idx] = {"location": ztp_app, "clusters": []}

  available_clusters = len(cluster_list)
  available_ztp_apps = len(ztp_deploy_apps)
  if available_clusters == 0:
    logger.error("Zero clusters discovered.")
    sys.exit(1)
  logger.info("Total {} available clusters for deployment".format(available_clusters))

  if "gitops" in cliargs.method:
    max_ztp_clusters = available_ztp_apps * cliargs.clusters_per_app
    logger.info("Discovered {} ztp cluster apps with capacity for {} * {} = {} Clusters".format(
        available_ztp_apps, available_ztp_apps, cliargs.clusters_per_app, max_ztp_clusters))
    if max_ztp_clusters < available_clusters:
      logger.error("There are more clusters than expected capacity of clusters per ZTP cluster application")
      sys.exit(1)

  # Now shuffle the list of siteconfigs
  if not cliargs.no_shuffle:
    random.shuffle(cluster_list)
    logger.debug("Randomized the cluster order: {}".format(cluster_list))

  # Create the results directory to store data into
  logger.info("Creating report directory: {}".format(report_dir))
  os.mkdir(report_dir)

  #############################################################################
  # Manifest application / gitops "phase"
  #############################################################################
  total_intervals = 0
  monitor_data = {
    "cluster_applied_committed": 0,
    "cluster_init": 0,
    "cluster_notstarted": 0,
    "node_booted": 0,
    "node_discovered": 0,
    "cluster_installing": 0,
    "cluster_install_failed": 0,
    "cluster_install_completed": 0,
    "managed": 0,
    "policy_init": 0,
    "policy_notstarted": 0,
    "policy_applying": 0,
    "policy_timedout": 0,
    "policy_compliant": 0,
    "playbook_notstarted": 0,
    "playbook_running": 0,
    "playbook_completed": 0
  }
  monitor_thread = ZTPMonitor(cliargs.method, talm_minor, monitor_data, monitor_data_csv_file, cliargs.dry_run, cliargs.monitor_interval)
  monitor_thread.start()
  if cliargs.start_delay > 0:
    phase_break()
    logger.info("Sleeping {}s for start delay".format(cliargs.start_delay))
    time.sleep(cliargs.start_delay)
  deploy_start_time = time.time()
  if cliargs.rate == "interval":
    phase_break()
    logger.info("Starting interval based cluster deployment rate - {}".format(int(time.time() * 1000)))
    phase_break()

    start_cluster_index = cliargs.start
    while True:
      total_intervals += 1
      start_interval_time = time.time()
      end_cluster_index = start_cluster_index + cliargs.batch
      if cliargs.end > 0:
        if end_cluster_index > cliargs.end:
          end_cluster_index = cliargs.end
      logger.info("Deploying interval {} with {} cluster(s) - {}".format(
          total_intervals, end_cluster_index - start_cluster_index, int(start_interval_time * 1000)))

      if "gitops" in cliargs.method:
        # Gitops method
        monitor_data["cluster_applied_committed"] += len(cluster_list[start_cluster_index:end_cluster_index])
        manifest_type = cliargs.method.split("-")[1]
        deploy_ztp_clusters(
            cluster_list, manifest_type, ztp_deploy_apps, start_cluster_index, end_cluster_index,
            cliargs.clusters_per_app, cliargs.argocd_directory, cliargs.dry_run, cliargs.ztp_client_templates)
      else:
        # Apply the clusters
        for cluster in cluster_list[start_cluster_index:end_cluster_index]:
          monitor_data["cluster_applied_committed"] += 1
          oc_cmd = ["oc", "apply", "-f", cluster]
          # Might need to add retries and have method to count retries
          rc, output = command(oc_cmd, cliargs.dry_run)
          if rc != 0:
            logger.error("acm-deploy-load, oc apply rc: {}".format(rc))
            sys.exit(1)

      start_cluster_index += cliargs.batch
      if start_cluster_index >= available_clusters or end_cluster_index == cliargs.end:
        phase_break()
        logger.info("Finished deploying clusters - {}".format(int(time.time() * 1000)))
        break

      # Interval wait logic
      expected_interval_end_time = start_interval_time + cliargs.interval
      current_time = time.time()
      wait_logger = 0
      logger.info("Sleep for {}s with {}s remaining".format(cliargs.interval, round(expected_interval_end_time - current_time)))
      while current_time < expected_interval_end_time:
        time.sleep(.1)
        wait_logger += 1
        # Approximately display this every 300s
        if wait_logger >= 3000:
          logger.info("Remaining interval time: {}s".format(round(expected_interval_end_time - current_time)))
          log_monitor_data(monitor_data, round(time.time() - start_time), cliargs)
          wait_logger = 0
        current_time = time.time()

  deploy_end_time = time.time()

  #############################################################################
  # Wait for Cluster Install Completion Phase
  #############################################################################
  wait_cluster_start_time = time.time()
  if (cliargs.rate == "interval") and (not cliargs.skip_wait_install):
    phase_break()
    logger.info("Waiting for clusters install completion - {}".format(int(time.time() * 1000)))
    phase_break()
    if cliargs.dry_run:
      monitor_data["cluster_applied_committed"] = 0

    wait_logger = 4
    while True:
      time.sleep(30)
      # Break from phase if inited clusters match applied/committed clusters and failed+completed = inited clusters
      if ((monitor_data["cluster_init"] >= monitor_data["cluster_applied_committed"]) and
          ((monitor_data["cluster_install_failed"] + monitor_data["cluster_install_completed"]) == monitor_data["cluster_init"])):
        logger.info("Clusters install completion")
        log_monitor_data(monitor_data, round(time.time() - start_time), cliargs)
        break

      # Break from phase if we exceed the timeout
      if cliargs.wait_cluster_max > 0 and ((time.time() - wait_cluster_start_time) > cliargs.wait_cluster_max):
        logger.info("Clusters install completion exceeded timeout: {}s".format(cliargs.wait_cluster_max))
        log_monitor_data(monitor_data, round(time.time() - start_time), cliargs)
        break

      wait_logger += 1
      if wait_logger >= 5:
        logger.info("Waiting for clusters install completion")
        e_time = round(time.time() - wait_cluster_start_time)
        logger.info("Elapsed cluster install completion time: {}s :: {} / {}s :: {}".format(
            e_time, str(timedelta(seconds=e_time)), cliargs.wait_cluster_max, str(timedelta(seconds=cliargs.wait_cluster_max))))
        log_monitor_data(monitor_data, round(time.time() - start_time), cliargs)
        wait_logger = 0

  wait_cluster_end_time = time.time()

  #############################################################################
  # Wait for DU Profile Completion Phase
  #############################################################################
  wait_du_profile_start_time = time.time()
  if cliargs.wait_du_profile:
    phase_break()
    logger.info("Waiting for DU Profile completion - {}".format(int(time.time() * 1000)))
    phase_break()
    if cliargs.dry_run:
      monitor_data["cluster_applied_committed"] = 0

    wait_logger = 4
    while True:
      time.sleep(30)
      # Break from phase if inited policy equal completed clusters and timeout+compliant policy = inited policy
      if ((monitor_data["policy_init"] >= monitor_data["cluster_install_completed"]) and
          ((monitor_data["policy_timedout"] + monitor_data["policy_compliant"]) == monitor_data["policy_init"])):
        logger.info("DU Profile completion")
        log_monitor_data(monitor_data, round(time.time() - start_time), cliargs)
        break

      # Break from phase if we exceed the timeout
      if cliargs.wait_du_profile_max > 0 and ((time.time() - wait_du_profile_start_time) > cliargs.wait_du_profile_max):
        logger.info("DU Profile completion exceeded timeout: {}s".format(cliargs.wait_du_profile_max))
        log_monitor_data(monitor_data, round(time.time() - start_time), cliargs)
        break

      wait_logger += 1
      if wait_logger >= 5:
        logger.info("Waiting for DU Profile completion")
        e_time = round(time.time() - wait_du_profile_start_time)
        logger.info("Elapsed DU Profile completion time: {}s :: {} / {}s :: {}".format(
            e_time, str(timedelta(seconds=e_time)), cliargs.wait_du_profile_max,
            str(timedelta(seconds=cliargs.wait_du_profile_max))))
        log_monitor_data(monitor_data, round(time.time() - start_time), cliargs)
        wait_logger = 0
  wait_du_profile_end_time = time.time()

  end_time = time.time()

  #############################################################################
  # Wait for Playbook Completion Phase
  #############################################################################
  wait_playbook_start_time = time.time()
  if cliargs.wait_playbook:
    phase_break()
    logger.info("Waiting for Playbook completion - {}".format(int(time.time() * 1000)))
    phase_break()

    wait_logger = 4
    while True:
      time.sleep(30)
      # Break from phase if playbook completed is greater than or equal to policy compliant
      if monitor_data["playbook_completed"] >= monitor_data["policy_compliant"]:
        logger.info("Playbook completion")
        log_monitor_data(monitor_data, round(time.time() - start_time), cliargs)
        break

      # Break from phase if we exceed the timeout
      if cliargs.wait_playbook_max > 0 and ((time.time() - wait_playbook_start_time) > cliargs.wait_playbook_max):
        logger.info("Playbook completion exceeded timeout: {}s".format(cliargs.wait_playbook_max))
        log_monitor_data(monitor_data, round(time.time() - start_time), cliargs)
        break

      wait_logger += 1
      if wait_logger >= 5:
        logger.info("Waiting for Playbook completion")
        e_time = round(time.time() - wait_playbook_start_time)
        logger.info("Elapsed Playbook completion time: {}s :: {} / {}s :: {}".format(
            e_time, str(timedelta(seconds=e_time)), cliargs.wait_playbook_max,
            str(timedelta(seconds=cliargs.wait_playbook_max))))
        log_monitor_data(monitor_data, round(time.time() - start_time), cliargs)
        wait_logger = 0
  wait_playbook_end_time = time.time()

  # End of Workload delay
  if cliargs.end_delay > 0:
    phase_break()
    logger.info("Sleeping {}s for end delay".format(cliargs.end_delay))
    time.sleep(cliargs.end_delay)

  # Stop monitoring thread
  logger.info("Stopping monitoring thread may take up to: {}".format(cliargs.monitor_interval))
  monitor_thread.signal = False
  monitor_thread.join()

  #############################################################################
  # Report Card / Graph Phase
  #############################################################################
  generate_report(start_time, end_time, deploy_start_time, deploy_end_time, wait_cluster_start_time,
      wait_cluster_end_time, wait_du_profile_start_time, wait_du_profile_end_time,
      wait_playbook_start_time, wait_playbook_end_time, available_clusters, monitor_data,
      cliargs, total_intervals, report_dir)

if __name__ == "__main__":
  sys.exit(main())
