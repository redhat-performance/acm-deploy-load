#!/usr/bin/env bash
#
# Run ACS Prometheus analysis for the hub and every ACM managed cluster.

set -uo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "${script_dir}/.." && pwd)
analyzer="${repo_root}/acm-deploy-load/analyze-prometheus-for-acs.py"

usage() {
  cat <<EOF
Usage: $(basename "$0") -s START_TS -e END_TS [options] [MANAGEDCLUSTER...]

Run ACS Prometheus analysis for the hub and managed clusters. When no managed
cluster names are supplied, all clusters except local-cluster are analyzed.

Required:
  -s START_TS                 UTC start timestamp: YYYY-MM-DDTHH:MM:SSZ
  -e END_TS                   UTC end timestamp: YYYY-MM-DDTHH:MM:SSZ

Options:
  -k HUB_KUBECONFIG           Hub kubeconfig (default: $HOME/mno/kubeconfig)
  -K SPOKE_KUBECONFIGS_DIR    Directory containing <cluster>-kubeconfig files
                              (default: ${repo_root}/../secured_clusters)
  -r RESULTS_DIR              Parent directory for analysis results
                              (default: ${repo_root}/results)
  -b MINUTES                  Analysis buffer on both sides of the interval (default: 5)
  -h                          Show this help text

Set PYTHON to choose the Python interpreter; source .venv/bin/activate first
when the project dependencies are installed in the project virtual environment.
EOF
}

hub_kubeconfig="${HOME}/mno/kubeconfig"
spoke_kubeconfigs_dir="${repo_root}/../secured_clusters"
results_dir="${repo_root}/results"
start_ts=""
end_ts=""
buffer_minutes=5
declare -a requested_clusters=()

while (($#)); do
  case "$1" in
    -s|-e|-k|-K|-r|-b)
      [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
      case "$1" in
        -s) start_ts="$2" ;;
        -e) end_ts="$2" ;;
        -k) hub_kubeconfig="$2" ;;
        -K) spoke_kubeconfigs_dir="$2" ;;
        -r) results_dir="$2" ;;
        -b) buffer_minutes="$2" ;;
      esac
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

[[ -n "$start_ts" && -n "$end_ts" ]] || { echo "ERROR: -s and -e are required" >&2; usage >&2; exit 2; }
[[ "$buffer_minutes" =~ ^[0-9]+$ ]] || { echo "ERROR: -b must be a non-negative integer" >&2; exit 2; }
[[ -f "$analyzer" ]] || { echo "ERROR: analyzer not found: $analyzer" >&2; exit 1; }
[[ -f "$hub_kubeconfig" ]] || { echo "ERROR: Hub kubeconfig not found: $hub_kubeconfig" >&2; exit 1; }
command -v oc >/dev/null || { echo "ERROR: oc is required" >&2; exit 1; }

python_bin="${PYTHON:-python3}"
command -v "$python_bin" >/dev/null || { echo "ERROR: Python interpreter not found: $python_bin" >&2; exit 1; }
mkdir -p "$results_dir"

if ((${#requested_clusters[@]})); then
  clusters=("${requested_clusters[@]}")
else
  mapfile -t clusters < <(oc --kubeconfig "$hub_kubeconfig" get managedclusters \
    -o jsonpath='{range .items[?(@.metadata.name!="local-cluster")]}{.metadata.name}{"\n"}{end}')
fi

run_analysis() {
  local name="$1"
  local kubeconfig="$2"
  local prefix="$3"

  echo "$(date -u +%FT%TZ) :: Analyzing ${name}" >&2
  if "$python_bin" "$analyzer" -k "$kubeconfig" -s "$start_ts" -e "$end_ts" \
    -b "$buffer_minutes" -p "$prefix" "$results_dir"; then
    return 0
  fi

  echo "ERROR: ACS analysis failed for ${name}" >&2
  return 1
}

failures=0
run_analysis "hub" "$hub_kubeconfig" "acs-hub" || failures=$((failures + 1))

for cluster in "${clusters[@]}"; do
  spoke_kubeconfig="${spoke_kubeconfigs_dir}/${cluster}-kubeconfig"
  if [[ ! -f "$spoke_kubeconfig" ]]; then
    echo "WARNING: spoke kubeconfig not found for ${cluster}: ${spoke_kubeconfig}" >&2
    failures=$((failures + 1))
    continue
  fi
  run_analysis "$cluster" "$spoke_kubeconfig" "acs-spoke-${cluster}" || failures=$((failures + 1))
done

if ((failures)); then
  echo "$(date -u +%FT%TZ) :: Completed with ${failures} failure(s); results: ${results_dir}" >&2
  exit 1
fi

echo "$(date -u +%FT%TZ) :: Completed ACS analysis; results: ${results_dir}" >&2
