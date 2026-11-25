#!/usr/bin/env python3
#
# Query and graph prometheus data in an OpenShift Cluster
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

# import prometheus_api_client
import argparse
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from utils.common_ocp import get_base_ocp_namespaces
from utils.common_ocp import get_ocp_node_list
from utils.common_ocp import get_ocp_namespace_list
from utils.common_ocp import get_ocp_version
from utils.common_ocp import get_prometheus_token
from utils.common_ocp import get_thanos_querier_route
from utils.talm import detect_talm_csv
import json
import logging
import os
import pandas as pd
import plotly.express as px
import urllib3
import requests
import sys
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# TODO:
# * Node Level networking instead of container level summed
# * Host OS Components (Kubelet and Crio)
# * Gather cluster data to make decisions for queries:
#   * Node Count (Is it an SNO, Compact or standard)

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acs-prometheus-analysis")
logging.Formatter.converter = time.gmtime

# Metric families exported by Central in central-snippet.prom that do not
# already have a purpose-built query below. Keep this list aligned with the
# captured Central metrics when that reference file is refreshed.
CENTRAL_SNIPPET_EXTRA_METRICS = """
file_extraction_count
file_extraction_inaccessible_count
file_extraction_match_count
go_gc_duration_seconds
go_gc_gogc_percent
go_gc_gomemlimit_bytes
go_goroutines
go_info
go_memstats_alloc_bytes
go_memstats_alloc_bytes_total
go_memstats_buck_hash_sys_bytes
go_memstats_frees_total
go_memstats_gc_sys_bytes
go_memstats_heap_alloc_bytes
go_memstats_heap_idle_bytes
go_memstats_heap_inuse_bytes
go_memstats_heap_objects
go_memstats_heap_released_bytes
go_memstats_heap_sys_bytes
go_memstats_last_gc_time_seconds
go_memstats_mallocs_total
go_memstats_mcache_inuse_bytes
go_memstats_mcache_sys_bytes
go_memstats_mspan_inuse_bytes
go_memstats_mspan_sys_bytes
go_memstats_next_gc_bytes
go_memstats_other_sys_bytes
go_memstats_stack_inuse_bytes
go_memstats_stack_sys_bytes
go_memstats_sys_bytes
go_sched_gomaxprocs_threads
go_threads
grpc_server_msg_received_total
grpc_server_msg_sent_total
grpc_server_started_total
http_incoming_in_flight_requests
http_incoming_request_size_histogram_bytes
http_incoming_response_size_histogram_bytes
process_cpu_seconds_total
process_max_fds
process_network_receive_bytes_total
process_network_transmit_bytes_total
process_open_fds
process_resident_memory_bytes
process_start_time_seconds
process_virtual_memory_bytes
process_virtual_memory_max_bytes
rox_base_image_watcher_metadata_fetch_errors
rox_base_image_watcher_poll_duration_seconds
rox_base_image_watcher_repositories_total
rox_base_image_watcher_scan_duration_seconds
rox_base_image_watcher_tags_listed
rox_central_administration_events_queue_size_total
rox_central_alert_and_notify_incoming_count
rox_central_background_migration_complete
rox_central_background_migration_seq_num
rox_central_cache_bypass_total
rox_central_cache_entries
rox_central_cache_hit_total
rox_central_cache_miss_total
rox_central_cache_op_duration
rox_central_cache_population_duration_seconds
rox_central_cluster_metrics_cpu_capacity
rox_central_cluster_metrics_node_count
rox_central_complianceoperator_num_scans_running_in_parallel
rox_central_complianceoperator_scan_watchers_active_time_minutes
rox_central_complianceoperator_scan_watchers_current
rox_central_complianceoperator_scan_watchers_finish_type_total
rox_central_datastore_function_duration
rox_central_deduping_hash_count
rox_central_deduping_hash_size
rox_central_deployment_enhancement_duration_ms
rox_central_deployment_risk_semaphore_holding_size
rox_central_deployment_risk_semaphore_queue_size
rox_central_deployment_risk_semaphore_timeouts_total
rox_central_function_segment_duration
rox_central_graphql_op_duration
rox_central_graphql_query_duration
rox_central_grpc_last_message_size_received_bytes
rox_central_grpc_last_message_size_sent_bytes
rox_central_grpc_max_message_size_sent_bytes
rox_central_grpc_message_size_sent_bytes
rox_central_imageV2_upsert_deduper
rox_central_image_vuln_retrieval_duration
rox_central_info
rox_central_internal_token_generation_duration_seconds
rox_central_internal_token_generation_total
rox_central_k8s_event_processing_duration
rox_central_key_bundle_updater_download_duration_seconds
rox_central_key_bundle_updater_downloads_total
rox_central_key_bundle_updater_last_success_timestamp
rox_central_key_bundle_watcher_file_errors_total
rox_central_key_bundle_watcher_keys_count
rox_central_key_bundle_watcher_last_success_timestamp
rox_central_key_bundle_watcher_upserts_total
rox_central_merge_many_alerts_duration_ms
rox_central_merge_many_alerts_previous_count
rox_central_metadata_cache_hits
rox_central_metadata_cache_misses
rox_central_node_scan_num_components
rox_central_number_of_external_policies_current
rox_central_orphaned_plop_total
rox_central_postgres_acquire_conn_op_duration
rox_central_postgres_available_size_bytes
rox_central_postgres_connected
rox_central_postgres_dead_tuples
rox_central_postgres_live_tuples
rox_central_postgres_maximum_db_connections
rox_central_postgres_query_errors
rox_central_postgres_table_data_bytes
rox_central_postgres_table_index_bytes
rox_central_postgres_table_size
rox_central_postgres_table_toast_bytes
rox_central_postgres_table_total_bytes
rox_central_postgres_total_size_bytes
rox_central_process_cpu_nr_periods
rox_central_process_cpu_nr_throttled
rox_central_process_cpu_throttled_time
rox_central_process_filter
rox_central_process_indicators_not_persisted
rox_central_process_indicators_removed
rox_central_process_indicators_removed_total
rox_central_process_not_persisted_args_size
rox_central_process_not_persisted_lineage_size
rox_central_process_pruning_cache_hits
rox_central_process_pruning_cache_misses
rox_central_process_queue_length
rox_central_process_upserted_args_size
rox_central_process_upserted_args_size_total
rox_central_process_upserted_count
rox_central_process_upserted_lineage_size
rox_central_process_upserted_lineage_size_total
rox_central_prune_duration
rox_central_rate_limiter_active_clients
rox_central_rate_limiter_per_client_bucket_max_tokens
rox_central_rate_limiter_per_client_bucket_refill_rate_per_second
rox_central_rate_limiter_requests_total
rox_central_registry_client_request_duration_seconds
rox_central_registry_client_requests_total
rox_central_reprocessor_duration_seconds
rox_central_resource_processed_count
rox_central_risk_processing_duration
rox_central_secured_vcpus
rox_central_sensor_connected
rox_central_sensor_event_deduper
rox_central_sensor_event_duration
rox_central_sensor_event_queue
rox_central_signature_verification_reprocessor_duration_seconds
rox_central_total_external_policies_count
rox_central_total_network_endpoints_received_counter
rox_central_total_network_flows_central_received_counter
rox_central_uptime_seconds
rox_endpoint_tls_handshakes_with_negotiated_alp_total
rox_image_scan_semaphore_holding_size
rox_image_scan_semaphore_limit
rox_image_scan_semaphore_queue_size
rox_tls_check_count
rox_tls_check_duration_seconds
tar_extracted_contents_bytes_per_layer
tar_file_count_per_layer
tar_matched_file_count_per_layer
""".split()

