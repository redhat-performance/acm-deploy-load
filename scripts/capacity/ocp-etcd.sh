echo "OCP Base CPU 50 percentile"
echo
cat phase*/base-ocp/stats/cpu-base-ocp.stats | grep 50% | awk '{print $2}'
echo
echo "OCP Base CPU 95 percentile"
echo
cat phase*/base-ocp/stats/cpu-base-ocp.stats | grep 95% | awk '{print $2}'
echo
echo "OCP Base CPU 99 percentile"
echo
cat phase*/base-ocp/stats/cpu-base-ocp.stats | grep 99% | awk '{print $2}'
echo
echo "OCP Base CPU max"
echo
cat phase*/base-ocp/stats/cpu-base-ocp.stats | grep max | awk '{print $2}'

echo
echo "OCP Base Memory max"
echo
cat phase*/base-ocp/stats/mem-base-ocp.stats | grep max | awk '{print $2}'

echo
echo "ETCD DB Size max"
echo
awk '/max/ {max=$2; for(i=3; i<=NF; i++) if($i>max) max=$i; print max}' phase*/etcd/stats/db-size.stats
