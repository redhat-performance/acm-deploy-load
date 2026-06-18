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
import logging
import os
import subprocess
import sys

logger = logging.getLogger("acm-deploy-load")


def launch_prometheus_analysis(report_dir, phase_name, start_ts, end_ts, kubeconfig, base_dir):
  """Launch analyze-prometheus.py in the background for the given time window."""
  analyzer_script = os.path.join(base_dir, "analyze-prometheus.py")
  if not os.path.isfile(analyzer_script):
    logger.warning("analyze-prometheus.py not found at {}, skipping phase {}".format(analyzer_script, phase_name))
    return
  start_str = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
  end_str = datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
  duration_seconds = round(end_ts - start_ts)
  if duration_seconds < 900:
    logger.warning("Skipping prometheus analysis phase {}: window {}s < 15 minutes".format(phase_name, duration_seconds))
    return
  # No buffer time since script is running against end time that is less than 5 minutes from now
  cmd = [
    sys.executable,
    analyzer_script,
    "-k", kubeconfig,
    "-s", start_str,
    "-e", end_str,
    "-b", "0",
    "-p", phase_name,
    report_dir,
  ]
  logger.info("Prometheus analysis command: {}".format(" ".join(cmd)))
  log_file = os.path.join(report_dir, "pa-{}.log".format(phase_name))
  try:
    with open(log_file, "w") as f:
      proc = subprocess.Popen(
        cmd,
        stdout=f,
        stderr=subprocess.STDOUT,
        cwd=base_dir,
        start_new_session=True,
      )
    logger.info("Launched prometheus analysis phase '{}' in background (pid {}, log: {})".format(
      phase_name, proc.pid, os.path.basename(log_file)))
  except Exception as e:
    logger.warning("Failed to launch prometheus analysis for phase {}: {}".format(phase_name, e))
