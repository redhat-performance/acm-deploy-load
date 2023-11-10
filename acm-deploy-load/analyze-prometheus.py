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
from collections import OrderedDict
from datetime import datetime
from datetime import timedelta
from utils.common_ocp import get_ocp_version
from utils.common_ocp import get_prometheus_token
from utils.common_ocp import get_thanos_querier_route
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
# * 4.13 vs 4.12 queries? (Seems network usage query returning empty)
# * Better report creation during queries
# * Fix timeseries with coming and leaving pods
# * Graph cluster/node disk (throughput, iops)
# * ACM Policy Engine Pods CPU/Memory, work queue?
# * Node kubelet, crio cpu/memory
# * OCP CPU, Memory, split on pods?
# * Total pod count??, total object count?
# * ACM Disk?, Network?
# * Split reports - All, cluster, node, etcd, ocp, acm etc to have smaller html files

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


directories = [
  "cluster",
  "node",
  "etcd",
  "ocp",
  "resource",
  "acm",
  "talm"
]
ocp_namespaces = [
  "openshift-apiserver",
  "openshift-controller-manager",
  "openshift-etcd",
  "openshift-gitops",
  "openshift-ingress",
  "openshift-kni-infra",
  "openshift-kube-apiserver",
  "openshift-kube-controller-manager",
  "openshift-kube-scheduler",
  "openshift-local-storage",
  "openshift-monitoring"
]

cluster_data = [
  "cpu-cluster",
  "mem-cluster",
  "net-rcv-cluster",
  "net-xmt-cluster"
]
node_data = [
  "cpu-node",
  "mem-node",
  "disk-util-root-node",
  "disk-util-etcd-node",
  "disk-util-containers-node",
  "net-rcv-node",
  "net-xmt-node"
]
etcd_data = [
  "db-size",
  "db-size-in-use",
  "fsync-duration",
  "backend-commit-duration",
  "total-leader-elections",
  "leader-changes",
  "peer-roundtrip-time"
]
ocp_data = []
for ns in ocp_namespaces:
  ocp_data.append("cpu-{}".format(ns))
  ocp_data.append("mem-{}".format(ns))
ocp_data.append("pod-restarts")
resource_data = [
  "all",
  "namespaces",
  "serviceaccounts",
  "pods",
  "replicasets",
  "deployments",
  "daemonsets",
  "statefulsets",
  "jobs",
  "cronjobs",
  "endpoints",
  "services",
  "configmaps",
  "secrets"
]
acm_data = [
  "acm-mc",
  "acm-mcaddons",
  "acm-policies",
  "acm-placementrules",
  "acm-placementbindings",
  "acm-placementdecisions",
  "acm-manifestworks",
  "cpu-acm",
  "mem-acm",
  "net-rcv-acm",
  "net-xmt-acm",
  "cpu-acm-ocm",
  "mem-acm-ocm",
  "net-rcv-acm-ocm",
  "net-xmt-acm-ocm",
  "cpu-acm-mce",
  "mem-acm-mce",
  "net-rcv-acm-mce",
  "net-xmt-acm-mce",
  "cpu-acm-mce-ai",
  "mem-acm-mce-ai",
  "cpu-acm-obs",
  "mem-acm-obs",
  "mem-acm-obs-rcv-total",
  "mem-acm-obs-rcv-pod",
  "net-rcv-acm-obs",
  "net-xmt-acm-obs",
  "cpu-acm-search",
  "mem-acm-search",
  "net-rcv-acm-search",
  "net-xmt-acm-search",
  "cpu-acm-grc-policy-prop",
  "mem-acm-grc-policy-prop",
  "net-rcv-acm-grc-policy-prop",
  "net-xmt-acm-grc-policy-prop"
]
talm_data = [
  "talm-cgu",
  "cpu-talm",
  "mem-talm",
  # "net-rcv-talm",
  # "net-xmt-talm"
]


def calculate_query_offset(end_ts):
  cur_utc_unix_time = time.mktime(datetime.utcnow().timetuple())
  offset_minutes = (int(cur_utc_unix_time) - end_ts) / 60
  if offset_minutes < 0:
    offset_minutes = 0
  return offset_minutes


