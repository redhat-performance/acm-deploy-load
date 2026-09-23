# Deploy O-Cloud Manager

This document explains how to deploy the O-Cloud Manager Operator with the `rhacm-deploy.yml` playbook.

_**Table of Contents**_

<!-- TOC -->
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Configuration Variables](#configuration-variables)
- [Deployment](#deployment)
- [Verification](#verification)
<!-- /TOC -->

## Overview

The O-Cloud Manager Operator provides O-RAN O2 IMS capabilities for managing cloud infrastructure. Installed after ACM, it is an optional component controlled by the `setup_ocloud_manager` variable in the `rhacm-deploy.yml` playbook.

## Prerequisites

### Default Storage Class Required

**IMPORTANT**: O-Cloud Manager requires a default storage class to be configured on the hub cluster before deployment. The role will validate this prerequisite and fail with a clear error if no default storage class exists.

To verify a default storage class exists:

```console
[root@<bastion> ~]# oc get sc
NAME                                  PROVISIONER                             RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
localstorage-disk-sc                  kubernetes.io/no-provisioner            Delete          WaitForFirstConsumer   false                  17h
ocs-storagecluster-ceph-rbd           openshift-storage.rbd.csi.ceph.com      Delete          Immediate              true                   17h
ocs-storagecluster-cephfs (default)   openshift-storage.cephfs.csi.ceph.com   Delete          Immediate              true                   17h
openshift-storage.noobaa.io           openshift-storage.noobaa.io/obc         Delete          Immediate              false                  17h
```

Look for a storage class with `(default)` next to its name. In the example above, `ocs-storagecluster-cephfs` is the default storage class.

If no default storage class is set, you can mark one as default:

```console
[root@<bastion> ~]# oc annotate storageclass <storageclass-name> storageclass.kubernetes.io/is-default-class=true
```

## Configuration Variables

Add these variables to your `ansible/vars/all.yml` file:

| Variable | Default | Description |
| - | - | - |
| `setup_ocloud_manager` | `false` | Enable O-Cloud Manager deployment. Set to `true` to deploy. |
| `ocloud_manager_source` | `cs-redhat-operator-index-v4-22` | Operator catalog source. Use `redhat-operators` for connected environments or a custom catalog for disconnected. |
| `ocloud_manager_channel` | `stable` | Operator subscription channel (defined in role defaults) |
| `ocloud_manager_namespace` | `oran-o2ims` | Namespace where the operator will be deployed (defined in role defaults) |

### Example Configuration

**Connected environment:**

```yaml
setup_ocloud_manager: true
ocloud_manager_source: redhat-operators
```

**Disconnected environment:**

```yaml
setup_ocloud_manager: true
ocloud_manager_source: cs-redhat-operator-index-v4-22
```

## Deployment

Deploy O-Cloud Manager as part of the ACM hub setup:

```console
(.venv) [root@<bastion> acm-deploy-load]# time ansible-playbook -i ansible/inventory/<cloudname>.local ansible/rhacm-deploy.yml
```

The `rhacm-deploy.yml` playbook will:

1. Deploy ACM and MCE
2. Configure assisted-installer, TALM, and ACM search and observability
3. Add ClusterImageSets
4. Deploy O-Cloud Manager Operator

The `o-cloud-manager-deploy` role performs these steps:

1. Validate default storage class exists
2. Create a directory for installation manifests
3. Template and apply operator subscription
4. Wait for all O-Cloud Manager microservices to be running

## Verification

After the playbook completes, verify all O-Cloud Manager pods are running:

```console
[root@<bastion> ~]# oc get pods -n oran-o2ims
NAME                                             READY   STATUS    RESTARTS   AGE
alarms-server-9779cb89d-x6l7r                    1/1     Running   0          2m
artifacts-server-5844688969-fdswd                1/1     Running   0          2m
cluster-server-6c4848c696-f2vl6                  1/1     Running   0          2m
hardwaremanager-server-66dd96d75b-7bzxv          1/1     Running   0          2m
oran-o2ims-controller-manager-6d84659bbd-kqx66   1/1     Running   0          2m
postgres-server-66b4b7f7c5-58gtd                 1/1     Running   0          2m
provisioning-server-768c54b69-csj8h              1/1     Running   0          2m
resource-server-8b66db54-phcc4                   1/1     Running   0          2m
```
