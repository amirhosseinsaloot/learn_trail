#!/usr/bin/env python3
import json
import os
import shutil
import sys
import time


def main():
    payload = json.load(sys.stdin)
    transcript_path = payload.get("transcript_path")
    if not transcript_path or not os.path.isfile(transcript_path):
        return

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    dest_dir = os.path.join(project_dir, ".claude", "transcript-snapshots")
    os.makedirs(dest_dir, exist_ok=True)

    stamp = time.strftime("%Y%m%dT%H%M%S")
    trigger = payload.get("compaction_trigger", "unknown")
    dest = os.path.join(dest_dir, f"{os.path.basename(transcript_path)}.{trigger}.{stamp}.bak")
    shutil.copy2(transcript_path, dest)


if __name__ == "__main__":
    main()
