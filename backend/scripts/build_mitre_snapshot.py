"""Rebuild data/mitre_snapshot.json.gz.

Usage: python -m scripts.build_mitre_snapshot [path/to/enterprise-attack.json]
Without a path the bundle is downloaded from the configured ST_MITRE_URL.
"""

import json
import sys

from app.ingest.mitre import SNAPSHOT_PATH, download_snapshot, parse_bundle, write_snapshot

if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            snap = parse_bundle(json.load(f))
    else:
        snap = download_snapshot()
    write_snapshot(snap)
    print(f"wrote {SNAPSHOT_PATH}: {len(snap['groups'])} groups, {len(snap['techniques'])} techniques, "
          f"{len(snap['software'])} software, {len(snap['campaigns'])} campaigns")
