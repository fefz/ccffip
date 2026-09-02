#!/usr/bin/env python3
"""Append validated rows to GitHub in batches, then flush the remainder."""
import argparse
import base64
import json
import subprocess
import time


def unique_rows(path):
    return list(dict.fromkeys(x.strip() for x in open(path, errors="replace") if x.strip()))


def get_blob(repo, path):
    r = subprocess.run(["gh", "api", f"repos/{repo}/contents/{path}"], text=True, capture_output=True, check=True)
    obj = json.loads(r.stdout)
    return obj, base64.b64decode(obj["content"]).decode().splitlines()


def put_blob(repo, path, old, rows, message):
    payload = {"message": message, "content": base64.b64encode(("\n".join(rows) + "\n").encode()).decode()}
    if old:
        payload["sha"] = old["sha"]
    r = subprocess.run(["gh", "api", "--method", "PUT", f"repos/{repo}/contents/{path}", "--input", "-"], input=json.dumps(payload), text=True, capture_output=True, check=True)
    return json.loads(r.stdout)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("--repo", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--batch-size", type=int, default=20)
    p.add_argument("--poll-seconds", type=int, default=60)
    p.add_argument("--done-marker", help="Only finish after this marker file exists")
    args = p.parse_args()
    while True:
        try:
            old, remote = get_blob(args.repo, args.path)
            new = [x for x in unique_rows(args.source) if x not in remote]
            count = (len(new) // args.batch_size) * args.batch_size
            if count:
                put_blob(args.repo, args.path, old, remote + new[:count], "Append validated CF NRT endpoints")
                print(f"uploaded={count} total={len(remote)+count}", flush=True)
            if args.done_marker and not __import__('os').path.exists(args.done_marker):
                time.sleep(args.poll_seconds)
                continue
            old, remote = get_blob(args.repo, args.path)
            new = [x for x in unique_rows(args.source) if x not in remote]
            if new:
                result = put_blob(args.repo, args.path, old, remote + new, "Complete validated CF NRT endpoints")
                print(f"final_flush={len(new)} total={len(remote)+len(new)} commit={result['commit']['sha']}", flush=True)
            break
        except Exception as exc:
            print(f"ERROR {exc}", flush=True)
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
