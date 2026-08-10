#!/usr/bin/env python3
#
# Generate overlay comparison graphs from two or more acm-deploy-load /
# acm-telco-core-load Prometheus analysis directories.
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

RESULT_COLORS = ["#2563eb", "#c2410c", "#16a34a", "#9333ea", "#0891b2", "#be185d"]
RESULT_DASHES = ["solid", "4px 4px", "8px 4px", "2px 2px 6px 2px", "12px 4px", "2px 6px"]

DEPLOY_RESULT_COLORS = [
    {"applied": "#1e3a5f", "milestone": "#60a5fa"},
    {"applied": "#7f1d1d", "milestone": "#c2410c"},
    {"applied": "#14532d", "milestone": "#4ade80"},
    {"applied": "#581c87", "milestone": "#a78bfa"},
    {"applied": "#164e63", "milestone": "#22d3ee"},
    {"applied": "#831843", "milestone": "#f472b6"},
]

DEPLOY_ALL_RESULT_COLORS = [
    ["#1e3a5f", "#1d4ed8", "#60a5fa", "#bfdbfe"],
    ["#7f1d1d", "#991b1b", "#c2410c", "#ea580c"],
    ["#14532d", "#15803d", "#22c55e", "#86efac"],
    ["#581c87", "#7e22ce", "#a78bfa", "#ddd6fe"],
    ["#164e63", "#0e7490", "#22d3ee", "#a5f3fc"],
    ["#831843", "#be185d", "#f472b6", "#fbcfe8"],
]

PHASE_COLORS = ["#dbeafe", "#fef9c3", "#dcfce7"]
PHASE_BAR_COLORS = [
    ["#93c5fd", "#fde047", "#86efac"],
    ["#c4b5fd", "#fdba74", "#67e8f9"],
    ["#f9a8d4", "#a3e635", "#fcd34d"],
    ["#99f6e4", "#fca5a5", "#d8b4fe"],
    ["#bae6fd", "#fef08a", "#bbf7d0"],
]
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


def add_phase_annotations(fig, all_phases_elapsed, labels, shading_idx=0):
    """Add phase annotations for all results.

    The result at shading_idx gets full-height shaded regions with labels at top.
    All other results get thin bars stacked along the bottom.
    A legend annotation explains which shading belongs to which result.
    """
    n = len(all_phases_elapsed)

    bar_indices = [i for i in range(n) if i != shading_idx]

    shading_parts = []
    if all_phases_elapsed[shading_idx]:
        shading_parts.append("Shading: {}".format(labels[shading_idx]))
    for bar_num, i in enumerate(bar_indices, 1):
        if all_phases_elapsed[i]:
            shading_parts.append("Bar {}: {}".format(bar_num, labels[i]))

    if shading_parts:
        fig.add_annotation(
            x=1.0, xref="paper", xanchor="right",
            y=0.0, yref="paper", yanchor="bottom",
            text="<br>".join(shading_parts),
            showarrow=False,
            font=dict(size=10, color="#374151"),
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#d1d5db",
            borderwidth=1,
            borderpad=4,
        )

    if all_phases_elapsed[shading_idx]:
        for num, label, start_min, end_min in all_phases_elapsed[shading_idx]:
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

    bar_height = 0.02
    bar_gap = 0.002
    for bar_num, i in enumerate(bar_indices, 1):
        if not all_phases_elapsed[i]:
            continue
        bar_colors = PHASE_BAR_COLORS[(bar_num - 1) % len(PHASE_BAR_COLORS)]
        y0 = (bar_height + bar_gap) * (bar_num - 1)
        y1 = y0 + bar_height
        fig.add_annotation(
            x=0.0, xref="paper", xanchor="left",
            y=(y0 + y1) / 2, yref="paper", yanchor="middle",
            text=" <b>{}</b>".format(bar_num),
            showarrow=False,
            font=dict(size=8, color="#000000"),
        )
        for num, _, start_min, end_min in all_phases_elapsed[i]:
            color = bar_colors[int(num) % len(bar_colors) - 1]
            fig.add_shape(
                type="rect",
                x0=start_min, x1=end_min,
                y0=y0, y1=y1, yref="paper",
                fillcolor=color, opacity=0.9,
                layer="above", line_width=0,
            )
            fig.add_vline(
                x=start_min, line_dash="dot", line_color="#d1d5db", line_width=0.8,
            )


