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
from datetime import datetime
from utils.command import command
from utils.common_ocp import get_ocp_version
from utils.common_ocp import get_prometheus_token
from utils.common_ocp import get_thanos_querier_route
from utils.time_utils import parse_ts


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# TODO: Future Enhancements:
# * Check if nodes flapped? (in last hour or larger period time)
# * Create a test namespace, deployment, pod, service, route and check route for http 200, then tear down
# * Pending/failed PVC & PV check; pending CSR check; etcd disk-latency percentiles
# * Accurate Prometheus windowed restart counts via increase(kube_pod_container_status_restarts_total[Nh])


def check_clusterversion(kubeconfig):
  logger.debug("Checking clusterversion")
  success = True
  messages = []
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterversion", "version", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("check_clusterversion: oc get clusterversion rc: {}".format(rc))
    return False, ["check_clusterversion: oc command failed (rc {})".format(rc)]
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
    logger.error("check_clusteroperators: oc get clusteroperators rc: {}".format(rc))
    return False, ["check_clusteroperators: oc command failed (rc {})".format(rc)]
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
    logger.error("check_nodes: oc get nodes rc: {}".format(rc))
    return False, ["check_nodes: oc command failed (rc {})".format(rc)]
  no_data = json.loads(output)

  for node in no_data["items"]:
    node_name = node["metadata"]["name"]
    conditions = node["status"].get("conditions", [])
    no_ready = [con for con in conditions if con["type"] == "Ready"][0]
    no_memory = [con for con in conditions if con["type"] == "MemoryPressure"][0]
    no_disk = [con for con in conditions if con["type"] == "DiskPressure"][0]
    no_pid = [con for con in conditions if con["type"] == "PIDPressure"][0]
    no_netunav_list = [con for con in conditions if con["type"] == "NetworkUnavailable"]
    no_netunav = no_netunav_list[0] if no_netunav_list else None
    cordoned = node["spec"].get("unschedulable", False) is True
    logger.debug("Node: {}, Ready: {}, MemoryPressure: {}, DiskPressure: {}, PIDPressure: {}".format(
        node_name, no_ready["status"], no_memory["status"], no_disk["status"], no_pid["status"]))

    node_failed = False
    message = "Node {}".format(node_name)
    if no_ready["status"] != "True":
      message += " is not Ready ({})".format(no_ready["reason"])
      success = False
      node_failed = True
    else:
      message += " is Ready"

    if no_memory["status"] == "True" or no_memory["status"] == "Unknown":
      message += " has MemoryPressure ({})".format(no_memory["reason"])
      success = False
      node_failed = True

    if no_disk["status"] == "True" or no_disk["status"] == "Unknown":
      message += " has DiskPressure ({})".format(no_disk["reason"])
      success = False
      node_failed = True

    if no_pid["status"] == "True" or no_pid["status"] == "Unknown":
      message += " has PIDPressure ({})".format(no_pid["reason"])
      success = False
      node_failed = True

    if no_netunav is not None and (no_netunav["status"] == "True" or no_netunav["status"] == "Unknown"):
      message += " has NetworkUnavailable ({})".format(no_netunav["reason"])
      success = False
      node_failed = True

    if cordoned:
      message += " is cordoned (unschedulable)"

    if node_failed or cordoned:
      messages.append(message)

  return success, messages


def check_machineconfigpools(kubeconfig):
  logger.debug("Checking machineconfigpools")
  success = True
  messages = []
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "machineconfigpools", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("check_machineconfigpools: oc get machineconfigpools rc: {}".format(rc))
    return False, ["check_machineconfigpools: oc command failed (rc {})".format(rc)]
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


