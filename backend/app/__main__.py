from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--reload-dir", action="append", default=None)
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        default=None,
        help="Baca konfigurasi dari file .env pada path ini.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.env_file:
        env_path = Path(args.env_file).expanduser()
        if not env_path.is_file():
            parser.error(f"File .env tidak ditemukan: {args.env_file}")
        # Propagate --env-file across uvicorn --reload worker subprocesses.
        os.environ["APP_ENV_FILE"] = str(env_path.resolve())
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=args.reload_dir,
    )


if __name__ == "__main__":
    main()
