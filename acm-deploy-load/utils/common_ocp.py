#!/usr/bin/env python3
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

from utils.command import command
import base64
import json
import logging
import time
import sys

logger = logging.getLogger("acm-deploy-load")


def detect_aap_install(kubeconfig=None, dry_run=False):
  logger.info("Detecting AAP install by checking count of aap objects in ansible-automation-platform namespace")
  if kubeconfig is None:
    oc_cmd = ["oc", "get", "aap", "-n", "ansible-automation-platform", "-o", "json"]
  else:
    oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "aap", "-n", "ansible-automation-platform", "-o", "json"]
  rc, output = command(oc_cmd, dry_run, no_log=True)
  if rc != 0:
    logger.error("oc get aap rc: {}".format(rc))
    sys.exit(1)
  if not dry_run:
    aap_data = json.loads(output)
    if len(aap_data["items"]) > 0:
      return True
    else:
      return False
  else:
    # Pretend AAP install detected for dry-run
    return True


def get_ocp_namespace_list(kubeconfig):
  logger.info("Getting OCP namespace list")
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "namespace", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("oc get namespace rc: {}".format(rc))
    sys.exit(1)
  namespace_data = json.loads(output)
  namespaces = [item["metadata"]["name"] for item in namespace_data["items"]]
  return namespaces


def get_ocp_version(kubeconfig):
  logger.info("Getting OCP version")
  version = {}
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "version", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("oc version rc: {}".format(rc))
    sys.exit(1)
  version_data = json.loads(output)
  if "openshiftVersion" in version_data:
    version_key = "openshiftVersion"
  elif "releaseClientVersion" in version_data:
    logger.info("openshiftVersion not found in oc version, falling back to releaseClientVersion")
    # If this fallback occurs, it means that the initial cluster install likely ended in partial state
    version_key = "releaseClientVersion"
  else:
    logger.warning("Unable to determine ocp version via oc version: {}".format(version_data))
    version["major"] = 0
    version["minor"] = 0
    version["patch"] = "0"
    return version

  logger.debug("Version is {}".format(version_data[version_key]))
  version["major"] = int(version_data[version_key].split(".")[0])
  version["minor"] = int(version_data[version_key].split(".")[1])
  # Sometimes patch version includes string data (Ex 4.14.0-rc.0)
  version["patch"] = ".".join(version_data[version_key].split(".")[2:])
  return version


def get_prometheus_token(kubeconfig, ocp_version):
  if ocp_version["major"] == 4 and ocp_version["minor"] > 10:
    # 4.11 requires us to create the token instead of find it in a secret
    # --duration=24h could be passed to get a token for longer duration
    oc_cmd = ["oc", "--kubeconfig", kubeconfig, "create", "token", "prometheus-k8s", "-n", "openshift-monitoring"]
    rc, output = command(oc_cmd, False, no_log=True)
    if rc != 0:
      logger.error("oc create token prometheus-k8s -n openshift-monitoring rc: {}".format(rc))
      output = ""
    return output
  elif ocp_version["major"] == 4 and ocp_version["minor"] <= 10:
    # 4.10 and below the token is located in a secret
    oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "serviceaccount", "prometheus-k8s", "-n", "openshift-monitoring", "-o", "json"]
    rc, output = command(oc_cmd, False, no_log=True)
    if rc != 0:
      logger.error("oc get serviceaccount prometheus-k8s -n openshift-monitoring rc: {}".format(rc))
      return ""
    prom_sa_data = json.loads(output)

    for secret_name in prom_sa_data["secrets"]:
      if "token" in secret_name["name"]:
        prom_token_name = secret_name["name"]
        break

    if prom_token_name == "":
      logger.error("Unable to identify prometheus token name")
      return ""

    oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "secret", prom_token_name, "-n", "openshift-monitoring", "-o", "json"]
    rc, output = command(oc_cmd, False, no_log=True)
    if rc != 0:
      logger.error("oc get secret {} -n openshift-monitoring rc: {}".format(prom_token_name, rc))
      return ""
    prom_secret_data = json.loads(output)

    token = (base64.b64decode(prom_secret_data["data"]["token"])).decode("utf-8")
    if token == "":
      logger.error("Unable to obtain prometheus token")
      return ""
  return token


def get_thanos_querier_route(kubeconfig):
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "route", "thanos-querier", "-n", "openshift-monitoring", "-o", "jsonpath={.spec.host}"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("oc get route thanos-querier -n openshift-monitoring rc: {}".format(rc))
    return ""

  if "thanos-querier" in output:
    return "https://{}".format(output)
  else:
    logger.error("Failed to find route for thanos-querier")
    return ""
