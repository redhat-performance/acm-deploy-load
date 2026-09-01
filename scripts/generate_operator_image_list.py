#!/usr/bin/env python3
import argparse
from datetime import datetime
import json
import os
import random
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


def get_random_operator_images(target_count: int) -> list:
    """Retrieves images for `target_count` unique operators, formatted with SHA digests."""
    log(f"Fetching Operator packages from Pyxis (Target count: {target_count})...")

    packages = fetch_pyxis_data("operators/packages", {"page_size": 300, "page": 0})
    if not packages:
        log("No operator packages retrieved from Pyxis.")
        return []

    unique_packages = list({pkg.get("package_name") for pkg in packages if pkg.get("package_name")})

    if len(unique_packages) < target_count:
        selected_packages = unique_packages
    else:
        selected_packages = random.sample(unique_packages, target_count)

    log(f"Selected {len(selected_packages)} unique operators. Fetching image digests...")

    results = []

    for pkg_name in selected_packages:
        bundles = fetch_pyxis_data(
            "operators/bundles",
            {"filter": f'package=="{pkg_name}"', "page_size": 1},
        )

        if not bundles:
            continue

        bundle = bundles[0]

        # Extract SHA digest from root fields or related images
        digest = (
            bundle.get("digest")
            or bundle.get("docker_image_digest")
            or bundle.get("manifest_schema2_digest")
        )

        image_ref = bundle.get("bundle_image") or bundle.get("image") or ""

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
    args = parser.parse_args()

    image_entries = get_random_operator_images(args.count)

    if not image_entries:
        log("Error: Failed to generate image list.")
        sys.exit(1)

    # Output to stdout if requested
    if args.stdout:
        for entry in image_entries:
            print(entry["quay_image"])

    # Write output files unless explicitly disabled
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
        log(f"- Processed {len(image_entries)} images.")
        log(f"- Pull list written to: {txt_file}")
        log(f"- Full metadata written to: {json_file}")


if __name__ == "__main__":
    main()