# Metric families exported by Scanner V4 Indexer in
# scanner-v4-indexer-snippet.prom that do not have purpose-built queries.
INDEXER_SNIPPET_EXTRA_METRICS = """
claircore_indexer_deletemanifests_duration_seconds
claircore_indexer_deletemanifests_total
claircore_indexer_distributionbylayer_duration_seconds
claircore_indexer_distributionbylayer_total
claircore_indexer_filesbylayer_duration_seconds
claircore_indexer_filesbylayer_total
claircore_indexer_indexdistributions_duration_seconds
claircore_indexer_indexdistributions_total
claircore_indexer_indexfiles_duration_seconds
claircore_indexer_indexfiles_total
claircore_indexer_indexreport_duration_seconds
claircore_indexer_indexreport_total
claircore_indexer_indexrepositories_duration_seconds
claircore_indexer_indexrepositories_total
claircore_indexer_layerscanned_duration_seconds
claircore_indexer_manifestscanned_duration_seconds
claircore_indexer_manifestscanned_total
claircore_indexer_packagesbylayer_duration_seconds
claircore_indexer_packagesbylayer_total
claircore_indexer_persistmanifest_duration_seconds
claircore_indexer_persistmanifest_total
claircore_indexer_registerscanners_duration_seconds
claircore_indexer_registerscanners_total
claircore_indexer_repositoriesbylayer_duration_seconds
claircore_indexer_repositoriesbylayer_total
claircore_indexer_setindexedfinished_total
claircore_indexer_setindexfinished_duration_seconds
claircore_indexer_setindexreport_duration_seconds
claircore_indexer_setindexreport_total
claircore_indexer_setlayerscanned_duration_seconds
claircore_indexer_setlayerscanned_total
file_extraction_count
file_extraction_inaccessible_count
file_extraction_match_count
go_gc_duration_seconds
go_gc_gogc_percent
go_gc_gomemlimit_bytes
go_goroutines
go_info
go_memstats_alloc_bytes
go_memstats_alloc_bytes_total
go_memstats_buck_hash_sys_bytes
go_memstats_frees_total
go_memstats_gc_sys_bytes
go_memstats_heap_alloc_bytes
go_memstats_heap_idle_bytes
go_memstats_heap_inuse_bytes
go_memstats_heap_objects
go_memstats_heap_released_bytes
go_memstats_heap_sys_bytes
go_memstats_last_gc_time_seconds
go_memstats_mallocs_total
go_memstats_mcache_inuse_bytes
go_memstats_mcache_sys_bytes
go_memstats_mspan_inuse_bytes
go_memstats_mspan_sys_bytes
go_memstats_next_gc_bytes
go_memstats_other_sys_bytes
go_memstats_stack_inuse_bytes
go_memstats_stack_sys_bytes
go_memstats_sys_bytes
go_sched_gomaxprocs_threads
go_threads
grpc_server_msg_received_total
grpc_server_msg_sent_total
grpc_server_started_total
http_incoming_in_flight_requests
http_incoming_request_duration_histogram_seconds
http_incoming_request_size_histogram_bytes
http_incoming_requests_total
http_incoming_response_size_histogram_bytes
pgxpool_acquire_duration_seconds_total
pgxpool_acquired_conns
pgxpool_canceled_acquire_count
pgxpool_constructing_conns
pgxpool_empty_acquire
pgxpool_max_conns
process_cpu_seconds_total
process_max_fds
process_network_receive_bytes_total
process_network_transmit_bytes_total
process_open_fds
process_resident_memory_bytes
process_start_time_seconds
process_virtual_memory_bytes
process_virtual_memory_max_bytes
rox_scanner_process_cpu_nr_periods
rox_scanner_process_cpu_nr_throttled
rox_scanner_process_cpu_throttled_time
rox_scanner_uptime_seconds
tar_extracted_contents_bytes_per_layer
tar_file_count_per_layer
tar_matched_file_count_per_layer
""".split()

# Metric families exported by Scanner V4 Matcher in
# scanner-v4-matcher-snippet.prom that do not have purpose-built queries.
MATCHER_SNIPPET_EXTRA_METRICS = """
claircore_vulnstore_gc_duration_seconds
claircore_vulnstore_getupdateoperations_duration_seconds
claircore_vulnstore_getupdateoperations_total
claircore_vulnstore_updateenrichments_duration_seconds
claircore_vulnstore_updateenrichments_total
file_extraction_count
file_extraction_inaccessible_count
file_extraction_match_count
go_gc_duration_seconds
go_gc_gogc_percent
go_gc_gomemlimit_bytes
go_goroutines
go_info
go_memstats_alloc_bytes
go_memstats_alloc_bytes_total
go_memstats_buck_hash_sys_bytes
go_memstats_frees_total
go_memstats_gc_sys_bytes
go_memstats_heap_alloc_bytes
go_memstats_heap_idle_bytes
go_memstats_heap_inuse_bytes
go_memstats_heap_objects
go_memstats_heap_released_bytes
go_memstats_heap_sys_bytes
go_memstats_last_gc_time_seconds
go_memstats_mallocs_total
go_memstats_mcache_inuse_bytes
go_memstats_mcache_sys_bytes
go_memstats_mspan_inuse_bytes
go_memstats_mspan_sys_bytes
go_memstats_next_gc_bytes
go_memstats_other_sys_bytes
go_memstats_stack_inuse_bytes
go_memstats_stack_sys_bytes
go_memstats_sys_bytes
go_sched_gomaxprocs_threads
go_threads
grpc_server_msg_received_total
grpc_server_msg_sent_total
grpc_server_started_total
http_incoming_in_flight_requests
http_incoming_request_duration_histogram_seconds
http_incoming_request_size_histogram_bytes
http_incoming_requests_total
http_incoming_response_size_histogram_bytes
pgxpool_acquire_duration_seconds_total
pgxpool_acquired_conns
pgxpool_canceled_acquire_count
pgxpool_constructing_conns
pgxpool_empty_acquire
pgxpool_max_conns
process_cpu_seconds_total
process_max_fds
process_network_receive_bytes_total
process_network_transmit_bytes_total
process_open_fds
process_resident_memory_bytes
process_start_time_seconds
process_virtual_memory_bytes
process_virtual_memory_max_bytes
rox_scanner_process_cpu_nr_periods
rox_scanner_process_cpu_nr_throttled
rox_scanner_process_cpu_throttled_time
rox_scanner_uptime_seconds
tar_extracted_contents_bytes_per_layer
tar_file_count_per_layer
tar_matched_file_count_per_layer
""".split()


def calculate_query_offset(end_ts):
  cur_utc_unix_time = time.mktime(datetime.now(tz=timezone.utc).timetuple())
  offset_minutes = (int(cur_utc_unix_time) - end_ts) / 60
  if offset_minutes < 1:
    offset_minutes = 0
  return offset_minutes


def metric_unit(metric):
  if metric.endswith("_bytes"):
    return "Bytes"
  if metric.endswith("_seconds") or metric.endswith("_duration"):
    return "Seconds"
  if metric.endswith("_ms"):
    return "Milliseconds"
  return "Count"


# ACS - Complete (stackrox or rhacs-operator namespace)
def acs_complete_queries(report_dir, route, token, end_ts, duration, w, h, nodes):
  sub_report_dir = os.path.join(report_dir, "acs-complete")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()

  # ACS namespace CPU/Memory/Network
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace=~'stackrox|rhacs-operator'})"
  query_thanos(route, q, "acs", token, end_ts, duration, sub_report_dir, "cpu-acs", "ACS CPU Cores Usage", "CPU", w, h, q_names)
  q = "sum(container_memory_working_set_bytes{cluster='',container!='',namespace=~'stackrox|rhacs-operator'})"
  query_thanos(route, q, "acs", token, end_ts, duration, sub_report_dir, "mem-acs", "ACS Memory Usage", "MEM", w, h, q_names)
  q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace=~'stackrox|rhacs-operator'}[5m]))"
  query_thanos(route, q, "acs", token, end_ts, duration, sub_report_dir, "net-rcv-acs", "ACS Network Receive Throughput", "NET", w, h, q_names)
  q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace=~'stackrox|rhacs-operator'}[5m]))"
  query_thanos(route, q, "acs", token, end_ts, duration, sub_report_dir, "net-xmt-acs", "ACS Network Transmit Throughput", "NET", w, h, q_names)

  # ACS pods
  q = "sum by (pod) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace=~'stackrox|rhacs-operator'})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "cpu-acs-pods", "ACS Pod CPU Cores Usage", "CPU", w, h, q_names)
  q = "sum by (pod) (container_memory_working_set_bytes{cluster='',container!='',namespace=~'stackrox|rhacs-operator'})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "mem-acs-pods", "ACS Pod Memory Usage", "MEM", w, h, q_names)

  # Separate read and write throughput graphs per node, with one series for
  # every ACS pod. The PromQL expressions convert filesystem byte rates to MB/s.
  for node in nodes:
    q = ("sum by (pod, node) (rate(container_fs_reads_bytes_total{cluster='',namespace=~'stackrox|rhacs-operator',node='" + node +
        "'}[5m])) / 1000000")
    query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir,
        "disk-read-tput-acs-pods-{}".format(node),
        "ACS Pod Disk Read Throughput on {}".format(node), "MB/s", w, h, q_names)
    q = ("sum by (pod, node) (rate(container_fs_writes_bytes_total{cluster='',namespace=~'stackrox|rhacs-operator',node='" + node +
        "'}[5m])) / 1000000")
    query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir,
        "disk-write-tput-acs-pods-{}".format(node),
        "ACS Pod Disk Write Throughput on {}".format(node), "MB/s", w, h, q_names)
  return q_names


