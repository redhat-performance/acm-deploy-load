#!/usr/bin/env bash
#
# Create hosts-file blocks for ACM managed clusters using their Infrastructure
# CRs. No changes are made to /etc/hosts; the generated file can be reviewed
# and applied separately.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: acm-managedcluster-hosts.sh [-k KUBECONFIG] [-o HOSTS_FILE] [-d BASE_DOMAIN] [MANAGEDCLUSTER...]

Generate hosts-file blocks for ACM managed clusters. If no managed-cluster
names are supplied, every cluster except local-cluster is processed.

Options:
  -k KUBECONFIG  Kubeconfig for the ACM hub (uses the active kubeconfig by default).
  -o HOSTS_FILE  Append blocks to this file. By default, a new file is created in /tmp.
  -d BASE_DOMAIN DNS base domain, such as rdu2.scalelab.redhat.com. By default,
                 it is derived from Infrastructure.status.apiServerInternalURL.
  -h             Show this help text.
EOF
}

kubeconfig=""
hosts_file=""
base_domain=""
declare -a requested_clusters=()

while (($#)); do
  case "$1" in
    -k)
      [[ $# -ge 2 ]] || { echo "ERROR: -k requires a value" >&2; exit 2; }
      kubeconfig="$2"
      shift 2
      ;;
    -o)
      [[ $# -ge 2 ]] || { echo "ERROR: -o requires a value" >&2; exit 2; }
      hosts_file="$2"
      shift 2
      ;;
    -d)
      [[ $# -ge 2 ]] || { echo "ERROR: -d requires a value" >&2; exit 2; }
      base_domain="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      requested_clusters+=("$@")
      break
      ;;
    -*)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      requested_clusters+=("$1")
      shift
      ;;
  esac
done

command -v oc >/dev/null || { echo "ERROR: oc is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "ERROR: jq is required" >&2; exit 1; }

declare -a oc_args=()
if [[ -n "$kubeconfig" ]]; then
  oc_args+=(--kubeconfig "$kubeconfig")
fi

oc_hub() {
  oc "${oc_args[@]}" "$@"
}

if [[ -z "$hosts_file" ]]; then
  hosts_file=$(mktemp "${TMPDIR:-/tmp}/acm-managedcluster-hosts.XXXXXX")
else
  : >> "$hosts_file"
fi

declare -a temporary_kubeconfigs=()
cleanup() {
  ((${#temporary_kubeconfigs[@]})) && rm -f "${temporary_kubeconfigs[@]}"
}
trap cleanup EXIT

if ((${#requested_clusters[@]})); then
  clusters=("${requested_clusters[@]}")
else
  mapfile -t clusters < <(oc_hub get managedclusters -o json |
    jq -r '.items[].metadata.name | select(. != "local-cluster")')
fi

if ((${#clusters[@]} == 0)); then
  echo "ERROR: no managed clusters found" >&2
  exit 1
fi

# These routes are the platform applications for which static name resolution
# is required. Each is mapped to every ingress VIP reported by Infrastructure.
platform_apps=(
  aap-ansible-automation-platform
  aap-controller-ansible-automation-platform
  aap-eda-ansible-automation-platform
  aap-hub-ansible-automation-platform
  acm-cli-downloads
  agent-registration-multicluster-engine
  alertmanager-main-openshift-monitoring
  alertmanager-open-cluster-management-observability
  assisted-image-service-multicluster-engine
  assisted-service-multicluster-engine
  canary-openshift-ingress-canary
  cluster-proxy-anp
  cluster-proxy-user
  console-openshift-console
  dittybopper-dittybopper
  downloads-openshift-console
  federate-openshift-user-workload-monitoring
  grafana-open-cluster-management-observability
  hcp-cli-download-multicluster-engine
  images-multicluster-engine
  kam-openshift-gitops
  minio-minio
  multicloud-console
  multicluster-global-hub-grafana-multicluster-global-hub
  oauth-openshift
  observatorium-api-open-cluster-management-observability
  openshift-gitops-server-openshift-gitops
  prometheus-k8s-federate-openshift-monitoring
  prometheus-k8s-openshift-monitoring
  rbac-query-proxy-open-cluster-management-observability
  search-api-open-cluster-management
  thanos-querier-openshift-monitoring
  thanos-ruler-openshift-user-workload-monitoring
)

for cluster in "${clusters[@]}"; do
  echo "Retrieving Infrastructure CR for ${cluster}" >&2
  spoke_kubeconfig=$(mktemp "${TMPDIR:-/tmp}/acm-${cluster}-kubeconfig.XXXXXX")
  chmod 0600 "$spoke_kubeconfig"
  temporary_kubeconfigs+=("$spoke_kubeconfig")

  if ! oc_hub get secret "${cluster}-admin-kubeconfig" -n "$cluster" \
    -o jsonpath='{.data.kubeconfig}' | base64 -d > "$spoke_kubeconfig"; then
    echo "WARNING: unable to retrieve the admin kubeconfig for ${cluster}; skipping" >&2
    continue
  fi

  if [[ ! -s "$spoke_kubeconfig" ]]; then
    echo "WARNING: the admin kubeconfig for ${cluster} is empty; skipping" >&2
    continue
  fi

  if ! infrastructure=$(oc --kubeconfig "$spoke_kubeconfig" get infrastructure cluster -o json); then
    echo "WARNING: unable to retrieve Infrastructure CR from ${cluster}; skipping" >&2
    continue
  fi

  mapfile -t api_ips < <(jq -r '.spec.platformSpec.baremetal.apiServerInternalIPs[]? | select(type == "string" and length > 0)' <<< "$infrastructure")
  mapfile -t ingress_ips < <(jq -r '.spec.platformSpec.baremetal.ingressIPs[]? | select(type == "string" and length > 0)' <<< "$infrastructure")

  if ((${#api_ips[@]} == 0 || ${#ingress_ips[@]} == 0)); then
    echo "WARNING: ${cluster} has no bare-metal API or ingress IPs in Infrastructure.spec; skipping" >&2
    continue
  fi

  cluster_base_domain="$base_domain"
  if [[ -z "$cluster_base_domain" ]]; then
    api_url=$(jq -r '.status.apiServerInternalURL // .status.apiServerURL // empty' <<< "$infrastructure")
    api_host=${api_url#https://}
    api_host=${api_host%%/*}
    api_host=${api_host%%:*}
    if [[ "$api_host" != api.* ]]; then
      echo "WARNING: cannot derive the DNS domain for ${cluster}; use -d BASE_DOMAIN; skipping" >&2
      continue
    fi
    cluster_base_domain=${api_host#api.}
  fi

  {
    printf '# BEGIN %s OCP CLUSTER MANAGED BLOCK\n' "$cluster"
    for ip in "${api_ips[@]}"; do
      printf '%s api.%s\n' "$ip" "$cluster_base_domain"
      printf '%s api-int.%s\n' "$ip" "$cluster_base_domain"
    done
    for ip in "${ingress_ips[@]}"; do
      for app in "${platform_apps[@]}"; do
        printf '%s %s.apps.%s\n' "$ip" "$app" "$cluster_base_domain"
      done
    done
    printf '# END %s OCP CLUSTER MANAGED BLOCK\n' "$cluster"
  } >> "$hosts_file"

  echo "Appended ${cluster} to ${hosts_file}" >&2
done

echo "$hosts_file"