def compute_x_range(all_phases_elapsed, all_dfs):
    """Compute trimmed x-axis range across all results."""
    max_data_minutes = max(df["minutes"].max() for df in all_dfs)
    deploy_starts = []
    soak_starts = []
    soak_durations = []
    for phases_elapsed in all_phases_elapsed:
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
        return [x_min, x_max]
    return None


def generate_deploy_graph(metric, result_dirs, labels, output_path, width, height,
                          all_phases=None, mirror_yaxis=False, solid_lines=False,
                          shading_idx=0, trim_idx=None):
    ddef = DEPLOY_DEFS[metric]
    n = len(result_dirs)

    csv_paths = [os.path.join(d, "monitor_data.csv") for d in result_dirs]
    for path in csv_paths:
        if not os.path.isfile(path):
            logger.warning("monitor_data.csv not found, skipping {}: {}".format(metric, path))
            return False

    dfs = []
    t0s = []
    for path in csv_paths:
        df, t0 = to_elapsed_minutes(read_monitor_csv(path))
        dfs.append(df)
        t0s.append(t0)

    fig = go.Figure()

    all_phases_elapsed = []
    if all_phases:
        for i in range(n):
            if all_phases[i]:
                all_phases_elapsed.append(phases_to_elapsed(all_phases[i], t0s[i]))
            else:
                all_phases_elapsed.append([])
        add_phase_annotations(fig, all_phases_elapsed, labels, shading_idx=shading_idx)

    x_range = None
    if all_phases_elapsed:
        if trim_idx is not None and all_phases_elapsed[trim_idx]:
            x_range = compute_x_range([all_phases_elapsed[trim_idx]], dfs)
        else:
            x_range = compute_x_range(all_phases_elapsed, dfs)

    is_combined = "milestone_cols" in ddef

    if is_combined:
        milestones = ddef["milestone_cols"]
        for i in range(n):
            colors = DEPLOY_ALL_RESULT_COLORS[i % len(DEPLOY_ALL_RESULT_COLORS)]
            dash = RESULT_DASHES[i % len(RESULT_DASHES)]
            line_dash = "solid" if solid_lines or i == 0 else dash

            fig.add_trace(go.Scatter(
                x=dfs[i]["minutes"], y=dfs[i]["cluster_applied"], mode="lines",
                name="{} Applied".format(labels[i]),
                line=dict(color=colors[0], width=2, dash=line_dash),
            ))
            for j, (col, mlabel) in enumerate(milestones):
                fig.add_trace(go.Scatter(
                    x=dfs[i]["minutes"], y=dfs[i][col], mode="lines",
                    name="{} {}".format(labels[i], mlabel),
                    line=dict(color=colors[j + 1], width=1.5, dash=line_dash),
                ))
    else:
        milestone_col = ddef["milestone_col"]
        milestone_label = ddef["milestone_label"]

        for i in range(n):
            dcolors = DEPLOY_RESULT_COLORS[i % len(DEPLOY_RESULT_COLORS)]
            dash = RESULT_DASHES[i % len(RESULT_DASHES)]
            line_dash = "solid" if solid_lines or i == 0 else dash

            fig.add_trace(go.Scatter(
                x=dfs[i]["minutes"], y=dfs[i]["cluster_applied"], mode="lines",
                name="{} Applied".format(labels[i]),
                line=dict(color=dcolors["applied"], width=2, dash=line_dash),
            ))
            fig.add_trace(go.Scatter(
                x=dfs[i]["minutes"], y=dfs[i][milestone_col], mode="lines",
                name="{} {}".format(labels[i], milestone_label),
                line=dict(color=dcolors["milestone"], width=1.5, dash=line_dash),
            ))

    title = "{} — {}".format(ddef["title"], " vs ".join(labels))
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

    if mirror_yaxis:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], yaxis="y2",
            showlegend=False, hoverinfo="skip",
        ))
        fig.update_layout(
            yaxis2=dict(
                title="# Clusters",
                overlaying="y",
                side="right",
                matches="y",
                showgrid=False,
            ),
        )
        if not is_combined:
            fig.update_layout(margin=dict(l=70, r=70, t=80, b=75))

    fig.write_image(output_path)
    logger.info("Wrote: {}".format(output_path))
    return True