# ACS Central - Central pod application metrics
def acs_central_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "acs-central")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()

  # Central pod CPU/Memory
  q = "sum by (pod) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace=~'stackrox|rhacs-operator',pod=~'central-.*'})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "cpu-acs-central", "ACS Central CPU Cores Usage", "CPU", w, h, q_names)
  q = "sum by (pod) (container_memory_working_set_bytes{cluster='',container!='',namespace=~'stackrox|rhacs-operator',pod=~'central-.*'})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "mem-acs-central", "ACS Central Memory Usage", "MEM", w, h, q_names)

  # Central alert processing metrics
  q = "rox_central_alert_and_notify_duration_ms"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "central-alert-duration", "ACS Central Alert Processing Duration", "Latency (ms)", w, h, q_names)
  q = "rox_central_alert_outcome_total"
  query_thanos(route, q, "outcome", token, end_ts, duration, sub_report_dir, "central-alert-outcomes", "ACS Central Alert Outcomes", "Count", w, h, q_names)

  # Central scan duration metrics
  q = "rox_central_scan_duration"
  query_thanos(route, q, "Scanner", token, end_ts, duration, sub_report_dir, "central-scan-duration", "ACS Central Image Scan Duration", "Latency (ms)", w, h, q_names)
  q = "rox_central_node_scan_duration"
  query_thanos(route, q, "Scanner", token, end_ts, duration, sub_report_dir, "central-node-scan-duration", "ACS Central Node Scan Duration", "Latency (ms)", w, h, q_names)

  # Central PostgreSQL metrics
  q = "rox_central_postgres_op_duration"
  query_thanos(route, q, "Operation", token, end_ts, duration, sub_report_dir, "central-postgres-op-duration", "ACS Central Postgres Operation Duration", "Latency (ms)", w, h, q_names)
  q = "rox_central_postgres_db_size_bytes"
  query_thanos(route, q, "database", token, end_ts, duration, sub_report_dir, "central-postgres-db-size", "ACS Central Postgres DB Size", "DISK_USAGE", w, h, q_names)
  q = "rox_central_postgres_total_connections"
  query_thanos(route, q, "state", token, end_ts, duration, sub_report_dir, "central-postgres-connections", "ACS Central Postgres Connections", "Count", w, h, q_names)

  # Central gRPC metrics
  q = "sum by (grpc_method) (rate(grpc_server_handling_seconds_sum{namespace=~'stackrox|rhacs-operator',pod=~'central-.*'}[5m]))"
  query_thanos(route, q, "grpc_method", token, end_ts, duration, sub_report_dir, "central-grpc-duration", "ACS Central gRPC Handling Duration", "Seconds", w, h, q_names)
  q = "sum by (grpc_code) (rate(grpc_server_handled_total{namespace=~'stackrox|rhacs-operator',pod=~'central-.*'}[5m]))"
  query_thanos(route, q, "grpc_code", token, end_ts, duration, sub_report_dir, "central-grpc-handled", "ACS Central gRPC Requests Rate", "Requests/s", w, h, q_names)

  # Central HTTP metrics
  q = "sum by (code) (rate(http_incoming_requests_total{namespace=~'stackrox|rhacs-operator',pod=~'central-.*'}[5m]))"
  query_thanos(route, q, "code", token, end_ts, duration, sub_report_dir, "central-http-requests", "ACS Central HTTP Requests Rate", "Requests/s", w, h, q_names)
  q = "http_incoming_request_duration_histogram_seconds{namespace=~'stackrox|rhacs-operator',pod=~'central-.*'}"
  query_thanos(route, q, "path", token, end_ts, duration, sub_report_dir, "central-http-duration", "ACS Central HTTP Request Duration", "Seconds", w, h, q_names)

  # Central resource metrics
  q = "rox_central_secured_clusters"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "central-secured-clusters", "ACS Secured Clusters", "Count", w, h, q_names)
  q = "rox_central_secured_nodes"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "central-secured-nodes", "ACS Secured Nodes", "Count", w, h, q_names)

  # Capture all remaining Central metric families in central-snippet.prom.
  # The target labels scope common Go, gRPC, HTTP, process, and tar metrics to
  # Central rather than similarly named Scanner metrics.
  for metric in CENTRAL_SNIPPET_EXTRA_METRICS:
    q = metric + "{namespace=~'stackrox|rhacs-operator',pod=~'central-.*'}"
    query_thanos(route, q, "__name__", token, end_ts, duration, sub_report_dir,
        "central-{}".format(metric), "ACS Central {}".format(metric),
        metric_unit(metric), w, h, q_names)

  return q_names


# ACS Scanner V4 Indexer - Image indexing metrics
def acs_scanner_indexer_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "acs-scanner-indexer")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()

  # Scanner Indexer pod CPU/Memory
  q = "sum by (pod) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace=~'stackrox|rhacs-operator',pod=~'scanner-v4-indexer-.*'})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "cpu-acs-scanner-indexer", "ACS Scanner Indexer CPU Cores Usage", "CPU", w, h, q_names)
  q = "sum by (pod) (container_memory_working_set_bytes{cluster='',container!='',namespace=~'stackrox|rhacs-operator',pod=~'scanner-v4-indexer-.*'})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "mem-acs-scanner-indexer", "ACS Scanner Indexer Memory Usage", "MEM", w, h, q_names)

  # Indexer operation metrics
  q = "claircore_indexer_scanned_manifests"
  query_thanos(route, q, "scanned_before", token, end_ts, duration, sub_report_dir, "indexer-scanned-manifests", "ACS Indexer Scanned Manifests", "Count", w, h, q_names)
  q = "rate(claircore_indexer_indexmanifest_total[5m])"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "indexer-manifest-rate", "ACS Indexer Manifest Indexing Rate", "Operations/s", w, h, q_names)
  q = "claircore_indexer_indexmanifest_duration_seconds"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "indexer-manifest-duration", "ACS Indexer Manifest Duration", "Seconds", w, h, q_names)

  # Indexer package/layer metrics
  q = "rate(claircore_indexer_indexpackage_total[5m])"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "indexer-package-rate", "ACS Indexer Package Indexing Rate", "Operations/s", w, h, q_names)
  q = "claircore_indexer_indexpackage_duration_seconds"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "indexer-package-duration", "ACS Indexer Package Duration", "Seconds", w, h, q_names)
  q = "rate(claircore_indexer_layerscanned_total[5m])"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "indexer-layer-scanned-rate", "ACS Indexer Layer Scanned Rate", "Operations/s", w, h, q_names)

  # Indexer PostgreSQL connection pool metrics
  q = "pgxpool_acquire_count{application_name='libindex'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "indexer-pg-acquire-count", "ACS Indexer Postgres Acquire Count", "Count", w, h, q_names)
  q = "pgxpool_idle_conns{application_name='libindex'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "indexer-pg-idle-conns", "ACS Indexer Postgres Idle Connections", "Count", w, h, q_names)
  q = "pgxpool_total_conns{application_name='libindex'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "indexer-pg-total-conns", "ACS Indexer Postgres Total Connections", "Count", w, h, q_names)

  # Indexer gRPC metrics
  q = "sum by (grpc_method) (rate(grpc_server_handling_seconds_sum{namespace=~'stackrox|rhacs-operator',pod=~'scanner-v4-indexer-.*'}[5m]))"
  query_thanos(route, q, "grpc_method", token, end_ts, duration, sub_report_dir, "indexer-grpc-duration", "ACS Indexer gRPC Handling Duration", "Seconds", w, h, q_names)
  q = "sum by (grpc_code) (rate(grpc_server_handled_total{namespace=~'stackrox|rhacs-operator',pod=~'scanner-v4-indexer-.*'}[5m]))"
  query_thanos(route, q, "grpc_code", token, end_ts, duration, sub_report_dir, "indexer-grpc-handled", "ACS Indexer gRPC Requests Rate", "Requests/s", w, h, q_names)

  # Capture all remaining Indexer metric families in
  # scanner-v4-indexer-snippet.prom. Target labels prevent common runtime,
  # gRPC, HTTP, process, and tar metrics from mixing with Matcher or Central.
  for metric in INDEXER_SNIPPET_EXTRA_METRICS:
    q = metric + "{namespace=~'stackrox|rhacs-operator',pod=~'scanner-v4-indexer-.*'}"
    query_thanos(route, q, "__name__", token, end_ts, duration, sub_report_dir,
        "indexer-{}".format(metric), "ACS Scanner Indexer {}".format(metric),
        metric_unit(metric), w, h, q_names)

  return q_names


