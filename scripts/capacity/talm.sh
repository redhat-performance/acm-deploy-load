echo "TALM CPU 50 percentile"
echo
cat phase*/talm/stats/cpu-talm.stats | grep 50% | awk '{print $2}'
echo
echo "TALM CPU 95 percentile"
echo
cat phase*/talm/stats/cpu-talm.stats | grep 95% | awk '{print $2}'
echo
echo "TALM CPU 99 percentile"
echo
cat phase*/talm/stats/cpu-talm.stats | grep 99% | awk '{print $2}'
echo
echo "TALM CPU max"
echo
cat phase*/talm/stats/cpu-talm.stats | grep max | awk '{print $2}'

echo
echo "TALM Memory max"
echo
cat phase*/talm/stats/mem-talm.stats | grep max | awk '{print $2}'
