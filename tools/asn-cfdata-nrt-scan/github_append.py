#!/usr/bin/env python3
"""Concurrency-safe append-only GitHub Contents publisher."""
import argparse, base64, json, os, subprocess, time


def unique_rows(path):
    rows = []
    seen = set()
    for raw in open(path, errors="replace"):
        row = raw.strip()
        if row and row not in seen:
            seen.add(row); rows.append(row)
    return rows


def get_blob(repo, path):
    r = subprocess.run(["gh", "api", f"repos/{repo}/contents/{path}"], text=True, capture_output=True)
    if r.returncode != 0 and "404" in (r.stderr + r.stdout): return None, []
    r.check_returncode(); obj = json.loads(r.stdout)
    return obj, base64.b64decode(obj["content"].replace("\n", "")).decode().splitlines()


def put_blob(repo, path, old, rows, message):
    payload = {"message": message, "content": base64.b64encode(("\n".join(rows) + "\n").encode()).decode()}
    if old: payload["sha"] = old["sha"]
    r = subprocess.run(["gh", "api", "--method", "PUT", f"repos/{repo}/contents/{path}", "--input", "-"], input=json.dumps(payload), text=True, capture_output=True)
    r.check_returncode(); return json.loads(r.stdout)


def publish_once(repo, path, source, batch_size, final=False):
    for attempt in range(3):
        old, remote = get_blob(repo, path)
        remote_set = set(remote)
        new = [row for row in unique_rows(source) if row not in remote_set]
        count = len(new) if final else (len(new) // batch_size) * batch_size
        if not count: return 0
        desired = remote + new[:count]
        try:
            put_blob(repo, path, old, desired, "Complete validated CF endpoints" if final else "Append validated CF endpoints")
            check_old, check_rows = get_blob(repo, path)
            if check_rows != desired or len(check_rows) != len(set(check_rows)):
                raise RuntimeError("GitHub read-back validation failed")
            return count
        except subprocess.CalledProcessError:
            if attempt == 2: raise
            time.sleep(1)
    return 0


def main():
    p = argparse.ArgumentParser(); p.add_argument("source"); p.add_argument("--repo", required=True); p.add_argument("--path", required=True); p.add_argument("--batch-size", type=int, default=20); p.add_argument("--poll-seconds", type=int, default=60); p.add_argument("--done-marker")
    args = p.parse_args()
    while True:
        try:
            publish_once(args.repo, args.path, args.source, args.batch_size, final=False)
            if args.done_marker and not os.path.exists(args.done_marker): time.sleep(args.poll_seconds); continue
            publish_once(args.repo, args.path, args.source, args.batch_size, final=True); break
        except Exception as exc:
            print(f"ERROR {exc}", flush=True); time.sleep(args.poll_seconds)

if __name__ == "__main__": main()
