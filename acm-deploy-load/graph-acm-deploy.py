#!/usr/bin/env python3
#
# Graph monitor_data.csv from acm-deploy-load.py
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
import logging
import pandas as pd
import pathlib
import plotly as py
import plotly.figure_factory as ff
import plotly.graph_objects as go
import plotly.express as px
import sys
import time

# TODO:
# Produce concurrency workload graph


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Produce graphs from acm-deploy-load monitor data",
      prog="graph-acm-deploy.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  # Graph Title Data
  parser.add_argument("--acm-version", type=str, default="", help="Sets ACM version for graph title")
  parser.add_argument("--test-version", type=str, default="ZTP Scale Run 1", help="Sets test version for graph title")
  parser.add_argument("--hub-version", type=str, default="", help="Sets OCP Hub version for graph title")
  parser.add_argument("--deploy-version", type=str, default="", help="Sets OCP deployed version for graph title")
  parser.add_argument("--wan-emulation", type=str, default="", help="Sets WAN emulation for graph title")

  # Name of csv file found in results directory
  parser.add_argument("--monitor-data-file-name", type=str, default="monitor_data.csv",
      help="The name of the monitor data csv file.")

  # Graph size
  parser.add_argument("-w", "--width", type=int, default=1000, help="Sets width of all graphs")
  parser.add_argument("-t", "--height", type=int, default=700, help="Sets height of all graphs")

  # Directory to find the csv file for graphing
  parser.add_argument("results_directory", type=str, help="The location of a acm-deploy-load results")

  cliargs = parser.parse_args()

  logger.info("ACM Deploy Graph")
  # logger.info("CLI Args: {}".format(cliargs))
  md_csv_file = "{}/{}".format(cliargs.results_directory, cliargs.monitor_data_file_name)
  if not pathlib.Path(md_csv_file).is_file():
    logger.error("File not found: {}".format(md_csv_file))
    sys.exit(1)

  df = pd.read_csv(md_csv_file)

  cluster_inited = df["cluster_init"].values[-1]
  cluster_completed = df["cluster_install_completed"].values[-1]
  managed = df["managed"].values[-1]
  policy_inited = df["policy_init"].values[-1]
  policy_compliant = df["policy_compliant"].values[-1]
  playbook_completed = df["playbook_completed"].values[-1]

  title_cluster_node = "ACM {} {} ({}/{} clusters)<br>OCP {}, Deployed Clusters {}, W/E {}".format(cliargs.acm_version,
      cliargs.test_version, cluster_completed, cluster_inited, cliargs.hub_version, cliargs.deploy_version,
      cliargs.wan_emulation)
  title_cluster = "ACM {} {} ({}/{} clusters)<br>OCP {}, Deployed Clusters {}, W/E {}".format(cliargs.acm_version,
      cliargs.test_version, managed, cluster_inited, cliargs.hub_version, cliargs.deploy_version, cliargs.wan_emulation)
  title_policy = "ACM {} {} ({}/{} du compliant)<br>OCP {}, Deployed Clusters {}, W/E {}".format(cliargs.acm_version,
      cliargs.test_version, policy_compliant, policy_inited, cliargs.hub_version, cliargs.deploy_version,
      cliargs.wan_emulation)
  title_playbook = "ACM {} {} ({}/{} playbook completed)<br>OCP {}, Deployed Clusters {}, W/E {}".format(cliargs.acm_version,
      cliargs.test_version, playbook_completed, policy_compliant, cliargs.hub_version, cliargs.deploy_version,
      cliargs.wan_emulation)
  title_share = "ACM {} {} ({}/{} compliant clusters)<br>OCP {}, Deployed Clusters {}, W/E {}".format(cliargs.acm_version,
      cliargs.test_version, policy_compliant, cluster_inited, cliargs.hub_version, cliargs.deploy_version,
      cliargs.wan_emulation)
  title_share_playbook = "ACM {} {} ({}/{} playbook completed clusters)<br>OCP {}, Deployed Clusters {}, W/E {}".format(
      cliargs.acm_version, cliargs.test_version, playbook_completed, cluster_inited, cliargs.hub_version,
      cliargs.deploy_version, cliargs.wan_emulation)

  y_cluster_node = ["cluster_applied", "cluster_init", "node_booted", "node_discovered", "cluster_installing",
      "cluster_install_failed", "cluster_install_completed"]
  y_cluster = ["cluster_applied", "cluster_init", "cluster_installing", "cluster_install_failed",
      "cluster_install_completed", "managed"]
  y_policy = ["cluster_init", "cluster_install_completed", "managed", "policy_init", "policy_applying", "policy_timedout",
      "policy_compliant"]
  y_playbook = ["cluster_init", "managed", "playbook_notstarted", "playbook_running", "playbook_completed"]
  y_share = ["cluster_applied", "cluster_init", "node_booted", "node_discovered", "cluster_installing",
      "cluster_install_failed", "cluster_install_completed", "managed", "policy_applying", "policy_timedout",
      "policy_compliant"]
  y_share2 = ["cluster_applied", "cluster_init", "cluster_installing", "cluster_install_failed",
      "cluster_install_completed", "managed", "policy_applying", "policy_timedout", "policy_compliant"]
  y_share_playbook = ["cluster_applied", "cluster_init", "cluster_installing", "cluster_install_failed",
      "cluster_install_completed", "managed", "policy_applying", "policy_timedout", "policy_compliant",
      "playbook_notstarted", "playbook_running", "playbook_completed"]

  l = {"value" : "# clusters", "date" : ""}
  l2 = {"value" : "# clusters or # nodes", "date" : ""}

  ts = datetime.utcfromtimestamp(time.time()).strftime("%Y%m%d-%H%M%S")

  logger.info("Creating Graph - {}/cluster-node-{}.png".format(cliargs.results_directory, ts))
  fig_cluster_node = px.line(df, x="date", y=y_cluster_node, labels=l2, width=cliargs.width, height=cliargs.height)
  fig_cluster_node.update_layout(title=title_cluster_node, legend_orientation="v")
  fig_cluster_node.write_image("{}/cluster-node-{}.png".format(cliargs.results_directory, ts), width=cliargs.width, height=cliargs.height)

  logger.info("Creating Graph - {}/cluster-{}.png".format(cliargs.results_directory, ts))
  fig_cluster = px.line(df, x="date", y=y_cluster, labels=l, width=cliargs.width, height=cliargs.height)
  fig_cluster.update_layout(title=title_cluster, legend_orientation="v")
  fig_cluster.write_image("{}/cluster-{}.png".format(cliargs.results_directory, ts), width=cliargs.width, height=cliargs.height)

  logger.info("Creating Graph - {}/policy-{}.png".format(cliargs.results_directory, ts))
  fig_policy = px.line(df, x="date", y=y_policy, labels=l, width=cliargs.width, height=cliargs.height)
  fig_policy.update_layout(title=title_policy, legend_orientation="v")
  fig_policy.write_image("{}/policy-{}.png".format(cliargs.results_directory, ts), width=cliargs.width, height=cliargs.height)

  logger.info("Creating Graph - {}/playbook-{}.png".format(cliargs.results_directory, ts))
  fig_policy = px.line(df, x="date", y=y_playbook, labels=l, width=cliargs.width, height=cliargs.height)
  fig_policy.update_layout(title=title_playbook, legend_orientation="v")
  fig_policy.write_image("{}/playbook-{}.png".format(cliargs.results_directory, ts), width=cliargs.width, height=cliargs.height)

  logger.info("Creating Graph - {}/share-{}.png".format(cliargs.results_directory, ts))
  fig_share = px.line(df, x="date", y=y_share, labels=l2, width=cliargs.width, height=cliargs.height)
  fig_share.update_layout(title=title_share, legend_orientation="v")
  fig_share.write_image("{}/share-{}.png".format(cliargs.results_directory, ts), width=cliargs.width, height=cliargs.height)

  logger.info("Creating Graph - {}/share2-{}.png".format(cliargs.results_directory, ts))
  fig_share = px.line(df, x="date", y=y_share2, labels=l, width=cliargs.width, height=cliargs.height)
  fig_share.update_layout(title=title_share, legend_orientation="v")
  fig_share.write_image("{}/share2-{}.png".format(cliargs.results_directory, ts), width=cliargs.width, height=cliargs.height)

  logger.info("Creating Graph - {}/playbook-share-{}.png".format(cliargs.results_directory, ts))
  fig_share = px.line(df, x="date", y=y_share_playbook, labels=l, width=cliargs.width, height=cliargs.height)
  fig_share.update_layout(title=title_share_playbook, legend_orientation="v")
  fig_share.write_image("{}/playbook-share-{}.png".format(cliargs.results_directory, ts), width=cliargs.width, height=cliargs.height)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
