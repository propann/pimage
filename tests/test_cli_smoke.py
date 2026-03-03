from pimage import cli


def test_cli_check_config_smoke(monkeypatch):
    monkeypatch.setattr("sys.argv", ["pimage", "--check-config"])
    assert cli.main() == 0
