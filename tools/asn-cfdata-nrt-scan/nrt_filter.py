#!/usr/bin/env python3
"""Keep CF TCP endpoints whose HTTPS trace reports the requested colo."""
import argparse
import concurrent.futures
import itertools
import os
import subprocess
from ipaddress import IPv4Address


def endpoint_from_line(line):
    fields = line.strip().split()
    if len(fields) == 5 and fields[:2] == ["open", "tcp"]:
        try:
            port = int(fields[2]); ip = str(IPv4Address(fields[3]))
            return f"{ip}:{port}" if 1 <= port <= 65535 else None
        except ValueError:
            return None
    endpoint = line.strip().split("#", 1)[0]
    try:
        ip, port = endpoint.rsplit(":", 1)
        return f"{IPv4Address(ip)}:{int(port)}" if 1 <= int(port) <= 65535 else None
    except ValueError:
        return None


def format_output(endpoint, label):
    return f"{endpoint}#{label}" if label else endpoint


def check(line, sni_host, colo, connect_timeout, max_time):
    endpoint = endpoint_from_line(line)
    if not endpoint:
        return None
    if colo.upper() in {"ANY", "ALL", "OFF", "NONE"}:
        return endpoint
    ip, port = endpoint.rsplit(":", 1)
    cmd = ["curl", "--noproxy", "*", "--connect-timeout", str(connect_timeout), "--max-time", str(max_time), "-ksS", "--resolve", f"{sni_host}:{port}:{ip}", f"https://{sni_host}:{port}/cdn-cgi/trace"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=max_time + 2)
        if result.returncode == 0 and any(row.strip() == f"colo={colo}" for row in result.stdout.splitlines()):
            return endpoint
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--colo", default="NRT")
    p.add_argument("--label", default=None, help="final semantic label, e.g. HKG")
    p.add_argument("--sni-host", default="speed.cloudflare.com")
    p.add_argument("--workers", type=int, default=128)
    p.add_argument("--connect-timeout", type=int, default=1); p.add_argument("--max-time", type=int, default=4)
    args = p.parse_args(); os.environ["NO_PROXY"] = os.environ["no_proxy"] = "*"
    seen = set(); checked = passed = 0
    label = args.label or (args.colo if args.colo.upper() not in {"ANY", "ALL", "OFF", "NONE"} else None)
    with open(args.output, "w", buffering=1024 * 1024) as dst, concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = pool.map(check, open(args.input, errors="replace"), itertools.repeat(args.sni_host), itertools.repeat(args.colo), itertools.repeat(args.connect_timeout), itertools.repeat(args.max_time))
        for endpoint in rows:
            checked += 1
            output = format_output(endpoint, label) if endpoint else None
            if output and output not in seen:
                seen.add(output); dst.write(output + "\n"); passed += 1
    print(f"completed colo_checked={checked} colo_pass={passed} output={args.output}", flush=True)


if __name__ == "__main__":
    main()
