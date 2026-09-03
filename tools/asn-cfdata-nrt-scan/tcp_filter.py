#!/usr/bin/env python3
"""Keep masscan endpoints that pass CFData's TCP test."""
import argparse, ipaddress, os, sys
from concurrent.futures import ThreadPoolExecutor
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "*"
sys.path.insert(0, "/opt/cfnb")
import main as cf

def endpoint_from_line(line):
    fields = line.split()
    if len(fields) == 5 and fields[:2] == ["open", "tcp"]:
        try:
            ip = str(ipaddress.IPv4Address(fields[3])); port = int(fields[2])
            return f"{ip}:{port}" if str(port) == fields[2] and 1 <= port <= 65535 else None
        except (ValueError, ipaddress.AddressValueError): return None
    value = line.strip().split("#", 1)[0]
    try:
        ip, port = value.rsplit(":", 1); number = int(port)
        if str(number) != port or not 1 <= number <= 65535: return None
        return f"{ipaddress.IPv4Address(ip)}:{number}"
    except (ValueError, ipaddress.AddressValueError): return None

def check(line):
    endpoint = endpoint_from_line(line)
    if not endpoint: return None
    result = cf.test_node(endpoint + "#JP")
    if not result: return None
    accepted = result[0].split("#", 1)[0].strip()
    return accepted if endpoint_from_line(accepted) == accepted else None

def main():
    p = argparse.ArgumentParser(); p.add_argument("input"); p.add_argument("output"); p.add_argument("--workers", type=int, default=300); p.add_argument("--label", default=None)
    args = p.parse_args(); checked = passed = 0; seen = set()
    with open(args.output, "w", buffering=1024 * 1024) as dst, ThreadPoolExecutor(max_workers=args.workers) as pool:
        for endpoint in pool.map(check, open(args.input, errors="replace")):
            checked += 1
            if endpoint and endpoint not in seen: seen.add(endpoint); dst.write(endpoint + "\n"); passed += 1
        dst.flush(); os.fsync(dst.fileno())
    print(f"completed tcp_checked={checked} tcp_pass={passed} output={args.output}", flush=True)
if __name__ == "__main__": main()
