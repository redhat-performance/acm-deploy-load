echo "ACM No Observability CPU 50 percentile"
echo
cat phase*/acm-complete/stats/cpu-acm-complete-no-obs.stats | grep 50% | awk '{print $2}'
echo
echo "ACM No Observability CPU 95 percentile"
echo
cat phase*/acm-complete/stats/cpu-acm-complete-no-obs.stats | grep 95% | awk '{print $2}'
echo
echo "ACM No Observability CPU 99 percentile"
echo
cat phase*/acm-complete/stats/cpu-acm-complete-no-obs.stats | grep 99% | awk '{print $2}'
echo
echo "ACM No Observability CPU max"
echo
cat phase*/acm-complete/stats/cpu-acm-complete-no-obs.stats | grep max | awk '{print $2}'

echo
echo "ACM No Observability Memory max"
echo
cat phase*/acm-complete/stats/mem-acm-complete-no-obs.stats | grep max | awk '{print $2}'

echo
echo "ACM No Observability Network RCV 95 percentile"
echo
cat phase*/acm-complete/stats/net-rcv-acm-complete-no-obs.stats | grep 95% | awk '{print $2}'
echo
echo "ACM No Observability Network XMT 95 percentile"
echo
cat phase*/acm-complete/stats/net-xmt-acm-complete-no-obs.stats | grep 95% | awk '{print $2}'
