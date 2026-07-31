#!/usr/bin/env python3
#
# Generate overlay comparison graphs from two acm-deploy-load / acm-telco-core-load
# Prometheus analysis directories.
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
import glob
import logging
import math
import os
import re
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(message)s")
logger = logging.getLogger("graph-acm-compare")
logging.Formatter.converter = time.gmtime

GRAPH_DEFS = {
    # CPU
    "cpu-cluster": {
        "csv": "cluster/csv/cpu-cluster.csv",
        "agg": "direct",
        "title": "Cluster CPU",
        "yaxis": "CPU (cores)",
    },
    "cpu-node": {
        "csv": "node/csv/cpu-node.csv",
        "agg": "max",
        "title": "Node CPU (Peak Node)",
        "yaxis": "CPU (cores)",
    },
    # Memory
    "mem-cluster": {
        "csv": "cluster/csv/mem-cluster.csv",
        "agg": "direct",
        "title": "Cluster Memory",
        "yaxis": "Memory (GiB)",
        "memory": True,
    },
    "mem-node": {
        "csv": "node/csv/mem-node.csv",
        "agg": "max",
        "title": "Node Memory (Peak Node)",
        "yaxis": "Memory (GiB)",
        "memory": True,
    },
    # Network
    "net-rcv-node": {
        "csv": "node/csv/net-rcv-node.csv",
        "agg": "max",
        "title": "Network Receive (Peak Node)",
        "yaxis": "Receive (Mbps)",
    },
    "net-xmt-node": {
        "csv": "node/csv/net-xmt-node.csv",
        "agg": "max",
        "title": "Network Transmit (Peak Node)",
        "yaxis": "Transmit (Mbps)",
    },
    # etcd
    "backend-commit-etcd": {
        "csv": "etcd/csv/backend-commit-duration.csv",
        "agg": "max",
        "title": "etcd Backend Commit Duration (Worst-Case Member)",
        "yaxis": "Duration (ms)",
        "scale": 1000,
        "hline": 25,
        "hline_label": "25ms Threshold",
    },
    "db-size-etcd": {
        "csv": "etcd/csv/db-size.csv",
        "agg": "max",
        "title": "etcd DB Size (Worst-Case Member)",
        "yaxis": "DB Size (GB)",
        "hline": 8.59,
        "hline_label": "8 GiB Quota (8.59 GB)",
    },
    "fsync-etcd": {
        "csv": "etcd/csv/fsync-duration.csv",
        "agg": "max",
        "title": "etcd WAL Fsync Duration (Worst-Case Member)",
        "yaxis": "Duration (ms)",
        "scale": 1000,
        "hline": 10,
        "hline_label": "10ms Threshold",
    },
    "peer-rtt-etcd": {
        "csv": "etcd/csv/peer-roundtrip-time.csv",
        "agg": "max",
        "title": "etcd Peer Round-Trip Time (Worst-Case Member)",
        "yaxis": "Duration (ms)",
        "scale": 1000,
        "hline": 50,
        "hline_label": "50ms Threshold",
    },
    # Disk (etcd partition)
    "disk-iops-write-etcd": {
        "csv": "node/csv/disk-iops-write-etcd-node.csv",
        "agg": "max",
        "title": "Disk Write IOPS — etcd Partition (Peak Node)",
        "yaxis": "IOPS",
    },
    "disk-tput-write-etcd": {
        "csv": "node/csv/disk-tput-write-etcd-node.csv",
        "agg": "max",
        "title": "Disk Write Throughput — etcd Partition (Peak Node)",
        "yaxis": "Throughput (MB/s)",
    },
}

DEPLOY_DEFS = {
    "deploy-installed": {
        "milestone_col": "cluster_install_completed",
        "milestone_label": "Installed",
        "title": "Cluster Deploy — Installed",
    },
    "deploy-managed": {
        "milestone_col": "managed",
        "milestone_label": "Managed",
        "title": "Cluster Deploy — Managed",
    },
    "deploy-compliant": {
        "milestone_col": "policy_compliant",
        "milestone_label": "Compliant",
        "title": "Cluster Deploy — Compliant",
    },
    "deploy-all": {
        "milestone_cols": [
            ("cluster_install_completed", "Installed"),
            ("managed", "Managed"),
            ("policy_compliant", "Compliant"),
        ],
        "title": "Cluster Deploy — All Milestones",
    },
}

