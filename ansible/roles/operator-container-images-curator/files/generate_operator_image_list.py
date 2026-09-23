#!/usr/bin/env python3
import argparse
from datetime import datetime
import json
import os
import random
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

# Environment variable configuration with defaults
PYXIS_BASE_URL = os.getenv("PYXIS_BASE_URL", "https://catalog.redhat.com/api/containers/v1")
TARGET_REGISTRY = os.getenv("TARGET_REGISTRY", "quay.io")
OUTPUT_PREFIX = os.getenv("OUTPUT_PREFIX", "deployable_operator_images")
CUSTOM_TXT_FILE = os.getenv("OUTPUT_TXT_FILE")
CUSTOM_JSON_FILE = os.getenv("OUTPUT_JSON_FILE")


def log(message: str) -> None:
    """Log informational messages to stderr so stdout remains clean for piping."""
    print(message, file=sys.stderr)


def fetch_pyxis_data(endpoint: str, params: dict) -> list:
    """Fetch records from the Pyxis API endpoint."""
    url = f"{PYXIS_BASE_URL}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Pyxis-ACS-Operator-Extractor/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                payload = json.loads(response.read().decode("utf-8"))
                return payload.get("data", [])
    except Exception as e:
        log(f"API Request error on {endpoint}: {e}")
    return []


def is_image_accessible(quay_pull_spec: str) -> bool:
    """Verifies image manifest accessibility using skopeo inspect or direct HTTP Quay API checks."""
    # Method 1: Use skopeo inspect if available on the system
    if shutil.which("skopeo"):
        try:
            cmd = ["skopeo", "inspect", "--raw", f"docker://{quay_pull_spec}"]
            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
            )
            return res.returncode == 0
        except Exception:
            return False

    # Method 2: Pure Python HTTP check against Quay Registry v2 API
    try:
        parts = quay_pull_spec.split("/", 1)
        if len(parts) < 2 or "@" not in parts[1]:
            return False
        repo_path, digest = parts[1].split("@", 1)

        # 1. Acquire anonymous Bearer token for repository pull access
        auth_url = f"https://quay.io/v2/auth?service=quay.io&scope=repository:{repo_path}:pull"
        auth_req = urllib.request.Request(
            auth_url, headers={"User-Agent": "Pyxis-ACS-Operator-Extractor/1.0"}
        )
        with urllib.request.urlopen(auth_req, timeout=5) as auth_resp:
            token = json.loads(auth_resp.read().decode("utf-8")).get("token")

        if not token:
            return False

        # 2. Probe manifest availability via HEAD request
        manifest_url = f"https://quay.io/v2/{repo_path}/manifests/{digest}"
        manifest_req = urllib.request.Request(
            manifest_url,
            method="HEAD",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json",
                "User-Agent": "Pyxis-ACS-Operator-Extractor/1.0",
            },
        )
        with urllib.request.urlopen(manifest_req, timeout=5) as manifest_resp:
            return manifest_resp.status == 200
    except Exception:
        return False


def get_random_operator_images(target_count: int, validate: bool = True) -> list:
    """Retrieves images for `target_count` unique operators, formatted with SHA digests."""
    log(f"Fetching Operator packages from Pyxis (Target count: {target_count})...")

    packages = fetch_pyxis_data("operators/packages", {"page_size": 500, "page": 0})
    if not packages:
        log("No operator packages retrieved from Pyxis.")
        return []

    unique_packages = list({pkg.get("package_name") for pkg in packages if pkg.get("package_name")})
    random.shuffle(unique_packages)

    results = []

    for pkg_name in unique_packages:
        if len(results) >= target_count:
            break

        bundles = fetch_pyxis_data(
            "operators/bundles",
            {"filter": f'package=="{pkg_name}"', "page_size": 1},
        )

        if not bundles:
            continue

        bundle = bundles[0]

        digest = (
            bundle.get("bundle_path_digest")
            or bundle.get("digest")
            or bundle.get("docker_image_digest")
            or bundle.get("manifest_schema2_digest")
        )

        image_ref = (
            bundle.get("bundle_path")
            or bundle.get("bundle_image")
            or bundle.get("image")
            or ""
        )

        if not digest and "@sha256:" in image_ref:
            digest = image_ref.split("@")[-1]

        if not digest and "related_images" in bundle:
            for rel in bundle.get("related_images", []):
                if rel.get("digest"):
                    digest = rel["digest"]
                    break

        if not digest:
            continue

        if not digest.startswith("sha256:"):
            digest = f"sha256:{digest}"

        clean_repo = image_ref.split("@")[0].split(":")[0]
        if "/" in clean_repo:
            repo_path = "/".join(clean_repo.split("/")[1:])
        else:
            repo_path = f"operators/{pkg_name}"

        quay_pull_spec = f"{TARGET_REGISTRY}/{repo_path}@{digest}"

        # Filter out unauthorized or non-existent public images prior to Ansible execution
        if validate:
            if not is_image_accessible(quay_pull_spec):
                log(f"Skipping inaccessible/unauthorized image: {quay_pull_spec}")
                continue

        results.append(
            {
                "operator": pkg_name,
                "csv_name": bundle.get("csv_name", ""),
                "sha_digest": digest,
                "quay_image": quay_pull_spec,
            }
        )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Generate a list of deployable operator container images from Pyxis API for ACS secured cluster targets."
    )
    parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=50,
        help="Number of random operators to extract (default: 50)",
    )
    parser.add_argument(
        "-s",
        "--stdout",
        action="store_true",
        help="Print raw list of quay pull specs directly to stdout for automation",
    )
    parser.add_argument(
        "--no-files",
        action="store_true",
        help="Skip generating disk output files (.txt and .json)",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip image accessibility check against Quay.io",
    )
    args = parser.parse_args()

    image_entries = get_random_operator_images(args.count, validate=not args.skip_validation)

    if not image_entries:
        log("Error: Failed to generate image list.")
        sys.exit(1)

    if args.stdout:
        for entry in image_entries:
            print(entry["quay_image"])

    if not args.no_files:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        txt_file = CUSTOM_TXT_FILE or f"{OUTPUT_PREFIX}_{timestamp}.txt"
        json_file = CUSTOM_JSON_FILE or f"{OUTPUT_PREFIX}_{timestamp}.json"

        with open(txt_file, "w") as tf:
            for entry in image_entries:
                tf.write(f"{entry['quay_image']}\n")

        with open(json_file, "w") as jf:
            json.dump(image_entries, jf, indent=2)

        log(f"\nCompleted successfully:")
        log(f"- Processed {len(image_entries)} valid images.")
        log(f"- Pull list written to: {txt_file}")
        log(f"- Full metadata written to: {json_file}")


if __name__ == "__main__":
    main()
