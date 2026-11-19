from pathlib import Path

import pytest

from app import __main__ as cli


def test_parser_accepts_env_file() -> None:
    args = cli.build_parser().parse_args(
        ["--env-file", "config/custom.env", "--host", "0.0.0.0", "--port", "9000"]
    )

    assert args.env_file == "config/custom.env"
    assert args.host == "0.0.0.0"
    assert args.port == 9000


def test_main_passes_uvicorn_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict = {}

    def fake_run(app: str, **kwargs) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    env_file = tmp_path / "custom.env"
    env_file.write_text("VISION_MODEL=custom/model\n", encoding="utf-8")

    cli.main(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "8001",
            "--reload",
            "--reload-dir",
            "app",
            "--env-file",
            str(env_file),
        ]
    )

    assert captured == {
        "app": "app.main:app",
        "host": "127.0.0.1",
        "port": 8001,
        "reload": True,
        "reload_dirs": ["app"],
    }
    assert cli.os.environ.get("APP_ENV_FILE") == str(env_file.resolve())
    monkeypatch.delenv("APP_ENV_FILE", raising=False)


def test_main_rejects_missing_env_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--env-file", str(tmp_path / "missing.env")])
