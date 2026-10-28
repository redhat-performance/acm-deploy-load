#!/usr/bin/env bash
#
# Dynamic Spoke Cluster Health Validator & Container Inspector
#

# Optional: Path where kubeconfig files are stored (defaults to current directory)
KUBECONFIG_DIR="${KUBECONFIG_DIR:-.}"

# 1. Dynamically retrieve all managed clusters from ACM (excluding local-cluster)
echo "Querying ACM Hub for managed clusters..."
CLUSTERS=$(oc get managedclusters -o jsonpath='{range .items[?(@.metadata.name!="local-cluster")]}{.metadata.name}{"\n"}{end}')

if [[ -z "${CLUSTERS}" ]]; then
  echo "[ERROR] No managed clusters found on this ACM hub."
  exit 1
fi

echo "Discovered clusters:"
echo "${CLUSTERS}"
echo ""

# 2. Iterate through each discovered spoke cluster
INSPECTION_FAILED=false

for CLUSTER in ${CLUSTERS}; do
  KUBECONFIG_FILE="${KUBECONFIG_DIR}/${CLUSTER}-kubeconfig"
  KUBECONFIG_TEMPORARY=false

  echo "=================================================================="
  echo ">>> Checking Spoke: ${CLUSTER}"
  echo "=================================================================="

  # Hub-side health check
  HUB_AVAIL=$(oc get managedcluster "${CLUSTER}" \
    -o jsonpath='{.status.conditions[?(@.type=="ManagedClusterConditionAvailable")].status}' 2>/dev/null || echo "Unknown")
  HUB_JOINED=$(oc get managedcluster "${CLUSTER}" \
    -o jsonpath='{.status.conditions[?(@.type=="ManagedClusterJoined")].status}' 2>/dev/null || echo "Unknown")

  if [[ "${HUB_AVAIL}" != "True" || "${HUB_JOINED}" != "True" ]]; then
    echo "[WARN] Hub reports cluster '${CLUSTER}' is degraded or offline:"
    echo "       Joined:    ${HUB_JOINED}"
    echo "       Available: ${HUB_AVAIL}"
  else
    echo "[OK] ACM Hub reports cluster '${CLUSTER}' is Joined and Available."
  fi

  # Kubeconfig resolution: Check if file exists locally, or fetch it on-the-fly from ACM secret
  if [[ ! -f "${KUBECONFIG_FILE}" ]]; then
    echo "[INFO] Kubeconfig '${KUBECONFIG_FILE}' not found locally. Attempting to extract from ACM secret..."

    # Create the credential file with restrictive permissions before writing to it.
    if ! (umask 077; : > "${KUBECONFIG_FILE}") || ! chmod 0600 "${KUBECONFIG_FILE}"; then
      echo "[ERROR] Could not create secure kubeconfig file '${KUBECONFIG_FILE}'. Skipping."
      rm -f "${KUBECONFIG_FILE}"
      INSPECTION_FAILED=true
      echo ""
      continue
    fi
    KUBECONFIG_TEMPORARY=true

    # In ACM, the admin kubeconfig secret resides in the spoke cluster's namespace on the hub
    oc get secret "${CLUSTER}-admin-kubeconfig" -n "${CLUSTER}" -o jsonpath='{.data.kubeconfig}' 2>/dev/null | base64 -d > "${KUBECONFIG_FILE}" 2>/dev/null || true

    if [[ ! -s "${KUBECONFIG_FILE}" ]]; then
      echo "[ERROR] Could not locate or extract kubeconfig for '${CLUSTER}'. Skipping."
      if [[ "${KUBECONFIG_TEMPORARY}" == true ]]; then
        rm -f "${KUBECONFIG_FILE}"
      fi
      INSPECTION_FAILED=true
      echo ""
      continue
    fi
    echo "[OK] Successfully extracted kubeconfig to '${KUBECONFIG_FILE}'."
  fi

  # Direct Spoke API Reachability & Node readiness
  if ! oc --kubeconfig "${KUBECONFIG_FILE}" get nodes --request-timeout=5s >/dev/null 2>&1; then
    echo "[ERROR] API server for '${CLUSTER}' unreachable via '${KUBECONFIG_FILE}'. Skipping pod inspection."
    if [[ "${KUBECONFIG_TEMPORARY}" == true ]]; then
      rm -f "${KUBECONFIG_FILE}"
    fi
    INSPECTION_FAILED=true
    echo ""
    continue
  fi

  if ! NODE_STATUS_OUTPUT=$(oc --kubeconfig "${KUBECONFIG_FILE}" get nodes \
    -o jsonpath='{range .items[*]}{.metadata.name}{": "}{range .status.conditions[?(@.type=="Ready")]}{.status}{"\n"}{end}{end}'); then
    echo "[ERROR] Could not query node status for '${CLUSTER}'. Skipping pod inspection."
    if [[ "${KUBECONFIG_TEMPORARY}" == true ]]; then
      rm -f "${KUBECONFIG_FILE}"
    fi
    INSPECTION_FAILED=true
    echo ""
    continue
  fi

  if [[ -z "${NODE_STATUS_OUTPUT}" ]]; then
    UNREADY_NODES=0
  else
    UNREADY_NODES=$(printf '%s\n' "${NODE_STATUS_OUTPUT}" | awk '$2 != "True" { count++ } END { print count + 0 }')
  fi

  if [[ "${UNREADY_NODES}" -gt 0 ]]; then
    echo "[WARN] Spoke has ${UNREADY_NODES} node(s) not in Ready state."
  else
    echo "[OK] Spoke API reachable; all nodes Ready."
  fi

  # Workload Pod Container Counting
  echo ""
  echo "--- Workload Pod Container Counts (Namespace: workload) ---"
  printf "%-50s %s\n" "POD NAME" "CONTAINER COUNT"
  printf "%-50s %s\n" "--------------------------------------------------" "---------------"

  if ! POD_QUERY_OUTPUT=$(oc --kubeconfig "${KUBECONFIG_FILE}" -n workload get pods \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].name}{"\n"}{end}'); then
    echo "[ERROR] Could not query workload pods for '${CLUSTER}'."
    if [[ "${KUBECONFIG_TEMPORARY}" == true ]]; then
      rm -f "${KUBECONFIG_FILE}"
    fi
    INSPECTION_FAILED=true
    echo ""
    continue
  fi

  if [[ -z "${POD_QUERY_OUTPUT}" ]]; then
    POD_OUTPUT=""
  else
    POD_OUTPUT=$(printf '%s\n' "${POD_QUERY_OUTPUT}" | awk '{print $1 "\t" NF-1}')
  fi

  if [[ -z "${POD_OUTPUT}" ]]; then
    echo "No pods found or namespace 'workload' does not exist"
  else
    echo "${POD_OUTPUT}" | awk -F'\t' '{printf "%-50s %s\n", $1, $2}'
  fi

  echo ""
  if [[ "${KUBECONFIG_TEMPORARY}" == true ]]; then
    rm -f "${KUBECONFIG_FILE}"
  fi
done

if [[ "${INSPECTION_FAILED}" == true ]]; then
  echo "[ERROR] One or more spoke inspections failed."
  exit 1
fi
