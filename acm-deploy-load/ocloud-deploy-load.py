#!/usr/bin/env python3
#
# Tool to orchestrate O-Cloud BMH inspection, SNO provisioning, and IBU upgrade
# via ProvisioningRequests.
#
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

import argparse
from datetime import datetime, timedelta, timezone
import glob
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import time

from utils.analysis import launch_prometheus_analysis
from utils.command import command
from utils.common_ocp import validate_kubeconfig, get_ocp_version, get_mch_version, get_mce_version, get_ocloud_manager_version
from utils.gitops import git_commit_push
from utils.ocloud_monitor import OCloudMonitor
from utils.output import generate_ocloud_deploy_load_report, phase_break


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def log_monitor_data(monitor_data, elapsed_seconds):
  logger.info("Elapsed total time: {}s :: {}".format(elapsed_seconds, str(timedelta(seconds=elapsed_seconds))))
  logger.info("BMH Committed (GitOps applied): {}".format(monitor_data["bmh_committed"]))
  logger.info("BMH Inspecting: {}".format(monitor_data["bmh_inspecting"]))
  logger.info("BMH Available (Inspect Complete): {}".format(monitor_data["bmh_inspect_complete"]))
  logger.info("BMH Inspect Failed: {}".format(monitor_data["bmh_inspect_failed"]))
  logger.info("BMH Provisioning: {}".format(monitor_data["bmh_provisioning"]))
  logger.info("BMH Provisioned: {}".format(monitor_data["bmh_provisioned"]))
  logger.info("BMH Error: {}".format(monitor_data["bmh_error"]))
  logger.info("PR Applied: {}".format(monitor_data["pr_applied"]))
  logger.info("PR Patched (for upgrade): {}".format(monitor_data["pr_patched"]))
  logger.info("PR Pending: {}".format(monitor_data["pr_pending"]))
  logger.info("PR Progressing: {}".format(monitor_data["pr_progressing"]))
  logger.info("PR Fulfilled: {}".format(monitor_data["pr_fulfilled"]))
  logger.info("PR Failed: {}".format(monitor_data["pr_failed"]))
  logger.info("PR Installed (ConfigurationApplied): {}".format(monitor_data["pr_installed"]))
  logger.info("PR Upgraded (UpgradeCompleted): {}".format(monitor_data["pr_upgraded"]))
  logger.info("PR Upgrade Failed: {}".format(monitor_data["pr_upgrade_failed"]))
  logger.info("Managed Clusters: {}".format(monitor_data["managed"]))
  logger.info("CI Not Started: {}".format(monitor_data["ci_notstarted"]))
  logger.info("CI Progressing: {}".format(monitor_data["ci_progressing"]))
  logger.info("CI Failed: {}".format(monitor_data["ci_failed"]))
  logger.info("CI Completed: {}".format(monitor_data["ci_completed"]))
  logger.info("ICI/ACI Installing: {}".format(monitor_data["ici_aci_installing"]))
  logger.info("ICI/ACI Failed: {}".format(monitor_data["ici_aci_failed"]))
  logger.info("ICI/ACI Completed: {}".format(monitor_data["ici_aci_completed"]))


def run_analyzer(script, extra_args, report_dir, base_dir, dry_run):
  cmd = [os.path.join(base_dir, script)] + extra_args + [report_dir]
  logger.info("Running analyzer: {}".format(" ".join(cmd)))
  if dry_run:
    return
  result = subprocess.run(cmd)
  if result.returncode != 0:
    logger.error("{} returned rc: {}".format(script, result.returncode))


