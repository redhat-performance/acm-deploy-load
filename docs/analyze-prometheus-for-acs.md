# ACS Prometheus Analysis

`acm-deploy-load/analyze-prometheus-for-acs.py` queries Prometheus or Thanos
on a live OpenShift cluster and creates an Advanced Cluster Security (ACS)
resource-consumption report. It is intended to be run against the ACM Hub (when 
Central is colocated) and each secured managed cluster for the same UTC analysis 
interval.

## Prerequisites

- An authenticated kubeconfig for the Hub and every managed cluster to analyze.
- `oc`, Python 3, and the project Python dependencies. Run `./bootstrap.sh` and
  `source .venv/bin/activate` on the bastion when necessary.
- Chrome or another supported Plotly/Kaleido image-export dependency for PNG
  generation.
- Network and DNS access from the bastion to the Hub and spoke API servers,
  Thanos routes, and ACS routes.

### Managed-cluster host entries

Before collecting spoke data, create a hosts-file fragment from each spoke's
`Infrastructure` CR:

```bash
scripts/acm-managedcluster-hosts.sh -k ~/mno/kubeconfig
```

The script prints the path to a temporary hosts file. Review it, then manually
append it to the bastion's hosts file. This operation is deliberately manual;
the script never changes `/etc/hosts` itself.

```bash
hosts_fragment=/tmp/acm-managedcluster-hosts.XXXXXX
sudo cp /etc/hosts /etc/hosts.pre-acs-analysis
sudo sh -c "cat '${hosts_fragment}' >> /etc/hosts"
```

Replace `hosts_fragment` with the path printed by the script. Do not append a
fragment blindly: confirm that its API and ingress VIPs match the intended
managed clusters and avoid appending duplicate blocks on repeated runs.

`acm-managedcluster-hosts.sh` lists ManagedClusters from the Hub, obtains each
cluster's admin kubeconfig secret, reads its `Infrastructure/cluster` CR, and
writes API, API-int, and platform-application ingress mappings. It requires
Hub permission to read the per-cluster admin kubeconfig secrets and reach each
spoke API server.

## Run Hub and spoke analysis

Use `scripts/post-acs-load-data-collection.sh` for a single, structured run
across the Hub and all discovered managed clusters:

```bash
source .venv/bin/activate

scripts/post-acs-load-data-collection.sh \
  -k ~/mno/kubeconfig \
  -K ../secured_clusters \
  -s 2026-11-10T01:00:00Z \
  -e 2026-11-10T06:00:00Z \
  -r results/
```

The runner obtains the managed-cluster list from the Hub with `oc get
managedclusters`, excluding `local-cluster`. For every cluster it expects a
kubeconfig named `<cluster>-kubeconfig` in the directory supplied with `-K`.
It uses the prefixes `acs-hub` and `acs-spoke-<cluster>` so reports created in
rapid succession remain distinct. Missing kubeconfigs or failed analyses are
reported, while remaining clusters continue to be analyzed; the script exits
nonzero if any cluster fails.

To limit the run to named managed clusters, add them after the options:

```bash
scripts/post-acs-load-data-collection.sh \
  -s 2026-11-10T01:00:00Z -e 2026-11-10T06:00:00Z \
  standard-00001 standard-00002
```

The direct equivalent for one cluster is:

```bash
python acm-deploy-load/analyze-prometheus-for-acs.py \
  -k ../secured_clusters/standard-00001-kubeconfig \
  -s 2026-11-10T01:00:00Z \
  -e 2026-11-10T06:00:00Z \
  results/
```

## Analyzer behavior and output

The analyzer defaults to a one-hour interval when `-s` and `-e` are omitted.
It adds a five-minute buffer to both ends by default (`-b` changes this),
discovers the OCP version and Thanos route, obtains a Prometheus token, and
samples the requested interval at one-minute resolution.

Each invocation creates `<prefix>-<run-timestamp>/` beneath the results
directory. It contains:

- `analysis` — interval, buffer, OCP version, and query-route metadata.
- `report.html` — linked and embedded report of generated graphs.
- One directory per section, containing PNG charts, `csv/` time series, and
  `stats/` descriptive statistics with 95th and 99th percentiles.

All runs include cluster, node, etcd, resource, base OpenShift, and core
OpenShift sections. `acs-complete`, `acs-central`,
`acs-scanner-indexer`, and `acs-scanner-matcher` are included only when the
`rhacs-operator` namespace exists. The optional `lso` section is included when
the Local Storage Operator namespace exists.

The ACS sections include namespace and pod CPU/memory/network consumption;
Central alert, scanning, Postgres, gRPC, HTTP, runtime, process, cache, and
secured-cluster metrics; and Scanner V4 Indexer and Matcher workload,
database-pool, and gRPC metrics. The Central section queries every metric
family captured in `central-snippet.prom`; purpose-built charts are retained
for the original key Central metrics, while the remaining families are emitted
as `central-<metric-name>` artifacts.
`acs-complete` also creates separate read and write filesystem-throughput
charts for every Hub node, with one line per `rhacs-operator` pod. These are
named `disk-read-tput-acs-pods-<node>.png` and
`disk-write-tput-acs-pods-<node>.png`, and report MB/s.

The Indexer and Matcher sections intentionally select operationally useful
metrics and do not query every family exposed in
`scanner-v4-indexer-snippet.prom` or `scanner-v4-matcher-snippet.prom`.
