import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
COORD = ROOT / "streaming" / "coordinator.py"


def test_launcher_uses_result_path_without_overwriting_system_path():
    launcher = (ROOT / "streaming" / "run_streaming.sh").read_text()
    assert 'RESULT_PATH' in launcher
    assert '${PATH:-}' not in launcher


def test_coordinator_processes_complete_rows_and_final_marker(tmp_path):
    (tmp_path / "masscan.list").write_text("open tcp 80 192.0.2.1 1\nopen tcp 443 192.0.2.2 1\n")
    (tmp_path / "masscan.done").write_text("0\n")
    tcp = tmp_path / "tcp.py"
    tcp.write_text("import sys; open(sys.argv[2],'w').write(open(sys.argv[1]).read())\n")
    colo = tmp_path / "colo.py"
    colo.write_text("import sys; open(sys.argv[2],'w').write(''.join(x.strip()+'#HKG\\n' for x in open(sys.argv[1]) if x.strip()))\n")
    subprocess.run([sys.executable, str(COORD), str(tmp_path), "--colo", "HKG", "--tcp-command", f"{sys.executable} {tcp} {{input}} {{output}}", "--colo-command", f"{sys.executable} {colo} {{input}} {{output}}"], check=True)
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["masscan_done"] is True
    assert state["tcp_pass"] == state["colo_pass"] == 2
    # Without a configured publisher, the coordinator must not claim publication.
    assert (tmp_path / "run.log").read_text().splitlines() == ["MASSCAN_FINISHED"]
    assert (tmp_path / "published/pending.txt").read_text().splitlines() == ["192.0.2.1:80#HKG", "192.0.2.2:443#HKG"]


def test_coordinator_once_leaves_partial_run_without_terminal_marker(tmp_path):
    (tmp_path / "masscan.list").write_text("open tcp 80 192.0.2.1")
    result = subprocess.run([sys.executable, str(COORD), str(tmp_path), "--once", "--tcp-command", "true", "--colo-command", "true"], check=True)
    assert not (tmp_path / "run.log").exists()
    assert json.loads((tmp_path / "state.json").read_text())["input_byte_cursor"] == 0
