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
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime

testUsers = ["search-admin", "search-limited-access-user", "search-wide-access-user"]
userClusterCounts = [0, 0, 0]

def getUserToken(user):
  # need support for older oc versions? 
  oc_cmd = ["oc", "create", "token", user, "-n", "open-cluster-management"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("oc create token {} -n open-cluster-management rc: {}".format(user, rc))
    output = ""
  return output

def getManagedClusterList():
  managedClusters = []
  oc_cmd = ["oc", "get", "managedcluster", "-A", "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("benchmark-search, oc get managedcluster rc: {}".format(output))
  mc_data = json.loads(output)
  for item in mc_data["items"]:
    # limited access users will get access to managed clusters only (not the hub - local-cluster)
    if item["metadata"]["name"] != "local-cluster":
      managedClusters.append(item["metadata"]["name"])
  return managedClusters

def createUsers():
  # create cluster-admin svcAccount
  createAdminSvcAcct_cmd = ["oc", "create", "serviceaccount", testUsers[0], "-n", "open-cluster-management"]
  adminrc1, adminoutput1 = command(createAdminSvcAcct_cmd, False, no_log=True)
  createAdminRoleBinding_cmd = ["oc", "create", "clusterrolebinding", testUsers[0], "--clusterrole=cluster-admin", "--serviceaccount=open-cluster-management:{}".format(testUsers[0])]
  adminrc2, adminoutput2 = command(createAdminRoleBinding_cmd, False, no_log=True)
  if (adminrc1 != 0 and adminoutput1.find('already exists') == -1) or (adminrc2 != 0 and adminoutput2.find('already exists') == -1):
    logger.error("Error creating {} test user".format(testUsers[0]))
  
  # create limited access svcAccount - user with access to ONLY 10 clusters
  createLimitedSvcAcct_cmd = ["oc", "create", "serviceaccount", testUsers[1], "-n", "open-cluster-management"]
  limitedRC, limitedOutput = command(createLimitedSvcAcct_cmd, False, no_log=True)
  if (limitedRC != 0 and limitedOutput.find('already exists') == -1):
    logger.error("Error creating {} test user".format(testUsers[1]))

  # create wide access svcAccount - user with access to all BUT 10 clusters
  createWideSvcAcct_cmd = ["oc", "create", "serviceaccount", testUsers[2], "-n", "open-cluster-management"]
  wideRC, wideOutput = command(createWideSvcAcct_cmd, False, no_log=True)
  if (wideRC != 0 and wideOutput.find('already exists') == -1):
    logger.error("Error creating {} test user".format(testUsers[2]))

  # create Role that gives users access to cluster resources in search
  createRole_cmd = ["oc", "create", "clusterrole", "managed-cluster-access", "--verb", "create,get,list,watch", "--resource", "managedclusterviews.view.open-cluster-management.io"]
  roleRC, roleOutput = command(createRole_cmd, False, no_log=True)
  if (roleRC != 0 and roleOutput.find('already exists') == -1):
    logger.error("Error creating managedCluster Role: {}".format(roleRC))

  clusterList = getManagedClusterList()
  userClusterCounts[0] = len(clusterList) + 1 # +1 is to add back local-cluster
  for idx, _ in enumerate(clusterList):
    # if cluster index is less than 10 create rolebinding for both users
    if idx < 10:
      userClusterCounts[1] += 1
      userClusterCounts[2] += 1
      createManagedClusterRoleBinding_cmd = ["oc", "create", "rolebinding", clusterList[idx], "--clusterrole", "managed-cluster-access", "--serviceaccount", "open-cluster-management:{}".format(testUsers[1]), "--serviceaccount", "open-cluster-management:{}".format(testUsers[2]), "-n", clusterList[idx]]
      roleBindingRC, roleBindingOutput = command(createManagedClusterRoleBinding_cmd, False, no_log=True)
      if (roleBindingRC != 0 and roleBindingOutput.find('already exists') == -1):
        logger.error("Error creating RoleBinding for cluster {}: {}".format(clusterList[idx], roleRC))
    # if cluster index is >= 10 create rolebinding for only wide access user (user get access to all but 10 clusters)
    elif idx >= 10 and (idx < len(clusterList) - 10):
      userClusterCounts[2] += 1
      createManagedClusterRoleBinding_cmd = ["oc", "create", "rolebinding", clusterList[idx], "--clusterrole", "managed-cluster-access", "--serviceaccount", "open-cluster-management:{}".format(testUsers[2]), "-n", clusterList[idx]]
      roleBindingRC, roleBindingOutput = command(createManagedClusterRoleBinding_cmd, False, no_log=True)
      if (roleBindingRC != 0 and roleBindingOutput.find('already exists') == -1):
        logger.error("Error creating RoleBinding for cluster {}: {}".format(clusterList[idx], roleRC))

def getTotalResourceCount(URL, TOKEN, user):
  headers = {"Authorization": "Bearer {}".format(TOKEN), "Content-Type": "application/json"}
  resource_count_data = requests.post(URL, headers=headers, json=json.loads('{"query":"query searchResultCount($input: [SearchInput]) {\\n    searchResult: search(input: $input) {\\n        count\\n    }\\n}\\n","variables":{"input":[{"keywords":[],"filters":[{"property":"cluster","values":["!not-exists"]}],"limit":-1}]}}'), verify=False)
  if resource_count_data.status_code == 200:
    qd_json = resource_count_data.json()
    if "errors" in qd_json:
      logger.error("GraphQL error encountered on resource count query: {}".format(qd_json["errors"][0]["message"]))
    elif "data" in qd_json and "searchResult" in qd_json["data"]:
      logger.debug("Total resource count for user {}: {}".format(user, qd_json["data"]["searchResult"][0]["count"]))
      return qd_json["data"]["searchResult"][0]["count"]
  else:
    logger.error("Error while parsing resource count response")
    return 0

# measureQuery - run search query numRequest times and calcuate the min, max & avg response times. 
def measureQuery(URL, TOKEN, numRequests, queryData, queryName):
  queryResArray = []
  min = sys.maxsize
  max = 0
  avg = 0
  for x in range(numRequests):
    try:
      headers = {"Authorization": "Bearer {}".format(TOKEN), "Content-Type": "application/json"}
      start_time = time.perf_counter()
      query_data = requests.post(URL, headers=headers, json=json.loads(queryData), verify=False)
      requestTime = time.perf_counter() - start_time
      if query_data.status_code == 200:
        qd_json = query_data.json()
        if "errors" in qd_json:
          logger.error("GraphQL error encountered on {} iteration {}: {}".format(qd_json["errors"][0]["message"]))
        elif "data" in qd_json:
          # Only add performance specs if query returns successfully
          queryResArray.append(requestTime)
          if requestTime < min:
            min = requestTime
          elif requestTime > max:
            max = requestTime
          if "searchResult" in qd_json["data"]:
            logger.debug("{} data length: {}".format(queryName, len(qd_json["data"]["searchResult"][0]["items"])))
          elif "searchComplete" in qd_json["data"]:
            logger.debug("{} data length: {}".format(queryName, len(qd_json["data"]["searchComplete"])))
      else:
        logger.error("{} iteration {} error: {}".format(queryName, x, query_data.text.rstrip()))
    except:
      logger.error("Error encountered on {} iteration {}".format(queryName, x))

  tempAvg = 0
  for queryTime in queryResArray:
    tempAvg = tempAvg + queryTime

  avg = tempAvg / len(queryResArray)
  # should error be returned if there is one?
  return "{:.3f}".format(min), "{:.3f}".format(max), "{:.3f}".format(avg)

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
    csv_file.write("user,scenario,clusterCount,totalAuthorizedResources,sampleCount,min,max,average\n")

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

  for idx, user in enumerate(testUsers):
    TOKEN = getUserToken(user)

    # measure search api performance
    # Empty cache scenario only runs once as the subsequent queries would have rbac cached already and be more performant. Future iterations could potentially reset the cache each time.
    _, _, emptyCacheAvg = measureQuery(SEARCH_API, TOKEN, 1, '{"query":"query searchResultItems($input: [SearchInput]) {\\n    searchResult: search(input: $input) {\\n        items\\n    }\\n}\\n","variables":{"input":[{"keywords":[],"filters":[{"property":"kind","values":["Pod"]}],"limit":-1}]}}', "query kind:Pod")
    searchKindMin, searchKindMax, searchKindAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchResultItems($input: [SearchInput]) {\\n    searchResult: search(input: $input) {\\n        items\\n    }\\n}\\n","variables":{"input":[{"keywords":[],"filters":[{"property":"kind","values":["Pod"]}],"limit":-1}]}}', "query kind:Pod")
    searchLabelMin, searchLabelMax, searchLabelAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchResultItems($input: [SearchInput]) {\\n    searchResult: search(input: $input) {\\n        items\\n    }\\n}\\n","variables":{"input":[{"keywords":[],"filters":[{"property":"label","values":["vendor=OpenShift"]}],"limit":-1}]}}', "query label:vendor=OpenShift")
    searchStatusMin, searchStatusMax, searchStatusAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchResultItems($input: [SearchInput]) {\\n    searchResult: search(input: $input) {\\n        items\\n    }\\n}\\n","variables":{"input":[{"keywords":[],"filters":[{"property":"status","values":["!=Running"]}],"limit":-1}]}}', "query status!=Running")
    autoNameMin, autoNameMax, autoNameAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchComplete($property:String!,$query:SearchInput,$limit:Int){\\n    searchComplete(property:$property,query:$query,limit:$limit)\\n}\\n","variables":{"property":"name","query":{"keywords":[],"filters":[]},"limit":-1}}', "autocomplete name")
    autoLabelMin, autoLabelMax, autoLabelAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchComplete($property:String!,$query:SearchInput,$limit:Int){\\n    searchComplete(property:$property,query:$query,limit:$limit)\\n}\\n","variables":{"property":"label","query":{"keywords":[],"filters":[]},"limit":-1}}', "autocomplete label")
    autoStatusMin, autoStatusMax, autoStatusAvg = measureQuery(SEARCH_API, TOKEN, cliargs.sample_count, '{"query":"query searchComplete($property:String!,$query:SearchInput,$limit:Int){\\n    searchComplete(property:$property,query:$query,limit:$limit)\\n}\\n","variables":{"property":"status","query":{"keywords":[],"filters":[]},"limit":-1}}', "autocomplete status")

    resourceCount = getTotalResourceCount(SEARCH_API, TOKEN, user)

    with open(search_benchmark_csv_file, "a") as csv_file:
      csv_file.write("{},{},{},{},{},{},{},{}\n".format(user, "Empty cache search [kind:Pod]", userClusterCounts[idx], resourceCount, 1, "", "", emptyCacheAvg))
      csv_file.write("{},{},{},{},{},{},{},{}\n".format(user, "search [kind:Pod]", userClusterCounts[idx], resourceCount, cliargs.sample_count, searchKindMin, searchKindMax, searchKindAvg))
      csv_file.write("{},{},{},{},{},{},{},{}\n".format(user, "search [label:vendor=OpenShift]", userClusterCounts[idx], resourceCount, cliargs.sample_count, searchLabelMin, searchLabelMax, searchLabelAvg))
      csv_file.write("{},{},{},{},{},{},{},{}\n".format(user, "search [status!=Running]", userClusterCounts[idx], resourceCount, cliargs.sample_count, searchStatusMin, searchStatusMax, searchStatusAvg))
      csv_file.write("{},{},{},{},{},{},{},{}\n".format(user, "autocomplete [name]", userClusterCounts[idx], resourceCount, cliargs.sample_count, autoNameMin, autoNameMax, autoNameAvg))
      csv_file.write("{},{},{},{},{},{},{},{}\n".format(user, "autocomplete [label]", userClusterCounts[idx], resourceCount, cliargs.sample_count, autoLabelMin, autoLabelMax, autoLabelAvg))
      csv_file.write("{},{},{},{},{},{},{},{}\n".format(user, "autocomplete [status]", userClusterCounts[idx], resourceCount, cliargs.sample_count, autoStatusMin, autoStatusMax, autoStatusAvg))

if __name__ == "__main__":
  sys.exit(main())