# ACS Scanner V4 Matcher - Vulnerability matching metrics
def acs_scanner_matcher_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "acs-scanner-matcher")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()

  # Scanner Matcher pod CPU/Memory
  q = "sum by (pod) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace=~'stackrox|rhacs-operator',pod=~'scanner-v4-matcher-.*'})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "cpu-acs-scanner-matcher", "ACS Scanner Matcher CPU Cores Usage", "CPU", w, h, q_names)
  q = "sum by (pod) (container_memory_working_set_bytes{cluster='',container!='',namespace=~'stackrox|rhacs-operator',pod=~'scanner-v4-matcher-.*'})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "mem-acs-scanner-matcher", "ACS Scanner Matcher Memory Usage", "MEM", w, h, q_names)

  # Matcher vulnerability store metrics
  q = "rate(claircore_vulnstore_getvulnerabilities_total[5m])"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "matcher-getvuln-rate", "ACS Matcher Get Vulnerabilities Rate", "Operations/s", w, h, q_names)
  q = "claircore_vulnstore_getvulnerabilities_duration_seconds"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "matcher-getvuln-duration", "ACS Matcher Get Vulnerabilities Duration", "Seconds", w, h, q_names)
  q = "rate(claircore_vulnstore_getenrichments_total[5m])"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "matcher-getenrich-rate", "ACS Matcher Get Enrichments Rate", "Operations/s", w, h, q_names)
  q = "claircore_vulnstore_getenrichments_duration_seconds"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "matcher-getenrich-duration", "ACS Matcher Get Enrichments Duration", "Seconds", w, h, q_names)

  # Matcher update metrics
  q = "rate(claircore_vulnstore_updatevulnerabilities_total[5m])"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "matcher-updatevuln-rate", "ACS Matcher Update Vulnerabilities Rate", "Operations/s", w, h, q_names)
  q = "claircore_vulnstore_updatevulnerabilities_duration_seconds"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "matcher-updatevuln-duration", "ACS Matcher Update Vulnerabilities Duration", "Seconds", w, h, q_names)
  q = "rate(claircore_vulnstore_gc_total[5m])"
  query_thanos(route, q, "query", token, end_ts, duration, sub_report_dir, "matcher-gc-rate", "ACS Matcher GC Rate", "Operations/s", w, h, q_names)

  # Matcher PostgreSQL connection pool metrics
  q = "pgxpool_acquire_count{application_name='libvuln'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "matcher-pg-acquire-count", "ACS Matcher Postgres Acquire Count", "Count", w, h, q_names)
  q = "pgxpool_idle_conns{application_name='libvuln'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "matcher-pg-idle-conns", "ACS Matcher Postgres Idle Connections", "Count", w, h, q_names)
  q = "pgxpool_total_conns{application_name='libvuln'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "matcher-pg-total-conns", "ACS Matcher Postgres Total Connections", "Count", w, h, q_names)

  # Matcher gRPC metrics
  q = "sum by (grpc_method) (rate(grpc_server_handling_seconds_sum{namespace=~'stackrox|rhacs-operator',pod=~'scanner-v4-matcher-.*'}[5m]))"
  query_thanos(route, q, "grpc_method", token, end_ts, duration, sub_report_dir, "matcher-grpc-duration", "ACS Matcher gRPC Handling Duration", "Seconds", w, h, q_names)
  q = "sum by (grpc_code) (rate(grpc_server_handled_total{namespace=~'stackrox|rhacs-operator',pod=~'scanner-v4-matcher-.*'}[5m]))"
  query_thanos(route, q, "grpc_code", token, end_ts, duration, sub_report_dir, "matcher-grpc-handled", "ACS Matcher gRPC Requests Rate", "Requests/s", w, h, q_names)

  # Capture all remaining Matcher metric families in
  # scanner-v4-matcher-snippet.prom. Target labels prevent common runtime,
  # gRPC, HTTP, process, and tar metrics from mixing with Indexer or Central.
  for metric in MATCHER_SNIPPET_EXTRA_METRICS:
    q = metric + "{namespace=~'stackrox|rhacs-operator',pod=~'scanner-v4-matcher-.*'}"
    query_thanos(route, q, "__name__", token, end_ts, duration, sub_report_dir,
        "matcher-{}".format(metric), "ACS Scanner Matcher {}".format(metric),
        metric_unit(metric), w, h, q_names)

  return q_names


# Base OCP Combines All Base OCP Namespaces CPU/Memory/Network into a single metric/graph
def base_ocp_queries(report_dir, route, token, end_ts, duration, w, h, ocp_version):
  sub_report_dir = os.path.join(report_dir, "base-ocp")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()
  base_ocp_namespaces = get_base_ocp_namespaces(ocp_version)
  ns = "namespace=~'" + "|".join(base_ocp_namespaces) + "'"
  cpu_q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster=''," + ns + "})"
  query_thanos(route, cpu_q, "base-ocp", token, end_ts, duration, sub_report_dir, "cpu-base-ocp", "Base OCP CPU Cores Usage", "CPU", w, h, q_names)
  mem_q = "sum(container_memory_working_set_bytes{cluster='',container!=''," + ns + "})"
  query_thanos(route, mem_q, "base-ocp", token, end_ts, duration, sub_report_dir, "mem-base-ocp", "Base OCP Memory Usage", "MEM", w, h, q_names)
  q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace!=''," + ns + "}[5m]))"
  query_thanos(route, q, "base-ocp", token, end_ts, duration, sub_report_dir, "net-rcv-base-ocp", "Base OCP Network Receive Throughput", "NET", w, h, q_names)
  q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace!=''," + ns + "}[5m]))"
  query_thanos(route, q, "base-ocp", token, end_ts, duration, sub_report_dir, "net-xmt-base-ocp", "Base OCP Network Transmit Throughput", "NET", w, h, q_names)
  return q_names


