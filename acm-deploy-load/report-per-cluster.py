#!/usr/bin/env python3
"""ZTP DU profile installation times - reports per cluster

Usage:
    report-per-cluster.py <day1.csv> <clustergroupupgrades.csv> [options]

Options:
    -h --help                       Show this help screen
    -p --profile=profile            Profile to use [default: combined]
    --no-report                     Skip text report
    -g --graph                      Create interactive graph
    -w --writegraph=filename        Write graph to file
    -d --debug                      Debug
"""

import datetime
from itertools import chain
from prettytable import PrettyTable
import pandas as pd
from docopt import docopt

# # Breakdown of different installation stages

# # Checkpoints
# ## day1
# 1. ACI created
# 2. AI cluster registration
# 3. BMH provision starts
# 4. AI host registration
# 5. BMH provision ends (host is rebooted into disk)
# 6. AI installed
# 7. ACI installed
# 8. Cluster becomes managed in ACM

# ## day2
# 9. CGU created
# 10. Policy application started
# 11. Policy application completed

# # Individual stages
# A.   1-2 - init to cluster registration in AI
# B.   2-3 - cluster registration to BMH provision starts
# C.   3-4 - BMH provision starts until host registration (Assisted Installer)
# D.   4-5 - From host registration till host reboots into disk ( day1 installation phase 1)
# E.   5-6 - Openshift installation and finalizing phase (day1 installation phase 2)
# F.   6-7 - Time for ACI to acknowledge installation
# G.   7-8 - Time for cluster to become managed in ACM
# H.   8-9 - Time since ACI acknowledges until CGU is created
# I.  9-10 - Delay since CGU creation until policy starts being applied
# J. 10-11 - Policies being applied

# # Grouped stages
# A-F - Total day1 installation time
# C-E - day1 installation time (only cluster installing)
# F-H - gap between day1 ends and day2 starts
# F-I - gap between day1 ends and day2 actually starts being applied
# H-J - Total day2 installation time
# A-J - Total installation time

stage_definitions = {
    "stage_a": "DAY 1 - Since ACI creation until cluster registration",
    "stage_b": "DAY 1 - Since Cluster is registered until BMH starts provision",
    "stage_c": "DAY 1 - Since BMH starts provision until Host is registered",
    "stage_d": "DAY 1 - Installation time since HOST is discovered until first reboot",
    "stage_e": "DAY 1 - Installation time since HOST is rebooted into disk",
    "stage_f": "DAY 1 - Since AI sets as installed until ACI sets as installed",
    "stage_g": "Since ACI sets as installed until cluster becomes Managed",
    "stage_h": "DAY 2 - Time since cluster is managed until CGU is created",
    "stage_i": "DAY 2 - Since CGU is created until CGU starts being applied",
    "stage_j": "DAY 2 - Since CGU starts being applied until CGU is completed",
    "stage_ac_aci_creation_to_host_reg": "DAY 1 - Total time until host is registered",
    "stage_af_total_day1": "DAY 1 - TOTAL day 1 installation time",
    "stage_aj_total_time_day1_and_day2": "DAY 1 and 2 - Total installation time",
    "stage_bc_cluster_reg_to_host_reg": "DAY 1 - Since cluster is registered until host is registered",
    "stage_be_ai_duration": "DAY 1 - Installation time since CLUSTER is registered in Assisted Installer",
    "stage_ce_day1_only_installation": "DAY 1 - installation time since BMH starts provision",
    "stage_de_ai_duration_since_host_reg": "DAY 1 - Installation time since HOST is registered in Assisted Installer",
    "stage_fh_day1_to_day2_start_gap": "Gap between day1 ends and day2 starts",
    "stage_fi_day1_to_day2_starts_applying": "DAY 2 - Gap between day1 ends and profiles start being applied",
    "stage_gh_since_aci_completion_until_cgu_creation": "Since ACI is completed until CGU is created",
    "stage_hj_total_day2": "DAY 2 - Total time after day1 finishes",
    "stage_ij_policies_duration_since_cgu_creation": "DAY 2 - Total day2 time",
}

