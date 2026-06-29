#!/usr/bin/env python3
#
# Check if cluster is healthy/stable
# * Check if clusterversion is available
# * Check if all clusteroperators available
# * Check if all nodes are ready
# * Check if all machineconfigpools updated
# * Check for etcd leader elections in the last hour
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
import json
import logging
import requests
import sys
import time
import urllib3
from utils.command import command
from utils.common_ocp import get_ocp_version
from utils.common_ocp import get_prometheus_token
from utils.common_ocp import get_thanos_querier_route


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# TODO: Future Enhancements:
# * Check if nodes flapped? (in last hour or larger period time)
# * Check critical ocp pods (Ex kube-apiserver) for restarts in last hour (or timeframe)
# * Abstract the prometheus query logic such that more queries can be completed easily
# * Create a test namespace, deployment, pod, service, route and check route for http 200, then tear down


def check_clusterversion(kubeconfig):
  logger.debug("Checking clusterversion")
  success = True
  messages = []
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterversion", "version", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("check_clusterversion, oc get clusterversion version rc: {}".format(rc))
    sys.exit(1)
  cv_data = json.loads(output)

  cv_available = [con for con in cv_data["status"]["conditions"] if con["type"] == "Available"][0]
  cv_failing = [con for con in cv_data["status"]["conditions"] if con["type"] == "Failing"][0]
  cv_progressing = [con for con in cv_data["status"]["conditions"] if con["type"] == "Progressing"][0]

  if cv_available["status"] != "True":
    messages.append("ClusterVersion is not Available")
    success = False

  if cv_failing["status"] == "True":
    messages.append("ClusterVersion is Failing ({})".format(cv_failing["reason"]))
    success = False

  if cv_progressing["status"] == "True":
    messages.append("ClusterVersion is Progressing ({})".format(cv_progressing["reason"]))
    success = False
  return success, messages


def check_clusteroperators(kubeconfig):
  logger.debug("Checking clusteroperators")
  success = True
  messages = []
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusteroperators", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("check_clusteroperators, oc get clusteroperators rc: {}".format(rc))
    sys.exit(1)
  co_data = json.loads(output)

  for operator in co_data["items"]:
    message = ""
    operator_name = operator["metadata"]["name"]
    co_available = [con for con in operator["status"]["conditions"] if con["type"] == "Available"][0]
    co_degraded = [con for con in operator["status"]["conditions"] if con["type"] == "Degraded"][0]
    co_progressing = [con for con in operator["status"]["conditions"] if con["type"] == "Progressing"][0]
    logger.debug("Operator: {}, Available: {}, Progressing: {}, Degraded: {}".format(
        operator_name, co_available["status"], co_progressing["status"], co_degraded["status"]))

    message = "ClusterOperator {} is Available".format(operator_name)
    if co_available["status"] != "True":
      success = False
      message = "ClusterOperator {} is not Available".format(operator_name)

    if co_degraded["status"] == "True":
      success = False
      message +=  " and Degraded ({})".format(co_degraded["reason"])

    if co_progressing["status"] == "True":
      success = False
      message +=  " and Progressing"

    if co_available["status"] != "True" or co_degraded["status"] == "True" or co_progressing["status"] == "True":
      messages.append(message)
  return success, messages