def cluster_queries(report_dir, route, token, end_ts, duration, w, h, namespaces):
  sub_report_dir = os.path.join(report_dir, "cluster")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()

  # Cluster Complete utilization (OS + Applications)
  # sum(node_cpu_info) is Cluster Core Count and sum(irate(node_cpu_seconds_total{mode="idle"}[1m])) is Idle CPU Usage, subtract idle from core count
  q = "(count(node_cpu_seconds_total{mode='idle'}) - sum(irate(node_cpu_seconds_total{mode='idle'}[1m])))"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "cpu-cluster", "Cluster CPU Cores Usage", "CPU", w, h, q_names)
  q = "sum(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "mem-cluster", "Cluster Memory Usage", "MEM", w, h, q_names)

  # Cluster Application utilization below
  if 'minio' in namespaces:
    # Cluster CPU/Memory/Network and nonterminated pods (excluding Minio)
    q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace!='minio'})"
    query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "cpu-cluster-app_no-minio", "Cluster Application CPU Cores Usage (Excluding Minio)", "CPU", w, h, q_names)
    q = "sum(container_memory_working_set_bytes{cluster='',namespace!='minio',container!=''})"
    query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "mem-cluster-app_no-minio", "Cluster Application Memory Usage (Excluding Minio)", "MEM", w, h, q_names)
    q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace!='',namespace!='minio'}[5m]))"
    query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "net-rcv-cluster_no-minio", "Cluster Network Receive Throughput (Excluding Minio)", "NET", w, h, q_names)
    q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace!='',namespace!='minio'}[5m]))"
    query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "net-xmt-cluster_no-minio", "Cluster Network Transmit Throughput (Excluding Minio)", "NET", w, h, q_names)
    q = "sum(kube_pod_status_phase{phase!='Succeeded',phase!='Failed',namespace!='minio'})"
    query_thanos(route, q, "non-terminated pods", token, end_ts, duration, sub_report_dir, "nonterm-pods-cluster_no-minio", "Non-terminated pods across entire cluster (Excluding Minio)", "Count", w, h, q_names)

  # Cluster CPU/Memory/Network and nonterminated pods (No namespaces excluded)
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster=''})"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "cpu-cluster-app", "Cluster Application CPU Cores Usage", "CPU", w, h, q_names)
  q = "sum(container_memory_working_set_bytes{cluster='',container!=''})"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "mem-cluster-app", "Cluster Application Memory Usage", "MEM", w, h, q_names)
  q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace!=''}[5m]))"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "net-rcv-cluster", "Cluster Network Receive Throughput", "NET", w, h, q_names)
  q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace!=''}[5m]))"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "net-xmt-cluster", "Cluster Network Transmit Throughput", "NET", w, h, q_names)
  q = "sum(kube_pod_status_phase{phase!='Succeeded',phase!='Failed'})"
  query_thanos(route, q, "non-terminated pods", token, end_ts, duration, sub_report_dir, "nonterm-pods-cluster", "Non-terminated pods across entire cluster", "Count", w, h, q_names)
  # Sum of nodes in each status (Ready, DiskPressure, MemoryPressure, PIDPressure)
  q = "sum by (condition) (kube_node_status_condition{status='true'})"
  query_thanos(route, q, "condition", token, end_ts, duration, sub_report_dir, "cluster-node-status", "Cluster Nodes Status", "Count", w, h, q_names)
  return q_names


def core_ocp_queries(report_dir, route, token, end_ts, duration, w, h):
  # Opinionated list of OCP Namespaces to collect prometheus data on
  core_ocp_namespaces = [
    "openshift-apiserver",
    "openshift-console",
    "openshift-controller-manager",
    "openshift-etcd",
    "openshift-ingress",
    "openshift-kni-infra",
    "openshift-kube-apiserver",
    "openshift-kube-controller-manager",
    "openshift-kube-scheduler",
    "openshift-machine-api",
    "openshift-monitoring",
    "openshift-ovn-kubernetes"
  ]

  sub_report_dir = os.path.join(report_dir, "core-ocp")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()
  for ns in core_ocp_namespaces:
    q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='" + ns + "'})"
    query_thanos(route, q, ns, token, end_ts, duration, sub_report_dir, "cpu-{}".format(ns), "{} CPU Cores Usage".format(ns), "CPU", w, h, q_names)
    q = "sum(container_memory_working_set_bytes{cluster='',container!='',namespace='" + ns + "'})"
    query_thanos(route, q, ns, token, end_ts, duration, sub_report_dir, "mem-{}".format(ns), "{} Memory Usage".format(ns), "MEM", w, h, q_names)
    # q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace='" + ns + "'}[5m]))"
    # query_thanos(route, q, ns, token, end_ts, duration, sub_report_dir, "net-rcv-{}".format(ns), "{} Network Receive Throughput".format(ns), "NET", w, h, q_names)
    # q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace='" + ns + "'}[5m]))"
    # query_thanos(route, q, ns, token, end_ts, duration, sub_report_dir, "net-xmt-{}".format(ns), "{} Network Transmit Throughput".format(ns), "NET", w, h, q_names)

    # split by pods in the namespaces
    q = "sum by (pod) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='" + ns + "'})"
    query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "cpu-{}-pod".format(ns), "{} CPU Cores Usage".format(ns), "CPU", w, h, q_names)
    q = "sum by (pod) (container_memory_working_set_bytes{cluster='',container!='',namespace='" + ns + "'})"
    query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "mem-{}-pod".format(ns), "{} Memory Usage".format(ns), "MEM", w, h, q_names)

    # Volume space used by openshift-monitoring, just monitoring for now
    if ns == "openshift-monitoring":
      q = "sum by (persistentvolumeclaim) (kubelet_volume_stats_used_bytes{namespace='" + ns + "'})"
      query_thanos(route, q, "persistentvolumeclaim", token, end_ts, duration, sub_report_dir, "pvc-{}".format(ns), "{} Volume Usage".format(ns), "DISK_USAGE", w, h, q_names)

  q = "(sum by (container) (kube_pod_container_status_restarts_total) > 3)"
  query_thanos(route, q, "container", token, end_ts, duration, sub_report_dir, "pod-restarts", "Pod Restarts > 3", "Count", w, h, q_names)
  return q_names


def etcd_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "etcd")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()
  # ETCD DB Size is what can trigger out of quota
  q = "etcd_mvcc_db_total_size_in_bytes"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "db-size", "ETCD DB Size", "DISK_USAGE", w, h, q_names)
  q = "etcd_mvcc_db_total_size_in_use_in_bytes"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "db-size-in-use", "ETCD DB Size In-use", "DISK_USAGE", w, h, q_names)
  q = "histogram_quantile(0.99, sum(rate(etcd_disk_wal_fsync_duration_seconds_bucket{job='etcd'}[5m])) by (instance, pod, le))"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "fsync-duration", "ETCD Disk Sync Duration", "Seconds", w, h, q_names)
  q = "histogram_quantile(0.99, irate(etcd_disk_backend_commit_duration_seconds_bucket[5m]))"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "backend-commit-duration", "ETCD Backend Commit Duration", "Seconds", w, h, q_names)
  q = "changes(etcd_server_leader_changes_seen_total{job='etcd'}[1d])"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "total-leader-elections", "ETCD Leader Elections Per Day", "Count", w, h, q_names)
  q = "max by (pod) (etcd_server_leader_changes_seen_total)"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "leader-changes", "ETCD Max Leader Changes", "Count", w, h, q_names)

  # Summing by pod means latencies between each other member are "summed" FYI
  q = "sum by (pod) (histogram_quantile(0.99, irate(etcd_network_peer_round_trip_time_seconds_bucket[1m])))"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "peer-roundtrip-time", "ETCD Peer Roundtrip Time", "Seconds", w, h, q_names)
  return q_names


def lso_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "lso")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()
  # Local Storage Operator CPU/Memory/Network
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='openshift-local-storage'})"
  query_thanos(route, q, "openshift-local-storage", token, end_ts, duration, sub_report_dir, "cpu-lso", "OpenShift LSO CPU Cores Usage", "CPU", w, h, q_names)
  q = "sum(container_memory_working_set_bytes{cluster='',container!='',namespace='openshift-local-storage'})"
  query_thanos(route, q, "openshift-local-storage", token, end_ts, duration, sub_report_dir, "mem-lso", "OpenShift LSO Memory Usage", "MEM", w, h, q_names)
  q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace='openshift-local-storage'}[5m]))"
  query_thanos(route, q, "openshift-local-storage", token, end_ts, duration, sub_report_dir, "net-rcv-lso", "OpenShift LSO Network Receive Throughput", "NET", w, h, q_names)
  q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace='openshift-local-storage'}[5m]))"
  query_thanos(route, q, "openshift-local-storage", token, end_ts, duration, sub_report_dir, "net-xmt-lso", "OpenShift LSO Network Transmit Throughput", "NET", w, h, q_names)
  return q_names