reports = {
    "day1": [
        [
            "stage_b",
            "stage_c",
            "stage_bc_cluster_reg_to_host_reg",
        ],
        [
            "stage_be_ai_duration",
            "stage_de_ai_duration_since_host_reg",
            "stage_af_total_day1",
        ],
    ],
    "day2": [
        [
            "stage_af_total_day1",
            "stage_aj_total_time_day1_and_day2",
        ],
        [
            "stage_i",
            "stage_j",
        ],
    ],
    "combined": [
        [
            "stage_b",
            "stage_c",
            "stage_ac_aci_creation_to_host_reg",
        ],
        [
            "stage_be_ai_duration",
            "stage_de_ai_duration_since_host_reg",
            "stage_af_total_day1",
        ],
        [
            "stage_i",
            "stage_j",
            "stage_aj_total_time_day1_and_day2",
        ],
    ],
    "debug": [
        [
            "stage_b",
            "stage_c",
            "stage_ac_aci_creation_to_host_reg",
        ],
        [
            # Remove bmh_provision_end checkpoint
            # "stage_d",
            # "stage_e",
            "stage_de_ai_duration_since_host_reg",
        ],
        [
            "stage_gh_since_aci_completion_until_cgu_creation",
            "stage_i",
            "stage_j",
        ],
        [
            "stage_af_total_day1",
            "stage_j",
            "stage_aj_total_time_day1_and_day2",
        ],
    ],
    "all_stages": [
        [
            "stage_a",
            "stage_b",
            "stage_c",
        ],
        [
            # Remove bmh_provision_end checkpoint
            # "stage_d",
            # "stage_e",
            "stage_de_ai_duration_since_host_reg",
            "stage_f",
        ],
        [
            "stage_g",
            "stage_h",
            "stage_i",
        ],
        [
            "stage_j",
            "stage_af_total_day1",
            "stage_aj_total_time_day1_and_day2",
        ],
    ],
}


def normalize_date(date):
    return date.replace("T", " ").split(".")[0].split("Z")[0]


def date_to_timestamp(date):
    return datetime.datetime.strptime(
        normalize_date(date), "%Y-%m-%d %H:%M:%S"
    ).timestamp()


