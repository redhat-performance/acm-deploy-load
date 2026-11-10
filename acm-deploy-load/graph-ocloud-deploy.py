#!/usr/bin/env python3
#
# Graph monitor_data.csv from ocloud-deploy-load.py
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
import json
import logging
import os
import pathlib
import sys
import time

import pandas as pd
import plotly.express as px


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime

# Phase label → short display name and color for vline/annotation
PHASE_DISPLAY = {
    "1": ("Idle",    "#6b7280"),
    "2": ("Inspect", "#2563eb"),
    "3": ("Install", "#16a34a"),
    "4": ("Upgrade", "#d97706"),
    "5": ("Soak",    "#7c3aed"),
}


def load_phases(results_dir):
  """Load phase timestamps from phases.json.

  Returns list of (num, label, start_dt, end_dt) for each phase present.
  """
  phases_path = os.path.join(results_dir, "phases.json")
  try:
    with open(phases_path) as f:
      data = json.load(f)
    return [
        (p["num"], p["label"],
         datetime.strptime(p["start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc),
         datetime.strptime(p["end"],   "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc))
        for p in data.get("phases", [])
    ]
  except FileNotFoundError:
    logger.warning("phases.json not found in {} — no phase annotations".format(results_dir))
    return []


def compute_x_range(phases, df):
  """Return (x_min_str, x_max_str) with idle trimmed to 30 min and soak to 60 min."""
  times = pd.to_datetime(df["date"], utc=True)
  x_min = times.min().to_pydatetime()
  x_max = times.max().to_pydatetime()

  for num, _, start, end in phases:
    if num == "2":  # first active phase — trim idle
      idle_secs = (start - x_min).total_seconds()
      if idle_secs > 30 * 60:
        x_min = start - timedelta(minutes=30)
    if num == "5":  # soak — trim tail
      soak_secs = (x_max - start).total_seconds()
      if soak_secs > 60 * 60:
        x_max = start + timedelta(minutes=60)

  return (
      x_min.strftime("%Y-%m-%dT%H:%M:%SZ"),
      x_max.strftime("%Y-%m-%dT%H:%M:%SZ"),
  )


def add_phase_lines(fig, phases):
  """Add a vertical dashed line and top annotation for each phase start."""
  for num, label, start, end in phases:
    display_label, color = PHASE_DISPLAY.get(num, (label, "#374151"))
    ts = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    fig.add_vline(
        x=ts,
        line_dash="dash",
        line_color=color,
        line_width=1.5,
        annotation_text="<b>{}</b>".format(display_label),
        annotation_position="top left",
        annotation_font_size=9,
        annotation_font_color=color,
    )


def make_graph(df, x, y_cols, labels, title, phases, x_range, width, height, out_path):
  fig = px.line(df, x=x, y=y_cols, labels=labels, width=width, height=height)
  fig.update_layout(title=title, legend_orientation="v")
  if x_range:
    fig.update_xaxes(range=list(x_range))
  if phases:
    add_phase_lines(fig, phases)
  logger.info("Creating Graph - {}".format(out_path))
  fig.write_image(out_path, width=width, height=height)


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Produce graphs from ocloud-deploy-load monitor data",
      prog="graph-ocloud-deploy.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("--acm-version", type=str, default="", help="Override ACM version for graph title")
  parser.add_argument("--mce-version", type=str, default="", help="Override MCE version for graph title")
  parser.add_argument("--ocloud-manager-version", type=str, default="",
      help="Override O-Cloud Manager version for graph title")
  parser.add_argument("--test-version", type=str, default="", help="Override test version for graph title")
  parser.add_argument("--hub-version", type=str, default="", help="Override OCP Hub version for graph title")

  parser.add_argument("--monitor-data-file-name", type=str, default="monitor_data.csv",
      help="The name of the monitor data csv file.")

  parser.add_argument("-w", "--width", type=int, default=1000, help="Sets width of all graphs")
  parser.add_argument("-t", "--height", type=int, default=700, help="Sets height of all graphs")

  parser.add_argument("results_directory", type=str, help="The location of an ocloud-deploy-load results directory")

  cliargs = parser.parse_args()

  versions_file = "{}/versions.json".format(cliargs.results_directory)
  if pathlib.Path(versions_file).is_file():
    with open(versions_file) as vf:
      versions_data = json.load(vf)
    for key in ["acm_version", "mce_version", "ocloud_manager_version", "test_version", "hub_version"]:
      if key in versions_data and not getattr(cliargs, key):
        setattr(cliargs, key, versions_data[key])

  logger.info("O-Cloud Deploy Graph")
  md_csv_file = "{}/{}".format(cliargs.results_directory, cliargs.monitor_data_file_name)
  if not pathlib.Path(md_csv_file).is_file():
    logger.error("File not found: {}".format(md_csv_file))
    sys.exit(1)

  df = pd.read_csv(md_csv_file)

  phases = load_phases(cliargs.results_directory)
  x_range = compute_x_range(phases, df) if phases else None

  pr_fulfilled = df["pr_fulfilled"].values[-1]
  pr_upgraded = df["pr_upgraded"].values[-1]
  managed = df["managed"].values[-1]
  pr_total = int(
      df["pr_pending"].values[-1] + df["pr_progressing"].values[-1] +
      df["pr_fulfilled"].values[-1] + df["pr_failed"].values[-1])

  title_base = "O-Cloud {} {} ({}/{} PRs fulfilled)<br>ACM {}, MCE {}, Hub OCP {}".format(
      cliargs.ocloud_manager_version, cliargs.test_version,
      pr_fulfilled, pr_total,
      cliargs.acm_version, cliargs.mce_version, cliargs.hub_version)
  title_upgrade = "O-Cloud {} {} ({}/{} PRs upgraded)<br>ACM {}, MCE {}, Hub OCP {}".format(
      cliargs.ocloud_manager_version, cliargs.test_version,
      pr_upgraded, pr_total,
      cliargs.acm_version, cliargs.mce_version, cliargs.hub_version)
  title_share = "O-Cloud {} {} ({}/{} managed)<br>ACM {}, MCE {}, Hub OCP {}".format(
      cliargs.ocloud_manager_version, cliargs.test_version,
      managed, pr_total,
      cliargs.acm_version, cliargs.mce_version, cliargs.hub_version)

  l_hosts    = {"value": "# hosts",    "date": ""}
  l_clusters = {"value": "# clusters", "date": ""}

  ts = datetime.fromtimestamp(time.time(), tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
  d = cliargs.results_directory

  make_graph(df, "date",
      ["bmh_committed", "bmh_inspecting", "bmh_available", "bmh_inspect_failed", "bmh_provisioning", "bmh_provisioned", "bmh_error"],
      l_hosts, title_base, phases, x_range, cliargs.width, cliargs.height,
      "{}/ocloud-bmh-{}.png".format(d, ts))

  make_graph(df, "date",
      ["pr_applied", "ci_notstarted", "ci_progressing", "ci_failed", "ci_completed", "managed"],
      l_clusters, title_base, phases, x_range, cliargs.width, cliargs.height,
      "{}/ocloud-ci-install-{}.png".format(d, ts))

  make_graph(df, "date",
      ["pr_applied", "ici_aci_installing", "ici_aci_failed", "ici_aci_completed", "managed"],
      l_clusters, title_base, phases, x_range, cliargs.width, cliargs.height,
      "{}/ocloud-ici-aci-install-{}.png".format(d, ts))

  make_graph(df, "date",
      ["pr_applied", "pr_pending", "pr_progressing", "managed", "pr_failed", "pr_installed"],
      l_clusters, title_base, phases, x_range, cliargs.width, cliargs.height,
      "{}/ocloud-pr-install-{}.png".format(d, ts))

  make_graph(df, "date",
      ["pr_applied", "pr_installed", "pr_fulfilled", "pr_patched", "pr_progressing", "pr_upgrade_failed", "pr_upgraded"],
      l_clusters, title_upgrade, phases, x_range, cliargs.width, cliargs.height,
      "{}/ocloud-pr-upgrade-{}.png".format(d, ts))

  make_graph(df, "date",
      ["bmh_committed", "bmh_available", "pr_applied", "managed", "pr_installed", "pr_patched", "pr_upgraded"],
      l_clusters, title_share, phases, x_range, cliargs.width, cliargs.height,
      "{}/ocloud-share-{}.png".format(d, ts))

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
