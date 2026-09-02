#!/usr/bin/env bash
# Run one isolated full-port scan on the authorized scan host.
set -euo pipefail
: "${WORKDIR:=/tmp/cfscan-run}"
: "${CIDRS:?Set CIDRS, e.g. '14.137.229.0/24 103.112.1.0/24'}"
: "${MASSCAN_RATE:=10000}"
: "${CF_FILTER:=/opt/cfnb/xtom_cfdata_filter.py}"
: "${NRT_FILTER:=./nrt_filter.py}"
: "${TCP_WORKERS:=1000}"
: "${HTTP_WORKERS:=1000}"
: "${NRT_WORKERS:=256}"
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
export WORKDIR CIDRS MASSCAN_RATE CF_FILTER NRT_FILTER TCP_WORKERS HTTP_WORKERS NRT_WORKERS
python3 - <<'PY'
import ipaddress, os
out = os.path.join(os.environ['WORKDIR'], 'targets.txt')
networks = []
for token in os.environ['CIDRS'].split():
    networks.append(ipaddress.ip_network(token, strict=True))
with open(out, 'w') as f:
    for net in networks:
        for ip in net:
            f.write(f'{ip}\n')
print(f'targets={sum(n.num_addresses for n in networks)} file={out}')
PY
printf 'prepared targets=%s rate=%s\n' "$(wc -l < "$WORKDIR/targets.txt")" "$MASSCAN_RATE" > "$WORKDIR/run.log"
masscan --include-file "$WORKDIR/targets.txt" -p 1-65535 --rate "$MASSCAN_RATE" --wait 5 -oL "$WORKDIR/masscan.list" >> "$WORKDIR/masscan.log" 2>&1
printf 'MASSCAN_FINISHED\n' >> "$WORKDIR/run.log"
python3 "$CF_FILTER" -in "$WORKDIR/masscan.list" -out "$WORKDIR/cfdata-validated.txt" -batch 10000 -workers "$TCP_WORKERS" -http-workers "$HTTP_WORKERS" >> "$WORKDIR/filter.log" 2>&1
printf 'CF_FILTER_FINISHED\n' >> "$WORKDIR/run.log"
python3 "$NRT_FILTER" "$WORKDIR/cfdata-validated.txt" "$WORKDIR/nrt-validated.txt" --workers "$NRT_WORKERS" >> "$WORKDIR/nrt.log" 2>&1
printf 'NRT_FINISHED\n' >> "$WORKDIR/run.log"