def check_pods(kubeconfig, window_hours):
  logger.debug("Checking pods")
  success = True
  messages = []
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "pods", "-A", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("check_pods: oc get pods rc: {}".format(rc))
    return False, ["check_pods: oc command failed (rc {})".format(rc)]
  pods_data = json.loads(output)

  window_seconds = window_hours * 3600
  now = datetime.utcnow()
  total = 0
  issues = 0

  bad_waiting_reasons = {
      "CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "ErrImageNeverPull",
      "ImageInspectError", "InvalidImageName", "RegistryUnavailable",
      "CreateContainerConfigError", "CreateContainerError",
  }

  for pod in pods_data["items"]:
    total += 1
    ns = pod["metadata"]["namespace"]
    name = pod["metadata"]["name"]
    phase = pod["status"].get("phase", "")
    created_ts = parse_ts(pod["metadata"].get("creationTimestamp"))

    if phase == "Succeeded":
      continue

    if phase == "Pending":
      if created_ts != "":
        age_s = (now - created_ts).total_seconds()
        age_str = "{}m".format(int(age_s // 60)) if age_s < 3600 else "{:.1f}h".format(age_s / 3600)
      else:
        age_str = "unknown age"
      messages.append("Pod {}/{}: Pending for {}".format(ns, name, age_str))
      issues += 1
      success = False

    pod_age_s = (now - created_ts).total_seconds() if created_ts != "" else None

    for cs_list_key in ("containerStatuses", "initContainerStatuses", "ephemeralContainerStatuses"):
      for cs in pod["status"].get(cs_list_key, []):
        cs_name = cs.get("name", "")
        restart_count = cs.get("restartCount", 0)
        state = cs.get("state", {})
        waiting = state.get("waiting", {})
        terminated = state.get("terminated", {})
        last_terminated = cs.get("lastState", {}).get("terminated", {})

        waiting_reason = waiting.get("reason")
        if waiting_reason in bad_waiting_reasons:
          logger.debug("Pod {}/{} container {}: {} (restarts={})".format(
              ns, name, cs_name, waiting_reason, restart_count))
          messages.append("Pod {}/{} container {}: {} (restarts={})".format(
              ns, name, cs_name, waiting_reason, restart_count))
          issues += 1
          success = False
          continue

        if terminated:
          term_reason = terminated.get("reason", "")
          term_exit = terminated.get("exitCode", 0)
          if term_reason == "OOMKilled" or term_exit != 0:
            logger.debug("Pod {}/{} container {}: terminated abnormally (reason={}, exitCode={})".format(
                ns, name, cs_name, term_reason, term_exit))
            messages.append("Pod {}/{} container {}: terminated abnormally (reason={}, exitCode={})".format(
                ns, name, cs_name, term_reason, term_exit))
            issues += 1
            success = False
            continue

        if last_terminated:
          finished_at = parse_ts(last_terminated.get("finishedAt"))
          if finished_at != "" and (now - finished_at).total_seconds() <= window_seconds:
            last_reason = last_terminated.get("reason", "")
            logger.debug("Pod {}/{} container {}: restarted within {}h (reason={}, restarts={})".format(
                ns, name, cs_name, window_hours, last_reason, restart_count))
            messages.append("Pod {}/{} container {}: restarted within {}h (reason={}, restarts={})".format(
                ns, name, cs_name, window_hours, last_reason, restart_count))
            issues += 1
            success = False
            continue

        if (cs.get("ready") is False and phase == "Running" and
              pod_age_s is not None and pod_age_s > window_seconds):
          logger.debug("Pod {}/{} container {}: running but not Ready (age>{})".format(
              ns, name, cs_name, window_hours))
          messages.append("Pod {}/{} container {}: running but not Ready (age>{}h)".format(
              ns, name, cs_name, window_hours))
          issues += 1
          success = False

  messages.insert(0, "Pods: {} pod(s) with issues out of {}".format(issues, total))
  return success, messages


def check_workloads(kubeconfig):
  # ClusterOperators only cover core OCP operators; this check catches ACM/add-on/GitOps partial failures
  logger.debug("Checking workloads")
  success = True
  messages = []

  for kind in ("deployments", "statefulsets", "daemonsets"):
    oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", kind, "-A", "-o", "json"]
    rc, output = command(oc_cmd, False, no_log=True)
    if rc != 0:
      logger.error("check_workloads: oc get {} rc: {}".format(kind, rc))
      return False, ["check_workloads: oc get {} failed (rc {})".format(kind, rc)]
    data = json.loads(output)

    for item in data["items"]:
      ns = item["metadata"]["namespace"]
      name = item["metadata"]["name"]
      spec = item.get("spec", {})
      status = item.get("status", {})

      if kind == "daemonsets":
        desired = status.get("desiredNumberScheduled", 0)
        ready = status.get("numberReady", 0)
      else:
        desired = spec.get("replicas", 0)
        ready = status.get("readyReplicas", 0)

      if desired == 0:
        continue

      if ready < desired:
        logger.debug("{} {}/{}: {}/{} ready".format(kind.rstrip("s").capitalize(), ns, name, ready, desired))
        messages.append("{} {}/{}: {}/{} ready".format(kind.rstrip("s").capitalize(), ns, name, ready, desired))
        success = False

  return success, messages


def query_prometheus(kubeconfig, version, query):
  querier_route = get_thanos_querier_route(kubeconfig)
  if querier_route == "":
    return False, [], "Could not obtain the thanos querier route"

  prom_token_data = get_prometheus_token(kubeconfig, version)
  if prom_token_data == "":
    return False, [], "Could not obtain the prometheus token"

  query_endpoint = "{}/api/v1/query?query={}".format(querier_route, query)
  headers = {"Authorization": "Bearer {}".format(prom_token_data)}
  try:
    resp = requests.post(query_endpoint, headers=headers, verify=False)
    query_data = resp.json()
  except Exception as exc:
    return False, [], "Prometheus request failed: {}".format(exc)

  if "data" not in query_data:
    return False, [], "No data returned from query: {}".format(query)

  return True, query_data["data"]["result"], ""


def check_etcd_leader_elections(kubeconfig, version, hours):
  logger.debug("Checking for etcd leader elections")
  success = True
  messages = []

  query = "increase(etcd_server_leader_changes_seen_total[{}h])".format(hours)
  ok, results, err = query_prometheus(kubeconfig, version, query)
  if not ok:
    logger.error("check_etcd_leader_elections: {}".format(err))
    return False, ["EtcdLeaderElections: {}".format(err)]

  logger.debug("Length of returned data: {}".format(len(results)))
  for result in results:
    if float(result["value"][1]) > 0:
      logger.debug("Pod: {}, Instance: {}, Result: {}".format(
          result["metric"]["pod"], result["metric"]["instance"], float(result["value"][1])))
      logger.debug("etcd encountered leader election(s) in the {} hour(s)".format(hours))
      success = False
      messages.append("EtcdLeaderElections: Pod: {}, Election Count: {}, Hours Queried: {}".format(
          result["metric"]["pod"], float(result["value"][1]), hours))
  return success, messages


def check_firing_alerts(kubeconfig, version, skip):
  # Monitoring is often the first thing to break on an unhealthy cluster, so this is enrichment
  # layered on top of pod/workload checks, never the primary signal.
  if skip:
    return True, ["Alerts: skipped"]

  logger.debug("Checking firing alerts")
  success = True
  messages = []

  query = 'ALERTS{alertstate="firing"}'
  ok, results, err = query_prometheus(kubeconfig, version, query)
  if not ok:
    logger.error("check_firing_alerts: {}".format(err))
    return False, ["Alerts: could not reach Prometheus ({}) — availability problem, not a confirmed alert".format(err)]

  counts = {}
  severities = {}
  for result in results:
    alertname = result["metric"].get("alertname", "")
    severity = result["metric"].get("severity", "")
    if alertname == "Watchdog":
      continue
    if severity not in ("warning", "critical"):
      continue
    counts[alertname] = counts.get(alertname, 0) + 1
    severities[alertname] = severity

  for alertname, count in sorted(counts.items()):
    logger.debug("Alert {} ({}): {} firing".format(alertname, severities[alertname], count))
    messages.append("Alert {} ({}): {} firing".format(alertname, severities[alertname], count))
    success = False

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

  parser.add_argument("-w", "--pod-restart-window-hours", type=int, default=1,
                      help="Window in hours for pod restart/OOMKill and not-Ready grace period")

  parser.add_argument("--skip-alerts", action="store_true", default=False,
                      help="Skip the firing-alerts Prometheus check (use when monitoring is absent)")

  parser.add_argument("-o", "--output", type=str, default="",
                      help="Write a plain-text report to this file (includes timestamp and options)")

  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  run_ts = datetime.utcfromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S UTC")

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

  c_pods, msgs = check_pods(cliargs.kubeconfig, cliargs.pod_restart_window_hours)
  details.extend(msgs)
  if c_pods:
    healthy += 1
    report.append("pods: Passed")
  else:
    unhealthy += 1
    report.append("pods: Failed")

  c_workloads, msgs = check_workloads(cliargs.kubeconfig)
  details.extend(msgs)
  if c_workloads:
    healthy += 1
    report.append("workloads: Passed")
  else:
    unhealthy += 1
    report.append("workloads: Failed")

  c_etcd_leader, msgs = check_etcd_leader_elections(cliargs.kubeconfig, version, cliargs.etcd_hours)
  details.extend(msgs)
  if c_etcd_leader:
    healthy += 1
    report.append("etcd leader elections: Passed")
  else:
    unhealthy += 1
    report.append("etcd leader elections: Failed")

  c_alerts, msgs = check_firing_alerts(cliargs.kubeconfig, version, cliargs.skip_alerts)
  details.extend(msgs)
  if c_alerts:
    healthy += 1
    report.append("firing alerts: Passed")
  else:
    unhealthy += 1
    report.append("firing alerts: Failed")

  logger.info("################################################################################")
  logger.info("Report:")
  for line in report:
    logger.info("  {}".format(line))
  logger.info("################################################################################")
  if details:
    logger.info("Details:")
    for line in details:
      logger.info("  {}".format(line))
  else:
    logger.info("Details: None")
  logger.info("################################################################################")
  if unhealthy > 0:
    logger.warning("Cluster failed {} out of {} checks".format(unhealthy, healthy + unhealthy))
  else:
    logger.info("Cluster passed all {} checks and appears healthy!!!".format(healthy))
  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

  if cliargs.output:
    ocp_version_str = "{}.{}.{}".format(version["major"], version["minor"], version["patch"])
    with open(cliargs.output, "w") as f:
      f.write("################################################################################\n")
      f.write("ocp-health.py Health Report\n")
      f.write("Run at:     {}\n".format(run_ts))
      f.write("Kubeconfig: {}\n".format(cliargs.kubeconfig))
      f.write("Options:    --etcd-hours {} --pod-restart-window-hours {}{}".format(
          cliargs.etcd_hours, cliargs.pod_restart_window_hours,
          " --skip-alerts" if cliargs.skip_alerts else ""))
      f.write("\n")
      f.write("OCP Version: {}\n".format(ocp_version_str))
      f.write("################################################################################\n")
      f.write("\nReport:\n")
      for line in report:
        f.write("  {}\n".format(line))
      f.write("\nDetails:\n")
      if details:
        for line in details:
          f.write("  {}\n".format(line))
      else:
        f.write("  None\n")
      f.write("\n################################################################################\n")
      if unhealthy > 0:
        f.write("Result: FAILED {} out of {} checks\n".format(unhealthy, healthy + unhealthy))
      else:
        f.write("Result: PASSED all {} checks\n".format(healthy))
      f.write("Took: {}s\n".format(round(end_time - start_time, 1)))
      f.write("################################################################################\n")
    logger.info("Report written to: {}".format(cliargs.output))

  return unhealthy

if __name__ == "__main__":
  sys.exit(main())
