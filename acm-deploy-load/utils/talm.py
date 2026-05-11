#!/usr/bin/env python3
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

import json
import logging
from utils.command import command


logger = logging.getLogger("acm-deploy-load")


def detect_talm_csv(kubeconfig=None):
  logger.info("Checking for TALM ClusterServiceVersion in openshift-operators")
  if kubeconfig is None:
    oc_cmd = ["oc", "get", "csv", "-n", "openshift-operators", "-o", "json"]
  else:
    oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "csv", "-n", "openshift-operators", "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc == 0:
    for item in json.loads(output).get("items", []):
      name = item.get("metadata", {}).get("name", "")
      if "topology-aware-lifecycle-manager" in name:
        logger.info("Detected TALM CSV in openshift-operators: {}".format(name))
        return True
  logger.info("No TALM CSV found in openshift-operators")
  return False


def detect_talm_minor(default_talm_version, dry_run):
  talm_version = default_talm_version
  logger.info("Detecting TALM version by image tag")
  # Try repo install (openshift-cluster-group-upgrades) — image tag carries version
  oc_cmd = ["oc", "get", "deploy", "-n", "openshift-cluster-group-upgrades", "cluster-group-upgrades-controller-manager-v2", "-o", "json"]
  rc, output = command(oc_cmd, dry_run, retries=3, no_log=True)
  if rc != 0:
    logger.warning("talm, oc get deploy -n openshift-cluster-group-upgrades rc: {}".format(rc))
  else:
    if not dry_run:
      td_data = json.loads(output)
      talm_image_ver = ""
      if "spec" in td_data and "template" in td_data["spec"] and "spec" in td_data["spec"]["template"]:
        for container in td_data["spec"]["template"]["spec"]["containers"]:
          if container["name"] == "manager":
            talm_image_ver = container["image"].split(":")[-1]
            break
      if talm_image_ver != "" and "." in talm_image_ver:
        logger.info("Detected TALM Version: {}".format(talm_image_ver))
        return talm_image_ver.split(".")[1]
      logger.warning("Unable to detect TALM version from image tag, trying CSV")

  # OLM/subscription install places TALM in openshift-operators with a SHA digest
  # instead of a version tag; fall back to the ClusterServiceVersion name
  logger.info("Detecting TALM version from ClusterServiceVersion (OLM install)")
  oc_cmd = ["oc", "get", "csv", "-n", "openshift-operators", "-o", "json"]
  rc, output = command(oc_cmd, dry_run, retries=3, no_log=True)
  if rc == 0 and not dry_run:
    for item in json.loads(output).get("items", []):
      name = item.get("metadata", {}).get("name", "")
      if "topology-aware-lifecycle-manager" in name and ".v" in name:
        talm_csv_ver = name.split(".v")[-1]
        if "." in talm_csv_ver:
          logger.info("Detected TALM Version from CSV: {}".format(talm_csv_ver))
          return talm_csv_ver.split(".")[1]
  logger.warning("Unable to detect TALM version, defaulting to: {}".format(talm_version))
  return talm_version.split(".")[1]
