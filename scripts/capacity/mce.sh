echo "MCE Complete CPU 50 percentile"
echo
cat phase*/mce-complete/stats/cpu-mce-complete.stats  | grep 50% | awk '{print $2}'
echo
echo "MCE Complete CPU 95 percentile"
echo
cat phase*/mce-complete/stats/cpu-mce-complete.stats  | grep 95% | awk '{print $2}'
echo
echo "MCE Complete CPU 99 percentile"
echo
cat phase*/mce-complete/stats/cpu-mce-complete.stats  | grep 99% | awk '{print $2}'
echo
echo "MCE Complete CPU max"
echo
cat phase*/mce-complete/stats/cpu-mce-complete.stats  | grep max | awk '{print $2}'

echo
echo "MCE Complete Memory max"
echo
cat phase*/mce-complete/stats/mem-mce-complete.stats  | grep max | awk '{print $2}'

echo
echo "MCE Complete Network RCV 95 percentile"
echo
cat phase*/mce-complete/stats/net-rcv-mce-complete.stats  | grep 95% | awk '{print $2}'
echo
echo "MCE Complete Network XMT 95 percentile"
echo
cat phase*/mce-complete/stats/net-xmt-mce-complete.stats  | grep 95% | awk '{print $2}'
