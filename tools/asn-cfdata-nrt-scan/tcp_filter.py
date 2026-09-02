#!/usr/bin/env python3
"""Keep masscan endpoints that pass CFData's TCP test."""
import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor

os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
sys.path.insert(0, '/opt/cfnb')
import main as cf


def check(line):
    line = line.strip()
    if line.startswith('open tcp '):
        fields = line.split()
        if len(fields) < 4:
            return None
        endpoint = f'{fields[3]}:{fields[2]}'
    else:
        endpoint = line.split('#', 1)[0]
    result = cf.test_node(endpoint + '#JP')
    return result[0] if result else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input')
    p.add_argument('output')
    p.add_argument('--workers', type=int, default=1000)
    args = p.parse_args()
    checked = passed = 0
    seen = set()
    with open(args.output, 'w', buffering=1024 * 1024) as dst:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for endpoint in pool.map(check, open(args.input, errors='replace')):
                checked += 1
                if endpoint and endpoint not in seen:
                    seen.add(endpoint)
                    dst.write(endpoint + '\n')
                    dst.flush()
                    passed += 1
                if checked % 1000 == 0:
                    print(f'tcp_checked={checked} tcp_passed={passed}', flush=True)
    print(f'completed tcp_checked={checked} tcp_passed={passed} output={args.output}', flush=True)


if __name__ == '__main__':
    main()