def wait_for_phase(monitor_data, phase, done_keys, target_count, wait_start, timeout, start_time):
  wait_logger = 4
  while True:
    time.sleep(30)
    done = monitor_data[done_keys[0]] + monitor_data[done_keys[1]]
    if done >= target_count:
      logger.info("{} complete: {}/{} done".format(phase.capitalize(), done, target_count))
      log_monitor_data(monitor_data, round(time.time() - start_time))
      break
    if timeout > 0 and (time.time() - wait_start) > timeout:
      logger.warning("{} timeout reached ({} done of {})".format(phase.capitalize(), done, target_count))
      log_monitor_data(monitor_data, round(time.time() - start_time))
      break
    wait_logger += 1
    if wait_logger >= 5:
      logger.info("Waiting for {}: {}/{} done ({}={}, {}={})".format(
          phase, done, target_count,
          done_keys[0], monitor_data[done_keys[0]],
          done_keys[1], monitor_data[done_keys[1]]))
      if timeout > 0:
        remaining = max(0, timeout - round(time.time() - wait_start))
        logger.info("{} timeout remaining: {}s :: {}".format(
            phase.capitalize(), remaining, str(timedelta(seconds=remaining))))
      log_monitor_data(monitor_data, round(time.time() - start_time))
      wait_logger = 0


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Tool to orchestrate O-Cloud BMH inspection, SNO install, and IBU upgrade",
      prog="ocloud-deploy-load.py",
      formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/mno/kubeconfig",
                      help="Hub cluster kubeconfig")
  parser.add_argument("-m", "--method", choices=["ai", "ibi"], default="ibi",
                      help="Install method: ai (Assisted Installer) or ibi (Image-Based Installer)")
  parser.add_argument("--baremetalhost-manifests", type=str, default="/root/hv-vm/sno/ocloud-inventory/",
                      help="Directory with BMH YAML files for inspection")
  parser.add_argument("--provisioningrequest-manifests", type=str, default="",
                      help="Directory with *-provisioningrequest.yml files (default: /root/hv-vm/sno/ocloud-{method}-provisioningrequest/)")
  parser.add_argument("--argocd-directory", type=str,
                      default="/root/rhacm-ztp/telco-reference/telco-ran/configuration/argocd",
                      help="Root of the ArgoCD git repo; used as the git working directory for commits and to locate the resource pool kustomization under clustertemplates/inventory/{resourcepool-name}/")
  parser.add_argument("--resourcepool-name", type=str, default="resourcepool-lab",
                      help="O-Cloud resource pool name; determines the pool subdirectory under clustertemplates/inventory/ where BMH manifests are copied and kustomization.yaml is updated")

  # Per-phase pacing
  parser.add_argument("--inspect-batch", type=int, default=100,
                      help="Number of BMH manifests per inspection batch")
  parser.add_argument("--inspect-interval", type=int, default=300,
                      help="Seconds between inspection batches (0=back-to-back)")
  parser.add_argument("--install-batch", type=int, default=100,
                      help="Number of PRs to apply per install batch")
  parser.add_argument("--install-interval", type=int, default=600,
                      help="Seconds between install batches (0=back-to-back)")
  parser.add_argument("--upgrade-batch", type=int, default=100,
                      help="Number of PRs to patch per upgrade batch")
  parser.add_argument("--upgrade-interval", type=int, default=600,
                      help="Seconds between upgrade batches (0=back-to-back)")

  # Ordering
  parser.add_argument("-n", "--no-shuffle", action="store_true", default=False,
                      help="Do not shuffle host/PR list")

  # Per-phase timeouts
  parser.add_argument("--inspect-timeout", type=int, default=1800,
                      help="Max seconds to wait for inspection completion (0=infinite)")
  parser.add_argument("--install-timeout", type=int, default=1800,
                      help="Max seconds to wait for install completion (0=infinite)")
  parser.add_argument("--upgrade-timeout", type=int, default=1800,
                      help="Max seconds to wait for upgrade completion (0=infinite)")

  # Upgrade target
  parser.add_argument("--upgrade-ocp-version", type=str, default="",
                      help="Target OCP version for IBU upgrade, e.g. 4.22.3")
  parser.add_argument("--upgrade-revision", choices=["v2", "v3"], default="v3",
                      help="ClusterTemplate revision (v2=full upgrade with AbortOnFailure+Finalize, v3=Prep+Upgrade no finalize)")
  parser.add_argument("--clustertemplate-name", type=str, default="sno-ran-du",
                      help="ClusterTemplate name")

  # Skip flags
  parser.add_argument("--skip-inspection", action="store_true", default=False,
                      help="Skip phase 2 (BMH inspection via GitOps)")
  parser.add_argument("--skip-install", action="store_true", default=False,
                      help="Skip phase 3 (ProvisioningRequest install)")
  parser.add_argument("--skip-upgrade", action="store_true", default=False,
                      help="Skip phase 4 (IBU upgrade via oc patch)")

  # Timing
  parser.add_argument("--start-delay", type=int, default=15,
                      help="Phase 1 / Idle Baseline delay before starting (seconds)")
  parser.add_argument("--end-delay", type=int, default=120,
                      help="Phase 5 / Soak Baseline delay after all phases (seconds)")
  parser.add_argument("-i", "--monitor-interval", type=int, default=60,
                      help="Monitor thread sampling interval (seconds)")

  # Analysis
  parser.add_argument("--no-prometheus-analysis", action="store_true", default=False,
                      help="Do not launch analyze-prometheus.py at phase boundaries")

  # Report
  parser.add_argument("-t", "--results-dir-suffix", type=str, default="test-00",
                      help="Suffix appended to results directory name")
  parser.add_argument("--test-version", type=str, default="",
                      help="Test version label for the report card")

  # Debug/dry-run
  parser.add_argument("-d", "--debug", action="store_true", default=False,
                      help="Set log level debug")
  parser.add_argument("--dry-run", action="store_true", default=False,
                      help="Echo commands instead of executing them")

  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  # Set defaults that depend on --method
  if not cliargs.provisioningrequest_manifests:
    cliargs.provisioningrequest_manifests = "/root/hv-vm/sno/ocloud-{}-provisioningrequest/".format(cliargs.method)

  phase_break()
  if cliargs.dry_run:
    logger.info("O-Cloud Deploy Load - Dry Run")
  else:
    logger.info("O-Cloud Deploy Load")
  phase_break()
  logger.debug("CLI Args: {}".format(cliargs))

  # Build templateVersion
  template_version = ""
  if cliargs.upgrade_ocp_version:
    ver_dashed = cliargs.upgrade_ocp_version.replace(".", "-")
    template_version = "v{}-{}-{}".format(ver_dashed, cliargs.method, cliargs.upgrade_revision)

  # Validate
  for name, val in [("--inspect-batch", cliargs.inspect_batch),
                    ("--install-batch", cliargs.install_batch),
                    ("--upgrade-batch", cliargs.upgrade_batch)]:
    if val < 1:
      parser.error("{} must be >= 1".format(name))
  if not cliargs.skip_upgrade and not cliargs.upgrade_ocp_version:
    logger.error("--upgrade-ocp-version is required when upgrade phase is not skipped")
    sys.exit(1)

  validate_kubeconfig(cliargs.kubeconfig)

  ocp_version = get_ocp_version(cliargs.kubeconfig)
  versions = {
    "hub_version": "{}.{}.{}".format(ocp_version["major"], ocp_version["minor"], ocp_version["patch"]),
    "acm_version": get_mch_version(cliargs.kubeconfig, cliargs.dry_run),
    "mce_version": get_mce_version(cliargs.kubeconfig, cliargs.dry_run),
    "ocloud_manager_version": get_ocloud_manager_version(cliargs.kubeconfig, cliargs.dry_run),
    "test_version": cliargs.test_version,
  }
  logger.info("Detected versions - ACM: {}, MCE: {}, O-Cloud Manager: {}, Hub OCP: {}".format(
      versions["acm_version"], versions["mce_version"],
      versions["ocloud_manager_version"], versions["hub_version"]))

  # Determine results directory
  base_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
  base_dir_down = os.path.dirname(base_dir)
  base_dir_results = os.path.join(base_dir_down, "results")
  report_dir_name = "{}-ocloud-{}-{}".format(
      datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y%m%d-%H%M%S"),
      cliargs.method, cliargs.results_dir_suffix)
  report_dir = os.path.join(base_dir_results, report_dir_name)
  monitor_data_csv_file = "{}/monitor_data.csv".format(report_dir)

  # Log parameters
  phase_break()
  logger.info("O-Cloud Deploy Load Parameters")
  logger.info(" * Method: {}".format(cliargs.method))
  logger.info(" * Kubeconfig: {}".format(cliargs.kubeconfig))
  logger.info(" * Phase 1 / Idle Baseline (Start delay): {}s :: {}".format(
      cliargs.start_delay, str(timedelta(seconds=cliargs.start_delay))))
  if not cliargs.skip_inspection:
    logger.info(" * Phase 2 (Inspection): batch={}, interval={}s, timeout={}s".format(
        cliargs.inspect_batch, cliargs.inspect_interval, cliargs.inspect_timeout))
    logger.info("   * BMH manifests: {}".format(cliargs.baremetalhost_manifests))
  else:
    logger.info(" * Phase 2 (Inspection): SKIPPED")
  if not cliargs.skip_install:
    logger.info(" * Phase 3 (Install): batch={}, interval={}s, timeout={}s".format(
        cliargs.install_batch, cliargs.install_interval, cliargs.install_timeout))
    logger.info("   * PR manifests: {}".format(cliargs.provisioningrequest_manifests))
  else:
    logger.info(" * Phase 3 (Install): SKIPPED")
  if not cliargs.skip_upgrade:
    logger.info(" * Phase 4 (Upgrade): batch={}, interval={}s, timeout={}s".format(
        cliargs.upgrade_batch, cliargs.upgrade_interval, cliargs.upgrade_timeout))
    logger.info("   * templateVersion: {}".format(template_version))
  else:
    logger.info(" * Phase 4 (Upgrade): SKIPPED")
  logger.info(" * Phase 5 / Soak Baseline (End delay): {}s :: {}".format(
      cliargs.end_delay, str(timedelta(seconds=cliargs.end_delay))))
  logger.info(" * Monitor interval: {}s".format(cliargs.monitor_interval))
  logger.info(" * Results data captured in: {}".format(report_dir))
  phase_break()

  # Pre-flight: discover manifests before any phase runs
  pool_dir = os.path.join(
      cliargs.argocd_directory, "clustertemplates", "inventory",
      cliargs.resourcepool_name)
  pool_kustomization = os.path.join(pool_dir, "kustomization.yaml")

  all_bmh_files = []
  if not cliargs.skip_inspection:
    if cliargs.dry_run:
      all_bmh_files = ["dryrun-host-{:05d}.yaml".format(i) for i in range(10)]
    else:
      all_bmh_files = sorted(glob.glob(os.path.join(cliargs.baremetalhost_manifests, "*.yaml")))
    if not cliargs.no_shuffle:
      random.shuffle(all_bmh_files)
    logger.info("Discovered {} BMH manifest files".format(len(all_bmh_files)))
    if not all_bmh_files and not cliargs.dry_run:
      logger.error("No BMH manifest files found in {}".format(cliargs.baremetalhost_manifests))
      sys.exit(1)

  all_pr_files = []
  if not cliargs.skip_install:
    if cliargs.dry_run:
      all_pr_files = ["dryrun-pr-{:05d}-provisioningrequest.yml".format(i) for i in range(5)]
    else:
      all_pr_files = sorted(glob.glob(
          os.path.join(cliargs.provisioningrequest_manifests, "*-provisioningrequest.yml")))
    if not cliargs.no_shuffle:
      random.shuffle(all_pr_files)
    logger.info("Discovered {} PR manifest files".format(len(all_pr_files)))
    if not all_pr_files and not cliargs.dry_run:
      logger.error("No PR manifest files found in {}".format(cliargs.provisioningrequest_manifests))
      sys.exit(1)

  os.makedirs(base_dir_results, exist_ok=True)
  os.mkdir(report_dir)
  with open("{}/versions.json".format(report_dir), "w") as vf:
    json.dump(versions, vf, indent=2)

  # Initialize monitor data and start monitor thread
  monitor_data = {
    "bmh_committed": 0,
    "bmh_inspecting": 0, "bmh_available": 0, "bmh_provisioning": 0,
    "bmh_provisioned": 0, "bmh_error": 0,
    "bmh_inspect_complete": 0, "bmh_inspect_failed": 0,
    "pr_applied": 0, "pr_patched": 0,
    "pr_pending": 0, "pr_progressing": 0, "pr_fulfilled": 0, "pr_failed": 0,
    "pr_installed": 0, "pr_upgraded": 0, "pr_upgrade_failed": 0,
    "managed": 0,
    "ci_notstarted": 0, "ci_progressing": 0, "ci_failed": 0, "ci_completed": 0,
    "ici_aci_installing": 0, "ici_aci_failed": 0, "ici_aci_completed": 0,
  }
  committed_hosts = set()
  monitor_thread = OCloudMonitor(
      cliargs.method, monitor_data, monitor_data_csv_file,
      cliargs.dry_run, cliargs.monitor_interval, cliargs.kubeconfig, committed_hosts)
  monitor_thread.start()

  #############################################################################
  # Phase 1: Idle Baseline
  #############################################################################
  phase_break()
  logger.info("Phase 1: Idle Baseline")
  phase_break()
  if cliargs.start_delay > 0:
    logger.info("Sleeping {}s :: {}".format(cliargs.start_delay, str(timedelta(seconds=cliargs.start_delay))))
    remaining = cliargs.start_delay
    while remaining > 300:
      time.sleep(300)
      remaining -= 300
      logger.info("{}s :: {} remaining in idle baseline".format(remaining, str(timedelta(seconds=remaining))))
    time.sleep(remaining)

  inspect_start_time = time.time()

  if not cliargs.no_prometheus_analysis:
    launch_prometheus_analysis(report_dir, "phase1-idle-baseline",
        start_time, inspect_start_time, cliargs.kubeconfig, base_dir)

  #############################################################################
  # Phase 2: BMH Inspection
  #############################################################################
  total_hosts_committed = 0
  total_hosts_inspected = 0
  total_hosts_inspect_failed = 0
  inspect_end_time = inspect_start_time

  if not cliargs.skip_inspection:
    phase_break()
    logger.info("Phase 2: BMH Inspection - {} - {}".format(
        cliargs.resourcepool_name, int(inspect_start_time * 1000)))
    phase_break()

    first_batch = True
    batch_num = 0
    host_idx = 0
    while host_idx < len(all_bmh_files):
      batch_num += 1
      batch_files = all_bmh_files[host_idx:host_idx + cliargs.inspect_batch]
      host_idx += cliargs.inspect_batch
      batch_names = [os.path.basename(f) for f in batch_files]
      batch_host_set = set(os.path.splitext(n)[0] for n in batch_names)

      logger.info("Inspection batch {}: copying {} BMH manifests - {}".format(
          batch_num, len(batch_files), int(time.time() * 1000)))

      files_to_commit = [pool_kustomization]
      if not cliargs.dry_run:
        for bmh_file in batch_files:
          dest = os.path.join(pool_dir, os.path.basename(bmh_file))
          shutil.copy2(bmh_file, dest)
          files_to_commit.append(dest)

        with open(pool_kustomization, "r") as f:
          content = f.read()
        if first_batch:
          content = content.replace("resources: []", "resources:")
        content += "".join("- {}\n".format(n) for n in batch_names)
        with open(pool_kustomization, "w") as f:
          f.write(content)
      else:
        logger.info("(dry-run) Would copy {} BMH files and update {}".format(
            len(batch_files), pool_kustomization))

      first_batch = False
      try:
        git_commit_push(
            files_to_commit,
            "Inspection batch {}: adding {} BMH manifests".format(batch_num, len(batch_files)),
            cliargs.argocd_directory, cliargs.dry_run)
      except RuntimeError as e:
        logger.error("Git operation failed, stopping monitor thread: {}".format(e))
        monitor_thread.signal = False
        monitor_thread.join()
        sys.exit(1)

      committed_hosts.update(batch_host_set)
      monitor_data["bmh_committed"] = len(committed_hosts)
      total_hosts_committed += len(batch_files)
      logger.info("Total hosts committed for inspection: {}".format(total_hosts_committed))

      if host_idx < len(all_bmh_files) and cliargs.inspect_interval > 0:
        logger.info("Sleeping {}s before next inspection batch".format(cliargs.inspect_interval))
        time.sleep(cliargs.inspect_interval)
        log_monitor_data(monitor_data, round(time.time() - start_time))

    # Wait for all committed hosts to complete inspection
    if total_hosts_committed > 0:
      logger.info("Waiting for {} hosts to complete inspection...".format(total_hosts_committed))
      wait_inspect_start = time.time()
      wait_for_phase(monitor_data, "inspection",
                     ("bmh_inspect_complete", "bmh_inspect_failed"),
                     total_hosts_committed, wait_inspect_start, cliargs.inspect_timeout, start_time)

    total_hosts_inspected = monitor_data["bmh_inspect_complete"]
    total_hosts_inspect_failed = monitor_data["bmh_inspect_failed"]
    logger.info("Inspection result: inspected={}, failed={}".format(
        total_hosts_inspected, total_hosts_inspect_failed))

    inspect_end_time = time.time()

    run_analyzer("analyze-baremetalhosts.py", [], report_dir, base_dir, cliargs.dry_run)

    if not cliargs.no_prometheus_analysis:
      launch_prometheus_analysis(report_dir, "phase2-inspection",
          inspect_start_time, inspect_end_time, cliargs.kubeconfig, base_dir)
  else:
    logger.info("Phase 2 (Inspection) skipped")

  #############################################################################
  # Phase 3: ProvisioningRequest Install
  #############################################################################
  total_prs_installed = 0
  total_prs_install_failed = 0
  total_prs_install_not_completed = 0
  installed_pr_uuids = []
  install_start_time = inspect_end_time
  install_end_time = install_start_time

  if not cliargs.skip_install:
    phase_break()
    logger.info("Phase 3: ProvisioningRequest Install - {}".format(int(time.time() * 1000)))
    phase_break()

    if cliargs.skip_inspection:
      bmh_available = monitor_data["bmh_available"]
      if bmh_available < len(all_pr_files):
        logger.warning("BMH available ({}) < PR count ({}); some installs may not find an inspected host".format(
            bmh_available, len(all_pr_files)))
      else:
        logger.info("BMH available: {} (>= {} PRs to apply)".format(bmh_available, len(all_pr_files)))

    install_start_time = time.time()

    batch_num = 0
    pr_idx = 0
    while pr_idx < len(all_pr_files):
      batch_num += 1
      batch = all_pr_files[pr_idx:pr_idx + cliargs.install_batch]
      pr_idx += cliargs.install_batch

      logger.info("Install batch {}: applying {} PRs - {}".format(
          batch_num, len(batch), int(time.time() * 1000)))
      for pr_file in batch:
        rc, output = command(
            ["oc", "--kubeconfig", cliargs.kubeconfig, "apply", "-f", pr_file],
            cliargs.dry_run, retries=3)
        if rc != 0:
          logger.error("oc apply failed for {}: rc={}, output={}".format(pr_file, rc, output))
        else:
          monitor_data["pr_applied"] += 1

      if pr_idx < len(all_pr_files) and cliargs.install_interval > 0:
        logger.info("Sleeping {}s before next install batch".format(cliargs.install_interval))
        time.sleep(cliargs.install_interval)
        log_monitor_data(monitor_data, round(time.time() - start_time))

    if monitor_data["pr_applied"] > 0:
      logger.info("Waiting for {} PRs to complete install...".format(monitor_data["pr_applied"]))
      wait_install_start = time.time()
      wait_for_phase(monitor_data, "install",
                     ("pr_fulfilled", "pr_failed"),
                     monitor_data["pr_applied"], wait_install_start, cliargs.install_timeout, start_time)

    total_prs_installed = monitor_data["pr_installed"]
    total_prs_install_failed = monitor_data["pr_failed"]
    total_prs_install_not_completed = monitor_data["pr_progressing"]
    logger.info("Install result: installed={}, failed={}, not_completed={}".format(
        total_prs_installed, total_prs_install_failed, total_prs_install_not_completed))

    install_end_time = time.time()

    rc, output = command(
        ["oc", "--kubeconfig", cliargs.kubeconfig,
         "get", "provisioningrequests.clcm.openshift.io", "-o", "json"],
        cliargs.dry_run, retries=3, no_log=True)
    if rc == 0 and output and not cliargs.dry_run:
      try:
        pr_data = json.loads(output)
        for item in pr_data.get("items", []):
          conditions = item.get("status", {}).get("conditions", [])
          if any(c.get("type") == "ConfigurationApplied" and c.get("status") == "True"
                 for c in conditions):
            installed_pr_uuids.append(item["metadata"]["name"])
      except json.decoder.JSONDecodeError:
        logger.error("Failed to parse PR data for upgrade list")
    run_analyzer("analyze-provisioningrequests.py", [], report_dir, base_dir, cliargs.dry_run)

    if not cliargs.no_prometheus_analysis:
      launch_prometheus_analysis(report_dir, "phase3-install",
          install_start_time, install_end_time, cliargs.kubeconfig, base_dir)
  else:
    logger.info("Phase 3 (Install) skipped")

  #############################################################################
  # Phase 4: IBU Upgrade
  #############################################################################
  total_prs_upgraded = 0
  total_prs_upgrade_failed = 0
  total_prs_upgrade_not_completed = 0
  upgrade_start_time = install_end_time
  upgrade_end_time = upgrade_start_time

  if not cliargs.skip_upgrade:
    phase_break()
    logger.info("Phase 4: IBU Upgrade (templateVersion: {}) - {}".format(
        template_version, int(time.time() * 1000)))
    phase_break()

    upgrade_start_time = time.time()

    if cliargs.dry_run:
      installed_pr_uuids = ["dry-run-uuid-{:05d}".format(i) for i in range(5)]
    elif cliargs.skip_install:
      # Upgrade-only mode: phase 3 did not run, query live
      rc, output = command(
          ["oc", "--kubeconfig", cliargs.kubeconfig,
           "get", "provisioningrequests.clcm.openshift.io", "-o", "json"],
          cliargs.dry_run, retries=3, no_log=True)
      if rc == 0 and output:
        try:
          pr_data = json.loads(output)
          for item in pr_data.get("items", []):
            conditions = item.get("status", {}).get("conditions", [])
            if any(c.get("type") == "ConfigurationApplied" and c.get("status") == "True"
                   for c in conditions):
              installed_pr_uuids.append(item["metadata"]["name"])
        except json.decoder.JSONDecodeError:
          logger.error("Failed to parse live PR data for upgrade")

    logger.info("Found {} installed PRs to upgrade".format(len(installed_pr_uuids)))

    batch_num = 0
    uuid_idx = 0
    while uuid_idx < len(installed_pr_uuids):
      batch_num += 1
      batch = installed_pr_uuids[uuid_idx:uuid_idx + cliargs.upgrade_batch]
      uuid_idx += cliargs.upgrade_batch

      logger.info("Upgrade batch {}: patching {} PRs - {}".format(
          batch_num, len(batch), int(time.time() * 1000)))
      for pr_uuid in batch:
        patch_time = datetime.fromtimestamp(time.time(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        patch_body = json.dumps({
          "spec": {
            "templateName": cliargs.clustertemplate_name,
            "templateVersion": template_version
          },
          "metadata": {
            "annotations": {"ibu-patch-time": patch_time}
          }
        })
        rc, output = command(
            ["oc", "--kubeconfig", cliargs.kubeconfig,
             "patch", "provisioningrequests", pr_uuid,
             "--type", "merge", "-p", patch_body],
            cliargs.dry_run, retries=3)
        if rc != 0:
          logger.error("oc patch failed for PR {}: rc={}, output={}".format(pr_uuid, rc, output))
        else:
          monitor_data["pr_patched"] += 1

      if uuid_idx < len(installed_pr_uuids) and cliargs.upgrade_interval > 0:
        logger.info("Sleeping {}s before next upgrade batch".format(cliargs.upgrade_interval))
        time.sleep(cliargs.upgrade_interval)
        log_monitor_data(monitor_data, round(time.time() - start_time))

    if monitor_data["pr_patched"] > 0:
      logger.info("Waiting for {} PRs to complete upgrade...".format(monitor_data["pr_patched"]))
      wait_upgrade_start = time.time()
      wait_for_phase(monitor_data, "upgrade",
                     ("pr_upgraded", "pr_upgrade_failed"),
                     monitor_data["pr_patched"], wait_upgrade_start, cliargs.upgrade_timeout, start_time)

    upgrade_end_time = time.time()

    if not cliargs.no_prometheus_analysis:
      launch_prometheus_analysis(report_dir, "phase4-upgrade",
          upgrade_start_time, upgrade_end_time, cliargs.kubeconfig, base_dir)
  else:
    logger.info("Phase 4 (Upgrade) skipped")

  #############################################################################
  # Phase 5: Soak Baseline
  #############################################################################
  phase_break()
  logger.info("Phase 5: Soak Baseline")
  phase_break()
  soak_start_time = time.time()
  if cliargs.end_delay > 0:
    logger.info("Sleeping {}s :: {}".format(cliargs.end_delay, str(timedelta(seconds=cliargs.end_delay))))
    remaining = cliargs.end_delay
    while remaining > 300:
      time.sleep(300)
      remaining -= 300
      logger.info("{}s :: {} remaining in soak baseline".format(remaining, str(timedelta(seconds=remaining))))
    time.sleep(remaining)

  end_time = time.time()

  if not cliargs.no_prometheus_analysis:
    launch_prometheus_analysis(report_dir, "phase5-soak-baseline",
        soak_start_time, end_time, cliargs.kubeconfig, base_dir)

  # Stop monitor thread
  logger.info("Stopping monitoring thread may take up to: {}s".format(cliargs.monitor_interval))
  monitor_thread.signal = False
  monitor_thread.join()

  total_prs_upgraded = monitor_data["pr_upgraded"]
  total_prs_upgrade_failed = monitor_data["pr_upgrade_failed"]
  total_prs_upgrade_not_completed = monitor_data["pr_progressing"]
  logger.info("Upgrade result: upgraded={}, upgrade_failed={}, not_completed={}".format(
      total_prs_upgraded, total_prs_upgrade_failed, total_prs_upgrade_not_completed))

  def _ts(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

  phases_list = [{"num": "1", "label": "Idle Baseline",
                  "start": _ts(start_time), "end": _ts(inspect_start_time)}]
  if not cliargs.skip_inspection:
    phases_list.append({"num": "2", "label": "Inspection",
                        "start": _ts(inspect_start_time), "end": _ts(inspect_end_time)})
  if not cliargs.skip_install:
    phases_list.append({"num": "3", "label": "Install",
                        "start": _ts(install_start_time), "end": _ts(install_end_time)})
  if not cliargs.skip_upgrade:
    phases_list.append({"num": "4", "label": "Upgrade",
                        "start": _ts(upgrade_start_time), "end": _ts(upgrade_end_time)})
  phases_list.append({"num": "5", "label": "Soak Baseline",
                      "start": _ts(soak_start_time), "end": _ts(end_time)})

  with open(os.path.join(report_dir, "phases.json"), "w") as pf:
    json.dump({"phases": phases_list}, pf, indent=2)
  logger.info("Phases written to {}/phases.json".format(report_dir))

  generate_ocloud_deploy_load_report(
      start_time, end_time,
      inspect_start_time, inspect_end_time,
      install_start_time, install_end_time,
      upgrade_start_time, upgrade_end_time,
      soak_start_time,
      cliargs.skip_inspection, cliargs.skip_install, cliargs.skip_upgrade,
      total_hosts_committed, total_hosts_inspected, total_hosts_inspect_failed,
      monitor_data["pr_applied"], total_prs_installed, total_prs_install_failed, total_prs_install_not_completed,
      monitor_data["pr_patched"], total_prs_upgraded, total_prs_upgrade_failed, total_prs_upgrade_not_completed,
      template_version, monitor_data, cliargs, versions, report_dir)

if __name__ == "__main__":
  sys.exit(main())
