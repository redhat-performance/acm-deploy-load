# ACS Operator Workload Image Generator

`generate_operator_image_list.py` queries the Red Hat Pyxis API to generate randomized lists of deployable Operator container images pinned by immutable `sha256` digests.

## Primary Use Case

This tool automates workload generation for Red Hat Advanced Cluster Security (ACS) environment testing. The generated image pull specifications are mirrored via `skopeo` to internal or air-gapped container registries. Pods deployed from these mirrored images serve as target workloads across managed/secured clusters for ACS scanner evaluation, compliance auditing, and vulnerability indexing.

---

## Prerequisites

* **Python 3.8+** (Standard library only; no external `pip` packages required)
* **Skopeo** (for image mirroring tasks)
* **Ansible** (optional, for automated playbooks)

---

## Configuration

### Command-Line Arguments

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

## Basic Usage

### Standard File Generation
Generates 50 random operator image specs and writes timestamped files to disk:
```bash
python3 generate_operator_image_list.py
```
