#!/usr/bin/env python3
#
# Tool to load a managed cluster with a number of namespaces, deployments, services, configmaps, secrets, and pods.
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
from datetime import datetime
from jinja2 import Template
import logging
import os
import sys
import time
from utils.command import command

# TODO:
# * cpu/memory - requests/limits

namespace_template = """---
apiVersion: v1
kind: Namespace
metadata:
  name: {{ name }}
  labels:
    mc-workload: "true"
"""

deployment_template = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
spec:
  replicas: {{ replicas }}
  selector:
    matchLabels:
      app: mc-workload-{{ name }}
  strategy:
    resources: {}
  template:
    metadata:
      labels:
        app: mc-workload-{{ name }}
    spec:
      containers:
      - name: mc-workload
        image: {{ image }}
        env:
        - name: PORT
          value: "{{ container_port }}"
      {%- if (configmaps|length > 0) or (secrets|length > 0) %}
        volumeMounts:
        {%- for cm in configmaps %}
        - name: {{ cm['v_name'] }}
          mountPath: /etc/{{ cm['v_name'] }}
        {%- endfor %}
        {%- for secret in secrets %}
        - name: {{ secret['v_name'] }}
          mountPath: /etc/{{ secret['v_name'] }}
        {%- endfor %}
      volumes:
      {%- for cm in configmaps %}
      - name: {{ cm['v_name'] }}
        configMap:
          name: {{ cm['name'] }}
      {%- endfor %}
      {%- for secret in secrets %}
      - name: {{ secret['v_name'] }}
        secret:
          secretName: {{ secret['name'] }}
      {%- endfor %}
      {%- endif %}
"""

configmap_template = """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
data:
  mc_workload: "{{ name }} - Random data"
"""

secret_template = """---
apiVersion: v1
kind: Secret
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
data:
  mc_workload: UmFuZG9tIGRhdGEK
"""

service_template = """---
apiVersion: v1
kind: Service
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
spec:
  selector:
    app: mc-workload-{{ deploy_name }}
  ports:
    - protocol: TCP
      name: port
      port: 8080
      targetPort: {{ container_port }}