def make_report_directories(sub_report_dir):
  csv_dir = os.path.join(sub_report_dir, "csv")
  stats_dir = os.path.join(sub_report_dir, "stats")
  if not os.path.exists(sub_report_dir):
    os.mkdir(sub_report_dir)
  if not os.path.exists(csv_dir):
    os.mkdir(csv_dir)
  if not os.path.exists(stats_dir):
    os.mkdir(stats_dir)


# MCE - Complete (Hive, Hypershift, MCE, UWM) CPU/Memory/Network
def node_queries(report_dir, route, token, end_ts, duration, w, h, namespaces):
  # Node CPU/Memory/Disk/Network
  sub_report_dir = os.path.join(report_dir, "node")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()

  # Keep in mind the below two queries include Minio
  # Subtract by node/instance idle CPU usage from core count to get each node/instance's CPU usage
  q = "(count by (instance) (node_cpu_seconds_total{mode='idle'}) - sum by (instance) (irate(node_cpu_seconds_total{mode='idle'}[1m])))"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "cpu-node", "Node CPU Cores Usage", "CPU", w, h, q_names)
  q = "sum by (instance) (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "mem-node", "Node Memory Usage", "MEM", w, h, q_names)

  if 'minio' in namespaces:
    # Node CPU/Memory/Disk/Network (excluding Minio)
    q = "sum by(node) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace!='minio'})"
    query_thanos(route, q, "node", token, end_ts, duration, sub_report_dir, "cpu-node-app_no-minio", "Node Application CPU Cores Usage (Excluding Minio)", "CPU", w, h, q_names)
    q = "sum by(node) (container_memory_working_set_bytes{cluster='',container!='',namespace!='minio'})"
    query_thanos(route, q, "node", token, end_ts, duration, sub_report_dir, "mem-node-app_no-minio", "Node Application Memory Usage (Excluding Minio)", "MEM", w, h, q_names)

  # Node CPU/Memory/Network (including Minio)
  q = "sum by(node) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster=''})"
  query_thanos(route, q, "node", token, end_ts, duration, sub_report_dir, "cpu-node-app", "Node Application CPU Cores Usage", "CPU", w, h, q_names)
  q = "sum by(node) (container_memory_working_set_bytes{cluster='',container!=''})"
  query_thanos(route, q, "node", token, end_ts, duration, sub_report_dir, "mem-node-app", "Node Application Memory Usage", "MEM", w, h, q_names)
  q = "sum by (instance) (instance:node_network_receive_bytes_excluding_lo:rate1m{cluster=''})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "net-rcv-node", "Node Network Receive Throughput", "NET", w, h, q_names)
  q = "sum by (instance) (instance:node_network_transmit_bytes_excluding_lo:rate1m{cluster=''})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "net-xmt-node", "Node Network Transmit Throughput", "NET", w, h, q_names)

  # Disk space utilization does not include Minio PV data (Separate PV Disk for Minio)
  q = "sum by (instance) (node_filesystem_size_bytes{mountpoint='/sysroot'} - node_filesystem_avail_bytes{mountpoint='/sysroot'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-util-root-node", "Node / space utilization", "DISK_USAGE", w, h, q_names)
  q = "sum by (instance) (node_filesystem_size_bytes{mountpoint='/var/lib/etcd'} - node_filesystem_avail_bytes{mountpoint='/var/lib/etcd'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-util-etcd-node", "Node /var/lib/etcd space utilization", "DISK_USAGE", w, h, q_names)
  q = "sum by (instance) (node_filesystem_size_bytes{mountpoint='/var/lib/containers'} - node_filesystem_avail_bytes{mountpoint='/var/lib/containers'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-util-containers-node", "Node /var/lib/containers space utilization", "DISK_USAGE", w, h, q_names)

  # Disk Throughput and Iops utilization by node for disk mounting / or /sysroot
  # Complexity in this query is due to device naming (/dev/sda1 vs sda) and grouping mountpoints to devices
  q = "sum by (instance) (irate(node_disk_read_bytes_total[5m]) * on(instance,device) group_left(mountpoint) (label_replace(node_filesystem_mount_info{mountpoint='/sysroot'}, 'device', '$1', 'device', '/dev/(nvme[0-9]+n[0-9]+|[a-z]+).*')))"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-tput-read-root-node", "Node / Read Throughput", "DISK_TPUT_MB", w, h, q_names)
  q = "sum by (instance) (irate(node_disk_written_bytes_total[5m]) * on(instance,device) group_left(mountpoint) (label_replace(node_filesystem_mount_info{mountpoint='/sysroot'}, 'device', '$1', 'device', '/dev/(nvme[0-9]+n[0-9]+|[a-z]+).*')))"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-tput-write-root-node", "Node / Write Throughput", "DISK_TPUT_MB", w, h, q_names)
  q = "sum by (instance) (irate(node_disk_reads_completed_total[5m]) * on(instance,device) group_left(mountpoint) (label_replace(node_filesystem_mount_info{mountpoint='/sysroot'}, 'device', '$1', 'device', '/dev/(nvme[0-9]+n[0-9]+|[a-z]+).*')))"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-iops-read-root-node", "Node / Read Iops", "Iops", w, h, q_names)
  q = "sum by (instance) (irate(node_disk_writes_completed_total[5m]) * on(instance,device) group_left(mountpoint) (label_replace(node_filesystem_mount_info{mountpoint='/sysroot'}, 'device', '$1', 'device', '/dev/(nvme[0-9]+n[0-9]+|[a-z]+).*')))"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-iops-write-root-node", "Node / Write Iops", "Iops", w, h, q_names)
  # Disk Throughput and Iops utilization by node for disk mounting /var/lib/etcd
  # /var/lib/etcd is usually placed on a separate nvme disk
  q = "sum by (instance) (irate(node_disk_read_bytes_total[5m]) * on(instance,device) group_left(mountpoint) (label_replace(node_filesystem_mount_info{mountpoint='/var/lib/etcd'}, 'device', '$1', 'device', '/dev/(nvme[0-9]+n[0-9]+|[a-z]+).*')))"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-tput-read-etcd-node", "Node /var/lib/etcd Read Throughput", "DISK_TPUT_MB", w, h, q_names)
  q = "sum by (instance) (irate(node_disk_written_bytes_total[5m]) * on(instance,device) group_left(mountpoint) (label_replace(node_filesystem_mount_info{mountpoint='/var/lib/etcd'}, 'device', '$1', 'device', '/dev/(nvme[0-9]+n[0-9]+|[a-z]+).*')))"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-tput-write-etcd-node", "Node /var/lib/etcd Write Throughput", "DISK_TPUT_MB", w, h, q_names)
  q = "sum by (instance) (irate(node_disk_reads_completed_total[5m]) * on(instance,device) group_left(mountpoint) (label_replace(node_filesystem_mount_info{mountpoint='/var/lib/etcd'}, 'device', '$1', 'device', '/dev/(nvme[0-9]+n[0-9]+|[a-z]+).*')))"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-iops-read-etcd-node", "Node /var/lib/etcd Read Iops", "Iops", w, h, q_names)
  q = "sum by (instance) (irate(node_disk_writes_completed_total[5m]) * on(instance,device) group_left(mountpoint) (label_replace(node_filesystem_mount_info{mountpoint='/var/lib/etcd'}, 'device', '$1', 'device', '/dev/(nvme[0-9]+n[0-9]+|[a-z]+).*')))"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-iops-write-etcd-node", "Node /var/lib/etcd Write Iops", "Iops", w, h, q_names)

  q = "sum(kube_pod_status_phase{phase!='Succeeded',phase!='Failed'} * on (namespace, pod, container, uid) group_left(node) kube_pod_info{pod_ip!=''}) by (node)"
  query_thanos(route, q, "node", token, end_ts, duration, sub_report_dir, "nonterm-pods-node", "Non-terminated pods by Node", "Count", w, h, q_names)
  return q_names


