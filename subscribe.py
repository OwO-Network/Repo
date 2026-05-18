'''
Author: Vincent Young
Telegram: https://t.me/missuo

Subscribe to upstream repositories' Releases. When an upstream Release
changes, download its IPA asset, rename it to follow the OwO naming
convention, and publish it as a new Release in this repository.

Copyright © 2026 by Vincent, All Rights Reserved.
'''
from github import Github
import argparse
import json
import os
import re
import requests

SUBSCRIPTIONS_FILE = "subscriptions.json"
TARGET_REPO = "owo-network/Repo"


def sanitize_version(tag):
    # Drop a leading "v" (e.g. v1.2.3 -> 1.2.3)
    return re.sub(r"^[vV](?=\d)", "", tag.strip())


def sanitize_tag(value):
    # Keep release tags safe for git refs.
    return re.sub(r"[^A-Za-z0-9._-]", "-", value)


def download_asset(url, dest):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)


def process_subscription(g, target_repo, sub):
    src_name = sub["repo"]
    print(f"==> Checking subscription: {src_name}")

    src_repo = g.get_repo(src_name)
    try:
        release = src_repo.get_latest_release()
    except Exception:
        releases = src_repo.get_releases()
        release = releases[0] if releases.totalCount else None
    if release is None:
        print("    No release found, skipped.")
        return False

    tag = release.tag_name
    if tag == sub.get("last_tag"):
        print(f"    No change (still {tag}), skipped.")
        return False

    pattern = sub.get("asset_pattern", r"\.ipa$")
    asset = next(
        (a for a in release.get_assets() if re.search(pattern, a.name)), None)
    if asset is None:
        print(f"    No asset matching /{pattern}/ in {tag}, skipped.")
        return False

    version = sanitize_version(tag)
    template = sub.get(
        "name_template", "{app_name}_{version}_{tweaks}_@repo.owo.network.ipa")
    new_name = template.format(
        app_name=sub["app_name"],
        version=version,
        tweaks=sub.get("tweaks", "Nothing"),
    )

    release_tag = sanitize_tag(f"{sub['app_name']}_{version}")

    # Skip if we already published this exact version.
    try:
        target_repo.get_release(release_tag)
        print(f"    Release '{release_tag}' already exists, marking as seen.")
        sub["last_tag"] = tag
        return True
    except Exception:
        pass

    print(f"    New version {tag}: downloading {asset.name}")
    download_asset(asset.browser_download_url, new_name)

    print(f"    Creating release '{release_tag}' and uploading {new_name}")
    new_release = target_repo.create_git_release(
        tag=release_tag,
        name=f"{sub['app_name']} {version}",
        message=(
            f"Automatically synced from "
            f"https://github.com/{src_name}/releases/tag/{tag}"
        ),
    )
    new_release.upload_asset(new_name, name=new_name)

    if os.path.exists(new_name):
        os.remove(new_name)

    sub["last_tag"] = tag
    print(f"    Done: {new_name}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--token", help="Github token")
    args = parser.parse_args()
    token = args.token or os.environ.get("GITHUB_TOKEN")

    with open(SUBSCRIPTIONS_FILE, "r") as f:
        config = json.load(f)

    g = Github(token)
    target_repo = g.get_repo(TARGET_REPO)

    changed = False
    for sub in config.get("subscriptions", []):
        try:
            if process_subscription(g, target_repo, sub):
                changed = True
        except Exception as e:
            print(f"    Error processing {sub.get('repo')}: {e}")

    if changed:
        with open(SUBSCRIPTIONS_FILE, "w") as f:
            json.dump(config, f, indent=4)
            f.write("\n")
        print("subscriptions.json updated.")
    else:
        print("No subscription changes.")
