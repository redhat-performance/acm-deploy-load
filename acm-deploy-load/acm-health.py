#!/usr/bin/env python3
#
# Check if ACM is healthy/stable
# * Check MCH, MCE, and MCO
# * Check for crashlooping pods in namespaces
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
import json
import logging
import sys
import time
from datetime import datetime
from utils.command import command

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


# TODO: Future Enhancements:
# * Implement crashlooping pod/container check for namespaces


def check_multiclusterengine(kubeconfig):
  logger.debug("Checking multiclusterengine")
  success = True
  messages = []
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "multiclusterengine", "multiclusterengine", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("check_multiclusterengine, oc get multiclusterengine multiclusterengine rc: {}".format(rc))
    sys.exit(1)
  mce_data = json.loads(output)

  mce_available = [con for con in mce_data["status"]["conditions"] if con["type"] == "Available"][0]

  if mce_available["status"] != "True":
    messages.append("MultiClusterEngine is not Available")
    success = False

  return success, messages


def check_multiclusterhub(kubeconfig):
  logger.debug("Checking multiclusterhub")
  success = True
  messages = []
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "multiclusterhub", "multiclusterhub", "-n", "open-cluster-management", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("check_multiclusterhub, oc get multiclusterhub multiclusterhub -n open-cluster-management rc: {}".format(rc))
    sys.exit(1)
  mch_data = json.loads(output)

  mch_available = [con for con in mch_data["status"]["conditions"] if con["type"] == "Complete"][0]

  if mch_available["status"] != "True":
    messages.append("MultiClusterHub is not Available")
    success = False

  return success, messages


def check_multiclusterobservability(kubeconfig):
  logger.debug("Checking multiclusterobservability")
  success = True
  messages = []
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "multiclusterobservability", "observability", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("check_multiclusterhub, oc get multiclusterobservability observability rc: {}".format(rc))
    sys.exit(1)
  mco_data = json.loads(output)

  mco_ready = [con for con in mco_data["status"]["conditions"] if con["type"] == "Ready"][0]

  if mco_ready["status"] != "True":
    messages.append("MultiClusterObservability is not Ready")
    success = False

  return success, messages


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Check that an ACM Hub is healthy and stable",
      prog="acm-health.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/mno/kubeconfig",
                      help="Changes which kubeconfig to connect to a cluster")

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

  logger.info("Checking ACM")

  c_mch, msgs = check_multiclusterhub(cliargs.kubeconfig)
  details.extend(msgs)
  if c_mch:
    healthy += 1
    report.append("multiclusterhub: Passed")
  else:
    unhealthy += 1
    report.append("multiclusterhub: Failed")

  c_mce, msgs = check_multiclusterengine(cliargs.kubeconfig)
  details.extend(msgs)
  if c_mce:
    healthy += 1
    report.append("multiclusterengine: Passed")
  else:
    unhealthy += 1
    report.append("multiclusterengine: Failed")

  c_mco, msgs = check_multiclusterobservability(cliargs.kubeconfig)
  details.extend(msgs)
  if c_mco:
    healthy += 1
    report.append("multiclusterobservability: Passed")
  else:
    unhealthy += 1
    report.append("multiclusterobservability: Failed")

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
    logger.warning("ACM failed {} out of {} checks".format(unhealthy, healthy + unhealthy))
  else:
    logger.info("ACM passed all {} checks and appears healthy!!!".format(healthy))
  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

  if cliargs.output:
    with open(cliargs.output, "w") as f:
      f.write("################################################################################\n")
      f.write("acm-health.py Health Report\n")
      f.write("Run at:     {}\n".format(run_ts))
      f.write("Kubeconfig: {}\n".format(cliargs.kubeconfig))
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
