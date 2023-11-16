#!/usr/bin/env python3
#
# benchmark search api performance
#
#  Copyright 2022 Red Hat
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import argparse
from utils.command import command
from datetime import datetime
import logging
import time
import json
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime

testUsers = ["search-admin"]

def getUserToken(user):
  # need support for older oc versions? 
  oc_cmd = ["oc", "create", "token", user, "-n", "open-cluster-management"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("oc create token {} -n open-cluster-management rc: {}".format(user, rc))
    output = ""
  return output

def createUsers():
  # create cluster-admin
  createAdminSvcAcct_cmd = ["oc", "create", "serviceaccount", testUsers[0], "-n", "open-cluster-management"]
  adminrc1, adminoutput1 = command(createAdminSvcAcct_cmd, False, no_log=True)
  createAdminRoleBinding_cmd = ["oc", "create", "rolebinding", testUsers[0], "--role=cluster-admin", "--serviceaccount=open-cluster-management:{}".format(testUsers[0])]
  adminrc2, adminoutput2 = command(createAdminRoleBinding_cmd, False, no_log=True)
  if (adminrc1 != 0 and adminoutput1.find('already exists') == -1) or (adminrc2 != 0 and adminoutput2.find('already exists') == -1):
    logger.error("Error creating {} test user".format(testUsers[0]))

  # todo create limited access user
  # oc create serviceaccount search-user-1 -n open-cluster-management
  # oc create role search-user-1 --verb=list --resource=configmaps -n open-cluster-management (todo what access to give? 10 cluster limit)
  # oc create rolebinding search-user-1 --role=cluster-admin --serviceaccount=open-cluster-management:search-user-1 -n open-cluster-management

  # todo create wide-access-user
  # oc create serviceaccount search-user-1 -n open-cluster-management
  # oc create role search-user-1 --verb=list --resource=configmaps -n open-cluster-management (todo what access to give? all clusters but limit resources?)
  # oc create rolebinding search-user-1 --role=cluster-admin --serviceaccount=open-cluster-management:search-user-1 -n open-cluster-management

def getTotalResourceCount():
  searchDB_cmd = ["oc", "get", "pods", "-n", "open-cluster-management", "-l", "app=search,name=search-postgres", "-o", "custom-columns=POD:.metadata.name", "--no-headers", "-o", "json"]
  rc, searchDBPod = command(searchDB_cmd, False, retries=3, no_log=True)
  route_data = json.loads(searchDBPod)
  parsedSearchDBPod = route_data["items"][0]["metadata"]["name"]
  total_resources_cmd = ["oc", "rsh", "-n", "open-cluster-management", parsedSearchDBPod, "psql", "-d", "search", "-U", "searchuser", "-t", "-c", "SELECT count(*) from search.resources;"]
  rc, output = command(total_resources_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("getTotalResourceCount rc: {}".format(rc))
  return json.loads(output)

# measureQuery - run search query numRequest times and calcuate the min, max & avg response times. 
def measureQuery(URL, TOKEN, numRequests, queryData, queryName):
  queryResArray = []
  min = sys.maxsize
  max = 0
  avg = 0
  for x in range(numRequests):
    start_time = time.perf_counter()
    search_cmd = [
      'curl',
      '--insecure',
      '--location',
      '--request',
      'POST',
      URL,
      '--header',
      'Authorization: Bearer {}'.format(TOKEN),
      '--header',
      'Content-Type: application/json',
      '--data-raw',
      queryData
    ]
    rc, _ = command(search_cmd, False, retries=3, no_log=True)
    requestTime = time.perf_counter() - start_time
    if rc != 0:
      logger.error("Error encountered on {} iteration {}: {}".format(queryName, x, rc))

    queryResArray.append(requestTime)
    if requestTime < min:
      min = requestTime
    elif requestTime > max:
      max = requestTime

  tempAvg = 0
  for queryTime in queryResArray:
    tempAvg = tempAvg + queryTime

  avg = tempAvg / len(queryResArray)
  # should error be returned if there is one?
  return min, max, avg

def main():
  # create csv file for results
  parser = argparse.ArgumentParser(
      description="Benchmark search query response times",
      prog="benchmark-search.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("results_directory", type=str, help="The location to place benchamrk data")
  parser.add_argument("--sample-count", type=int, default=10, help="Uses previously stored raw data")
  cliargs = parser.parse_args()
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  search_benchmark_csv_file = "{}/search-benchmark-{}.csv".format(cliargs.results_directory, ts)
  with open(search_benchmark_csv_file, "w") as csv_file:
    csv_file.write("user,scenario,totalResources,sampleCount,min,max,average\n")

  # create users
  createUsers()

  # search-api route is created in ansible/roles/rhacm-hub-deploy/tasks/main
  get_route_cmd = ["oc", "get", "route", "search-api", "-n", "open-cluster-management", "-o", "json"]
  rc, getRouteOutput = command(get_route_cmd, False, retries=3)
  if rc != 0:
    logger.error("GET search route errored: {}".format(rc))
  route_data = json.loads(getRouteOutput)
  searchApiRoute = route_data["spec"]["host"]
  SEARCH_API="https://{}/searchapi/graphql".format(searchApiRoute)

  for user in testUsers:
    TOKEN = getUserToken(user)

    resourceCount = getTotalResourceCount()

    # measure search api performance
    # Empty cache scenario only runs once as the subsequent queries would have rbac cached already and be more performant. Future iterations could potentially reset the cache each time.
    _, _, emptyCacheAvg = measureQuery(SEARCH_API, TOKEN, 1, '{"query":"query searchResultItems($input: [SearchInput]) {\n    searchResult: search(input: $input) {\n        items\n        }\n    }\n","variables":{"input":[{"keywords":[],"filters":[{"property":"kind","values":["Pod"]}]}]}}', "query kind:Pod")
    searchKindMin, searchKindMax, searchKindAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchResultItems($input: [SearchInput]) {\n    searchResult: search(input: $input) {\n        items\n        }\n    }\n","variables":{"input":[{"keywords":[],"filters":[{"property":"kind","values":["Pod"]}]}]}}', "query kind:Pod")
    searchLabelMin, searchLabelMax, searchLabelAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchResultItems($input: [SearchInput]) {\n    searchResult: search(input: $input) {\n        items\n        }\n    }\n","variables":{"input":[{"keywords":[],"filters":[{"property":"label","values":["app=search"]}]}]}}', "query label:app=search")
    searchStatusMin, searchStatusMax, searchStatusAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchResultItems($input: [SearchInput]) {\n    searchResult: search(input: $input) {\n        items\n        }\n    }\n","variables":{"input":[{"keywords":[],"filters":[{"property":"status","values":["!=Running"]}]}]}}', "query status!=Running")
    autoNameMin, autoNameMax, autoNameAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchComplete($property:String!,$query:SearchInput,$limit:Int){\n    searchComplete(property:$property,query:$query,limit:$limit)\n}\n","variables":{"property":"name","query":{"keywords":[],"filters":[],"limit":10000},"limit":10000}}', "autocomplete name")
    autoLabelMin, autoLabelMax, autoLabelAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchComplete($property:String!,$query:SearchInput,$limit:Int){\n    searchComplete(property:$property,query:$query,limit:$limit)\n}\n","variables":{"property":"label","query":{"keywords":[],"filters":[],"limit":10000},"limit":10000}}', "autocomplete label")
    autoStatusMin, autoStatusMax, autoStatusAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchComplete($property:String!,$query:SearchInput,$limit:Int){\n    searchComplete(property:$property,query:$query,limit:$limit)\n}\n","variables":{"property":"status","query":{"keywords":[],"filters":[],"limit":10000},"limit":10000}}', "autocomplete status")

    with open(search_benchmark_csv_file, "a") as csv_file:
      csv_file.write("{},{},{},{},{},{},{}\n".format(user, "Empty cache search [kind:Pod]", resourceCount, 1, "", "", emptyCacheAvg))
      csv_file.write("{},{},{},{},{},{},{}\n".format(user, "search [kind:Pod]", resourceCount, cliargs.sample_count, searchKindMin, searchKindMax, searchKindAvg))
      csv_file.write("{},{},{},{},{},{},{}\n".format(user, "search [label:app=search]", resourceCount, cliargs.sample_count, searchLabelMin, searchLabelMax, searchLabelAvg))
      csv_file.write("{},{},{},{},{},{},{}\n".format(user, "search [status!=Running]", resourceCount, cliargs.sample_count, searchStatusMin, searchStatusMax, searchStatusAvg))
      csv_file.write("{},{},{},{},{},{},{}\n".format(user, "autocomplete [name]", resourceCount, cliargs.sample_count, autoNameMin, autoNameMax, autoNameAvg))
      csv_file.write("{},{},{},{},{},{},{}\n".format(user, "autocomplete [label]", resourceCount, cliargs.sample_count, autoLabelMin, autoLabelMax, autoLabelAvg))
      csv_file.write("{},{},{},{},{},{},{}\n".format(user, "autocomplete [status]", resourceCount, cliargs.sample_count, autoStatusMin, autoStatusMax, autoStatusAvg))
    
    # todo reset the search-api cache fro new user

if __name__ == "__main__":
  sys.exit(main())