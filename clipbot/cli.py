"""Command line: clipbot run | auth | render | status."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from clipbot.config import PLATFORMS, Settings, load_settings


def _settings(config: str) -> Settings:
    load_dotenv(Path(".env"))
    return load_settings(Path(config), os.environ)


def _logging(s: Settings) -> None:
    s.data_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file = RotatingFileHandler(s.data_dir / "clipbot.log", maxBytes=10 * 1024 * 1024, backupCount=5)
    console = logging.StreamHandler()
    for h in (file, console):
        h.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[file, console], force=True)
    for noisy in ("httpx", "httpcore", "websockets", "faster_whisper"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="clipbot", description="Autonomous GTA 6 hype clip bot")
    ap.add_argument("--config", default="config.yaml", help="settings file (default: config.yaml)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="start the bot (runs until stopped)")
    a = sub.add_parser("auth", help="one-time login for a platform")
    a.add_argument("provider", choices=["twitch", *PLATFORMS])
    a.add_argument("--redirect-uri", default="http://localhost:8765/callback")
    a.add_argument("--paste", action="store_true", default=None,
                   help="paste the address your browser lands on (automatic over SSH)")
    sub.add_parser("setup", help="enter your app keys and choose platforms, one question at a time")
    r = sub.add_parser("render", help="turn one Twitch clip URL into a short (to check the look)")
    r.add_argument("clip_url")
    r.add_argument("--name", default="StreamerName", help="streamer display name for the tag")
    r.add_argument("--type", default="general", choices=["funny", "hype", "shock", "general"])
    sub.add_parser("status", help="show what the bot is doing")
    args = ap.parse_args(argv)
    s = _settings(args.config)

    if args.cmd == "run":
        _logging(s)
        from clipbot.app import run
        try:
            asyncio.run(run(s))
        except KeyboardInterrupt:
            pass
        return 0

    if args.cmd == "auth":
        from clipbot.db import Db
        from clipbot.oauth import AuthSetupError, TokenStore, run_oauth
        try:
            asyncio.run(run_oauth(args.provider, s, TokenStore(s.tokens_path), args.redirect_uri, args.paste))
        except AuthSetupError as e:
            print(f"Login failed: {e}", file=sys.stderr)
            return 1
        Db(s.db_path).delete_state(f"disabled:{args.provider}")
        print(f"{args.provider} login saved.")
        return 0

    if args.cmd == "render":
        _logging(s)
        from clipbot.db import Db, Moment
        from clipbot.render.pipeline import render_moment
        db = Db(s.db_path)
        login = args.name.lower()
        m = Moment(None, login, args.name, args.type, 0.0, datetime.now(timezone.utc), None, args.clip_url,
                   "ready", [])
        m.id = db.add_moment(m)
        v = asyncio.run(render_moment(m, s, db))
        print(v.path if v else "Render skipped (clip too short or download failed); see the log.")
        return 0 if v else 1

    if args.cmd == "setup":
        from clipbot.setup_wizard import run_wizard
        run_wizard(Path(".env"), Path(args.config))
        return 0

    if args.cmd == "status":
        from clipbot.app import status_report
        from clipbot.db import Db
        print(status_report(Db(s.db_path), s, datetime.now(timezone.utc)))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
