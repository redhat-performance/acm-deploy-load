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
for CLUSTER in ${CLUSTERS}; do
  KUBECONFIG_FILE="${KUBECONFIG_DIR}/${CLUSTER}-kubeconfig"

  echo "=================================================================="
  echo ">>> Checking Spoke: ${CLUSTER}"
  echo "=================================================================="

  # Hub-side health check
  HUB_AVAIL=$(oc get managedcluster "${CLUSTER}" \
    -o jsonpath='{.status.conditions[?(@.type=="ManagedClusterConditionAvailable")].status}' 2>/dev/null || echo "Unknown")
  HUB_JOINED=$(oc get managedcluster "${CLUSTER}" \
    -o jsonpath='{.status.conditions[?(@.type=="ManagedClusterJoined")].status}' 2>/dev/null || echo "Unknown")

  if [[ "${HUB_AVAIL}" != "True" \vert{}\vert{} "${HUB_JOINED}" != "True" ]]; then
    echo "[WARN] Hub reports cluster '${CLUSTER}' is degraded or offline:"
    echo "       Joined:    ${HUB_JOINED}"
    echo "       Available: ${HUB_AVAIL}"
  else
    echo "[OK] ACM Hub reports cluster '${CLUSTER}' is Joined and Available."
  fi

  # Kubeconfig resolution: Check if file exists locally, or fetch it on-the-fly from ACM secret
  if [[ ! -f "${KUBECONFIG_FILE}" ]]; then
    echo "[INFO] Kubeconfig '${KUBECONFIG_FILE}' not found locally. Attempting to extract from ACM secret..."
    
    # In ACM, the admin kubeconfig secret resides in the spoke cluster's namespace on the hub
    oc get secret "${CLUSTER}-admin-kubeconfig" -n "${CLUSTER}" -o jsonpath='{.data.kubeconfig}' 2>/dev/null | base64 -d > "${KUBECONFIG_FILE}" 2>/dev/null || true

    if [[ ! -s "${KUBECONFIG_FILE}" ]]; then
      echo "[ERROR] Could not locate or extract kubeconfig for '${CLUSTER}'. Skipping."
      rm -f "${KUBECONFIG_FILE}"
      echo ""
      continue
    fi
    echo "[OK] Successfully extracted kubeconfig to '${KUBECONFIG_FILE}'."
  fi

  # Direct Spoke API Reachability & Node readiness
  if ! oc --kubeconfig "${KUBECONFIG_FILE}" get nodes --request-timeout=5s >/dev/null 2>&1; then
    echo "[ERROR] API server for '${CLUSTER}' unreachable via '${KUBECONFIG_FILE}'. Skipping pod inspection."
    echo ""
    continue
  fi

  UNREADY_NODES=$(oc --kubeconfig "${KUBECONFIG_FILE}" get nodes \
    -o jsonpath='{range .items[*]}{.metadata.name}{": "}{range .status.conditions[?(@.type=="Ready")]}{.status}{"\n"}{end}{end}' | grep -vc "True" || true)

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

  POD_OUTPUT=$(oc --kubeconfig "${KUBECONFIG_FILE}" -n workload get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].name}{"\n"}{end}' 2>/dev/null | awk '{print $1 "\t" NF-1}')

  if [[ -z "${POD_OUTPUT}" ]]; then
    echo "No pods found or namespace 'workload' does not exist
