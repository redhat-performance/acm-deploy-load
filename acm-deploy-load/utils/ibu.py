#!/usr/bin/env python3
#
# IBU (ImageBasedUpgrade) shared utilities for spoke-side data fetching and history parsing
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

import json
import logging
import os
from utils.command import command
from utils.time_utils import parse_ts

logger = logging.getLogger("acm-deploy-load")

KNOWN_STAGES = ("Prep", "Upgrade", "Finalize", "Rollback")


def fetch_spoke_ibu(cluster, kubeconfigs_dir, raw_data_dir, offline):
  """Query `oc get ibu upgrade` on a spoke cluster and return parsed JSON or empty string.

  In live mode, runs oc with the cluster kubeconfig and writes the result to
  {raw_data_dir}/{cluster}-ibu.json. In offline mode, reads the previously saved file.
  Returns the parsed JSON dict, or "" when the cluster is unreachable or the file is empty.
  """
  ibu_file = "{}/{}-ibu.json".format(raw_data_dir, cluster)
  if not offline:
    kubeconfig = "{}/{}/kubeconfig".format(kubeconfigs_dir, cluster)
    oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "ibu", "upgrade", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=2, no_log=True)
    if rc != 0:
      logger.error("fetch_spoke_ibu: oc get ibu upgrade failed (rc={}) for cluster {}".format(rc, cluster))
      output = ""
    with open(ibu_file, "w") as f:
      f.write(output)
  try:
    if os.stat(ibu_file).st_size == 0:
      return ""
  except FileNotFoundError:
    logger.error("fetch_spoke_ibu: IBU file not found for cluster {}".format(cluster))
    return ""
  with open(ibu_file, "r") as f:
    return json.load(f)


def parse_ibu_history(ibu_data):
  """Extract stage and sub-phase timings from status.history[] (LCA 4.17+).

  Handles Prep, Upgrade, Finalize, and Rollback stages. Each stage entry includes the
  overall start/completion times and a list of sub-phase timings (e.g. Stateroot/Precache
  for Prep; PrePivot/PostPivot for Upgrade).

  Args:
    ibu_data: Parsed IBU JSON dict, or "" when unavailable.

  Returns:
    Dict keyed by stage name. Each value is:
      {"start": datetime|"", "completion": datetime|"", "phases": [{"phase": str,
       "start": datetime|"", "completion": datetime|""}]}
    Unknown stages are added dynamically with a warning log.
  """
  result = {stage: {"start": "", "completion": "", "phases": []} for stage in KNOWN_STAGES}

  if not isinstance(ibu_data, dict):
    return result

  history = ibu_data.get("status", {}).get("history", [])
  if not history:
    logger.warning("parse_ibu_history: status.history missing or empty (LCA must be 4.17+)")
    return result

  for entry in history:
    stage = entry.get("stage", "")
    if stage not in result:
      logger.warning("parse_ibu_history: unknown stage '{}', adding".format(stage))
      result[stage] = {"start": "", "completion": "", "phases": []}
    result[stage]["start"] = parse_ts(entry.get("startTime", ""))
    result[stage]["completion"] = parse_ts(entry.get("completionTime", ""))
    result[stage]["phases"] = [
        {
            "phase": p.get("phase", ""),
            "start": parse_ts(p.get("startTime", "")),
            "completion": parse_ts(p.get("completionTime", "")),
        }
        for p in entry.get("phases", [])
    ]

  return result
