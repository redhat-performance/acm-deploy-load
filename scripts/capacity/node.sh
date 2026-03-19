# Grab the max value for each column in the node stats files
echo "Node CPU 50 percentile"
echo
awk '/50%/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/cpu-node.stats
echo
echo "Node CPU 95 percentile"
echo
awk '/95%/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/cpu-node.stats
echo
echo "Node CPU 99 percentile"
echo
awk '/99%/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/cpu-node.stats
echo
echo "Node CPU max"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/cpu-node.stats

echo
echo "Node Memory max"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/mem-node.stats

echo
echo "Node Disk Space Utilization root"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/disk-util-root-node.stats
echo
echo "Node Disk Space Utilization /var/lib/etcd"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/disk-util-etcd-node.stats
echo
echo "Node Disk Space Utilization /var/lib/containers"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/disk-util-containers-node.stats