def check_nodes(kubeconfig):
  logger.debug("Checking nodes")
  success = True
  messages = []
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "nodes", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("check_nodes, oc get nodes rc: {}".format(rc))
    sys.exit(1)
  no_data = json.loads(output)

  for node in no_data["items"]:
    message = ""
    node_name = node["metadata"]["name"]
    no_ready = [con for con in node["status"]["conditions"] if con["type"] == "Ready"][0]
    no_memory = [con for con in node["status"]["conditions"] if con["type"] == "MemoryPressure"][0]
    no_disk = [con for con in node["status"]["conditions"] if con["type"] == "DiskPressure"][0]
    no_pid = [con for con in node["status"]["conditions"] if con["type"] == "PIDPressure"][0]
    logger.debug("Node: {}, Ready: {}, MemoryPressure: {}, DiskPressure: {}, PIDPressure: {}".format(
        node_name, no_ready["status"], no_memory["status"], no_disk["status"], no_pid["status"]))

    message = "Node {}".format(node_name)
    if no_ready["status"] != "True" or no_ready["status"] == "Unknown":
      message += " is not Ready ({})".format(no_ready["reason"])
      success = False
    else:
      message += " is Ready"

    if no_memory["status"] == "True" or no_memory["status"] == "Unknown":
      message += " has MemoryPressure ({})".format(no_memory["reason"])
      success = False

    if no_disk["status"] == "True" or no_disk["status"] == "Unknown":
      message += " has DiskPressure ({})".format(no_disk["reason"])
      success = False

    if no_pid["status"] == "True" or no_pid["status"] == "Unknown":
      message += " has PIDPressure ({})".format(no_pid["reason"])
      success = False

    if ((no_ready["status"] != "True" or no_ready["status"] == "Unknown") or
          (no_memory["status"] == "True" or no_memory["status"] == "Unknown") or
          (no_disk["status"] == "True" or no_disk["status"] == "Unknown") or
          (no_pid["status"] == "True" or no_pid["status"] == "Unknown")):
      messages.append(message)

  return success, messages


def check_machineconfigpools(kubeconfig):
  logger.debug("Checking machineconfigpools")
  success = True
  messages = []
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "machineconfigpools", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("check_machineconfigpools, oc get machineconfigpools rc: {}".format(rc))
    sys.exit(1)
  mcp_data = json.loads(output)

  for mcp in mcp_data['items']:
    mcp_name = mcp["metadata"]["name"]
    mcp_updated = [con for con in mcp["status"]["conditions"] if con["type"] == "Updated"][0]
    mcp_updating = [con for con in mcp["status"]["conditions"] if con["type"] == "Updating"][0]
    mcp_nodedegraded = [con for con in mcp["status"]["conditions"] if con["type"] == "NodeDegraded"][0]
    mcp_degraded = [con for con in mcp["status"]["conditions"] if con["type"] == "Degraded"][0]
    logger.debug("MCP: {}, Updated: {}, Updating: {}, NodeDegraded: {}, Degraded: {}".format(
        mcp_name, mcp_updated["status"], mcp_updating["status"], mcp_nodedegraded["status"], mcp_degraded["status"]))

    message = "MCP {}".format(mcp_name)
    if mcp_updated["status"] != "True":
      message += " is not Updated ({})".format(mcp_updated["reason"])
      success = False

    if mcp_updating["status"] == "True":
      message += " is Updating ({})".format(mcp_updating["reason"])
      success = False

    if mcp_nodedegraded["status"] == "True":
      message += " is NodeDegraded ({})".format(mcp_nodedegraded["reason"])
      success = False

    if mcp_degraded["status"] == "True":
      message += " is Degraded ({})".format(mcp_degraded["reason"])
      success = False

    if ((mcp_updated["status"] != "True") or
          (mcp_updating["status"] == "True") or
          (mcp_nodedegraded["status"] == "True") or
          (mcp_degraded["status"] == "True")):
      messages.append(message)

  return success, messages


