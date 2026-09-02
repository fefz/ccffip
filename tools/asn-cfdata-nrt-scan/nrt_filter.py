#!/usr/bin/env python3
"""Keep only CF endpoints whose HTTPS trace reports the requested colo."""
import argparse
import concurrent.futures
import itertools
import os
import re
import subprocess


MASSCAN_LINE = re.compile(r"^open\s+tcp\s+(\d+)\s+(\d{1,3}(?:\.\d{1,3}){3})\s+")


def endpoint_from_line(line):
    line = line.strip()
    match = MASSCAN_LINE.match(line)
    if match:
        port, ip = match.groups()
        return f"{ip}:{port}"
    return line.split("#", 1)[0]


def check(line, sni_host, colo, connect_timeout, max_time):
    endpoint = endpoint_from_line(line)
    if colo.upper() in {"ANY", "ALL", "OFF", "NONE"}:
        return endpoint
    try:
        ip, port = endpoint.rsplit(":", 1)
        cmd = [
            "curl", "--noproxy", "*", "--connect-timeout", str(connect_timeout),
            "--max-time", str(max_time), "-ksS", "--resolve",
            f"{sni_host}:{port}:{ip}",
            f"https://{sni_host}:{port}/cdn-cgi/trace",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=max_time + 2)
        if result.returncode == 0 and any(
            row.strip() == f"colo={colo}" for row in result.stdout.splitlines()
        ):
            return endpoint
    except Exception:
        pass
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--colo", default="NRT", help="Colo to keep; ANY/ALL/OFF disables colo filtering")
    p.add_argument("--sni-host", default="speed.cloudflare.com")
    p.add_argument("--workers", type=int, default=256)
    p.add_argument("--connect-timeout", type=int, default=1)
    p.add_argument("--max-time", type=int, default=4)
    args = p.parse_args()
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    seen = set()
    checked = passed = 0
    with open(args.output, "w", buffering=1024 * 1024) as dst:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            rows = pool.map(
                check,
                open(args.input, errors="replace"),
                itertools.repeat(args.sni_host),
                itertools.repeat(args.colo),
                itertools.repeat(args.connect_timeout),
                itertools.repeat(args.max_time),
            )
            for endpoint in rows:
                checked += 1
                if endpoint and endpoint not in seen:
                    seen.add(endpoint)
                    dst.write(endpoint + "#JP\n")
                    dst.flush()
                    passed += 1
                if checked % 100 == 0:
                    print(f"nrt_checked={checked} nrt={passed}", flush=True)
    print(f"completed nrt_checked={checked} nrt={passed} output={args.output}", flush=True)


if __name__ == "__main__":
    main()
