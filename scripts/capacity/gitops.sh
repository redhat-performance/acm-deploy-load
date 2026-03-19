echo "Gitops CPU 50 percentile"
echo
cat phase*/gitops/stats/cpu-gitops.stats | grep 50% | awk '{print $2}'
echo
echo "Gitops CPU 95 percentile"
echo
cat phase*/gitops/stats/cpu-gitops.stats | grep 95% | awk '{print $2}'
echo
echo "Gitops CPU 99 percentile"
echo
cat phase*/gitops/stats/cpu-gitops.stats | grep 99% | awk '{print $2}'
echo
echo "Gitops CPU max"
echo
cat phase*/gitops/stats/cpu-gitops.stats | grep max | awk '{print $2}'

echo
echo "Gitops Memory max"
echo
cat phase*/gitops/stats/mem-gitops.stats | grep max | awk '{print $2}'
