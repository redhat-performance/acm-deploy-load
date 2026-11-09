#!/usr/bin/env python3
#  Copyright 2026 Red Hat
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

from datetime import datetime, timezone
import json
import logging
import os
import time
import traceback
from threading import Thread

from utils.command import command


logger = logging.getLogger("acm-deploy-load")


class OCloudMonitor(Thread):
  def __init__(self, method, monitor_data, csv_file, dry_run, sample_interval, kubeconfig, committed_hosts):
    super(OCloudMonitor, self).__init__()
    self.method = method  # "ai" or "ibi"
    self.monitor_data = monitor_data
    self.csv_file = csv_file
    self.dry_run = dry_run
    self.sample_interval = sample_interval
    self.kubeconfig = kubeconfig
    self.committed_hosts = committed_hosts  # set of host names for inspection counting
    self.signal = True

  def _get_json(self, oc_args, label=""):
    cmd = ["oc", "--kubeconfig", self.kubeconfig] + oc_args
    rc, output = command(cmd, self.dry_run, retries=3, no_log=True)
    if rc != 0:
      logger.error("ocloud_monitor oc {} rc: {}".format(label, rc))
      return {"items": []}
    if self.dry_run:
      return {"items": []}
    try:
      return json.loads(output)
    except json.decoder.JSONDecodeError:
      logger.warning("JSONDecodeError ({}): {}".format(label, output[:2500]))
      return {"items": []}

  def _real_run(self):
    logger.info("Starting OCloud Monitor")

    with open(self.csv_file, "w") as csv_file:
      csv_file.write(
          "date,"
          "bmh_inspecting,bmh_available,bmh_provisioning,bmh_provisioned,bmh_error,"
          "bmh_inspect_complete,bmh_inspect_failed,"
          "pr_pending,pr_progressing,pr_fulfilled,pr_failed,"
          "pr_installed,pr_upgraded,pr_upgrade_failed,"
          "ci_notstarted,ci_progressing,ci_failed,ci_completed,"
          "ici_aci_installing,ici_aci_failed,ici_aci_completed\n")

    while self.signal:
      start_sample_time = time.time()

      bmh_inspecting = 0
      bmh_available = 0
      bmh_provisioning = 0
      bmh_provisioned = 0
      bmh_error = 0
      bmh_inspect_complete = 0
      bmh_inspect_failed = 0
      pr_pending = 0
      pr_progressing = 0
      pr_fulfilled = 0
      pr_failed = 0
      pr_installed = 0
      pr_upgraded = 0
      pr_upgrade_failed = 0
      ci_notstarted = 0
      ci_progressing = 0
      ci_failed = 0
      ci_completed = 0
      ici_aci_installing = 0
      ici_aci_failed = 0
      ici_aci_completed = 0

      # 1. BareMetalHost — count states; for committed hosts track inspect complete/failed
      bmh_data = self._get_json(["get", "baremetalhost", "-A", "-o", "json"], "bmh")
      for item in bmh_data["items"]:
        state = item.get("status", {}).get("provisioning", {}).get("state", "")
        name = item.get("metadata", {}).get("name", "")
        if state == "unmanaged":
          continue
        if state == "inspecting":
          bmh_inspecting += 1
        elif state == "available":
          bmh_available += 1
        elif state == "provisioning":
          bmh_provisioning += 1
        elif state in ("provisioned", "externally provisioned"):
          bmh_provisioned += 1
        elif state:
          bmh_error += 1
        if name in self.committed_hosts:
          inspect_end = item.get("status", {}).get("operationHistory", {}).get("inspect", {}).get("end", "")
          if state == "available" and inspect_end:
            bmh_inspect_complete += 1
          elif "error" in state.lower():
            bmh_inspect_failed += 1

      # 2. ProvisioningRequest — control signal for install and upgrade phases
      pr_data = self._get_json(
          ["get", "provisioningrequests.clcm.openshift.io", "-o", "json"], "pr")
      for item in pr_data["items"]:
        phase = item.get("status", {}).get("provisioningStatus", {}).get("provisioningPhase", "")
        conditions = item.get("status", {}).get("conditions", [])
        has_patch_annotation = "ibu-patch-time" in item.get("metadata", {}).get("annotations", {})

        if phase == "fulfilled":
          pr_fulfilled += 1
        elif phase == "failed":
          pr_failed += 1
        elif phase == "progressing":
          pr_progressing += 1
        else:
          pr_pending += 1

        ca = any(c.get("type") == "ConfigurationApplied" and c.get("status") == "True" for c in conditions)
        uc = any(c.get("type") == "UpgradeCompleted" and c.get("status") == "True" for c in conditions)
        if ca:
          pr_installed += 1
        if uc:
          pr_upgraded += 1
        if has_patch_annotation and not uc and phase == "failed":
          pr_upgrade_failed += 1

      # 3. ClusterInstance — monitoring depth only
      ci_data = self._get_json(["get", "clusterinstances", "-A", "-o", "json"], "ci")
      for item in ci_data["items"]:
        conditions = item.get("status", {}).get("conditions", [])
        is_provisioned = any(
            c.get("type") == "Provisioned" and c.get("status") == "True" for c in conditions)
        is_failed = any(
            c.get("status") == "False"
            and c.get("reason", "").lower() in ("failed", "timedout", "clusterinstancefailed")
            for c in conditions)
        if is_provisioned:
          ci_completed += 1
        elif is_failed:
          ci_failed += 1
        elif conditions:
          ci_progressing += 1
        else:
          ci_notstarted += 1

      # 4. ICI (ibi) or ACI (ai) — monitoring depth only
      if self.method == "ibi":
        ici_data = self._get_json(["get", "imageclusterinstalls", "-A", "-o", "json"], "ici")
        for item in ici_data["items"]:
          for condition in item.get("status", {}).get("conditions", []):
            if condition.get("type") == "Completed":
              reason = condition.get("reason", "")
              if reason == "ClusterInstallationInProgress":
                ici_aci_installing += 1
              elif reason == "ClusterInstallationTimedOut":
                ici_aci_failed += 1
              elif reason == "ClusterInstallationSucceeded":
                ici_aci_completed += 1
              break
      else:
        aci_data = self._get_json(["get", "agentclusterinstalls", "-A", "-o", "json"], "aci")
        for item in aci_data["items"]:
          name = item.get("metadata", {}).get("name", "")
          if name in ("local-agent-cluster-cluster-install", "local-cluster"):
            continue
          for condition in item.get("status", {}).get("conditions", []):
            if condition.get("type") == "Completed":
              reason = condition.get("reason", "")
              if reason == "InstallationInProgress":
                ici_aci_installing += 1
              elif reason == "InstallationFailed":
                ici_aci_failed += 1
              elif reason == "InstallationCompleted":
                ici_aci_completed += 1
              break

      # Update shared monitor_data
      self.monitor_data["bmh_inspecting"] = bmh_inspecting
      self.monitor_data["bmh_available"] = bmh_available
      self.monitor_data["bmh_provisioning"] = bmh_provisioning
      self.monitor_data["bmh_provisioned"] = bmh_provisioned
      self.monitor_data["bmh_error"] = bmh_error
      self.monitor_data["bmh_inspect_complete"] = bmh_inspect_complete
      self.monitor_data["bmh_inspect_failed"] = bmh_inspect_failed
      self.monitor_data["pr_pending"] = pr_pending
      self.monitor_data["pr_progressing"] = pr_progressing
      self.monitor_data["pr_fulfilled"] = pr_fulfilled
      self.monitor_data["pr_failed"] = pr_failed
      self.monitor_data["pr_installed"] = pr_installed
      self.monitor_data["pr_upgraded"] = pr_upgraded
      self.monitor_data["pr_upgrade_failed"] = pr_upgrade_failed
      self.monitor_data["ci_notstarted"] = ci_notstarted
      self.monitor_data["ci_progressing"] = ci_progressing
      self.monitor_data["ci_failed"] = ci_failed
      self.monitor_data["ci_completed"] = ci_completed
      self.monitor_data["ici_aci_installing"] = ici_aci_installing
      self.monitor_data["ici_aci_failed"] = ici_aci_failed
      self.monitor_data["ici_aci_completed"] = ici_aci_completed

      # Write CSV row
      with open(self.csv_file, "a") as csv_file:
        csv_file.write("{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
            datetime.fromtimestamp(start_sample_time, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            bmh_inspecting, bmh_available, bmh_provisioning, bmh_provisioned, bmh_error,
            bmh_inspect_complete, bmh_inspect_failed,
            pr_pending, pr_progressing, pr_fulfilled, pr_failed,
            pr_installed, pr_upgraded, pr_upgrade_failed,
            ci_notstarted, ci_progressing, ci_failed, ci_completed,
            ici_aci_installing, ici_aci_failed, ici_aci_completed
        ))

      logger.debug("BMH inspecting/available/provisioning/provisioned/error: {}/{}/{}/{}/{}".format(
          bmh_inspecting, bmh_available, bmh_provisioning, bmh_provisioned, bmh_error))
      logger.debug("BMH inspect complete/failed (committed): {}/{}".format(
          bmh_inspect_complete, bmh_inspect_failed))
      logger.debug("PR pending/progressing/fulfilled/failed: {}/{}/{}/{}".format(
          pr_pending, pr_progressing, pr_fulfilled, pr_failed))
      logger.debug("PR installed/upgraded/upgrade_failed: {}/{}/{}".format(
          pr_installed, pr_upgraded, pr_upgrade_failed))
      logger.debug("CI notstarted/progressing/failed/completed: {}/{}/{}/{}".format(
          ci_notstarted, ci_progressing, ci_failed, ci_completed))
      logger.debug("ICI/ACI installing/failed/completed: {}/{}/{}".format(
          ici_aci_installing, ici_aci_failed, ici_aci_completed))

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