def acm_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "acm")
  # Interesting ACM objects
  q = "apiserver_storage_objects{resource='managedclusters.cluster.open-cluster-management.io'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "acm-mc", "Managedcluster Objects", "Count", w, h)
  q = "apiserver_storage_objects{resource='managedclusteraddons.addon.open-cluster-management.io'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "acm-mcaddons", "Managedclusteraddons Objects", "Count", w, h)
  q = "apiserver_storage_objects{resource='policies.policy.open-cluster-management.io'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "acm-policies", "Policy Objects", "Count", w, h)
  q = "apiserver_storage_objects{resource='placementrules.apps.open-cluster-management.io'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "acm-placementrules", "Placementrules Objects", "Count", w, h)
  q = "apiserver_storage_objects{resource='placementbindings.policy.open-cluster-management.io'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "acm-placementbindings", "Placementbindings Objects", "Count", w, h)
  q = "apiserver_storage_objects{resource='placementdecisions.cluster.open-cluster-management.io'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "acm-placementdecisions", "Placementdecisions Objects", "Count", w, h)
  q = "apiserver_storage_objects{resource='manifestworks.work.open-cluster-management.io'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "acm-manifestworks", "Manifestworks Objects", "Count", w, h)

  # ACM CPU/Memory/Network
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace=~'open-cluster-management.*|multicluster-engine'})"
  query_thanos(route, q, "ACM", token, end_ts, duration, sub_report_dir, "cpu-acm", "ACM CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='',container!='',namespace=~'open-cluster-management.*|multicluster-engine'})"
  query_thanos(route, q, "ACM", token, end_ts, duration, sub_report_dir, "mem-acm", "ACM Memory Usage", "MEM", w, h)
  q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace=~'open-cluster-management.*|multicluster-engine'}[5m]))"
  query_thanos(route, q, "ACM", token, end_ts, duration, sub_report_dir, "net-rcv-acm", "ACM Network Receive Throughput", "NET", w, h)
  q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace=~'open-cluster-management.*|multicluster-engine'}[5m]))"
  query_thanos(route, q, "ACM", token, end_ts, duration, sub_report_dir, "net-xmt-acm", "ACM Network Transmit Throughput", "NET", w, h)

  # ACM Open-cluster-management namespace CPU/Memory/Network
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='open-cluster-management'})"
  query_thanos(route, q, "ACM - open-cluster-management", token, end_ts, duration, sub_report_dir, "cpu-acm-ocm", "ACM open-cluster-management CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='',container!='',namespace='open-cluster-management'})"
  query_thanos(route, q, "ACM - open-cluster-management", token, end_ts, duration, sub_report_dir, "mem-acm-ocm", "ACM open-cluster-management Memory Usage", "MEM", w, h)
  q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace='open-cluster-management'}[5m]))"
  query_thanos(route, q, "ACM - open-cluster-management", token, end_ts, duration, sub_report_dir, "net-rcv-acm-ocm", "ACM open-cluster-management Network Receive Throughput", "NET", w, h)
  q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace='open-cluster-management'}[5m]))"
  query_thanos(route, q, "ACM - open-cluster-management", token, end_ts, duration, sub_report_dir, "net-xmt-acm-ocm", "ACM open-cluster-management Network Transmit Throughput", "NET", w, h)

  # ACM MCE CPU/Memory/Network
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='multicluster-engine'})"
  query_thanos(route, q, "ACM - MCE", token, end_ts, duration, sub_report_dir, "cpu-acm-mce", "ACM MCE CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='',container!='',namespace='multicluster-engine'})"
  query_thanos(route, q, "ACM - MCE", token, end_ts, duration, sub_report_dir, "mem-acm-mce", "ACM MCE Memory Usage", "MEM", w, h)
  q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace='multicluster-engine'}[5m]))"
  query_thanos(route, q, "ACM - MCE", token, end_ts, duration, sub_report_dir, "net-rcv-acm-mce", "ACM MCE Network Receive Throughput", "NET", w, h)
  q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace='multicluster-engine'}[5m]))"
  query_thanos(route, q, "ACM - MCE", token, end_ts, duration, sub_report_dir, "net-xmt-acm-mce", "ACM MCE Network Transmit Throughput", "NET", w, h)

  # ACM MCE Assisted-installer CPU/Memory
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='multicluster-engine',pod=~'assisted-service.*'})"
  query_thanos(route, q, "ACM - MCE Assisted-Installer", token, end_ts, duration, sub_report_dir, "cpu-acm-mce-ai", "ACM Assisted-Installer CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='', container!='',namespace='multicluster-engine',pod=~'assisted-service.*'})"
  query_thanos(route, q, "ACM - MCE Assisted-Installer", token, end_ts, duration, sub_report_dir, "mem-acm-mce-ai", "ACM Assisted-Installer Memory Usage", "MEM", w, h)

  # ACM Observability CPU/Memory/Network
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='open-cluster-management-observability'})"
  query_thanos(route, q, "ACM - Observability", token, end_ts, duration, sub_report_dir, "cpu-acm-obs", "ACM Observability CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='', container!='',namespace='open-cluster-management-observability'})"
  query_thanos(route, q, "ACM - Observability", token, end_ts, duration, sub_report_dir, "mem-acm-obs", "ACM Observability Memory Usage", "MEM", w, h)

  q = "sum(container_memory_working_set_bytes{cluster='',namespace='open-cluster-management-observability', pod=~'observability-thanos-receive-default.*', container!=''})"
  query_thanos(route, q, "ACM - Observability Receiver", token, end_ts, duration, sub_report_dir, "mem-acm-obs-rcv-total", "ACM Observability Receiver Memory Usage", "MEM", w, h)
  q = "sum by (pod) (container_memory_working_set_bytes{cluster='',namespace='open-cluster-management-observability', pod=~'observability-thanos-receive-default.*', container!=''})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "mem-acm-obs-rcv-pod", "ACM Observability Receiver Memory Usage", "MEM", w, h)
  q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace='open-cluster-management-observability'}[5m]))"
  query_thanos(route, q, "ACM - Observability", token, end_ts, duration, sub_report_dir, "net-rcv-acm-obs", "ACM Observability Network Receive Throughput", "NET", w, h)
  q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace='open-cluster-management-observability'}[5m]))"
  query_thanos(route, q, "ACM - Observability", token, end_ts, duration, sub_report_dir, "net-xmt-acm-obs", "ACM Observability Network Transmit Throughput", "NET", w, h)

  # ACM Search CPU/Memory/Network
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='open-cluster-management',pod=~'search.*'})"
  query_thanos(route, q, "ACM - Search", token, end_ts, duration, sub_report_dir, "cpu-acm-search", "ACM Search CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='',container!='',namespace='open-cluster-management',pod=~'search.*'})"
  query_thanos(route, q, "ACM - Search", token, end_ts, duration, sub_report_dir, "mem-acm-search", "ACM Search Memory Usage", "MEM", w, h)
  q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace='open-cluster-management',pod=~'search.*'}[5m]))"
  query_thanos(route, q, "ACM - Search", token, end_ts, duration, sub_report_dir, "net-rcv-acm-search", "ACM Search Network Receive Throughput", "NET", w, h)
  q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace='open-cluster-management',pod=~'search.*'}[5m]))"
  query_thanos(route, q, "ACM - Search", token, end_ts, duration, sub_report_dir, "net-xmt-acm-search", "ACM Search Network Transmit Throughput", "NET", w, h)

  # ACM governance policy propagator CPU/Memory/Network
  q = "sum by (pod) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='open-cluster-management', container='governance-policy-propagator'})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "cpu-acm-grc-policy-prop", "ACM governance-policy-propagator CPU Cores Usage", "CPU", w, h)
  q = "sum by (pod) (container_memory_working_set_bytes{cluster='',container!='',namespace='open-cluster-management',container='governance-policy-propagator'})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "mem-acm-grc-policy-prop", "ACM governance-policy-propagator Memory Usage", "MEM", w, h)
  q = "sum by (pod) (irate(container_network_receive_bytes_total{cluster='',namespace='open-cluster-management', pod=~'grc-policy-propagator-.*'}[5m]))"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "net-rcv-acm-grc-policy-prop", "ACM Governance Policy Propagator Network Receive Throughput", "NET", w, h)
  q = "sum by (pod) (irate(container_network_transmit_bytes_total{cluster='',namespace='open-cluster-management', pod=~'grc-policy-propagator-.*'}[5m]))"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "net-xmt-acm-grc-policy-prop", "ACM Governance Policy Propagator Network Transmit Throughput", "NET", w, h)

