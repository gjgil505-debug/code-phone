from clipbot.cli import main


def test_cli_status_runs(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(f"data_dir: {tmp_path / 'data'}\n")
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Watching: 0 streams" in out


def test_cli_rejects_unknown_provider(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    try:
        main(["auth", "myspace"])
    except SystemExit as e:
        assert e.code == 2
