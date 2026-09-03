#!/usr/bin/env python3
"""Strict, restart-safe snapshots of a growing masscan -oL file."""
from dataclasses import dataclass
import ipaddress
import os
from pathlib import Path
import tempfile

@dataclass(frozen=True)
class Snapshot:
    endpoints: list[str]
    end_offset: int
    complete_bytes: int

def parse_masscan_line(line: str) -> str | None:
    if not line.endswith("\n"):
        return None
    fields = line.strip().split()
    if len(fields) != 5 or fields[:2] != ["open", "tcp"]:
        return None
    try:
        port = int(fields[2]); ip = str(ipaddress.IPv4Address(fields[3]))
    except (ValueError, ipaddress.AddressValueError):
        return None
    return f"{ip}:{port}" if 1 <= port <= 65535 else None

def parse_endpoint(value: str) -> str | None:
    try:
        if value != value.strip() or value.count(":") != 1:
            return None
        ip, port = value.rsplit(":", 1)
        number = int(port)
        if str(number) != port or not 1 <= number <= 65535:
            return None
        return f"{ipaddress.IPv4Address(ip)}:{number}"
    except (ValueError, ipaddress.AddressValueError):
        return None

def _read_seen(path) -> set[str]:
    p = Path(path)
    return {x.strip() for x in p.read_text(errors="replace").splitlines() if x.strip()} if p.exists() else set()

def snapshot_complete(path, cursor: int, seen_path, max_rows: int | None = None) -> Snapshot:
    data = Path(path).read_bytes()
    if cursor < 0 or cursor > len(data):
        raise ValueError("cursor outside masscan file")
    end = data.rfind(b"\n") + 1
    if end < cursor: end = cursor
    seen = _read_seen(seen_path); endpoints = []; local = set(); consumed_end = cursor
    for raw in data[cursor:end].splitlines(keepends=True):
        consumed_end += len(raw)
        endpoint = parse_masscan_line(raw.decode("utf-8", errors="replace"))
        if endpoint and endpoint not in seen and endpoint not in local:
            local.add(endpoint); endpoints.append(endpoint)
            if max_rows is not None and len(endpoints) >= max_rows: break
    return Snapshot(endpoints, consumed_end, consumed_end - cursor)

def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
        dfd = os.open(path.parent, os.O_DIRECTORY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(name): os.unlink(name)

def persist_input(path, endpoints: list[str]) -> None:
    _atomic_write(Path(path), "".join(f"{x}\n" for x in endpoints))

def validate_endpoint_file(path) -> list[str]:
    rows = [x.strip() for x in Path(path).read_text(errors="replace").splitlines() if x.strip()]
    if any(parse_endpoint(x) != x for x in rows) or len(rows) != len(set(rows)):
        raise ValueError(f"invalid endpoint artifact: {path}")
    return rows
