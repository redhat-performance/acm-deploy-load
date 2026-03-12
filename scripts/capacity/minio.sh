echo "Minio CPU 50 percentile"
echo
cat  phase*/minio/stats/cpu-minio.stats | grep 50% | awk '{print $2}'
echo
echo "Minio CPU 95 percentile"
echo
cat  phase*/minio/stats/cpu-minio.stats | grep 95% | awk '{print $2}'
echo
echo "Minio CPU 99 percentile"
echo
cat  phase*/minio/stats/cpu-minio.stats | grep 99% | awk '{print $2}'
echo
echo "Minio CPU max"
echo
cat  phase*/minio/stats/cpu-minio.stats | grep max | awk '{print $2}'

echo
echo "Minio Memory max"
echo
cat  phase*/minio/stats/mem-minio.stats | grep max | awk '{print $2}'