"""


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Tool to load a managedcluster with namespaces, deployments, pods, and configmaps",
      prog="mc-workload.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str,
                      help="Set to the desired cluster kubeconfig")

  subparsers = parser.add_subparsers(dest="action")
  parser_gen = subparsers.add_parser("generate", help="Creates manifests and applies manifests",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser_cleanup = subparsers.add_parser("cleanup", help="Cleans up all generated namespaces",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser_gen.add_argument("-n", "--namespaces", type=int, default=1, help="Number of namespaces to create")
  parser_gen.add_argument("-d", "--deployments", type=int, default=1, help="Number of deployments per namespace to create")
  parser_gen.add_argument("-p", "--pods", type=int, default=1, help="Number of pod replicas per deployment to create")

  # Per Deployment config
  parser_gen.add_argument("-c", "--configmaps", type=int, default=1, help="Number of configmaps per deployment")
  parser_gen.add_argument("-s", "--secrets", type=int, default=1, help="Number of secrets per deployment")
  parser_gen.add_argument("-l", "--service", action="store_true", default=False, help="Include service per deployment")
  parser_gen.add_argument("--container-port", type=int, default=8000, help="The container port to expose (PORT Env Var)")

  parser_gen.add_argument("-i", "--container-image", type=str,
                      # default="quay.io/redhat-performance/test-gohttp-probe:v0.0.2", help="The container image to use")
                      default="e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/redhat-performance/test-gohttp-probe:v0.0.2",
                      help="The container image to use")

  parser_gen.add_argument("-m", "--manifests-directory", type=str, help="The location to place mc-workload manifests")

  parser_gen.add_argument("--no-apply", action="store_true", default=False, help="Do not apply the manifests")

  parser.set_defaults(action="generate")

  cliargs = parser.parse_args()

  #### Generate Manifests
  if cliargs.action == "generate":

    if not cliargs.no_apply and cliargs.kubeconfig == None:
      logger.error("Set a kubeconfig arguement")
      sys.exit(1)

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
      manifests_dir_name = "mc-workload-{}".format(datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y%m%d-%H%M%S"))
      manifests_dir = os.path.join(base_dir_manifests, manifests_dir_name)
      os.mkdir(manifests_dir)
      logger.info("Using created manifests directory: {}".format(manifests_dir))

    logger.info("Creating {} namespaces with {} deployments with {} pod replicas".format(cliargs.namespaces, cliargs.deployments, cliargs.pods))

    for ns in range(0, cliargs.namespaces):
      ns_name = "mc-workload-{:04d}".format(ns)
      ns_fname = "01-ns-{}.yml".format(ns_name)
      logger.info("Templating Namespace: {}".format(ns_name))
      t = Template(namespace_template)
      ns_template_rendered = t.render(name=ns_name)
      with open("{}/{}".format(manifests_dir, ns_fname), "w") as file1:
        file1.writelines(ns_template_rendered)
      for deploy in range(0, cliargs.deployments):
        configmaps = []
        secrets = []
        deploy_name = "deploy-{:04d}".format(deploy)
        deploy_fname = "04-{}-deploy-{}.yml".format(ns_name, deploy_name)

        # Template the Configmaps
        for cm in range(0, cliargs.configmaps):
          cm_name = "cm-{:04d}-{:04d}-{:04d}".format(ns, deploy, cm)
          cm_fname = "02-{}-{}.yml".format(ns_name, cm_name)
          configmaps.append({"name": cm_name, "v_name": "cm-{}".format(cm)})
          logger.info("Templating Configmap: {}".format(cm_name))
          t = Template(configmap_template)
          cm_template_rendered = t.render(name=cm_name, namespace=ns_name)
          with open("{}/{}".format(manifests_dir, cm_fname), "w") as file1:
            file1.writelines(cm_template_rendered)

        # Template the Secrets
        for secret in range(0, cliargs.secrets):
          secret_name = "s-{:04d}-{:04d}-{:04d}".format(ns, deploy, secret)
          secret_fname = "03-{}-{}.yml".format(ns_name, secret_name)
          secrets.append({"name": secret_name, "v_name": "s-{}".format(secret)})
          logger.info("Templating Secret: {}".format(secret_name))
          t = Template(secret_template)
          secret_template_rendered = t.render(name=secret_name, namespace=ns_name)
          with open("{}/{}".format(manifests_dir, secret_fname), "w") as file1:
            file1.writelines(secret_template_rendered)

        if cliargs.service:
          service_name = "service-{:04d}".format(deploy)
          service_fname = "04-{}-service-{}.yml".format(ns_name, service_name)
          logger.info("Templating Service: {}".format(service_name))
          t = Template(service_template)
          service_template_rendered = t.render(
              name=service_name,
              namespace=ns_name,
              deploy_name=deploy_name,
              container_port=cliargs.container_port)
          with open("{}/{}".format(manifests_dir, service_fname), "w") as file1:
            file1.writelines(service_template_rendered)

        logger.info("Templating Deployment: {}".format(deploy_name))
        t = Template(deployment_template)
        deploy_template_rendered = t.render(
            name=deploy_name,
            namespace=ns_name,
            replicas=cliargs.pods,
            image=cliargs.container_image,
            container_port=cliargs.container_port,
            configmaps=configmaps,
            secrets=secrets)
        with open("{}/{}".format(manifests_dir, deploy_fname), "w") as file1:
          file1.writelines(deploy_template_rendered)

    #### Generate - Apply manifests
    if cliargs.no_apply:
      logger.info("Skipping applying the manifests")
    else:
      logger.info("Applying the manifests")
      oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "apply", "-f", manifests_dir]
      rc, output = command(oc_cmd, False, readlines=True)
      if rc != 0:
        logger.error("oc apply -f {} rc: {}".format(manifests_dir, rc))
        sys.exit(1)

  #### Cleanup action
  elif cliargs.action == "cleanup":
    logger.info("Cleanup")
    if cliargs.kubeconfig == None:
      logger.error("Set a kubeconfig arguement")
      sys.exit(1)
    oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "delete", "namespaces", "-l", "mc-workload=true"]
    rc, output = command(oc_cmd, False, readlines=True)
    if rc != 0:
      logger.error("oc delete namespaces -l mc-workload=true rc: {}".format(rc))
      sys.exit(1)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