def resource_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "resource")
  make_report_directories(sub_report_dir)
  q_names = OrderedDict()
  q = "sum by (instance) (apiserver_storage_objects)"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "all", "All Resources", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='namespaces'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "namespaces", "Namespaces", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='serviceaccounts'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "serviceaccounts", "Serviceaccounts", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='pods'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "pods", "Pods", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='replicasets.apps'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "replicasets", "Replicasets", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='deployments.apps'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "deployments", "Deployments", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='daemonsets.apps'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "daemonsets", "Daemonsets", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='statefulsets.apps'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "statefulsets", "Statefulsets", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='jobs.batch'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "jobs", "Jobs", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='cronjobs.batch'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "cronjobs", "Cronjobs", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='endpoints'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "endpoints", "Endpoints", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='services'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "services", "Services", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='configmaps'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "configmaps", "Configmaps", "Count", w, h, q_names)
  q = "sum by (instance) (apiserver_storage_objects{resource='secrets'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "secrets", "Secrets", "Count", w, h, q_names)
  q = "sum by (namespace) (kubelet_volume_stats_used_bytes)"
  query_thanos(route, q, "namespace", token, end_ts, duration, sub_report_dir, "pvc-usage", "Volume Usage By Namespace", "DISK_USAGE", w, h, q_names)
  return q_names