def cluster_queries(report_dir, route, token, end_ts, duration, w, h):
  # Cluster CPU/Memory
  sub_report_dir = os.path.join(report_dir, "cluster")
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='', namespace!='minio'})"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "cpu-cluster", "Cluster CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='',namespace!='minio', container!=''})"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "mem-cluster", "Cluster Memory Usage", "MEM", w, h)
  q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace!=''}[5m]))"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "net-rcv-cluster", "Cluster Network Receive Throughput", "NET", w, h)
  q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace!=''}[5m]))"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "net-xmt-cluster", "Cluster Network Transmit Throughput", "NET", w, h)


def etcd_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "etcd")
  q = "etcd_mvcc_db_total_size_in_bytes"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "db-size", "ETCD DB Size", "DISK", w, h)
  q = "etcd_mvcc_db_total_size_in_use_in_bytes"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "db-size-in-use", "ETCD DB Size In-use", "DISK", w, h)
  q = "histogram_quantile(0.99, sum(rate(etcd_disk_wal_fsync_duration_seconds_bucket{job='etcd'}[5m])) by (instance, pod, le))"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "fsync-duration", "ETCD Disk Sync Duration", "Seconds", w, h)
  q = "histogram_quantile(0.99, irate(etcd_disk_backend_commit_duration_seconds_bucket[5m]))"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "backend-commit-duration", "ETCD Backend Commit Duration", "Seconds", w, h)
  q = "changes(etcd_server_leader_changes_seen_total{job='etcd'}[1d])"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "total-leader-elections", "ETCD Leader Elections Per Day", "Count", w, h)
  q = "max by (pod) (etcd_server_leader_changes_seen_total)"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "leader-changes", "ETCD Max Leader Changes", "Count", w, h)
  q = "histogram_quantile(0.99, irate(etcd_network_peer_round_trip_time_seconds_bucket[1m]))"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "peer-roundtrip-time", "ETCD Peer Roundtrip Time", "Seconds", w, h)


