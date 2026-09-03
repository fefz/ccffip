#!/usr/bin/env python3
"""Crash-safe consumer for a growing masscan -oL file."""
import argparse, fcntl, json, os, shlex, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from snapshot import snapshot_complete, persist_input, validate_endpoint_file, parse_endpoint

def atomic_json(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    with tmp.open("w") as f:
        json.dump(obj, f, sort_keys=True, indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    dfd = os.open(path.parent, os.O_DIRECTORY)
    try: os.fsync(dfd)
    finally: os.close(dfd)

def initial_state(args):
    return {"input_byte_cursor": 0, "batch_number": 0, "masscan_open": 0,
            "tcp_checked": 0, "tcp_pass": 0, "colo_checked": 0, "colo_pass": 0,
            "uploaded": 0, "producer_pid": args.producer_pid, "producer_exit_code": None,
            "masscan_done": False, "colo": args.colo, "repo": args.repo or "", "path": args.path or ""}

def load_state(workdir, args):
    path = workdir / "state.json"
    if path.exists(): return json.loads(path.read_text())
    state = initial_state(args); atomic_json(path, state); return state

def run_command(template, input_path, output_path, colo):
    command = template.format(input=shlex.quote(str(input_path)), output=shlex.quote(str(output_path)), colo=shlex.quote(colo))
    return subprocess.run(command, shell=True, check=True).returncode

def append_pending(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = set(path.read_text().splitlines()) if path.exists() else set()
    with path.open("a") as f:
        for row in rows:
            if row not in existing: f.write(row + "\n"); existing.add(row)
        f.flush(); os.fsync(f.fileno())
    dfd = os.open(path.parent, os.O_DIRECTORY)
    try: os.fsync(dfd)
    finally: os.close(dfd)

def atomic_text(path, text):
    tmp = Path(str(path) + ".tmp")
    with tmp.open("w") as f: f.write(text); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    dfd = os.open(path.parent, os.O_DIRECTORY)
    try: os.fsync(dfd)
    finally: os.close(dfd)

def colo_rows(path, label):
    rows = [x.strip() for x in Path(path).read_text(errors="replace").splitlines() if x.strip()]
    expected = []
    for row in rows:
        if row.count("#") != 1: raise ValueError("invalid colo artifact")
        endpoint, got = row.split("#")
        if not got or got != label or parse_endpoint(endpoint) != endpoint: raise ValueError("invalid colo artifact")
        expected.append(row)
    if len(expected) != len(set(expected)): raise ValueError("duplicate colo artifact")
    return expected

def apply_meta(workdir, state, number):
    meta = json.loads((workdir / "batches" / f"{number:06d}.meta").read_text())
    state.update(input_byte_cursor=meta["end_offset"], batch_number=number + 1)
    for key in ("masscan_open", "tcp_checked", "tcp_pass", "colo_checked", "colo_pass", "uploaded"):
        state[key] = state.get(key, 0) + meta.get(key, 0)

def recover_batches(workdir, state):
    batches = workdir / "batches"
    # A crash can leave the artifacts and metadata durable but not the commit
    # marker.  Validate that complete work and finish its marker before replay.
    for meta_path in sorted(batches.glob("*.meta")):
        stem = meta_path.with_suffix("")
        if not stem.with_suffix(".done").exists() and stem.with_suffix(".input").exists() and stem.with_suffix(".tcp").exists() and stem.with_suffix(".colo").exists():
            validate_endpoint_file(stem.with_suffix(".tcp"))
            colo_rows(stem.with_suffix(".colo"), state.get("colo", ""))
            atomic_text(stem.with_suffix(".done"), "done\n")
    while (batches / f"{int(state['batch_number']):06d}.done").exists():
        apply_meta(workdir, state, int(state["batch_number"]))
        atomic_json(workdir / "state.json", state)
    # Rebuild the durable de-duplication set from committed batches.  This
    # closes the crash window between the state replace and seen replace.
    seen = set()
    for done in sorted(batches.glob("*.done")):
        inp = done.with_suffix(".input")
        if inp.exists(): seen.update(x.strip() for x in inp.read_text().splitlines() if x.strip())
    if seen:
        atomic_text(workdir / "seen.txt", "".join(x + "\n" for x in sorted(seen)))

def process_batch(workdir, state, snap, args):
    batches = workdir / "batches"; batches.mkdir(exist_ok=True)
    number = int(state["batch_number"]); stem = batches / f"{number:06d}"
    persist_input(stem.with_suffix(".input"), snap.endpoints)
    tcp_tmp = stem.with_suffix(".tcp.tmp"); colo_tmp = stem.with_suffix(".colo.tmp")
    run_command(args.tcp_command, stem.with_suffix(".input"), tcp_tmp, args.colo)
    tcp_rows = validate_endpoint_file(tcp_tmp); os.replace(tcp_tmp, stem.with_suffix(".tcp"))
    run_command(args.colo_command, stem.with_suffix(".tcp"), colo_tmp, args.colo)
    rows = colo_rows(colo_tmp, args.colo); os.replace(colo_tmp, stem.with_suffix(".colo"))
    append_pending(workdir / "published/pending.txt", rows)
    uploaded = 0
    if args.publisher_command:
        run_command(args.publisher_command, stem.with_suffix(".colo"), workdir / "published/publisher.out", args.colo)
        uploaded = len(rows)
    atomic_text(stem.with_suffix(".meta"), json.dumps({"end_offset": snap.end_offset, "masscan_open": len(snap.endpoints), "tcp_checked": len(snap.endpoints), "tcp_pass": len(tcp_rows), "colo_checked": len(tcp_rows), "colo_pass": len(rows), "uploaded": uploaded}) + "\n")
    atomic_text(stem.with_suffix(".done"), "done\n")
    recover_batches(workdir, state)
    seen_path = workdir / "seen.txt"; seen = set(seen_path.read_text().splitlines()) if seen_path.exists() else set()
    seen.update(snap.endpoints); atomic_text(seen_path, "".join(x + "\n" for x in sorted(seen)))

def producer_finished(workdir, args):
    marker = workdir / "masscan.done"
    if not marker.exists(): return None
    text = marker.read_text().strip()
    marker_code = int(text) if text.isdigit() else 0
    if args.producer_pid:
        try:
            waited, status = os.waitpid(args.producer_pid, os.WNOHANG)
            if waited:
                code = os.waitstatus_to_exitcode(status)
                if text.isdigit() and code != marker_code:
                    raise RuntimeError("producer exit status disagrees with masscan.done")
                return code
        except ChildProcessError:
            if Path(f"/proc/{args.producer_pid}").exists(): return None
            # A non-child cannot expose its exit status; require the marker to carry it.
        except ProcessLookupError: pass
    return marker_code

def run(args):
    workdir = Path(args.workdir); workdir.mkdir(parents=True, exist_ok=True)
    lock = (workdir / "coordinator.lock").open("w"); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = load_state(workdir, args); recover_batches(workdir, state)
    while True:
        masscan = workdir / "masscan.list"
        snap = snapshot_complete(masscan, state["input_byte_cursor"], workdir / "seen.txt", args.batch_lines) if masscan.exists() else None
        if snap and snap.end_offset > state["input_byte_cursor"]:
            if snap.endpoints: process_batch(workdir, state, snap, args)
            else:
                state["input_byte_cursor"] = snap.end_offset; atomic_json(workdir / "state.json", state)
            continue
        exit_code = producer_finished(workdir, args)
        if exit_code is not None:
            if exit_code != 0: raise RuntimeError(f"producer exited {exit_code}")
            state["masscan_done"] = True; state["producer_exit_code"] = exit_code; atomic_json(workdir / "state.json", state)
            (workdir / "run.log").write_text("MASSCAN_FINISHED\n")
            if args.publisher_command:
                run_command(args.publisher_command, workdir / "published/pending.txt", workdir / "published/publisher-final.out", args.colo)
                # Final marker is emitted only after publisher success/readback (publisher contract).
                with (workdir / "run.log").open("a") as f: f.write("COLO_FINISHED\n"); f.flush(); os.fsync(f.fileno())
            break
        if args.once: break
        time.sleep(args.poll_seconds)
    return 0

def main():
    p = argparse.ArgumentParser(); p.add_argument("workdir"); p.add_argument("--colo", default="HKG"); p.add_argument("--repo"); p.add_argument("--path"); p.add_argument("--tcp-command", required=True); p.add_argument("--colo-command", required=True); p.add_argument("--publisher-command"); p.add_argument("--batch-lines", type=int, default=1000); p.add_argument("--poll-seconds", type=float, default=5); p.add_argument("--producer-pid", type=int); p.add_argument("--once", action="store_true")
    return run(p.parse_args())
if __name__ == "__main__": raise SystemExit(main())
