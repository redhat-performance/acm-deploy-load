#!/usr/bin/env python3
#
# Tool to load ACM by deploying Telco Core clusters and on interval update a configmap that maps to policy templates
# triggering re-enforcing policies.
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
from datetime import datetime, timedelta, timezone
import glob
from math import ceil
from jinja2 import Template
from utils.command import command
from utils.output import log_write
from utils.output import phase_break
import logging
import os
import shutil
import sys
import time


kustomization_clusterinstance_template = """---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
generators:

resources:
{%- for cluster in clusters %}
- ./{{ cluster }}
{%- endfor %}

"""

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


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def deploy_clusters(full_cluster_list, commit_message, gitops_dir):
  logger.debug("Deploying clusters: {}".format(len(full_cluster_list)))
  logger.debug("Full cluster list: {}".format(full_cluster_list))
  logger.debug("Commit message: {}".format(commit_message))
  for cluster in full_cluster_list:
    logger.info("Copying {} to {}".format(cluster, "{}/{}".format(gitops_dir, os.path.basename(cluster))))
    shutil.copy2(cluster, "{}/{}".format(gitops_dir, os.path.basename(cluster)))
  t = Template(kustomization_clusterinstance_template)
  base_names = [os.path.basename(cluster) for cluster in full_cluster_list]
  kustomization_rendered = t.render(
      clusters=base_names)
  with open("{}/kustomization.yaml".format(gitops_dir), "w") as file1:
    file1.writelines(kustomization_rendered)
  # Git Process:
  git_add = ["git", "add", "{}/kustomization.yaml".format(gitops_dir)]
  rc, output = command(git_add, False, retries=3, cmd_directory=gitops_dir)
  if rc != 0:
    logger.error("acm-telco-core-load, git add rc: {}, Output: {}".format(rc, output))
    sys.exit(1)
  for cluster in full_cluster_list:
    git_add = ["git", "add", "{}/{}".format(gitops_dir, os.path.basename(cluster))]
    rc, output = command(git_add, False, retries=3, cmd_directory=gitops_dir)
    if rc != 0:
      logger.error("acm-telco-core-load, git add rc: {}, Output: {}".format(rc, output))
      sys.exit(1)
  git_commit = ["git", "commit", "-m", commit_message]
  rc, output = command(git_commit, False, cmd_directory=gitops_dir)
  rc, output = command(["git", "push"], False, cmd_directory=gitops_dir)



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
      description="Tool to load ACM by deploying Telco Core clusters",
      prog="acm-telco-core-load.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/mno/kubeconfig",
                      help="Changes which kubeconfig to connect to the hub cluster")

  parser.add_argument("-m", "--cluster-manifests", type=str, default="/root/telco-core-manifests/",
                      help="The location of the Telco Core manifest files")
  parser.add_argument("-g", "--gitops-dir", type=str,
                      default="/root/rhacm-ztp/cnf-features-deploy/ztp/gitops-subscriptions/argocd/cluster/ztp-core/",
                      help="The location of the GitOps cluster directory for Telco Core")

  parser.add_argument("--hub-policy-namespace", type=str, default="policies", help="Namespace for the policies")
  parser.add_argument("--hub-policy-cm-name", type=str, default="policy-template-map",
                      help="Name for hub side configmap for policy data keys")
  parser.add_argument("--hub-policy-cm-keys", type=int, default=5, help="Number of keys for the hub side configmap")

  # Workload args
  parser.add_argument("--no-deploy", action="store_true", default=False, help="Do not deploy Telco Core clusters")
  parser.add_argument("--no-policy", action="store_true", default=False, help="Do not update the policy configmap")

  parser.add_argument("-i", "--interval-deploy", type=int, default=3600,
                      help="Time in seconds between deploying Telco Core clusters")
  parser.add_argument("-l", "--last-deploy-runtime", type=int, default=3600,
                      help="Amount of seconds after last cluster deployment to continue running")
  parser.add_argument("-b", "--batch", type=int, default=1, help="Number of clusters to deploy per interval")
  parser.add_argument("-p", "--interval-policy", type=int, default=720,
                      help="Interval between updating configmap used in policy templates")
  parser.add_argument("--max-policy-intervals", type=int, default=10,
                      help="Maximum number of policy intervals to run (Used with --no-deploy only)")

  # Delay args are idle time before and after the workload
  parser.add_argument("-s", "--start-delay", type=int, default=120, help="Delay on start of script")
  parser.add_argument("-e", "--end-delay", type=int, default=120, help="Delay on end of script")

  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")

  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  if cliargs.no_deploy and cliargs.no_policy:
    parser.error("Cannot set both --no-deploy and --no-policy. Modes are: Deploy+Policy (default), "
                 "Deploy only (--no-policy), or Policy only (--no-deploy).")

  phase_break()
  logger.info("ACM Telco Core Load")
  phase_break()
  logger.debug("CLI Args: {}".format(cliargs))

  # Determine where the report directory will be located
  base_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
  base_dir_down = os.path.dirname(base_dir)
  base_dir_results = os.path.join(base_dir_down, "results")
  report_dir_name = "{}-telco-core-load".format(datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y%m%d-%H%M%S"))
  report_dir = os.path.join(base_dir_results, report_dir_name)
  policy_dir = os.path.join(report_dir, "policy-cm")
  logger.info("Results data captured in: {}".format("/".join(report_dir.split("/")[-2:])))

  clusterinstance_files = []
  if cliargs.no_deploy == False:
    # Detect all clusterinstance file manifests to be deployed
    logger.info("Checking {}clusterinstance/ for cluster instance manifests".format(cliargs.cluster_manifests))
    temp_cluster_list = glob.glob("{}clusterinstance/*-clusterinstance.yml".format(cliargs.cluster_manifests))
    temp_cluster_list.sort()
    for cluster_instance_file in temp_cluster_list:
      logger.debug("Found cluster instance file: {}".format(cluster_instance_file))
      clusterinstance_files.append(cluster_instance_file)

    if len(clusterinstance_files) == 0:
      logger.error("Zero clusters discovered.")
      sys.exit(1)
    deploy_batch_count = ceil(len(clusterinstance_files) / cliargs.batch)
  phase_break()

  logger.info("Workload Parameters")
  if cliargs.no_deploy == False:
    expected_run_time = cliargs.start_delay + (deploy_batch_count - 1) * cliargs.interval_deploy + cliargs.last_deploy_runtime + cliargs.end_delay
    if cliargs.no_policy == False:
      logger.info("* Mode: Deploy+Policy")
    else:
      logger.info("* Mode: Deploy Clusters only")
    logger.info(f" * Start delay: {cliargs.start_delay}s")
    logger.info(f" * Deploy {cliargs.batch} cluster(s) per {cliargs.interval_deploy}s interval")
    logger.info(f"  * Available clusters: {len(clusterinstance_files)}")
    logger.info(f"  * Total batches: {deploy_batch_count}")
    logger.info(f"  * Last deploy runtime: {cliargs.last_deploy_runtime}s")
    if cliargs.no_policy == False:
      logger.info(f" * Update policy configmap ({cliargs.hub_policy_cm_keys} keys) in namespace {cliargs.hub_policy_namespace} per {cliargs.interval_policy}s interval")
    else:
      logger.info(f" * No policy updates")
    logger.info(f" * End delay: {cliargs.end_delay}s")
    logger.info(f"* Expected run time: {expected_run_time}s")
  elif cliargs.no_deploy == True:
    expected_run_time = cliargs.start_delay + cliargs.max_policy_intervals * cliargs.interval_policy + cliargs.end_delay
    logger.info("* Mode: Policy configmap updates only")
    logger.info(f" * Start delay: {cliargs.start_delay}s")
    logger.info(f" * Update policy configmap ({cliargs.hub_policy_cm_keys} keys) in namespace {cliargs.hub_policy_namespace} per {cliargs.interval_policy}s interval")
    logger.info(f"  * Maximum number of policy intervals to run: {cliargs.max_policy_intervals}")
    logger.info(f" * End delay: {cliargs.end_delay}s")
    logger.info(f"* Expected run time: {expected_run_time}s")
  else:
    # Should not occur due to cliargs check above
    logger.error("* Invalid mode.")
    sys.exit(1)

  phase_break()
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
  os.mkdir(policy_dir)

  # Start of workload with start delay
  workload_start_time = time.time()
  if cliargs.start_delay > 0:
    phase_break()
    logger.info("Sleeping {}s for start delay".format(cliargs.start_delay))
    total_start_delay = cliargs.start_delay
    while(total_start_delay > 300):
      time.sleep(300)
      total_start_delay -= 300
      logger.info("{}s remaining in start delay".format(total_start_delay))
    # Sleep remaining less than 5 minutes time
    time.sleep(total_start_delay)
  start_delay_complete_ts = time.time()


  total_clusters_deployed = 0
  total_policy_cm_updates = 0
  deployed_clusters = []
  cluster_deployed_timestamps = []

  next_deploy_time = workload_start_time + cliargs.start_delay
  next_policy_time = next_deploy_time
  last_logged = workload_start_time
  phase_break()
  logger.info("Begin Telco Core ACM Load - {}".format(int(time.time() * 1000)))
  phase_break()
  current_time = time.time()
  while True:
    # Check if deploying clusters and if it is time to deploy
    if cliargs.no_deploy == False and current_time >= next_deploy_time:
      if total_clusters_deployed >= len(clusterinstance_files):
        # Deploying all clusters triggers the infinite loop to break
        # This occurs after the last cluster is deployed + interval time after that
        logger.info("Completed deploying all clusters")
        break

      if total_clusters_deployed + cliargs.batch >= len(clusterinstance_files):
        new_cluster_count = len(clusterinstance_files) - total_clusters_deployed
        next_deploy_time = next_deploy_time + cliargs.last_deploy_runtime
      else:
        new_cluster_count = cliargs.batch
        next_deploy_time = next_deploy_time + cliargs.interval_deploy
      st = time.time()
      deployed_clusters.extend(clusterinstance_files[total_clusters_deployed:total_clusters_deployed + new_cluster_count])
      commit_message = "Deploying new cluster(s): {}".format(', '.join([x.split("/")[-1].split("-clusterinstance.yml")[0] for x in clusterinstance_files[total_clusters_deployed:total_clusters_deployed + new_cluster_count]]))
      deploy_clusters(deployed_clusters, commit_message, cliargs.gitops_dir)
      et = time.time()
      cluster_deployed_timestamps.append(et)
      logger.info("Deploying took: {}".format(round(et - st, 1)))
      total_clusters_deployed += new_cluster_count

    elif cliargs.no_deploy == True:
      # Not deploying clusters, thus break once max policy intervals are reached
      if total_policy_cm_updates >= cliargs.max_policy_intervals:
        logger.info("Completed policy configmap updates")
        break

    # Check if updating policy configmap and if it is time to update
    if cliargs.no_policy == False and current_time >= next_policy_time:
      logger.info("Apply new policy cm with keys: {}".format(policy_cm_keys))
      policy_cm_keys[starting_key_increment % len(policy_cm_keys)] += 1
      starting_key_increment += 1
      update_policy_cm(cliargs.hub_policy_namespace, cliargs.hub_policy_cm_name, policy_cm_keys, policy_dir, cliargs.kubeconfig)
      next_policy_time = next_policy_time + cliargs.interval_policy
      total_policy_cm_updates += 1

    # Log something to make sure we know this is still alive every 5 minutes
    if current_time - 300 > last_logged:
      last_logged = current_time
      remaining_deploy_time = round(next_deploy_time - current_time)
      remaining_policy_time = round(next_policy_time - current_time)
      if cliargs.no_deploy == False:
        logger.info("Total clusters deployed: {}".format(total_clusters_deployed))
        if total_clusters_deployed >= len(clusterinstance_files):
          logger.info("Last cluster deployed, remaining interval time: {}s :: {}".format(remaining_deploy_time, str(timedelta(seconds=remaining_deploy_time))))
        else:
          logger.info("Time until next cluster to deploy: {}s :: {}".format(remaining_deploy_time, str(timedelta(seconds=remaining_deploy_time))))
      if cliargs.no_policy == False:
        if cliargs.no_deploy == True:
          logger.info("Total policy updates: {} of {}".format(total_policy_cm_updates, cliargs.max_policy_intervals))
          if total_policy_cm_updates >= cliargs.max_policy_intervals:
            logger.info("Last policy update, remaining interval time: {}s :: {}".format(remaining_policy_time, str(timedelta(seconds=remaining_policy_time))))
        else:
          logger.info("Total policy updates: {}".format(total_policy_cm_updates))
        logger.info("Time until next policy update: {}s :: {}".format(remaining_policy_time, str(timedelta(seconds=remaining_policy_time))))

    time.sleep(.1)
    current_time = time.time()
    # End run loop

  # End of workload with end delay
  end_delay_start_ts = time.time()
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

  end_time = time.time()

  # Make a report card
  with open("{}/report.txt".format(report_dir), "w") as report:
    phase_break(True, report)
    log_write(report, "acm-telco-core-load Report Card")
    phase_break(True, report)
    log_write(report, "Workload Parameters")
    if cliargs.no_deploy == False and cliargs.no_policy == False:
      log_write(report, "* Mode: Deploy+Policy")
      log_write(report, f" * Start delay: {cliargs.start_delay}s")
      log_write(report, f" * Deploy {cliargs.batch} cluster(s) per {cliargs.interval_deploy}s interval")
      log_write(report, f"  * Available clusters: {len(clusterinstance_files)}")
      log_write(report, f"  * Total batches: {deploy_batch_count}")
      log_write(report, f"  * Last deploy runtime: {cliargs.last_deploy_runtime}s")
      log_write(report, f" * Update policy configmap ({cliargs.hub_policy_cm_keys} keys) in namespace {cliargs.hub_policy_namespace} per {cliargs.interval_policy}s interval")
      log_write(report, f" * End delay: {cliargs.end_delay}s")
    elif cliargs.no_deploy == False and cliargs.no_policy == True:
      log_write(report, " * Mode: Deploy Clusters only")
      log_write(report, f" * Start delay: {cliargs.start_delay}s")
      log_write(report, f" * Deploy {cliargs.batch} cluster(s) per {cliargs.interval_deploy}s interval")
      log_write(report, f"  * Available clusters: {len(clusterinstance_files)}")
      log_write(report, f"  * Total batches: {deploy_batch_count}")
      log_write(report, f"  * Last deploy runtime: {cliargs.last_deploy_runtime}s")
      log_write(report, f" * End delay: {cliargs.end_delay}s")
    elif cliargs.no_deploy == True and cliargs.no_policy == False:
      log_write(report, " * Mode: Policy configmap updates only")
      log_write(report, f" * Start delay: {cliargs.start_delay}s")
      log_write(report, f" * Update policy configmap ({cliargs.hub_policy_cm_keys} keys) in namespace {cliargs.hub_policy_namespace} per {cliargs.interval_policy}s interval")
      log_write(report, f"  * Maximum number of policy intervals to run: {cliargs.max_policy_intervals}")
      log_write(report, f" * End delay: {cliargs.end_delay}s")
    log_write(report, "Workload Results")
    log_write(report, " * Total cluster(s) deployed: {}".format(total_clusters_deployed))
    log_write(report, " * Total policy cm updates: {}".format(total_policy_cm_updates))
    log_write(report, "Workload Timestamps")
    log_write(report, " * Start Time: {} {}".format(datetime.fromtimestamp(workload_start_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), int(workload_start_time * 1000)))
    log_write(report, " * Start Delay Complete Time: {}".format(datetime.fromtimestamp(start_delay_complete_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    for i, ts in enumerate(cluster_deployed_timestamps):
      log_write(report, " * Cluster(s) Batch {} deployed: {}".format(i, datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    log_write(report, " * End Delay Start Time: {}".format(datetime.fromtimestamp(end_delay_start_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    log_write(report, " * End Time: {} {}".format(datetime.fromtimestamp(end_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), int(end_time * 1000)))

  logger.info("Took {}s".format(round(end_time - start_time, 1)))


if __name__ == "__main__":
  sys.exit(main())