def query_thanos(route, query, series_label, token, end_ts, duration, directory, fname, g_title, y_unit, g_width, g_height, q_names, resolution="1m"):
  logger.info("Querying data for {}".format(fname))
  if fname in q_names:
    logger.error("Query name already exists")
    sys.exit(1)
  q_names[fname] = g_title

  if y_unit == "CPU":
    y_title = "CPU (Cores)"
  elif y_unit == "MEM":
    y_title = "Memory (GiB)"
  elif y_unit == "NET":
    y_title = "Network (Mbps)"
  elif y_unit == "DISK_USAGE":
    y_title = "Disk Usage (GB)"
  elif y_unit == "DISK_TPUT_MB":
    y_title = "Disk Throughput (MB/s)"
  else:
    y_title = y_unit

  # Determine query offset from end timestamp
  offset = calculate_query_offset(end_ts)

  # Apply the subquery to the complete expression. Appending it directly can
  # bind the range selector to a trailing scalar (for example, `/ 1000000`)
  # instead of the instant vector returned by the query.
  if offset == 0:
    query_complete = "(" + query + ")[" + duration + ":" + resolution + "]"
  else:
    query_complete = "(" + query + ")[" + duration + ":" + resolution + "] offset " + str(int(offset)) + "m"
  logger.info("Query: {}".format(query_complete))
  # Use POST body so the query is form-encoded; putting it in the URL unencoded breaks
  # complex queries (spaces, quotes, slashes, regex) and can return empty results.
  query_endpoint = "{}/api/v1/query".format(route)
  headers = {"Authorization": "Bearer {}".format(token)}
  payload = {"query": query_complete}
  query_data = requests.post(query_endpoint, headers=headers, data=payload, verify=False)

  if query_data.status_code == 200:
    qd_json = query_data.json()
    # print("qd_json: {}".format(json.dumps(qd_json, indent=4)))
    if ("data" in qd_json) and ("result" in qd_json["data"]):
      logger.debug("Length of returned result data: {}".format(len(qd_json["data"]["result"])))

      if len(qd_json["data"]["result"]) == 0:
        logger.warning("Empty data returned from query")
      else:
        # Build list of DataFrames, one per metric, then merge them.  A
        # Prometheus query can return several series with the same selected
        # display label (for example, grpc_code="OK" for several methods).
        # Make those column names unique before merging.
        def get_metric_name(metric):
          if series_label not in metric["metric"]:
            return series_label
          return metric["metric"][series_label]

        metric_names = [get_metric_name(metric) for metric in qd_json["data"]["result"]]
        duplicate_metric_names = {name for name, count in Counter(metric_names).items() if count > 1}

        dfs = []
        series = []

        for metric, base_metric_name in zip(qd_json["data"]["result"], metric_names):
          # Create datetime series for this metric
          metric_datetime = [datetime.fromtimestamp(x[0], tz=timezone.utc) for x in metric["values"]]

          # Determine the series name
          if series_label not in metric["metric"]:
            metric_name = base_metric_name
            logger.debug("Num of values: {}".format(len(metric["values"])))
          else:
            metric_name = base_metric_name
            logger.debug("{}: {}, Num of values: {}".format(series_label, metric_name, len(metric["values"])))

          if base_metric_name in duplicate_metric_names:
            labels = ", ".join("{}={}".format(key, value)
                               for key, value in sorted(metric["metric"].items())
                               if key != "__name__")
            metric_name = "{} ({})".format(base_metric_name, labels)

          # Convert values based on unit
          if y_unit == "MEM":
            bytes_to_gib = 1024 * 1024 * 1024
            metric_values = [float(x[1]) / bytes_to_gib for x in metric["values"]]
          elif y_unit == "NET":
            # Prometheus irate() returns bytes/s; convert to megabits per second (Mbps)
            bytes_to_mbps = 1_000_000 / 8
            metric_values = [float(x[1]) / bytes_to_mbps for x in metric["values"]]
          elif y_unit == "DISK_USAGE":
            bytes_to_gb = 1000 * 1000 * 1000
            metric_values = [float(x[1]) / bytes_to_gb for x in metric["values"]]
          elif y_unit == "DISK_TPUT_MB":
            bytes_to_mb = 1000 * 1000
            metric_values = [float(x[1]) / bytes_to_mb for x in metric["values"]]
          else:
            metric_values = [float(x[1]) for x in metric["values"]]

          # Create a DataFrame for this metric
          metric_df = pd.DataFrame({
            "datetime": metric_datetime,
            metric_name: metric_values
          })
          dfs.append(metric_df)
          series.append(metric_name)

        # Merge all DataFrames on datetime using outer join to handle different lengths
        df = dfs[0]
        for metric_df in dfs[1:]:
          df = pd.merge(df, metric_df, on="datetime", how="outer")
        # Sort by datetime after merge if we merged multiple DataFrames
        if len(dfs) > 1:
          df = df.sort_values("datetime").reset_index(drop=True)
        
        # Ensure datetime column is properly formatted for plotly
        if "datetime" in df.columns:
          df["datetime"] = pd.to_datetime(df["datetime"])

        # Filter series list to only include columns that actually exist in the DataFrame
        series_to_plot = [s for s in series if s in df.columns]

        if len(series_to_plot) == 0:
          logger.warning("No valid series to plot after merge")
        else:
          csv_dir = os.path.join(directory, "csv")
          stats_dir = os.path.join(directory, "stats")

          # Write graph and stats file
          with open("{}/{}.stats".format(stats_dir, fname), "a") as stats_file:
            stats_file.write("Unit: {}\n".format(y_title))
            with pd.option_context("display.max_columns", None, "display.width", 240):
              stats_file.write(str(df.describe(percentiles=[.25, .5, .75, .95, .99])))
          df.to_csv("{}/{}.csv".format(csv_dir, fname))

          # Create a copy for plotting with datetime as string to avoid plotly conversion issues
          df_plot = df.copy()
          if "datetime" in df_plot.columns:
            df_plot["datetime"] = df_plot["datetime"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

          l = {"value" : y_title, "datetime": "Time (UTC)"}
          fig_cluster_node = px.line(df_plot, x="datetime", y=series_to_plot, labels=l, width=g_width, height=g_height)
          fig_cluster_node.update_layout(title=g_title, legend_orientation="v")
          fig_cluster_node.write_image("{}/{}.png".format(directory, fname))

      logger.info("Completed querying and graphing data")

    else:
      logger.error("Missing data/results field(s) from query result: {}".format(qd_json))
  else:
    logger.error("Query Post status returned: {}".format(query_data.status_code))
    logger.error("Query response: \n{}".format(query_data.text.rstrip()))


def generate_report_html(report_dir, report_data):
  logger.info("Generating report html file")
  with open("{}/report.html".format(report_dir), "w") as html_file:
    html_file.write("<html>\n")
    html_file.write("<head><title>Prometheus Analysis Report</title></head>")
    html_file.write("<body>\n")
    html_file.write("<b>Prometheus Analysis Report</b><br>\n")
    for i, (section, v) in enumerate(report_data.items()):
      if i == len(report_data) - 1:
        html_file.write("<a href='#{0}'>{0} section</a>\n".format(section))
      else:
        html_file.write("<a href='#{0}'>{0} section</a> | \n".format(section))
    for section in report_data:
      html_file.write("<h2 id='{0}'>{0} section</h2>\n".format(section))
      for dp in report_data[section]:
        html_file.write("{} - {} | \n".format(report_data[section][dp], dp))
        html_file.write("<a href='{0}/{1}.png'>graph</a> | \n".format(section, dp))
        html_file.write("<a href='{0}/stats/{1}.stats'>stats</a> | \n".format(section, dp))
        html_file.write("<a href='{0}/csv/{1}.csv'>csv</a><br>\n".format(section, dp))
        html_file.write("<a href='{0}/{1}.png'><img src='{0}/{1}.png' width='700' height='500'></a><br>\n".format(section,dp))
    html_file.write("</body>\n")
    html_file.write("</html>\n")
  logger.info("Finished generating report html file")


def valid_datetime(datetime_arg):
    try:
        return datetime.strptime(datetime_arg, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise argparse.ArgumentTypeError("Datetime ({}) not valid! Expected format, 'YYYY-MM-DDTHH:mm:SSZ'!".format(datetime_arg))


def main():
  # Start time of script (Now)
  start_time = time.time()
  # Default end time for analysis is the start time of the script
  # Default start time for analysis is start time of script minus one hour (Default analyzes one hour from now)
  default_ap_end_time = datetime.fromtimestamp(start_time, tz=timezone.utc)
  default_ap_start_time = datetime.fromtimestamp(start_time - (60 * 60), tz=timezone.utc)

  parser = argparse.ArgumentParser(
      description="Query and Graph Prometheus data for ACS (Advanced Cluster Security) off a live OpenShift cluster",
      prog="analyze-prometheus-for-acs.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/mno/kubeconfig",
                      help="Changes which kubeconfig to connect to a cluster")

  parser.add_argument("-s", "--start-ts", type=valid_datetime, default=default_ap_start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                      help="Sets start utc timestamp")
  parser.add_argument("-e", "--end-ts", type=valid_datetime, default=default_ap_end_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                      help="Sets end utc timestamp")

  # Quick way to add small amount of time to front and end of test period
  parser.add_argument("-b", "--buffer-minutes", type=int, default=5,
                      help="Buffers start/end time stamps of data selected in minutes")

  parser.add_argument("-p", "--prefix", type=str, default="pa", help="Sets directory name prefix for files")

  # Graph size
  parser.add_argument("-w", "--width", type=int, default=1400, help="Sets width of all graphs")
  parser.add_argument("-t", "--height", type=int, default=1000, help="Sets height of all graphs")

  # Directory to place graphs
  parser.add_argument("results_directory", type=str, help="The location to place graphs and stats files")

  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)
  logger.debug("CLI Args: {}".format(cliargs))

  logger.info("Analyze Prometheus")

  w = cliargs.width
  h = cliargs.height

  # Set/Validate start and end timestamps for queries
  buffer_time = (cliargs.buffer_minutes * 60)
  logger.info("Buffer time set to: {} seconds".format(buffer_time))

  logger.info("Start timestamp set: {}".format(cliargs.start_ts))
  q_start_ts = int(time.mktime(cliargs.start_ts.timetuple())) - buffer_time
  logger.info("Start timestamp Unix: {}".format(q_start_ts))

  logger.info("End timestamp set: {}".format(cliargs.end_ts))
  q_end_ts = int(time.mktime(cliargs.end_ts.timetuple())) + buffer_time
  logger.info("End timestamp Unix: {}".format(q_end_ts))

  analyze_duration = q_end_ts - q_start_ts
  # Ensure start/end are at least 5 minutes apart
  if analyze_duration <= (60 * 5):
    logger.error("Start/End timestamps are too close")
    sys.exit(1)
  q_duration = "{}m".format(int(analyze_duration / 60))
  logger.info("Examining duration {}s :: {}".format(analyze_duration, str(timedelta(seconds=analyze_duration))))
  logger.info("Query duration: {}".format(q_duration))
  # Finished with start/end time

  version = get_ocp_version(cliargs.kubeconfig)
  logger.info("OCP version is {}.{}.{}".format(version["major"], version["minor"], version["patch"]))

  route = get_thanos_querier_route(cliargs.kubeconfig)
  if route == "":
    logger.error("Could not obtain the thanos querier route")
    sys.exit(1)
  logger.info("Route to Query: {}".format(route))

  token = get_prometheus_token(cliargs.kubeconfig, version)
  if token == "":
    logger.error("Could not obtain the prometheus token")
    sys.exit(1)

  # Detect which queries to make based on namespaces present
  namespaces = get_ocp_namespace_list(cliargs.kubeconfig)

  # Create the results directories to store data into
  report_dir = os.path.join(cliargs.results_directory, "{}-{}".format(cliargs.prefix,
      datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y%m%d-%H%M%S")))
  logger.debug("Creating report directory: {}".format(report_dir))
  if not os.path.exists(report_dir):
    os.mkdir(report_dir)

  with open("{}/analysis".format(report_dir), "a") as report_file:
    report_file.write("Analyzed Cluster Version: {}.{}.{}\n".format(version["major"], version["minor"], version["patch"]))
    report_file.write("Start Time: {}\n".format(cliargs.start_ts))
    report_file.write("End Time: {}\n".format(cliargs.end_ts))
    report_file.write("Buffer time: {}s\n".format(buffer_time))
    report_file.write("Examining duration: {}s :: {}\n".format(analyze_duration, str(timedelta(seconds=analyze_duration))))
    report_file.write("Query duration: {}\n".format(q_duration))
    report_file.write("Query route: {}\n".format(route))

  report_data = OrderedDict()

  # Query prometheus and build data structure to help build report html file
  report_data["cluster"] = cluster_queries(report_dir, route, token, q_end_ts, q_duration, w, h, namespaces)
  report_data["node"] = node_queries(report_dir, route, token, q_end_ts, q_duration, w, h, namespaces)
  report_data["etcd"] = etcd_queries(report_dir, route, token, q_end_ts, q_duration, w, h)
  report_data["resource"] = resource_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  report_data["base-ocp"] = base_ocp_queries(report_dir, route, token, q_end_ts, q_duration, w, h, version)
  report_data["core-ocp"] = core_ocp_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  # ACS (Advanced Cluster Security) Queries
  if {"stackrox", "rhacs-operator"}.intersection(namespaces):
    logger.info("ACS namespace found, querying for ACS metrics")
    nodes = get_ocp_node_list(cliargs.kubeconfig)
    report_data["acs-complete"] = acs_complete_queries(report_dir, route, token, q_end_ts, q_duration, w, h, nodes)
    report_data["acs-central"] = acs_central_queries(report_dir, route, token, q_end_ts, q_duration, w, h)
    report_data["acs-scanner-indexer"] = acs_scanner_indexer_queries(report_dir, route, token, q_end_ts, q_duration, w, h)
    report_data["acs-scanner-matcher"] = acs_scanner_matcher_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  # Local Storage Operator
  if "openshift-local-storage" in namespaces:
    logger.info("openshift-local-storage namespace found, querying for lso metrics")
    report_data["lso"] = lso_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  generate_report_html(report_dir, report_data)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
