import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hkg_label_and_no_jp():
    nrt = load('nrt_filter')
    assert nrt.format_output('192.0.2.1:443', 'HKG') == '192.0.2.1:443#HKG'
    assert '#JP' not in nrt.format_output('192.0.2.1:443', 'HKG')


def test_tcp_check_uses_bare_endpoint(monkeypatch):
    fake = types.SimpleNamespace(test_node=lambda value: [value])
    monkeypatch.setitem(sys.modules, 'main', fake)
    tcp = load('tcp_filter')
    seen = []
    monkeypatch.setattr(tcp.cf, 'test_node', lambda value: (seen.append(value) or ['192.0.2.1:443']))
    assert tcp.check('open tcp 443 192.0.2.1 1') == '192.0.2.1:443'
    assert seen == ['192.0.2.1:443#JP']