def node_queries(report_dir, route, token, end_ts, duration, w, h):
  # Node CPU/Memory/Disk/Network
  sub_report_dir = os.path.join(report_dir, "node")
  q = "sum by(node) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace!='minio'})"
  query_thanos(route, q, "node", token, end_ts, duration, sub_report_dir, "cpu-node", "Node CPU Cores Usage", "CPU", w, h)
  q = "sum by(node) (container_memory_working_set_bytes{cluster='',namespace!='minio', container!=''})"
  query_thanos(route, q, "node", token, end_ts, duration, sub_report_dir, "mem-node", "Node Memory Usage", "MEM", w, h)
  q = "sum by (instance) (node_filesystem_size_bytes{mountpoint='/'} - node_filesystem_avail_bytes{mountpoint='/'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-util-root-node", "Node / usage", "DISK", w, h)
  q = "sum by (instance) (node_filesystem_size_bytes{mountpoint='/var/lib/etcd'} - node_filesystem_avail_bytes{mountpoint='/var/lib/etcd'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-util-etcd-node", "Node /var/lib/etcd usage", "DISK", w, h)
  q = "sum by (instance) (node_filesystem_size_bytes{mountpoint='/var/lib/containers'} - node_filesystem_avail_bytes{mountpoint='/var/lib/containers'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "disk-util-containers-node", "Node /var/lib/containers usage", "DISK", w, h)
  q = "sum by (instance) (instance:node_network_receive_bytes_excluding_lo:rate1m{cluster=''})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "net-rcv-node", "Node Network Receive Throughput", "NET", w, h)
  q = "sum by (instance) (instance:node_network_transmit_bytes_excluding_lo:rate1m{cluster=''})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "net-xmt-node", "Node Network Transmit Throughput", "NET", w, h)


