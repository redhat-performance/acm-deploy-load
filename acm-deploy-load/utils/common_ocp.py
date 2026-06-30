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


def detect_aap_instance(kubeconfig, dry_run=False):
  logger.info("Checking for AnsibleAutomationPlatform instance")
  if dry_run:
    logger.info("Dry-run: assuming AAP instance exists")
    return True
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "ansibleautomationplatform",
      "-n", "ansible-automation-platform", "-o", "jsonpath={.items[0].metadata.name}"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0 or not output.strip():
    logger.info("No AnsibleAutomationPlatform instance found")
    return False
  logger.info("AnsibleAutomationPlatform instance found: {}".format(output.strip()))
  return True


def get_aap_version(kubeconfig, dry_run=False):
  logger.info("Getting AnsibleAutomationPlatform version")
  if dry_run:
    logger.info("Dry-run: assuming AAP installed")
    return "aap-operator (dry-run)"
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "csv", "-n", "ansible-automation-platform", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.warning("AnsibleAutomationPlatform CSV lookup failed (rc: {}), assuming not installed".format(rc))
    return ""
  csv_data = json.loads(output)
  for item in csv_data.get("items", []):
    name = item.get("metadata", {}).get("name", "")
    if name.startswith("aap-operator"):
      logger.info("AnsibleAutomationPlatform version: {}".format(name))
      return name
  logger.warning("AnsibleAutomationPlatform CSV not found, assuming not installed")
  return ""


def get_base_ocp_namespaces(ocp_version):
  # 4.20/4.21 OpenShift Namespaces for "Base OCP"
  ocp_4_20_base_namespaces = [
    "openshift-apiserver",
    "openshift-apiserver-operator",
    "openshift-authentication",
    "openshift-authentication-operator",
    "openshift-catalogd",
    "openshift-cloud-controller-manager-operator",
    "openshift-cloud-credential-operator",
    "openshift-cluster-machine-approver",
    "openshift-cluster-node-tuning-operator",
    "openshift-cluster-olm-operator",
    "openshift-cluster-samples-operator",
    "openshift-cluster-storage-operator",
    "openshift-cluster-version",
    "openshift-config-operator",
    "openshift-console",
    "openshift-console-operator",
    "openshift-controller-manager",
    "openshift-controller-manager-operator",
    "openshift-dns",
    "openshift-dns-operator",
    "openshift-etcd",
    "openshift-etcd-operator",
    "openshift-image-registry",
    "openshift-ingress",
    "openshift-ingress-canary",
    "openshift-ingress-operator",
    "openshift-insights",
    "openshift-kni-infra",
    "openshift-kube-apiserver",
    "openshift-kube-apiserver-operator",
    "openshift-kube-controller-manager",
    "openshift-kube-controller-manager-operator",
    "openshift-kube-scheduler",
    "openshift-kube-scheduler-operator",
    "openshift-kube-storage-version-migrator",
    "openshift-kube-storage-version-migrator-operator",
    "openshift-machine-api",
    "openshift-machine-config-operator",
    "openshift-marketplace",
    "openshift-monitoring",
    "openshift-multus",
    "openshift-network-console",
    "openshift-network-diagnostics",
    "openshift-network-node-identity",
    "openshift-network-operator",
    "openshift-oauth-apiserver",
    "openshift-operator-controller",
    "openshift-operator-lifecycle-manager",
    "openshift-ovn-kubernetes",
    "openshift-route-controller-manager",
    "openshift-service-ca",
    "openshift-service-ca-operator",
  ]
  # 4.20, 4.21, and 4.22 have the same base namespaces
  if ocp_version["major"] == 4 and ocp_version["minor"] in [20, 21, 22]:
    return ocp_4_20_base_namespaces
  else:
    return ocp_4_20_base_namespaces


def get_mce_version(kubeconfig, dry_run=False):
  logger.info("Getting MultiClusterEngine version")
  if dry_run:
    return "mce (dry-run)"
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "multiclusterengine", "multiclusterengine",
      "-o", "jsonpath={.status.currentVersion}"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.warning("MultiClusterEngine not found (rc: {})".format(rc))
    return ""
  version = output.strip()
  logger.info("MultiClusterEngine version: {}".format(version))
  return version


def get_mch_version(kubeconfig, dry_run=False):
  logger.info("Getting MultiClusterHub version")
  if dry_run:
    return "mch (dry-run)"
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "multiclusterhub", "multiclusterhub",
      "-n", "open-cluster-management", "-o", "jsonpath={.status.currentVersion}"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.warning("MultiClusterHub not found (rc: {}), ACM may not be installed".format(rc))
    return ""
  version = output.strip()
  logger.info("MultiClusterHub version: {}".format(version))
  return version


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
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterversion", "version", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("oc get clusterversion version rc: {}".format(rc))
    sys.exit(1)
  cv_data = json.loads(output)

  # Prefer the first Completed entry in history; fall back to desired
  version_string = ""
  history = cv_data.get("status", {}).get("history", [])
  for entry in history:
    if entry.get("state", "") == "Completed":
      version_string = entry.get("version", "")
      break
  if not version_string:
    version_string = cv_data.get("status", {}).get("desired", {}).get("version", "")

  if not version_string:
    logger.error("Unable to determine OCP version from ClusterVersion status")
    sys.exit(1)

  logger.info("OCP version: {}".format(version_string))
  version["major"] = int(version_string.split(".")[0])
  version["minor"] = int(version_string.split(".")[1])
  # Sometimes patch version includes string data (Ex 4.14.0-rc.0)
  version["patch"] = ".".join(version_string.split(".")[2:])
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


def validate_kubeconfig(kubeconfig):
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "whoami"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("Kubeconfig validation failed (oc whoami rc: {}): {}".format(rc, kubeconfig))
    sys.exit(1)
  logger.info("Kubeconfig validated, connected as: {}".format(output.strip()))
