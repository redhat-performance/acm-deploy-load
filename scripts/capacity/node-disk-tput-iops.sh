# Grab the max value for each column in the node disk throughput and iops stats files
echo "Node Disk Throughput Read / max"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/disk-tput-read-root-node.stats
echo
echo "Node Disk Throughput Read /var/lib/etcd max"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/disk-tput-read-etcd-node.stats

echo
echo "Node Disk Throughput Write / max"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/disk-tput-write-root-node.stats
echo
echo "Node Disk Throughput Write /var/lib/etcd max"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/disk-tput-write-etcd-node.stats


echo
echo "Node Disk Iops Read / max"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/disk-iops-read-root-node.stats
echo
echo "Node Disk Iops Read /var/lib/etcd max"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/disk-iops-read-etcd-node.stats

echo
echo "Node Disk Iops Write / max"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/disk-iops-write-root-node.stats
echo
echo "Node Disk Iops Write /var/lib/etcd max"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/node/stats/disk-iops-write-etcd-node.stats