def ocp_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "ocp")
  for ns in ocp_namespaces:
    q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='" + ns + "'})"
    query_thanos(route, q, ns, token, end_ts, duration, sub_report_dir, "cpu-{}".format(ns), "{} CPU Cores Usage".format(ns), "CPU", w, h)
    q = "sum(container_memory_working_set_bytes{cluster='',container!='',namespace='" + ns + "'})"
    query_thanos(route, q, ns, token, end_ts, duration, sub_report_dir, "mem-{}".format(ns), "{} Memory Usage".format(ns), "MEM", w, h)

    # Needs work as pods don't always "survive" complete query time period
    # # split by pods in the namespaces
    # q = "sum by (pod) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='" + ns + "'})"
    # query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "cpu-{}-pod".format(ns), "{} CPU Cores Usage".format(ns), "CPU", w, h)
    # q = "sum by (pod) (container_memory_working_set_bytes{cluster='',namespace!='minio', container!='',namespace='" + ns + "'})"
    # query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "mem-{}-pod".format(ns), "{} CPU Cores Usage".format(ns), "MEM", w, h)

  q = "(sum by (container) (kube_pod_container_status_restarts_total) > 3)"
  query_thanos(route, q, "container", token, end_ts, duration, sub_report_dir, "pod-restarts", "Pod Restarts > 3", "Count", w, h)


def resource_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "resource")
  q = "sum by (instance) (apiserver_storage_objects)"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "all", "All Resources", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='namespaces'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "namespaces", "Namespaces", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='serviceaccounts'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "serviceaccounts", "Serviceaccounts", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='pods'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "pods", "Pods", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='replicasets.apps'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "replicasets", "Replicasets", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='deployments.apps'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "deployments", "Deployments", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='daemonsets.apps'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "daemonsets", "Daemonsets", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='statefulsets.apps'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "statefulsets", "Statefulsets", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='jobs.batch'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "jobs", "Jobs", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='cronjobs.batch'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "cronjobs", "Cronjobs", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='endpoints'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "endpoints", "Endpoints", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='services'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "services", "Services", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='configmaps'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "configmaps", "Configmaps", "Count", w, h)
  q = "sum by (instance) (apiserver_storage_objects{resource='secrets'})"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "secrets", "Secrets", "Count", w, h)