def combine_and_extend_dataframes(day1_df, cgu_df):
    cgu_df = cgu_df[cgu_df["status"] == "Completed"]

    d = []
    # day1
    # name, cluster_name, aci_creation, aci_installed, assisted_cluster_registration, assisted_host_registration, assisted_installed, bmh_provision_start, bmh_provision_end
    # cgu
    # name,status,creationTimestamp,precacheCompleted,precache_duration,startedAt,completedAt,duration
    for index, day1_row in day1_df.iterrows():
        name = day1_row["name"]
        cluster_name = day1_row["cluster_name"]

        # If cluster is not in status "Completed", skip the row
        if cluster_name not in cgu_df["name"].values:
            continue

        cgu_row = cgu_df[cgu_df["name"] == cluster_name].iloc[0].to_dict()

        # Checkpoints
        day1_01_aci_created = normalize_date(day1_row["aci_creation"])
        day1_02_ai_cluster_reg = normalize_date(
            day1_row["assisted_cluster_registration"]
        )
        day1_03_bmh_provision_start = normalize_date(day1_row["bmh_provision_start"])
        day1_04_ai_host_reg = normalize_date(day1_row["assisted_host_registration"])
        # Remove bmh_provision_end checkpoint
        # day1_05_bmh_provision_end = normalize_date(day1_row["bmh_provision_end"])
        day1_06_ai_installed = normalize_date(day1_row["assisted_installed"])
        day1_07_aci_installed = normalize_date(day1_row["aci_installed"])
        day1_08_aci_managed = normalize_date(day1_row["managedcluster_imported"])

        day2_09_cgu_created = normalize_date(cgu_row["creationTimestamp"])
        day2_10_cgu_started = normalize_date(cgu_row["startedAt"])
        day2_11_cgu_completed = normalize_date(cgu_row["completedAt"])

        # Dates to timestamps
        day1_01_aci_created_ts = date_to_timestamp(day1_01_aci_created)
        day1_02_ai_cluster_reg_ts = date_to_timestamp(day1_02_ai_cluster_reg)
        day1_03_bmh_provision_start_ts = date_to_timestamp(day1_03_bmh_provision_start)
        day1_04_ai_host_reg_ts = date_to_timestamp(day1_04_ai_host_reg)
        # Remove bmh_provision_end checkpoint
        # day1_05_bmh_provision_end_ts = date_to_timestamp(day1_05_bmh_provision_end)
        day1_06_ai_installed_ts = date_to_timestamp(day1_06_ai_installed)
        day1_07_aci_installed_ts = date_to_timestamp(day1_07_aci_installed)
        day1_08_aci_managed_ts = date_to_timestamp(day1_08_aci_managed)

        day2_09_cgu_created_ts = date_to_timestamp(day2_09_cgu_created)
        day2_10_cgu_started_ts = date_to_timestamp(day2_10_cgu_started)
        day2_11_cgu_completed_ts = date_to_timestamp(day2_11_cgu_completed)

        # Individual stages
        stage_a = day1_02_ai_cluster_reg_ts - day1_01_aci_created_ts
        stage_b = day1_03_bmh_provision_start_ts - day1_02_ai_cluster_reg_ts
        stage_c = day1_04_ai_host_reg_ts - day1_03_bmh_provision_start_ts
        # Remove bmh_provision_end checkpoint
        # stage_d = day1_05_bmh_provision_end_ts - day1_04_ai_host_reg_ts
        # stage_e = day1_06_ai_installed_ts - day1_05_bmh_provision_end_ts
        stage_de = day1_06_ai_installed_ts - day1_04_ai_host_reg_ts
        stage_f = day1_07_aci_installed_ts - day1_06_ai_installed_ts
        stage_g = day1_08_aci_managed_ts - day1_07_aci_installed_ts
        stage_h = day2_09_cgu_created_ts - day1_08_aci_managed_ts
        stage_i = day2_10_cgu_started_ts - day2_09_cgu_created_ts
        stage_j = day2_11_cgu_completed_ts - day2_10_cgu_started_ts

        # Grouped stages
        stage_ac_aci_creation_to_host_reg = stage_a + stage_b + stage_c

        stage_af_total_day1 = stage_a + stage_b + stage_c + stage_de + stage_f

        stage_aj_total_time_day1_and_day2 = (
            stage_a
            + stage_b
            + stage_c
            + stage_de
            + stage_f
            + stage_g
            + stage_h
            + stage_i
            + stage_j
        )

        stage_be_ai_duration = stage_b + stage_c + stage_de
        stage_bc_cluster_reg_to_host_reg = stage_b + stage_c
        stage_ce_day1_only_installation = stage_c + stage_de
        stage_de_ai_duration_since_host_reg = stage_de
        stage_fh_day1_to_day2_start_gap = stage_f + stage_g + stage_h
        stage_fi_day1_to_day2_starts_applying = stage_f + stage_g + stage_h + stage_i
        stage_gh_since_aci_completion_until_cgu_creation = stage_g + stage_h
        stage_hj_total_day2 = stage_h + stage_i + stage_j
        stage_ij_policies_duration_since_cgu_creation = stage_i + stage_j

        d.append(
            {
                "name": name,
                "day1_01_aci_created": day1_01_aci_created,
                "day1_02_ai_cluster_reg": day1_02_ai_cluster_reg,
                "day1_03_bmh_provision_start": day1_03_bmh_provision_start,
                "day1_04_ai_host_reg": day1_04_ai_host_reg,
                # Remove bmh_provision_end checkpoint
                # "day1_05_bmh_provision_end": day1_05_bmh_provision_end,
                "day1_06_ai_installed": day1_06_ai_installed,
                "day1_07_aci_installed": day1_07_aci_installed,
                "day1_08_aci_managed": day1_08_aci_managed,
                "day1_01_aci_created_ts": day1_01_aci_created_ts,
                "day1_02_ai_cluster_reg_ts": day1_02_ai_cluster_reg_ts,
                "day1_03_bmh_provision_start_ts": day1_03_bmh_provision_start_ts,
                "day1_04_ai_host_reg_ts": day1_04_ai_host_reg_ts,
                # Remove bmh_provision_end checkpoint
                # "day1_05_bmh_provision_end_ts": day1_05_bmh_provision_end_ts,
                "day1_06_ai_installed_ts": day1_06_ai_installed_ts,
                "day1_07_aci_installed_ts": day1_07_aci_installed_ts,
                "day1_08_aci_managed_ts": day1_08_aci_managed_ts,
                "day2_09_cgu_created": day2_09_cgu_created,
                "day2_10_cgu_started": day2_10_cgu_started,
                "day2_11_cgu_completed": day2_11_cgu_completed,
                "day2_09_cgu_created_ts": day2_09_cgu_created_ts,
                "day2_10_cgu_started_ts": day2_10_cgu_started_ts,
                "day2_11_cgu_completed_ts": day2_11_cgu_completed_ts,
                "stage_a": stage_a,
                "stage_b": stage_b,
                "stage_c": stage_c,
                # Remove bmh_provision_end checkpoint
                # "stage_d": stage_d,
                # "stage_e": stage_e,
                "stage_de": stage_de,
                "stage_f": stage_f,
                "stage_g": stage_g,
                "stage_h": stage_h,
                "stage_i": stage_i,
                "stage_j": stage_j,
                "stage_ac_aci_creation_to_host_reg": stage_ac_aci_creation_to_host_reg,
                "stage_af_total_day1": stage_af_total_day1,
                "stage_aj_total_time_day1_and_day2": stage_aj_total_time_day1_and_day2,
                "stage_bc_cluster_reg_to_host_reg": stage_bc_cluster_reg_to_host_reg,
                "stage_be_ai_duration": stage_be_ai_duration,
                "stage_ce_day1_only_installation": stage_ce_day1_only_installation,
                "stage_de_ai_duration_since_host_reg": stage_de_ai_duration_since_host_reg,
                "stage_fh_day1_to_day2_start_gap": stage_fh_day1_to_day2_start_gap,
                "stage_fi_day1_to_day2_starts_applying": stage_fi_day1_to_day2_starts_applying,
                "stage_gh_since_aci_completion_until_cgu_creation": stage_gh_since_aci_completion_until_cgu_creation,
                "stage_hj_total_day2": stage_hj_total_day2,
                "stage_ij_policies_duration_since_cgu_creation": stage_ij_policies_duration_since_cgu_creation,
            }
        )

    return pd.DataFrame(d).sort_values(by="day1_01_aci_created_ts", ignore_index=True)


