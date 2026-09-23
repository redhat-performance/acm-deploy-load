# ACS Operator Workload Image Curator 

`curate-images-for-acs-testing.yml` queries the Red Hat Pyxis API to generate randomized lists of deployable Operator container images pinned by immutable `sha256` digests. Image mirroring is orchestrated via the **operator-container-images-curator** Ansible role.

## Primary Use Case

This tool automates workload image preparation for Red Hat Advanced Cluster Security (ACS) environment testing. The generated image pull specifications are mirrored via `skopeo` to internal or air-gapped container registries. Pods deployed from these mirrored images serve as target workloads across managed/secured clusters for ACS scanner evaluation, compliance auditing, and vulnerability indexing.

---

## Prerequisites

* **Python 3.8+** (Standard library only; no external `pip` packages required)
* **Skopeo** (for image mirroring tasks)
* **Ansible** (optional, for automated playbooks)

---

## Configuration

### The image list generator script

The `operator-container-images-curator` role uses the `generate_operator_image_list.py` script to fetch and test images that are accessible publicly. It is used in the role to generate a list and sets stdout to capture them for use in the registry sync task. Here's some of the params and env vars it supports:

| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--count` | `-c` | `50` | Number of random operator packages to retrieve. |
| `--stdout` | `-s` | `False` | Outputs raw Quay image specs to `stdout`. Debug logs are routed to `stderr`. |
| `--no-files` | | `False` | Disables writing `.txt` and `.json` artifacts to disk. |

### Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `PYXIS_BASE_URL` | `https://catalog.redhat.com/api/containers/v1` | Pyxis REST API endpoint URL. |
| `TARGET_REGISTRY` | `quay.io` | Destination registry domain prepended to image specs. |
| `OUTPUT_PREFIX` | `deployable_operator_images` | Prefix used for generated output filenames. |
| `OUTPUT_TXT_FILE` | *None* | Explicit override for the plain text output path. |
| `OUTPUT_JSON_FILE` | *None* | Explicit override for the JSON metadata output path. |

---

## Basic usage

The **operator-container-images-curator** Ansible role automates operator containers image mirroring, making them available on a local registry to isolate network latency as a factor that could skew test results:

```bash
ansible-playbook -i inventory/hosts ansible/curate-images-for-acs-testing.yml
```

Override defaults with `--extra-vars`:
```bash
ansible-playbook -i inventory/hosts ansible/curate-images-for-acs-testing.yml \
  --extra-vars "acs_operator_containers_target_count=100 acs_registry_port=5000"
```
