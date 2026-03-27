echo "Cluster CPU 50 percentile"
echo
cat phase*/cluster/stats/cpu-cluster.stats | grep 50% | awk '{print $2}'
echo
echo "Cluster CPU 95 percentile"
echo
cat phase*/cluster/stats/cpu-cluster.stats | grep 95% | awk '{print $2}'
echo
echo "Cluster CPU 99 percentile"
echo
cat phase*/cluster/stats/cpu-cluster.stats | grep 99% | awk '{print $2}'
echo
echo "Cluster CPU max"
echo
cat phase*/cluster/stats/cpu-cluster.stats | grep max | awk '{print $2}'

echo
echo "Cluster Memory max"
echo
cat phase*/cluster/stats/mem-cluster.stats | grep max | awk '{print $2}'

echo
echo "Cluster Network RCV 95 percentile"
echo
cat phase*/cluster/stats/net-rcv-cluster.stats | grep 95% | awk '{print $2}'
echo
echo "Cluster Network XMT 95 percentile"
echo
cat phase*/cluster/stats/net-xmt-cluster.stats | grep 95% | awk '{print $2}'

# Double check the columns
echo
echo "MCE PVC max"
echo
ls phase*/resource/stats/pvc-usage.stats | xargs -I % sh -c 'echo "$(cat %)"' | grep -v multicluster-engine | grep max | awk '{print $2}'

echo
echo "ACM OBS PVC max"
echo
ls phase*/resource/stats/pvc-usage.stats | xargs -I % sh -c 'echo "$(cat %)"' | grep -v multicluster-engine | grep max | awk '{print $3}'

echo
echo "OpenShift Monitoring PVC max"
echo
ls phase*/resource/stats/pvc-usage.stats | xargs -I % sh -c 'echo "$(cat %)"' | grep -v multicluster-engine | grep max | awk '{print $4}'
