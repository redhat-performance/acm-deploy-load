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

from datetime import datetime
import json
import logging
import time
import os
from utils.command import command
import time
from threading import Thread
import traceback


logger = logging.getLogger("acm-deploy-load")


class ZTPMonitor(Thread):
  def __init__(self, method, talm_minor, monitor_data, csv_file, dry_run, sample_interval):
    super(ZTPMonitor, self).__init__()
    if method in ["ai-manifest", "ai-clusterinstance", "ai-clusterinstance-gitops", "ai-siteconfig-gitops"]:
      self.method = "agent"
    elif method in ["ibi-manifest", "ibi-clusterinstance", "ibi-clusterinstance-gitops"]:
      self.method = "image"
    self.talm_minor = talm_minor
    self.monitor_data = monitor_data
    self.csv_file = csv_file
    self.dry_run = dry_run
    self.sample_interval = sample_interval
    self.signal = True

  def _real_run(self):
    logger.info("Starting ZTP Monitor")

    with open(self.csv_file, "w") as csv_file:
      csv_file.write("date,cluster_applied,cluster_init,cluster_notstarted,node_booted,node_discovered,cluster_installing,cluster_install_failed,cluster_install_completed,managed,policy_init,policy_notstarted,policy_applying,policy_timedout,policy_compliant,playbook_running,playbook_completed\n")

    while self.signal:
      start_sample_time = time.time()

      if self.method == "agent":
        # Get agentclusterinstall data
        oc_cmd = ["oc", "get", "agentclusterinstall", "-A", "-o", "json"]
        rc, output = command(oc_cmd, self.dry_run, retries=3, no_log=True)
        if rc != 0:
          logger.error("acm-deploy-load, oc get agentclusterinstall rc: {}".format(rc))
        else:
          if self.dry_run:
            aci_data = {"items": []}
          else:
            try:
              aci_data = json.loads(output)
            except json.decoder.JSONDecodeError:
              logger.warning("aci JSONDecodeError: {}".format(output[:2500]))
      elif self.method == "image":
        # Get imageclusterinstall data
        oc_cmd = ["oc", "get", "imageclusterinstall", "-A", "-o", "json"]
        rc, output = command(oc_cmd, self.dry_run, retries=3, no_log=True)
        if rc != 0:
          logger.error("acm-deploy-load, oc get imageclusterinstall rc: {}".format(rc))
        else:
          if self.dry_run:
            ici_data = {"items": []}
          else:
            try:
              ici_data = json.loads(output)
            except json.decoder.JSONDecodeError:
              logger.warning("ici JSONDecodeError: {}".format(output[:2500]))

      # Get baremetalhost data
      oc_cmd = ["oc", "get", "baremetalhost", "-A", "-o", "json"]
      rc, output = command(oc_cmd, self.dry_run, retries=3, no_log=True)
      if rc != 0:
        logger.error("acm-deploy-load, oc get baremetalhost rc: {}".format(rc))
      else:
        if self.dry_run:
          bmh_data = {"items": []}
        else:
          try:
            bmh_data = json.loads(output)
          except json.decoder.JSONDecodeError:
            logger.warning("bmh JSONDecodeError: {}".format(output[:2500]))

      if self.method == "agent":
        # Get agent data
        oc_cmd = ["oc", "get", "agent", "-A", "-o", "json"]
        rc, output = command(oc_cmd, self.dry_run, retries=3, no_log=True)
        if rc != 0:
          logger.error("acm-deploy-load, oc get agent rc: {}".format(rc))
        else:
          if self.dry_run:
            agent_data = {"items": []}
          else:
            try:
              agent_data = json.loads(output)
            except json.decoder.JSONDecodeError:
              logger.warning("agent JSONDecodeError: {}".format(output[:2500]))
      elif self.method == "image":
        # No discovered agents collected for image based installs
        agent_data = {"items": []}

      # Get managedcluster data
      oc_cmd = ["oc", "get", "managedcluster", "-A", "-o", "json"]
      rc, output = command(oc_cmd, self.dry_run, retries=3, no_log=True)
      if rc != 0:
        logger.error("acm-deploy-load, oc get managedcluster rc: {}".format(rc))
      else:
        if self.dry_run:
          mc_data = {"items": []}
        else:
          try:
            mc_data = json.loads(output)
          except json.decoder.JSONDecodeError:
            logger.warning("mc JSONDecodeError: {}".format(output[:2500]))

      # Get clustergroupupgrades data
      oc_cmd = ["oc", "get", "clustergroupupgrades", "-n", "ztp-install", "-o", "json"]
      rc, output = command(oc_cmd, self.dry_run, retries=3, no_log=True)
      if rc != 0:
        logger.error("acm-deploy-load, oc get clustergroupupgrades rc: {}".format(rc))
      else:
        if self.dry_run:
          cgu_data = {"items": []}
        else:
          try:
            cgu_data = json.loads(output)
          except json.decoder.JSONDecodeError:
            logger.warning("cgu JSONDecodeError: {}".format(output[:2500]))

      cluster_init = 0
      cluster_notstarted = 0
      node_booted = 0
      node_discovered = len(agent_data["items"])
      cluster_installing = 0
      cluster_install_failed = 0
      cluster_install_completed = 0
      cluster_managed = 0
      cluster_policy_init = 0
      cluster_policy_notstarted = 0
      cluster_policy_applying = 0
      cluster_policy_timedout = 0
      cluster_policy_compliant = 0
      cluster_playbook_running = 0
      cluster_playbook_completed = 0


      if self.method == "agent":
        # Parse agentclusterinstall data
        for item in aci_data["items"]:
          if item["metadata"]["name"] == "local-agent-cluster-cluster-install":
            logger.debug("aci: Skipping local-agent-cluster-cluster-install")
            continue
          if item["metadata"]["name"] == "local-cluster":
            logger.debug("aci: Skipping local-cluster")
            continue
          cluster_init += 1
          if "status" in item and "conditions" in item["status"]:
            for condition in item["status"]["conditions"]:
              if "type" in condition:
                if condition["type"] == "Completed":
                  if "reason" in condition:
                    logger.debug("ACI: {} is {}".format(item["metadata"]["name"], condition["reason"]))
                    if condition["reason"] == "InstallationNotStarted":
                      cluster_notstarted += 1
                    elif condition["reason"] == "InstallationInProgress":
                      cluster_installing += 1
                    elif condition["reason"] == "InstallationFailed":
                      cluster_install_failed += 1
                    elif condition["reason"] == "InstallationCompleted":
                      cluster_install_completed += 1
                    else:
                      logger.info("aci: {}: Unrecognized Completed Reason: {}".format(item["metadata"]["name"], condition["reason"]))
                    break
                  else:
                    logger.warning("reason missing from condition: {}".format(condition))
              else:
                logger.warning("aci: type missing from condition(item): {}".format(item))
                logger.warning("aci: type missing from condition(condition): {}".format(condition))
          else:
            logger.warning("status or conditions not found in agentclusterinstall object: {}".format(item))
      elif self.method == "image":
        # Parse imageclusterinstall data
        for item in ici_data["items"]:
          cluster_init += 1
          if "status" in item and "conditions" in item["status"]:
            for condition in item["status"]["conditions"]:
              if "type" in condition:
                if condition["type"] == "Completed":
                  if "reason" in condition:
                    logger.debug("ICI: {} is {}".format(item["metadata"]["name"], condition["reason"]))
                    if condition["reason"] == "Unknown":
                      cluster_notstarted += 1
                    elif condition["reason"] == "ClusterInstallationInProgress":
                      cluster_installing += 1
                    elif condition["reason"] == "ClusterInstallationTimedOut":
                      cluster_install_failed += 1
                    elif condition["reason"] == "ClusterInstallationSucceeded":
                      cluster_install_completed += 1
                    else:
                      logger.info("ici: {}: Unrecognized Completed Reason: {}".format(item["metadata"]["name"], condition["reason"]))
                    break
                  else:
                    logger.warning("reason missing from condition: {}".format(condition))
              else:
                logger.warning("ici: type missing from condition(item): {}".format(item))
                logger.warning("ici: type missing from condition(condition): {}".format(condition))
          else:
            logger.warning("status or conditions not found in imageclusterinstall object: {}".format(item))

      # Parse baremetalhost data
      for item in bmh_data["items"]:
        if "status" in item and "provisioning" in item["status"] and "state" in item["status"]["provisioning"]:
          if item["status"]["provisioning"]["state"] in ("inspecting", "provisioning", "preparing", "provisioned"):
            logger.debug("BMH: {} is {}".format(item["metadata"]["name"], item["status"]["provisioning"]["state"]))
            node_booted += 1
        else:
          logger.warning("missing status or elements under status in baremetalhost object: {}".format(item))

      # Parse managedcluster data
      for item in mc_data["items"]:
        if item["metadata"]["name"] == "local-cluster":
          logger.debug("mc: Skipping local-cluster")
          continue
        if "status" in item and "conditions" in item["status"]:
          for condition in item["status"]["conditions"]:
            if "type" in condition:
              if condition["type"] == "ManagedClusterConditionAvailable":
                logger.debug(
                    "MC: {} is {} is {}".format(item["metadata"]["name"], condition["type"], condition["status"]))
                if condition["status"] == "True":
                  cluster_managed += 1
                break
            else:
              logger.warning("mc: type missing from condition(item): {}".format(item))
              logger.warning("mc: type missing from condition(condition): {}".format(condition))
        else:
          logger.warning("status or conditions not found in managedcluster object: {}".format(item))
        # Monitoring for the aap day 2 playbook running
        if "ztp-ansible" in item["metadata"]["labels"]:
          mc_aap_label = item["metadata"]["labels"]["ztp-ansible"]
          if mc_aap_label == "running":
            cluster_playbook_running += 1
          elif mc_aap_label == "completed":
            cluster_playbook_completed += 1
          else:
            logger.warning("Unexpected ztp-ansible value: {}".format(mc_aap_label))

      # Parse clustergroupupgrades data
      for item in cgu_data["items"]:
        if item["metadata"]["name"] == "local-cluster":
          logger.debug("cgu: Skipping local-cluster")
          continue
        cluster_policy_init += 1
        if "status" in item and "conditions" in item["status"]:
          for condition in item["status"]["conditions"]:
            if self.talm_minor >= 12:
              if "type" in condition:
                logger.debug("CGU: {} Condition: {}".format(item["metadata"]["name"], condition))
                if (condition["type"] == "Progressing" and condition["status"] == "False"
                    and condition["reason"] != "Completed" and condition["reason"] != "TimedOut"):
                  cluster_policy_notstarted += 1
                  break
                if condition["type"] == "Progressing" and condition["status"] == "True" and condition["reason"] == "InProgress":
                  cluster_policy_applying += 1
                  break
                if condition["type"] == "Succeeded" and condition["status"] == "False" and condition["reason"] == "TimedOut":
                  cluster_policy_timedout += 1
                  break
                if condition["type"] == "Succeeded" and condition["status"] == "True" and condition["reason"] == "Completed":
                  cluster_policy_compliant += 1
                  break
              else:
                logger.warning("cgu: type missing from condition(item): {}".format(item))
                logger.warning("cgu: type missing from condition(condition): {}".format(condition))
            else:
              if "type" in condition:
                if condition["type"] == "Ready":
                  if "reason" in condition:
                    logger.debug("CGU: {} is {}".format(item["metadata"]["name"], condition["reason"]))
                    if condition["reason"] == "UpgradeNotStarted":
                      cluster_policy_notstarted += 1
                    elif condition["reason"] == "UpgradeNotCompleted":
                      cluster_policy_applying += 1
                    elif condition["reason"] == "UpgradeTimedOut":
                      cluster_policy_timedout += 1
                    elif condition["reason"] == "UpgradeCompleted":
                      cluster_policy_compliant += 1
                    else:
                      logger.info("cgu: {}: Unrecognized Completed Reason: {}".format(item["metadata"]["name"], condition["reason"]))
                    break
                  else:
                    logger.warning("reason missing from condition: {}".format(condition))
              else:
                logger.warning("cgu: type missing from condition(item): {}".format(item))
                logger.warning("cgu: type missing from condition(condition): {}".format(condition))
        else:
          logger.warning("status or conditions not found in clustergroupupgrades object: {}".format(item))

      self.monitor_data["cluster_init"] = cluster_init
      self.monitor_data["cluster_notstarted"] = cluster_notstarted
      self.monitor_data["node_booted"] = node_booted
      self.monitor_data["node_discovered"] = node_discovered
      self.monitor_data["cluster_installing"] = cluster_installing
      self.monitor_data["cluster_install_failed"] = cluster_install_failed
      self.monitor_data["cluster_install_completed"] = cluster_install_completed
      self.monitor_data["managed"] = cluster_managed
      self.monitor_data["policy_init"] = cluster_policy_init
      self.monitor_data["policy_notstarted"] = cluster_policy_notstarted
      self.monitor_data["policy_applying"] = cluster_policy_applying
      self.monitor_data["policy_timedout"] = cluster_policy_timedout
      self.monitor_data["policy_compliant"] = cluster_policy_compliant
      self.monitor_data["playbook_running"] = cluster_playbook_running
      self.monitor_data["playbook_completed"] = cluster_playbook_completed

      # Write csv data
      with open(self.csv_file, "a") as csv_file:
        csv_file.write("{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
            datetime.utcfromtimestamp(start_sample_time).strftime('%Y-%m-%dT%H:%M:%SZ'),
            self.monitor_data["cluster_applied_committed"], cluster_init, cluster_notstarted, node_booted,
            node_discovered, cluster_installing, cluster_install_failed, cluster_install_completed, cluster_managed,
            cluster_policy_init, cluster_policy_notstarted, cluster_policy_applying, cluster_policy_timedout,
            cluster_policy_compliant, cluster_playbook_running, cluster_playbook_completed
        ))

      logger.debug("Applied/Committed Clusters: {}".format(self.monitor_data["cluster_applied_committed"]))
      logger.debug("Initialized Clusters: {}".format(self.monitor_data["cluster_init"]))
      logger.debug("Not Started Clusters: {}".format(self.monitor_data["cluster_notstarted"]))
      logger.debug("Booted Nodes: {}".format(self.monitor_data["node_booted"]))
      logger.debug("Discovered Nodes: {}".format(self.monitor_data["node_discovered"]))
      logger.debug("Installing Clusters: {}".format(self.monitor_data["cluster_installing"]))
      logger.debug("Failed Clusters: {}".format(self.monitor_data["cluster_install_failed"]))
      logger.debug("Completed Clusters: {}".format(self.monitor_data["cluster_install_completed"]))
      logger.debug("Managed Clusters: {}".format(self.monitor_data["managed"]))
      logger.debug("Initialized Policy Clusters: {}".format(self.monitor_data["policy_init"]))
      logger.debug("Policy Not Started Clusters: {}".format(self.monitor_data["policy_notstarted"]))
      logger.debug("Policy Applying Clusters: {}".format(self.monitor_data["policy_applying"]))
      logger.debug("Policy Timedout Clusters: {}".format(self.monitor_data["policy_timedout"]))
      logger.debug("Policy Compliant Clusters: {}".format(self.monitor_data["policy_compliant"]))
      logger.debug("Playbook Running Clusters: {}".format(self.monitor_data["playbook_running"]))
      logger.debug("Playbook Completed Clusters: {}".format(self.monitor_data["playbook_completed"]))

      end_sample_time = time.time()
      sample_time = round(end_sample_time - start_sample_time, 1)
      logger.info("Monitor sampled in {}".format(sample_time))

      time_to_sleep = self.sample_interval - sample_time
      if time_to_sleep > 0:
        time.sleep(time_to_sleep)
      else:
        logger.warning("Time to monitor exceeded monitor interval")
    logger.info("Monitor Thread terminating")

  def run(self):
    try:
      self._real_run()
    except Exception as e:
      logger.error("Error in Monitoring Thread: {}".format(e))
      logger.error('\n{}'.format(traceback.format_exc()))
      os._exit(1)
