import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("snapshot", ROOT / "streaming" / "snapshot.py")
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


def test_parse_real_masscan_order_and_reject_invalid_rows():
    assert snapshot.parse_masscan_line("open tcp 443 192.0.2.1 123\n") == "192.0.2.1:443"
    assert snapshot.parse_masscan_line("open udp 443 192.0.2.1 123\n") is None
    assert snapshot.parse_masscan_line("open tcp 0 192.0.2.1 123\n") is None
    assert snapshot.parse_masscan_line("open tcp 443 999.0.2.1 123\n") is None
    assert snapshot.parse_masscan_line("open tcp 443 192.0.2.1") is None


def test_snapshot_stops_at_partial_line_and_deduplicates(tmp_path):
    masscan = tmp_path / "masscan.list"
    seen = tmp_path / "seen.txt"
    masscan.write_text("open tcp 80 192.0.2.1 1\nopen tcp 80 192.0.2.1 2\nopen tcp 443 192.0.2.2")
    result = snapshot.snapshot_complete(masscan, 0, seen)
    assert result.end_offset == len("open tcp 80 192.0.2.1 1\nopen tcp 80 192.0.2.1 2\n")
    assert result.endpoints == ["192.0.2.1:80"]
    assert not seen.exists()  # caller persists only after batch input succeeds


def test_snapshot_excludes_durable_seen_and_persists_input_atomically(tmp_path):
    masscan = tmp_path / "masscan.list"
    seen = tmp_path / "seen.txt"
    batch = tmp_path / "batch.input"
    masscan.write_text("open tcp 80 192.0.2.1 1\nopen tcp 443 192.0.2.2 1\n")
    seen.write_text("192.0.2.1:80\n")
    result = snapshot.snapshot_complete(masscan, 0, seen)
    snapshot.persist_input(batch, result.endpoints)
    assert batch.read_text() == "192.0.2.2:443\n"
    assert result.end_offset == masscan.stat().st_size
    assert snapshot.validate_endpoint_file(batch) == ["192.0.2.2:443"]