COLORS = {"a": "#2563eb", "b": "#c2410c"}
DEPLOY_COLORS = {
    "a_applied": "#1e3a5f", "a_milestone": "#60a5fa",
    "b_applied": "#7f1d1d", "b_milestone": "#c2410c",
}

PHASE_COLORS = ["#dbeafe", "#fef9c3", "#dcfce7"]
PHASE_LABELS = {
    "1": "Idle",
    "2": "Deploy",
    "3": "Soak",
}

LAYOUT_DEFAULTS = dict(
    template="plotly_white",
    font=dict(family="Arial, Helvetica, sans-serif", size=13),
    title_font_size=16,
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="center",
        x=0.5,
        font=dict(size=13),
    ),
    margin=dict(l=70, r=30, t=80, b=75),
    xaxis=dict(
        title="Minutes into Test",
        showgrid=True,
        gridcolor="#e5e7eb",
        gridwidth=1,
        dtick=60,
        tick0=0,
        minor=dict(dtick=30, showgrid=True, gridcolor="#f3f4f6", gridwidth=1),
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="#e5e7eb",
        gridwidth=1,
    ),
)



def memory_ticks(max_val):
    """Return (dtick_major, dtick_minor) in GiB using base-2 values.

    Picks a major tick interval that yields 4-8 gridlines, with minor
    ticks at half the major interval.
    """
    candidates = [8, 16, 32, 64, 128, 256, 512]
    for major in candidates:
        if max_val / major <= 8:
            return major, major // 2
    return 512, 256


def find_deploy_pa(result_dir):
    patterns = [
        os.path.join(result_dir, "deploy-pa-[0-9]*"),
        os.path.join(result_dir, "acm-telco-load-hub-[0-9]*"),
    ]
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return None