def talm_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "talm")
  q = "apiserver_storage_objects{resource='clustergroupupgrades.ran.openshift.io'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "talm-cgu", "ClusterGroupUpgrades Objects", "Count", w, h)

  # TALM CPU/Memory/Network
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace=~'openshift-cluster-group-upgrades'})"
  query_thanos(route, q, "TALM", token, end_ts, duration, sub_report_dir, "cpu-talm", "TALM CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='',container!='',namespace=~'openshift-cluster-group-upgrades'})"
  query_thanos(route, q, "TALM", token, end_ts, duration, sub_report_dir, "mem-talm", "TALM Memory Usage", "MEM", w, h)
  # network appears so minimal that it's nothing
  # q = "sum(irate(container_network_receive_bytes_total{cluster='',namespace=~'openshift-cluster-group-upgrades'}[5m]))"
  # query_thanos(route, q, "TALM", token, end_ts, duration, sub_report_dir, "net-rcv-talm", "TALM Network Receive Throughput", "NET", w, h)
  # q = "sum(irate(container_network_transmit_bytes_total{cluster='',namespace=~'openshift-cluster-group-upgrades'}[5m]))"
  # query_thanos(route, q, "TALM", token, end_ts, duration, sub_report_dir, "net-xmt-talm", "TALM Network Transmit Throughput", "NET", w, h)


def query_thanos(route, query, series_label, token, end_ts, duration, directory, fname, g_title, y_unit, g_width, g_height, resolution="1m"):
  logger.info("Querying data")

  if y_unit == "CPU":
    y_title = "CPU (Cores)"
  elif y_unit == "MEM":
    y_title = "Memory (GiB)"
  elif y_unit == "NET":
    y_title = "Network (MiB)"
  elif y_unit == "DISK":
    y_title = "Disk (GB)"
  else:
    y_title = y_unit

  # Determine query offset from end timestamp
  offset = calculate_query_offset(end_ts)

  if offset == 0:
    query_complete = query + "[" + duration + ":" + resolution + "]"
  else:
    query_complete = query + "[" + duration + ":" + resolution + "] offset " + str(int(offset)) + "m"
  logger.info("Query: {}".format(query_complete))
  query_endpoint = "{}/api/v1/query?query={}".format(route, query_complete)
  headers = {"Authorization": "Bearer {}".format(token)}
  # logger.debug("Query Endpoint: {}".format(query_endpoint))
  query_data = requests.post(query_endpoint, headers=headers, verify=False)

  if query_data.status_code == 200:
    qd_json = query_data.json()
    # print("qd_json: {}".format(json.dumps(qd_json, indent=4)))
    if ("data" in qd_json) and ("result" in qd_json["data"]):
      logger.debug("Length of returned result data: {}".format(len(qd_json["data"]["result"])))

      if len(qd_json["data"]["result"]) == 0:
        logger.warning("Empty data returned from query")
      else:
        frame = {}
        series = []
        for metric in qd_json["data"]["result"]:
          # Get/set the datetime series
          if len(frame) == 0:
            frame["datetime"] = pd.Series([datetime.utcfromtimestamp(x[0]) for x in metric["values"]], name="datetime")
          # Need to rework how datetime series is generated and how series are merged together.  Pods come and go and their
          # series of data is shorter and not paded, so we need some sort of "merge" method instead of picking the largest.
          # Also not all series start at the same datetime. ugh
          # else:
          #   logger.debug("length of metrics: {}, length of previous datetime: {}".format(len(metric["values"]), len(frame["datetime"])))
          #   if len(metric["values"]) > len(frame["datetime"]):
          #     frame["datetime"] = pd.Series([datetime.utcfromtimestamp(x[0]) for x in metric["values"]], name="datetime")
          # Get the metrics series
          if series_label not in metric["metric"]:
            logger.debug("Num of values: {}".format(len(metric["values"])))
            if y_unit == "MEM":
              bytes_to_gib = 1024 * 1024 * 1024
              frame[series_label] = pd.Series([float(x[1]) / bytes_to_gib for x in metric["values"]], name=series_label)
            elif y_unit == "NET":
              bytes_to_mib = 1024 * 1024
              frame[series_label] = pd.Series([float(x[1]) / bytes_to_mib for x in metric["values"]], name=series_label)
            elif y_unit == "DISK":
              bytes_to_gb = 1000 * 1000 * 1000
              frame[series_label] = pd.Series([float(x[1]) / bytes_to_gb for x in metric["values"]], name=series_label)
            else:
              frame[series_label] = pd.Series([float(x[1]) for x in metric["values"]], name=series_label)
            series.append(series_label)
          else:
            logger.debug("{}: {}, Num of values: {}".format(series_label, metric["metric"][series_label], len(metric["values"])))
            if y_unit == "MEM":
              bytes_to_gib = 1024 * 1024 * 1024
              frame[metric["metric"][series_label]] = pd.Series([float(x[1]) / bytes_to_gib for x in metric["values"]], name=metric["metric"][series_label])
            elif y_unit == "NET":
              bytes_to_mib = 1024 * 1024
              frame[metric["metric"][series_label]] = pd.Series([float(x[1]) / bytes_to_mib for x in metric["values"]], name=metric["metric"][series_label])
            elif y_unit == "DISK":
              bytes_to_gb = 1000 * 1000 * 1000
              frame[metric["metric"][series_label]] = pd.Series([float(x[1]) / bytes_to_gb for x in metric["values"]], name=metric["metric"][series_label])
            else:
              frame[metric["metric"][series_label]] = pd.Series([float(x[1]) for x in metric["values"]], name=metric["metric"][series_label])
            series.append(metric["metric"][series_label])

        df = pd.DataFrame(frame)

        csv_dir = os.path.join(directory, "csv")
        stats_dir = os.path.join(directory, "stats")

        # Write graph and stats file
        with open("{}/{}.stats".format(stats_dir, fname), "a") as stats_file:
          stats_file.write(str(df.describe()))
        df.to_csv("{}/{}.csv".format(csv_dir, fname))

        l = {"value" : y_title, "date" : ""}
        fig_cluster_node = px.line(df, x="datetime", y=series, labels=l, width=g_width, height=g_height)
        fig_cluster_node.update_layout(title=g_title, legend_orientation="v")
        fig_cluster_node.write_image("{}/{}.png".format(directory, fname))

      logger.info("Completed querying and graphing data")

    else:
      logger.error("Missing data/results field(s) from query result: {}".format(qd_json))
  else:
    logger.error("Query Post status returned: {}".format(query_data.status_code))
    logger.error("Query response: \n{}".format(query_data.text.rstrip()))


def generate_report_html(report_dir):

  report_data = OrderedDict()
  report_data["cluster"] = cluster_data
  report_data["node"] = node_data
  report_data["etcd"] = etcd_data
  report_data["ocp"] = ocp_data
  report_data["resource"] = resource_data
  report_data["acm"] = acm_data
  report_data["talm"] = talm_data

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
        html_file.write("<a href='{0}/{1}.png'><img src='{0}/{1}.png' width='700' height='500'></a><br>\n".format(section,dp))
        html_file.write("<a href='{0}/{1}.png'>graph</a> | \n".format(section, dp))
        html_file.write("<a href='{0}/stats/{1}.stats'>stats</a> | \n".format(section, dp))
        html_file.write("<a href='{0}/csv/{1}.csv'>csv</a><br>\n".format(section, dp))
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
  default_ap_end_time = datetime.utcfromtimestamp(start_time)
  default_ap_start_time = datetime.utcfromtimestamp(start_time - (60 * 60))

  parser = argparse.ArgumentParser(
      description="Query and Graph Prometheus data off a live OpenShift cluster",
      prog="graph-acm-deploy.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/bm/kubeconfig",
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
  logger.info("oc version reports cluster is {}.{}.{}".format(version["major"], version["minor"], version["patch"]))

  # Get node count
  # Determine if SNO, Compact, or Standard
  # Determine if ACM, TALM, Gitops, and LSO are installed
  # Vary queries based on what is installed/analyzed

  route = get_thanos_querier_route(cliargs.kubeconfig)
  if route == "":
    logger.error("Could not obtain the thanos querier route")
    sys.exit(1)
  logger.info("Route to Query: {}".format(route))

  token = get_prometheus_token(cliargs.kubeconfig, version)
  if token == "":
    logger.error("Could not obtain the prometheus token")
    sys.exit(1)

  # Create the results directories to store data into
  report_dir = os.path.join(cliargs.results_directory, "{}-{}".format(cliargs.prefix,
      datetime.utcfromtimestamp(start_time).strftime("%Y%m%d-%H%M%S")))
  logger.debug("Creating report directory: {}".format(report_dir))
  if not os.path.exists(report_dir):
    os.mkdir(report_dir)
  for dir in directories:
    sub_report_dir = os.path.join(report_dir, dir)
    csv_dir = os.path.join(sub_report_dir, "csv")
    stats_dir = os.path.join(sub_report_dir, "stats")
    if not os.path.exists(sub_report_dir):
      os.mkdir(sub_report_dir)
    if not os.path.exists(csv_dir):
      os.mkdir(csv_dir)
    if not os.path.exists(stats_dir):
      os.mkdir(stats_dir)

  with open("{}/analysis".format(report_dir), "a") as report_file:
    report_file.write("Analyzed Cluster Version: {}.{}.{}\n".format(version["major"], version["minor"], version["patch"]))
    report_file.write("Start Time: {}\n".format(cliargs.start_ts))
    report_file.write("End Time: {}\n".format(cliargs.end_ts))
    report_file.write("Examining duration: {}s :: {}\n".format(analyze_duration, str(timedelta(seconds=analyze_duration))))
    report_file.write("Query duration: {}\n".format(q_duration))
    report_file.write("Query route: {}\n".format(route))

  cluster_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  node_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  etcd_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  ocp_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  resource_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  acm_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  talm_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  generate_report_html(report_dir)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
