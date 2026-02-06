#!/usr/bin/env python3
#
# Tool to load a hub cluster with policies that creates a workload on the managedclusters
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
from datetime import datetime, timezone
from jinja2 import Template
import logging
import os
import sys
import time
from utils.command import command
from utils.output import phase_break


hub_namespace_template = """---
apiVersion: v1
kind: Namespace
metadata:
  name: {{ name }}
  labels:
    hub-policy-workload: "true"
"""

hub_configmap_template = """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
data:
{%- for key in keys %}
  key{{ key }}: "{{ '%06d' % (key * 100000) }}"
{%- endfor %}
"""

policy_template = """---
apiVersion: apps.open-cluster-management.io/v1
kind: PlacementRule
metadata:
  name: placement-{{ name }}
  namespace: {{ namespace }}
spec:
  clusterSelector:
    matchExpressions:
    - key: {{ selector_key }}
      operator: In
      values:
      - "{{ selector_value }}"
---
apiVersion: policy.open-cluster-management.io/v1
kind: PlacementBinding
metadata:
  name: binding-{{ name }}
  namespace:  {{ namespace }}
placementRef:
  apiGroup: apps.open-cluster-management.io
  kind: PlacementRule
  name: placement-{{ name }}
subjects:
- apiGroup: policy.open-cluster-management.io
  kind: Policy
  name: policy-{{ name }}
---
apiVersion: policy.open-cluster-management.io/v1
kind: Policy
metadata:
  annotations:
    policy.open-cluster-management.io/categories: CM Configuration Management
    policy.open-cluster-management.io/controls: CM-2 Baseline Configuration
    policy.open-cluster-management.io/standards: NIST SP 800-53
  name: policy-{{ name }}
  namespace: {{ namespace }}
spec:
  disabled: false
  remediationAction: enforce
  policy-templates:
  - objectDefinition:
      apiVersion: policy.open-cluster-management.io/v1
      kind: ConfigurationPolicy
      metadata:
        name: cfgpolicy-{{ name }}
      spec:
        remediationAction: enforce
        severity: medium
        object-templates:
        {%- for ns in policy_namespaces %}
        - complianceType: musthave
          objectDefinition:
            apiVersion: v1
            kind: Namespace
            metadata:
              name: {{ ns }}
              labels:
                mc-workload: "true"
        {%- for deploy in deployments[ns] %}
        - complianceType: musthave
          objectDefinition:
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: mc-deploy-{{ deploy }}
              namespace: {{ ns }}
              labels:
                mc-workload: "true"
            spec:
              replicas: {{ replicas }}
              selector:
                matchLabels:
                  app: mc-deploy-{{ deploy }}
              template:
                metadata:
                  labels:
                    app: mc-deploy-{{ deploy }}
                    mc-workload: "true"
                spec:
                  containers:
                  - name: mc-workload
                    image: {{ container_image }}
                    env:
                    - name: PORT
                      value: "{{ container_port }}"
                    - name: KEY1
                      value: '{%raw%}{{{%endraw%}hub fromConfigMap "" "{{ hub_policy_cm_name }}" "key{{ (deploy | int) % hub_policy_cm_key_count }}" hub{%raw%}}}{%endraw%}'
                  {%- if (configmaps[ns][deploy]|length > 0) or (secrets[ns][deploy]|length > 0) %}
                    volumeMounts:
                    {%- for cm in configmaps[ns][deploy] %}
                    - name: {{ cm['v_name'] }}
                      mountPath: /etc/{{ cm['v_name'] }}
                    {%- endfor %}
                    {%- for secret in secrets[ns][deploy] %}
                    - name: {{ secret['v_name'] }}
                      mountPath: /etc/{{ secret['v_name'] }}
                    {%- endfor %}
                  volumes:
                  {%- for cm in configmaps[ns][deploy] %}
                  - name: {{ cm['v_name'] }}
                    configMap:
                      name: {{ cm['name'] }}
                  {%- endfor %}
                  {%- for secret in secrets[ns][deploy] %}
                  - name: {{ secret['v_name'] }}
                    secret:
                      secretName: {{ secret['name'] }}
                  {%- endfor %}
                  {%- endif %}
            status:
              availableReplicas: {{ replicas }}
        {%- for cm in configmaps[ns][deploy] %}
        - complianceType: musthave
          objectDefinition:
            apiVersion: v1
            kind: ConfigMap
            metadata:
              name: {{ cm['name'] }}
              namespace: {{ ns }}
            data:
              mc_workload: "{{ cm['name'] }} - Random data"
        {%- endfor %}
        {%- for secret in secrets[ns][deploy] %}
        - complianceType: musthave
          objectDefinition:
            apiVersion: v1
            kind: Secret
            metadata:
              name: {{ secret['name'] }}
              namespace: {{ ns }}
            data:
              mc_workload: UmFuZG9tIGRhdGEK
        {%- endfor %}
        {%- if service %}
        - complianceType: musthave
          objectDefinition:
            apiVersion: v1
            kind: Service
            metadata:
              name: mc-service-{{ deploy }}
              namespace: {{ ns }}
            spec:
              selector:
                app: mc-deploy-{{ deploy }}
              ports:
                - protocol: TCP
                  name: port
                  port: 8080
                  targetPort: {{ container_port }}
        {%- endif %}
        {%- endfor %}
        {%- endfor %}
"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Tool to load a hub cluster with policies that creates a workload on the managedclusters",
      prog="hub-policy-generator.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/mno/kubeconfig",
                      help="Changes which kubeconfig to connect to a cluster")

  subparsers = parser.add_subparsers(dest="action")
  parser_gen = subparsers.add_parser("generate", help="Creates policies, namespace, configmap and applies manifests",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser_cleanup = subparsers.add_parser("cleanup", help="Cleans up all generated manifests",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser_gen.add_argument("-p", "--policies", type=int, default=1, help="Number of policies to create")
  parser_gen.add_argument("-n", "--namespaces", type=int, default=1, help="Number of namespaces per policy")
  parser_gen.add_argument("-d", "--deployments", type=int, default=1, help="Number of deployments per namespace")
  parser_gen.add_argument("-r", "--replicas", type=int, default=1, help="Number of pod replicas per deployment")

  # Per Deployment config
  parser_gen.add_argument("-c", "--configmaps", type=int, default=1, help="Number of configmaps per deployment")
  parser_gen.add_argument("-s", "--secrets", type=int, default=1, help="Number of secrets per deployment")
  parser_gen.add_argument("-l", "--service", action="store_true", default=False, help="Include service per deployment")
  parser_gen.add_argument("--container-port", type=int, default=8000, help="The container port to expose (PORT Env Var)")

  parser_gen.add_argument("-i", "--container-image", type=str,
                      # default="quay.io/redhat-performance/test-gohttp-probe:v0.0.2", help="The container image to use")
                      default="e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/redhat-performance/test-gohttp-probe:v0.0.2",
                      help="The container image to use")

  parser_gen.add_argument("-m", "--manifests-directory", type=str, help="The location to place hub policy manifests")

  parser.add_argument("--hub-policy-namespace", type=str, default="policies", help="Namespace for the policies")
  parser_gen.add_argument("--hub-policy-cm-name", type=str, default="policy-template-map", help="Name for hub side configmap for policy data keys")
  parser_gen.add_argument("--hub-policy-cm-keys", type=int, default=5, help="Number of keys for the hub side configmap")

  parser_gen.add_argument("--cluster-selector", type=str, default="common=true",
                      help="Cluster selector in key=value format (e.g., common=true, common=core)")

  parser_gen.add_argument("--no-apply", action="store_true", default=False, help="Do not apply the manifests")

  parser.set_defaults(action="generate")

  cliargs = parser.parse_args()

  logger.info("Hub Policy Generator")

  #### Generate Manifests
  if cliargs.action == "generate":

    # Parse cluster selector
    if "=" not in cliargs.cluster_selector:
      logger.error("Invalid cluster selector format. Use key=value format (e.g., common=true)")
      sys.exit(1)
    selector_key, selector_value = cliargs.cluster_selector.split("=", 1)

    manifests_dir = ""
    if cliargs.manifests_directory:
      # Check if directory exists
      if os.path.exists(cliargs.manifests_directory):
        logger.info("Using directory: {}".format(cliargs.manifests_directory))
        manifests_dir = cliargs.manifests_directory
      else:
        logger.error("Manifests directory specified does not exist: {}".format(cliargs.manifests_directory))
        sys.exit(1)
    else:
      base_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
      base_dir_down = os.path.dirname(base_dir)
      base_dir_manifests = os.path.join(base_dir_down, "manifests")
      manifests_dir_name = "hub-policies-{}".format(datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y%m%d-%H%M%S"))
      manifests_dir = os.path.join(base_dir_manifests, manifests_dir_name)
      os.mkdir(manifests_dir)
      logger.info("Using created manifests directory: {}".format(manifests_dir))

    phase_break()

    logger.info("Creating manifests with:")
    logger.info(" * Cluster selector: {}={}".format(selector_key, selector_value))
    logger.info(" * 1 namespace ({}) for policies".format(cliargs.hub_policy_namespace))
    logger.info("   * 1 configmap ({}) with {} keys".format(cliargs.hub_policy_cm_name, cliargs.hub_policy_cm_keys))
    if cliargs.policies > 1:
      logger.info("   * {} policies".format(cliargs.policies))
    else:
      logger.info("   * 1 policy")
    logger.info("     * {} namespaces per policy".format(cliargs.namespaces))
    logger.info("       * {} deployment(s) per namespace with {} pod replicas".format(cliargs.deployments, cliargs.replicas))
    logger.info("       * {} configmap(s) per deployment".format(cliargs.configmaps))
    logger.info("       * {} secret(s) per deployment".format(cliargs.secrets))
    if cliargs.service:
      logger.info("       * 1 service per deployment".format(cliargs.configmaps))
    else:
      logger.info("       * no service per deployment".format(cliargs.configmaps))

    total_ns = cliargs.policies * cliargs.namespaces
    total_deploys = cliargs.policies * cliargs.namespaces * cliargs.deployments
    total_pods = cliargs.policies * cliargs.namespaces * cliargs.deployments * cliargs.replicas
    total_cms = cliargs.policies * cliargs.namespaces * cliargs.deployments * cliargs.configmaps
    total_secrets = cliargs.policies * cliargs.namespaces * cliargs.deployments * cliargs.secrets
    total_services = 0
    if cliargs.service:
      total_services = cliargs.policies * cliargs.namespaces * cliargs.deployments
    total_objs = total_ns + total_deploys + total_pods + total_cms + total_secrets + total_services
    phase_break()
    logger.info("Resulting in a creating the following on a managedcluster:")
    logger.info(" * {} namespaces".format(total_ns))
    logger.info(" * {} deployments".format(total_deploys))
    logger.info(" * {} pod replicas".format(total_pods))
    logger.info(" * {} configmaps".format(total_cms))
    logger.info(" * {} secrets".format(total_secrets))
    logger.info(" * {} services".format(total_services))
    logger.info("Total Objects: {}".format(total_objs))

    phase_break()
    if cliargs.no_apply:
      logger.info("Not Applying Manifests")
    else:
      logger.info("Applying Manifests")

    phase_break()
    logger.info("Rendering Hub Policy Namespace: {}".format(cliargs.hub_policy_namespace))
    t = Template(hub_namespace_template)
    hns_template_rendered = t.render(name=cliargs.hub_policy_namespace)
    with open("{}/{}".format(manifests_dir, "01-policy-namespace.yml"), "w") as file1:
      file1.writelines(hns_template_rendered)

    logger.info("Rendering Hub Policy ConfigMap: {}".format(cliargs.hub_policy_cm_name))
    keys = [i for i in range(cliargs.hub_policy_cm_keys)]
    t = Template(hub_configmap_template)
    hcm_template_rendered = t.render(
        name=cliargs.hub_policy_cm_name,
        namespace=cliargs.hub_policy_namespace,
        keys=keys)
    with open("{}/{}".format(manifests_dir, "02-policy-cm.yml"), "w") as file1:
      file1.writelines(hcm_template_rendered)

    for policy in range(cliargs.policies):
      policy_name = "policy-{:04d}".format(policy)
      namespaces = []
      deployments = {}
      configmaps = {}
      secrets = {}
      for ns in range(cliargs.namespaces):
        namespace_name = "mc-ns-{:04d}-{:04d}".format(policy, ns)
        namespaces.append(namespace_name)
        deployments[namespace_name] = []
        configmaps[namespace_name] = {}
        secrets[namespace_name] = {}
        for deploy in range(cliargs.deployments):
          deployment_name = "{:04d}".format(deploy)
          configmaps[namespace_name][deployment_name] = []
          secrets[namespace_name][deployment_name] = []
          deployments[namespace_name].append(deployment_name)
          for cm in range(cliargs.configmaps):
            configmap_name = "mc-cm-{:04d}-{:04d}".format(deploy, cm)
            configmaps[namespace_name][deployment_name].append({"name": configmap_name, "v_name": "cm-{}".format(cm)})
          for secret in range(cliargs.secrets):
            secret_name = "mc-s-{:04d}-{:04d}".format(deploy, secret)
            secrets[namespace_name][deployment_name].append({"name": secret_name, "v_name": "s-{}".format(secret)})
      logger.info("Rendering policy: {}".format(policy_name))
      # logger.info("Namespaces: {}".format(namespaces))
      # logger.info("Deployments: {}".format(deployments))
      # logger.info("ConfigMaps: {}".format(configmaps))
      # logger.info("Secrets: {}".format(secrets))
      t = Template(policy_template)
      policy_template_rendered = t.render(
          name=policy_name,
          namespace=cliargs.hub_policy_namespace,
          selector_key=selector_key,
          selector_value=selector_value,
          policy_namespaces=namespaces,
          deployments=deployments,
          replicas=cliargs.replicas,
          container_image=cliargs.container_image,
          container_port=cliargs.container_port,
          configmaps=configmaps,
          secrets=secrets,
          service=cliargs.service,
          hub_policy_cm_name=cliargs.hub_policy_cm_name,
          hub_policy_cm_key_count=cliargs.hub_policy_cm_keys)
      with open("{}/{}".format(manifests_dir, "03-policy-{:04d}.yml".format(policy)), "w") as file1:
        file1.writelines(policy_template_rendered)

    phase_break()
    #### Generate - Apply manifests
    if cliargs.no_apply:
      logger.info("Skipping applying the policy manifests")
    else:
      logger.info("Applying the policy manifests")
      rc = 0
      oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "apply", "-f", manifests_dir]
      rc, output = command(oc_cmd, False, readlines=True)
      if rc != 0:
        logger.error("oc apply -f {} rc: {}".format(manifests_dir, rc))
        sys.exit(1)

  #### Cleanup action
  elif cliargs.action == "cleanup":
    logger.info("Cleanup")
    rc = 0
    oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "delete", "ns", cliargs.hub_policy_namespace]
    rc, output = command(oc_cmd, False, readlines=True)
    if rc != 0:
      logger.error("oc delete namespace rc: {}".format(rc))
      sys.exit(1)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