def check_etcd_leader_elections(kubeconfig, version, hours):
  logger.debug("Checking for etcd leader elections")
  success = True
  messages = []

  querier_route = get_thanos_querier_route(kubeconfig)
  if querier_route == "":
    logger.error("Could not obtain the thanos querier route")
    success = False
    messages.append("EtcdLeaderElections: Could not obtain the thanos querier route")
  else:
    logger.debug("Route to Query: {}".format(querier_route))

    prom_token_data = get_prometheus_token(kubeconfig, version)
    if prom_token_data == "":
      logger.error("Could not obtain the prometheus token")
      success = False
      messages.append("EtcdLeaderElections: Could not obtain the prometheus token")
    else:
      query = "increase(etcd_server_leader_changes_seen_total[{}h])".format(hours)
      query_endpoint = "{}/api/v1/query?query={}".format(querier_route, query)
      headers = {"Authorization": "Bearer {}".format(prom_token_data)}
      query_data = requests.post(query_endpoint, headers=headers, verify=False).json()

      if "data" in query_data:
        logger.debug("Length of returned data: {}".format(len(query_data["data"]["result"])))

        for result in query_data["data"]["result"]:
          if float(result["value"][1]) > 0:
            logger.debug("Pod: {}, Instance: {}, Result: {}".format(result["metric"]["pod"],result["metric"]["instance"], float(result["value"][1])))
            logger.debug("etcd encountered leader election(s) in the {} hour(s)".format(hours))
            success = False
            messages.append("EtcdLeaderElections: Pod: {}, Election Count: {}, Hours Queried: {}".format(result["metric"]["pod"], float(result["value"][1]), hours))
      else:
        logger.error("No data returned from query: {}".format(query))
        success = False
        messages.append("EtcdLeaderElections: No data returned from prometheus query: {}".format(query))
  return success, messages


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Check that an OpenShift cluster is healthy and stable",
      prog="ocp-health.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/mno/kubeconfig",
                      help="Changes which kubeconfig to connect to a cluster")

  parser.add_argument("-e", "--etcd-hours", type=int, default=1,
                      help="Number of hours to query to examine for etcd leader elections")

  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  healthy = 0
  unhealthy = 0
  report = []
  details = []

  version = get_ocp_version(cliargs.kubeconfig)
  logger.info("OCP version is {}.{}.{}".format(version["major"], version["minor"], version["patch"]))

  logger.info("Checking cluster")

  c_cv, msgs = check_clusterversion(cliargs.kubeconfig)
  details.extend(msgs)
  if c_cv:
    healthy += 1
    report.append("clusterversion: Passed")
  else:
    unhealthy += 1
    report.append("clusterversion: Failed")

  c_co, msgs = check_clusteroperators(cliargs.kubeconfig)
  details.extend(msgs)
  if c_co:
    healthy += 1
    report.append("clusteroperators: Passed")
  else:
    unhealthy += 1
    report.append("clusteroperators: Failed")

  c_nodes, msgs = check_nodes(cliargs.kubeconfig)
  details.extend(msgs)
  if c_nodes:
    healthy += 1
    report.append("nodes: Passed")
  else:
    unhealthy += 1
    report.append("nodes: Failed")

  c_mcp, msgs = check_machineconfigpools(cliargs.kubeconfig)
  details.extend(msgs)
  if c_mcp:
    healthy += 1
    report.append("machineconfigpool: Passed")
  else:
    unhealthy += 1
    report.append("machineconfigpool: Failed")

  c_etcd_leader, msgs = check_etcd_leader_elections(cliargs.kubeconfig, version, cliargs.etcd_hours)
  details.extend(msgs)
  if c_etcd_leader:
    healthy += 1
    report.append("etcd leader elections: Passed")
  else:
    unhealthy += 1
    report.append("etcd leader elections: Failed")

  logger.info("################################################################################")
  logger.info("Report:\n{}".format("\n".join(report)))
  logger.info("################################################################################")
  if len(details) > 0:
    logger.info("Details:\n{}".format("\n".join(details)))
  else:
    logger.info("Details: None")
  logger.info("################################################################################")
  if unhealthy > 0:
    logger.warning("Cluster failed {} out of {} checks".format(unhealthy, healthy + unhealthy))
  else:
    logger.info("Cluster passed all {} checks and appears healthy!!!".format(healthy))
  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))
  return unhealthy

if __name__ == "__main__":
  sys.exit(main())