def parse_phases(report_path):
    """Parse phase boundaries from report.txt.

    Returns list of (phase_num, label, start_dt, end_dt) tuples.
    """
    phases = []
    phase_re = re.compile(
        r"\* Phase (\d+) \(([^)]+)\): (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z) to (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"
    )
    try:
        with open(report_path) as f:
            for line in f:
                m = phase_re.search(line)
                if m:
                    num = m.group(1)
                    label = PHASE_LABELS.get(num, m.group(2))
                    start = datetime.strptime(m.group(3), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    end = datetime.strptime(m.group(4), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    phases.append((num, label, start, end))
    except FileNotFoundError:
        logger.warning("report.txt not found: {}".format(report_path))
    return phases


def phases_to_elapsed(phases, t0):
    """Convert phase boundaries to elapsed minutes from t0."""
    result = []
    for num, label, start, end in phases:
        start_min = (start - t0).total_seconds() / 60
        end_min = (end - t0).total_seconds() / 60
        result.append((num, label, start_min, end_min))
    return result


def read_csv(path):
    df = pd.read_csv(path, index_col=0)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    return df


def to_elapsed_minutes(df):
    t0 = df["datetime"].iloc[0]
    df = df.copy()
    df["minutes"] = (df["datetime"] - t0).dt.total_seconds() / 60
    return df, t0


def get_series(df, agg):
    data_cols = [c for c in df.columns if c not in ("datetime", "minutes")]
    if agg == "direct":
        return df[data_cols[0]]
    elif agg == "max":
        return df[data_cols].max(axis=1)
    elif agg == "sum":
        return df[data_cols].sum(axis=1)
    else:
        raise ValueError("Unknown aggregation: {}".format(agg))


def read_monitor_csv(path):
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["date"], utc=True)
    df = df.drop(columns=["date"])
    return df


DEPLOY_ALL_COLORS = {
    "a": ["#1e3a5f", "#1d4ed8", "#60a5fa", "#bfdbfe"],
    "b": ["#7f1d1d", "#991b1b", "#c2410c", "#ea580c"],
}


def generate_deploy_graph(metric, result_dir_a, result_dir_b, label_a, label_b,
                          output_path, width, height, phases_a=None, phases_b=None):
    ddef = DEPLOY_DEFS[metric]
    csv_a = os.path.join(result_dir_a, "monitor_data.csv")
    csv_b = os.path.join(result_dir_b, "monitor_data.csv")

    if not os.path.isfile(csv_a):
        logger.warning("monitor_data.csv not found, skipping {}: {}".format(metric, csv_a))
        return False
    if not os.path.isfile(csv_b):
        logger.warning("monitor_data.csv not found, skipping {}: {}".format(metric, csv_b))
        return False

    df_a, t0_a = to_elapsed_minutes(read_monitor_csv(csv_a))
    df_b, t0_b = to_elapsed_minutes(read_monitor_csv(csv_b))

    fig = go.Figure()

    if phases_a or phases_b:
        pa = phases_to_elapsed(phases_a, t0_a) if phases_a else []
        pb = phases_to_elapsed(phases_b, t0_b) if phases_b else []
        add_phase_annotations(fig, pa, pb, label_a, label_b)

    b_dash = "1px 1px"
    is_combined = "milestone_cols" in ddef

    # Dynamically trim x-axis to focus on deploy activity:
    # - Keep 30 min of idle before the earliest deploy start (trim only if idle > 30 min)
    # - Keep 60 min of soak after the latest soak start (trim only if soak > 60 min)
    # - Never trim the deploy phase — use the union of both results' deploy windows
    x_range = None
    if phases_a or phases_b:
        pa = phases_to_elapsed(phases_a, t0_a) if phases_a else []
        pb = phases_to_elapsed(phases_b, t0_b) if phases_b else []
        max_data_minutes = max(df_a["minutes"].max(), df_b["minutes"].max())
        deploy_starts = []
        soak_starts = []
        soak_durations = []
        for phases_elapsed in [pa, pb]:
            for num, _, start_min, end_min in phases_elapsed:
                if num == "2":
                    deploy_starts.append(start_min)
                elif num == "3":
                    soak_starts.append(start_min)
                    soak_durations.append(end_min - start_min)

        x_min = 0
        x_max = max_data_minutes
        if deploy_starts and min(deploy_starts) > 30:
            x_min = min(deploy_starts) - 30
        if soak_starts and soak_durations and max(soak_durations) > 60:
            x_max = max(soak_starts) + 60
        if x_min > 0 or x_max < max_data_minutes:
            x_range = [x_min, x_max]

    if is_combined:
        milestones = ddef["milestone_cols"]
        a_colors = DEPLOY_ALL_COLORS["a"]
        b_colors = DEPLOY_ALL_COLORS["b"]

        fig.add_trace(go.Scatter(
            x=df_a["minutes"], y=df_a["cluster_applied"], mode="lines",
            name="{} Applied".format(label_a),
            line=dict(color=a_colors[0], width=2),
        ))
        for i, (col, label) in enumerate(milestones):
            fig.add_trace(go.Scatter(
                x=df_a["minutes"], y=df_a[col], mode="lines",
                name="{} {}".format(label_a, label),
                line=dict(color=a_colors[i + 1], width=1.5),
            ))

        fig.add_trace(go.Scatter(
            x=df_b["minutes"], y=df_b["cluster_applied"], mode="lines",
            name="{} Applied".format(label_b),
            line=dict(color=b_colors[0], width=2, dash=b_dash),
        ))
        for i, (col, label) in enumerate(milestones):
            fig.add_trace(go.Scatter(
                x=df_b["minutes"], y=df_b[col], mode="lines",
                name="{} {}".format(label_b, label),
                line=dict(color=b_colors[i + 1], width=1.5, dash=b_dash),
            ))
    else:
        milestone_col = ddef["milestone_col"]
        milestone_label = ddef["milestone_label"]

        fig.add_trace(go.Scatter(
            x=df_a["minutes"], y=df_a["cluster_applied"], mode="lines",
            name="{} Applied".format(label_a),
            line=dict(color=DEPLOY_COLORS["a_applied"], width=2),
        ))
        fig.add_trace(go.Scatter(
            x=df_a["minutes"], y=df_a[milestone_col], mode="lines",
            name="{} {}".format(label_a, milestone_label),
            line=dict(color=DEPLOY_COLORS["a_milestone"], width=1.5),
        ))
        fig.add_trace(go.Scatter(
            x=df_b["minutes"], y=df_b["cluster_applied"], mode="lines",
            name="{} Applied".format(label_b),
            line=dict(color=DEPLOY_COLORS["b_applied"], width=2, dash=b_dash),
        ))
        fig.add_trace(go.Scatter(
            x=df_b["minutes"], y=df_b[milestone_col], mode="lines",
            name="{} {}".format(label_b, milestone_label),
            line=dict(color=DEPLOY_COLORS["b_milestone"], width=1.5, dash=b_dash),
        ))

    title = "{} — {} vs {}".format(ddef["title"], label_a, label_b)
    layout = dict(
        title=title,
        yaxis_title="# Clusters",
        width=width,
        height=height,
        **LAYOUT_DEFAULTS,
    )
    if x_range:
        layout["xaxis"] = dict(**LAYOUT_DEFAULTS["xaxis"], range=x_range)
    if is_combined:
        layout["legend"] = dict(
            orientation="v",
            yanchor="top",
            y=1.0,
            xanchor="left",
            x=1.02,
            font=dict(size=11),
        )
        layout["margin"] = dict(l=70, r=200, t=80, b=75)

    fig.update_layout(**layout)

    fig.write_image(output_path)
    logger.info("Wrote: {}".format(output_path))
    return True


def add_phase_annotations(fig, phases_a_elapsed, phases_b_elapsed, label_a, label_b):
    """Add phase annotations for both results.

    Result A: full-height shaded regions with labels at top.
    Result B: thin bar along the bottom with labels.
    Legend entries explain which shading belongs to which result.
    """
    # Phase shading key — bottom-right corner
    fig.add_annotation(
        x=1.0, xref="paper", xanchor="right",
        y=0.0, yref="paper", yanchor="bottom",
        text="Shading: {}<br>Bottom bar: {}".format(label_a, label_b),
        showarrow=False,
        font=dict(size=10, color="#374151"),
        bgcolor="rgba(255,255,255,0.85)",
        bordercolor="#d1d5db",
        borderwidth=1,
        borderpad=4,
    )

    for num, label, start_min, end_min in phases_a_elapsed:
        color = PHASE_COLORS[int(num) % len(PHASE_COLORS) - 1]
        fig.add_vrect(
            x0=start_min, x1=end_min,
            fillcolor=color, opacity=0.4,
            layer="below", line_width=0,
        )
        fig.add_vline(
            x=start_min, line_dash="dot", line_color="#9ca3af", line_width=1,
        )
        fig.add_annotation(
            x=(start_min + end_min) / 2,
            y=1.0, yref="paper",
            text="<b>{}</b>".format(label),
            showarrow=False,
            font=dict(size=11, color="#374151"),
            yanchor="bottom",
        )

    PHASE_COLORS_B = ["#93c5fd", "#fde047", "#86efac"]
    for num, _, start_min, end_min in phases_b_elapsed:
        color = PHASE_COLORS_B[int(num) % len(PHASE_COLORS_B) - 1]
        fig.add_shape(
            type="rect",
            x0=start_min, x1=end_min,
            y0=0, y1=0.05, yref="paper",
            fillcolor=color, opacity=0.9,
            layer="above", line_width=0,
        )
        fig.add_vline(
            x=start_min, line_dash="dot", line_color="#d1d5db", line_width=0.8,
        )


def generate_graph(metric, dir_a, dir_b, label_a, label_b, output_path,
                   width, height, phases_a=None, phases_b=None):
    gdef = GRAPH_DEFS[metric]
    csv_a = os.path.join(dir_a, gdef["csv"])
    csv_b = os.path.join(dir_b, gdef["csv"])

    if not os.path.isfile(csv_a):
        logger.warning("CSV not found, skipping {}: {}".format(metric, csv_a))
        return False
    if not os.path.isfile(csv_b):
        logger.warning("CSV not found, skipping {}: {}".format(metric, csv_b))
        return False

    df_a, t0_a = to_elapsed_minutes(read_csv(csv_a))
    df_b, t0_b = to_elapsed_minutes(read_csv(csv_b))

    series_a = get_series(df_a, gdef["agg"])
    series_b = get_series(df_b, gdef["agg"])

    scale = gdef.get("scale")
    if scale:
        series_a = series_a * scale
        series_b = series_b * scale

    fig = go.Figure()

    if phases_a or phases_b:
        pa = phases_to_elapsed(phases_a, t0_a) if phases_a else []
        pb = phases_to_elapsed(phases_b, t0_b) if phases_b else []
        add_phase_annotations(fig, pa, pb, label_a, label_b)

    fig.add_trace(go.Scatter(
        x=df_a["minutes"], y=series_a, mode="lines", name=label_a,
        line=dict(color=COLORS["a"], width=1.5),
    ))
    fig.add_trace(go.Scatter(
        x=df_b["minutes"], y=series_b, mode="lines", name=label_b,
        line=dict(color=COLORS["b"], width=1.5),
    ))

    if "hline" in gdef:
        fig.add_hline(
            y=gdef["hline"], line_dash="dash", line_color="#dc2626", line_width=1.5,
            annotation_text=gdef["hline_label"], annotation_position="top left",
            annotation_font_color="#dc2626", annotation_font_size=11,
        )

    title = "{} — {} vs {}".format(gdef["title"], label_a, label_b)
    fig.update_layout(
        title=title,
        yaxis_title=gdef["yaxis"],
        width=width,
        height=height,
        **LAYOUT_DEFAULTS,
    )

    if gdef.get("memory"):
        max_val = max(series_a.max(), series_b.max())
        major, minor = memory_ticks(max_val)
        fig.update_yaxes(
            dtick=major,
            tick0=0,
            minor=dict(dtick=minor, showgrid=True, gridcolor="#f3f4f6", gridwidth=1),
        )

    fig.write_image(output_path)
    logger.info("Wrote: {}".format(output_path))
    return True


def main():
    start_time = time.time()

    parser = argparse.ArgumentParser(
        description="Generate overlay comparison graphs from two test results",
        prog="graph-acm-compare.py",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("result_dir_a", type=str,
        help="Result directory for result A (top-level, e.g., results/20260718-...)")
    parser.add_argument("result_dir_b", type=str,
        help="Result directory for result B")
    parser.add_argument("--label-a", type=str, default="Result A",
        help="Display label for result A")
    parser.add_argument("--label-b", type=str, default="Result B",
        help="Display label for result B")
    parser.add_argument("-o", "--output-dir", type=str, default=".",
        help="Directory to write PNG files")
    parser.add_argument("-p", "--prefix", type=str, default="comparison",
        help="Output filename prefix")
    parser.add_argument("-m", "--metrics", type=str, nargs="+",
        default=list(GRAPH_DEFS.keys()),
        choices=list(GRAPH_DEFS.keys()),
        help="Which graphs to generate")
    parser.add_argument("-w", "--width", type=int, default=1400,
        help="Graph width in pixels")
    parser.add_argument("-t", "--height", type=int, default=600,
        help="Graph height in pixels")

    cliargs = parser.parse_args()

    for d in [cliargs.result_dir_a, cliargs.result_dir_b]:
        if not os.path.isdir(d):
            logger.error("Directory not found: {}".format(d))
            sys.exit(1)

    dir_a = find_deploy_pa(cliargs.result_dir_a)
    dir_b = find_deploy_pa(cliargs.result_dir_b)
    if not dir_a:
        logger.error("No deploy-pa / acm-telco-load-hub directory found in: {}".format(cliargs.result_dir_a))
        sys.exit(1)
    if not dir_b:
        logger.error("No deploy-pa / acm-telco-load-hub directory found in: {}".format(cliargs.result_dir_b))
        sys.exit(1)
    logger.info("Result A analysis dir: {}".format(dir_a))
    logger.info("Result B analysis dir: {}".format(dir_b))

    phases_a = parse_phases(os.path.join(cliargs.result_dir_a, "report.txt"))
    phases_b = parse_phases(os.path.join(cliargs.result_dir_b, "report.txt"))
    if phases_a:
        logger.info("Parsed {} phases from result A".format(len(phases_a)))
    if phases_b:
        logger.info("Parsed {} phases from result B".format(len(phases_b)))

    os.makedirs(cliargs.output_dir, exist_ok=True)

    generated = 0
    for metric in cliargs.metrics:
        output_path = os.path.join(cliargs.output_dir, "{}-{}.png".format(cliargs.prefix, metric))
        try:
            if generate_graph(metric, dir_a, dir_b, cliargs.label_a, cliargs.label_b,
                              output_path, cliargs.width, cliargs.height,
                              phases_a=phases_a, phases_b=phases_b):
                generated += 1
        except Exception:
            logger.exception("Failed to generate graph for metric: {}".format(metric))

    deploy_generated = 0
    for dmetric in DEPLOY_DEFS:
        output_path = os.path.join(cliargs.output_dir, "{}-{}.png".format(cliargs.prefix, dmetric))
        try:
            if generate_deploy_graph(dmetric, cliargs.result_dir_a, cliargs.result_dir_b,
                                     cliargs.label_a, cliargs.label_b,
                                     output_path, cliargs.width, cliargs.height,
                                     phases_a=phases_a, phases_b=phases_b):
                deploy_generated += 1
        except Exception:
            logger.exception("Failed to generate deploy graph: {}".format(dmetric))

    elapsed = time.time() - start_time
    total = generated + deploy_generated
    logger.info("Generated {} graphs ({} resource, {} deploy) in {:.1f}s".format(
        total, generated, deploy_generated, elapsed))


if __name__ == "__main__":
    main()
