echo "ACM Observability CPU 50 percentile"
echo
cat phase*/acm-observability/stats/cpu-acm-obs.stats  | grep 50% | awk '{print $2}'
echo
echo "ACM Observability CPU 95 percentile"
echo
cat phase*/acm-observability/stats/cpu-acm-obs.stats  | grep 95% | awk '{print $2}'
echo
echo "ACM Observability CPU 99 percentile"
echo
cat phase*/acm-observability/stats/cpu-acm-obs.stats  | grep 99% | awk '{print $2}'
echo
echo "ACM Observability CPU max"
echo
cat phase*/acm-observability/stats/cpu-acm-obs.stats  | grep max | awk '{print $2}'

echo
echo "ACM Observability Memory max"
echo
cat phase*/acm-observability/stats/mem-acm-obs.stats  | grep max | awk '{print $2}'

echo
echo "ACM Observability Network RCV 95 percentile"
echo
cat phase*/acm-observability/stats/net-rcv-acm-obs.stats  | grep 95% | awk '{print $2}'
echo
echo "ACM Observability Network XMT 95 percentile"
echo
cat phase*/acm-observability/stats/net-xmt-acm-obs.stats  | grep 95% | awk '{print $2}'
