echo "ACM+MCE Complete CPU 50 percentile"
echo
cat phase*/acm-mce-complete/stats/cpu-acm-mce-complete.stats | grep 50% | awk '{print $2}'
echo
echo "ACM+MCE Complete CPU 95 percentile"
echo
cat phase*/acm-mce-complete/stats/cpu-acm-mce-complete.stats | grep 95% | awk '{print $2}'
echo
echo "ACM+MCE Complete CPU 99 percentile"
echo
cat phase*/acm-mce-complete/stats/cpu-acm-mce-complete.stats | grep 99% | awk '{print $2}'
echo
echo "ACM+MCE Complete CPU max"
echo
cat phase*/acm-mce-complete/stats/cpu-acm-mce-complete.stats | grep max | awk '{print $2}'

echo
echo "ACM+MCE Complete Memory max"
echo
cat phase*/acm-mce-complete/stats/mem-acm-mce-complete.stats | grep max | awk '{print $2}'

echo
echo "ACM+MCE Complete Network RCV 95 percentile"
echo
cat phase*/acm-mce-complete/stats/net-rcv-acm-mce-complete.stats | grep 95% | awk '{print $2}'
echo
echo "ACM+MCE Complete Network XMT 95 percentile"
echo
cat phase*/acm-mce-complete/stats/net-xmt-acm-mce-complete.stats | grep 95% | awk '{print $2}'