def generate_graph(metric, pa_dirs, labels, output_path, width, height,
                   all_phases=None, mirror_yaxis=False,
                   solid_lines=False, shading_idx=0, trim_idx=None):
    gdef = GRAPH_DEFS[metric]
    n = len(pa_dirs)

    csv_paths = [os.path.join(d, gdef["csv"]) for d in pa_dirs]
    for path in csv_paths:
        if not os.path.isfile(path):
            logger.warning("CSV not found, skipping {}: {}".format(metric, path))
            return False

    dfs = []
    t0s = []
    all_series = []
    for path in csv_paths:
        df, t0 = to_elapsed_minutes(read_csv(path))
        series = get_series(df, gdef["agg"])
        scale = gdef.get("scale")
        if scale:
            series = series * scale
        dfs.append(df)
        t0s.append(t0)
        all_series.append(series)

    fig = go.Figure()

    all_phases_elapsed = []
    if all_phases:
        for i in range(n):
            if all_phases[i]:
                all_phases_elapsed.append(phases_to_elapsed(all_phases[i], t0s[i]))
            else:
                all_phases_elapsed.append([])
        add_phase_annotations(fig, all_phases_elapsed, labels, shading_idx=shading_idx)

    x_range = None
    if trim_idx is not None and all_phases_elapsed and all_phases_elapsed[trim_idx]:
        phases = all_phases_elapsed[trim_idx]
        x_range = [min(s for _, _, s, _ in phases), max(e for _, _, _, e in phases)]

    for i in range(n):
        color = RESULT_COLORS[i % len(RESULT_COLORS)]
        line_dash = "solid" if solid_lines or i == 0 else RESULT_DASHES[i % len(RESULT_DASHES)]
        fig.add_trace(go.Scatter(
            x=dfs[i]["minutes"], y=all_series[i], mode="lines", name=labels[i],
            line=dict(color=color, width=1.5, dash=line_dash),
        ))

    if "hline" in gdef:
        fig.add_hline(
            y=gdef["hline"], line_dash="dash", line_color="#dc2626", line_width=1.5,
            annotation_text=gdef["hline_label"], annotation_position="top left",
            annotation_font_color="#dc2626", annotation_font_size=11,
        )

    title = "{} — {}".format(gdef["title"], " vs ".join(labels))
    layout = dict(
        title=title,
        yaxis_title=gdef["yaxis"],
        width=width,
        height=height,
        **LAYOUT_DEFAULTS,
    )
    if x_range:
        layout["xaxis"] = dict(**LAYOUT_DEFAULTS["xaxis"], range=x_range)
    fig.update_layout(**layout)

    if mirror_yaxis:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], yaxis="y2",
            showlegend=False, hoverinfo="skip",
        ))
        fig.update_layout(
            yaxis2=dict(
                title=gdef["yaxis"],
                overlaying="y",
                side="right",
                matches="y",
                showgrid=False,
            ),
            margin=dict(l=70, r=70, t=80, b=75),
        )

    if gdef.get("memory"):
        max_val = max(s.max() for s in all_series)
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
        description="Generate overlay comparison graphs from two or more test results",
        prog="graph-acm-compare.py",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("result_dirs", type=str, nargs="+",
        help="Result directories to compare (two or more)")
    parser.add_argument("--labels", type=str, nargs="+",
        help="Display labels for each result (must match number of result dirs)")
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
    parser.add_argument("--mirror-yaxis", action="store_true", default=False,
        help="Show y-axis labels on both left and right sides")
    parser.add_argument("--solid-lines", action="store_true", default=False,
        help="Use solid lines for all series instead of varied dash patterns")
    parser.add_argument("--shading-index", type=int, default=0,
        help="Which result (0-based) provides the full-height phase shading")
    parser.add_argument("--trim-index", type=int, default=None,
        help="Trim x-axis using this result's phases (0-based)")

    cliargs = parser.parse_args()

    if len(cliargs.result_dirs) < 2:
        logger.error("At least two result directories are required")
        sys.exit(1)

    n = len(cliargs.result_dirs)

    if cliargs.labels:
        if len(cliargs.labels) != n:
            logger.error("Number of labels ({}) must match number of result directories ({})".format(
                len(cliargs.labels), n))
            sys.exit(1)
        labels = cliargs.labels
    else:
        labels = ["Result {}".format(chr(65 + i)) for i in range(n)]

    shading_idx = cliargs.shading_index
    if shading_idx < 0 or shading_idx >= n:
        logger.error("--shading-index {} is out of range (0 to {})".format(shading_idx, n - 1))
        sys.exit(1)

    trim_idx = cliargs.trim_index
    if trim_idx is not None and (trim_idx < 0 or trim_idx >= n):
        logger.error("--trim-index {} is out of range (0 to {})".format(trim_idx, n - 1))
        sys.exit(1)

    for d in cliargs.result_dirs:
        if not os.path.isdir(d):
            logger.error("Directory not found: {}".format(d))
            sys.exit(1)

    pa_dirs = []
    for d in cliargs.result_dirs:
        pa = find_deploy_pa(d)
        if not pa:
            logger.error("No deploy-pa / acm-telco-load-hub directory found in: {}".format(d))
            sys.exit(1)
        pa_dirs.append(pa)

    for i, pa in enumerate(pa_dirs):
        logger.info("Result {} ({}) analysis dir: {}".format(chr(65 + i), labels[i], pa))

    all_phases = []
    for i, d in enumerate(cliargs.result_dirs):
        phases = parse_phases(os.path.join(d, "report.txt"))
        all_phases.append(phases)
        if phases:
            logger.info("Parsed {} phases from result {}".format(len(phases), chr(65 + i)))

    os.makedirs(cliargs.output_dir, exist_ok=True)

    generated = 0
    for metric in cliargs.metrics:
        output_path = os.path.join(cliargs.output_dir, "{}-{}.png".format(cliargs.prefix, metric))
        try:
            if generate_graph(metric, pa_dirs, labels, output_path, cliargs.width,
                              cliargs.height, all_phases=all_phases,
                              mirror_yaxis=cliargs.mirror_yaxis,
                              solid_lines=cliargs.solid_lines,
                              shading_idx=shading_idx,
                              trim_idx=trim_idx):
                generated += 1
        except Exception:
            logger.exception("Failed to generate graph for metric: {}".format(metric))

    deploy_generated = 0
    for dmetric in DEPLOY_DEFS:
        output_path = os.path.join(cliargs.output_dir, "{}-{}.png".format(cliargs.prefix, dmetric))
        try:
            if generate_deploy_graph(dmetric, cliargs.result_dirs, labels,
                                     output_path, cliargs.width, cliargs.height,
                                     all_phases=all_phases,
                                     mirror_yaxis=cliargs.mirror_yaxis,
                                     solid_lines=cliargs.solid_lines,
                                     shading_idx=shading_idx,
                                     trim_idx=trim_idx):
                deploy_generated += 1
        except Exception:
            logger.exception("Failed to generate deploy graph: {}".format(dmetric))

    elapsed = time.time() - start_time
    total = generated + deploy_generated
    logger.info("Generated {} graphs ({} resource, {} deploy) in {:.1f}s".format(
        total, generated, deploy_generated, elapsed))


if __name__ == "__main__":
    main()