def seconds_to_human(seconds):
    return str(datetime.timedelta(seconds=seconds)).split(".")[0]


def gen_stat(name, stat):
    return [
        name,
        seconds_to_human(stat.min()),
        seconds_to_human(stat.max()),
        seconds_to_human(stat.quantile(0.5)),
        seconds_to_human(stat.quantile(0.75)),
        seconds_to_human(stat.quantile(0.9)),
        seconds_to_human(stat.quantile(0.99)),
    ]


def print_stats(stats, df):
    print(f"Number of clusters: {len(df)}")
    tab = PrettyTable(
        [
            "",
            "Min",
            "Max",
            "50 percentile",
            "75 percentile",
            "90 percentile",
            "99 percentile",
        ]
    )

    tab.align[""] = "l"
    stats = list(chain(*stats))

    for stat in stats:
        tab.add_row(gen_stat(stage_definitions[stat], df[stat]))
    print(tab)


def graph_stats(stats, df, show, filename):
    import matplotlib.pyplot as plt

    dot_size = 1
    xlabel_text = "Cluster"
    ylabel_text = "Minutes"
    divider = 60
    same_range = False

    nrows = len(stats)
    ncols = max([len(n) for n in stats])

    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(20, 10))

    for row_index, row in enumerate(stats):
        for col_index, column in enumerate(row):
            col_name = column
            col_title = stage_definitions[column]
            axes[row_index, col_index].scatter(
                df.index, df[col_name] / divider, s=dot_size
            )
            axes[row_index, col_index].set_title(col_title)

    for ax in axes.flat:
        # ax.grid(True)
        ax.set_xlabel(xlabel_text)
        ax.set_ylabel(ylabel_text)

    if same_range:
        ranges = [ax.get_ylim() for ax in axes.flat]
        range = (min([t[0] for t in ranges]), max([t[1] for t in ranges]))
        plt.setp(axes, range)

    plt.tight_layout()

    if filename is not None:
        plt.savefig(filename)

    if show:
        plt.show()


if __name__ == "__main__":
    args = docopt(__doc__)
    day1_df = pd.read_csv(args["<day1.csv>"])
    cgu_df = pd.read_csv(args["<clustergroupupgrades.csv>"])
    df = combine_and_extend_dataframes(day1_df, cgu_df)
    report = reports[args["--profile"]]

    if args["--debug"]:
        print(
            df[
                [
                    "name",
                    "day1_08_aci_managed",
                    "day2_09_cgu_created",
                    "stage_h",
                ]
            ].to_csv()
        )

    if not args["--no-report"]:
        print_stats(report, df)

    if args["--graph"] or args["--writegraph"]:
        graph_stats(report, df, args["--graph"], args["--writegraph"])
