"""SQLite store shared by all loops."""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS moments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT, display_name TEXT, trigger_type TEXT,
  score REAL, created_at TEXT, clip_id TEXT, clip_url TEXT, status TEXT, chat_snippet TEXT);
CREATE INDEX IF NOT EXISTS moments_created ON moments(created_at);
CREATE TABLE IF NOT EXISTS videos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, moment_id INTEGER, path TEXT, meta_path TEXT,
  score REAL, hook_id TEXT, safe INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, video_id INTEGER, remote_id TEXT,
  url TEXT, status TEXT, created_at TEXT, error TEXT);
CREATE INDEX IF NOT EXISTS posts_platform ON posts(platform, created_at);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
"""


@dataclass
class Moment:
    id: int | None
    channel: str
    display_name: str
    trigger_type: str
    score: float
    created_at: datetime
    clip_id: str | None
    clip_url: str | None
    status: str  # pending|ready|unusable|rendered|skipped
    chat_snippet: list[str]


@dataclass
class Video:
    id: int | None
    moment_id: int
    path: str
    meta_path: str
    score: float
    hook_id: str
    safe: bool
    created_at: datetime


@dataclass
class Post:
    platform: str
    video_id: int
    remote_id: str | None
    url: str | None
    status: str  # ok|failed
    created_at: datetime
    error: str | None


def _ts(d: datetime) -> str:
    return d.isoformat()


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


class Db:
    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def _all(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    # moments
    @staticmethod
    def _moment(r: sqlite3.Row) -> Moment:
        return Moment(r["id"], r["channel"], r["display_name"], r["trigger_type"], r["score"],
                      _dt(r["created_at"]), r["clip_id"], r["clip_url"], r["status"],
                      json.loads(r["chat_snippet"] or "[]"))

    def add_moment(self, m: Moment) -> int:
        cur = self._exec(
            "INSERT INTO moments(channel,display_name,trigger_type,score,created_at,clip_id,clip_url,status,chat_snippet)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (m.channel, m.display_name, m.trigger_type, m.score, _ts(m.created_at), m.clip_id,
             m.clip_url, m.status, json.dumps(m.chat_snippet)))
        return int(cur.lastrowid)

    def update_moment(self, m: Moment) -> None:
        self._exec("UPDATE moments SET clip_id=?, clip_url=?, status=? WHERE id=?",
                   (m.clip_id, m.clip_url, m.status, m.id))

    def set_moment_status(self, moment_id: int, status: str) -> None:
        self._exec("UPDATE moments SET status=? WHERE id=?", (status, moment_id))

    def get_moment(self, moment_id: int) -> Moment | None:
        rows = self._all("SELECT * FROM moments WHERE id=?", (moment_id,))
        return self._moment(rows[0]) if rows else None

    def ready_moments(self, since: datetime) -> list[Moment]:
        return [self._moment(r) for r in self._all(
            "SELECT * FROM moments WHERE status='ready' AND created_at>=? ORDER BY score DESC", (_ts(since),))]

    def moments_since(self, since: datetime) -> list[Moment]:
        return [self._moment(r) for r in self._all(
            "SELECT * FROM moments WHERE created_at>=? ORDER BY created_at", (_ts(since),))]

    # videos
    @staticmethod
    def _video(r: sqlite3.Row) -> Video:
        return Video(r["id"], r["moment_id"], r["path"], r["meta_path"], r["score"], r["hook_id"],
                     bool(r["safe"]), _dt(r["created_at"]))

    def add_video(self, v: Video) -> int:
        cur = self._exec(
            "INSERT INTO videos(moment_id,path,meta_path,score,hook_id,safe,created_at) VALUES (?,?,?,?,?,?,?)",
            (v.moment_id, v.path, v.meta_path, v.score, v.hook_id, int(v.safe), _ts(v.created_at)))
        return int(cur.lastrowid)

    def videos_since(self, since: datetime) -> list[Video]:
        return [self._video(r) for r in self._all(
            "SELECT * FROM videos WHERE created_at>=? ORDER BY created_at", (_ts(since),))]

    def recent_hook_ids(self, n: int) -> list[str]:
        return [r["hook_id"] for r in self._all("SELECT hook_id FROM videos ORDER BY id DESC LIMIT ?", (n,))]

    # posts
    @staticmethod
    def _post(r: sqlite3.Row) -> Post:
        return Post(r["platform"], r["video_id"], r["remote_id"], r["url"], r["status"],
                    _dt(r["created_at"]), r["error"])

    def add_post(self, p: Post) -> None:
        self._exec("INSERT INTO posts(platform,video_id,remote_id,url,status,created_at,error) VALUES (?,?,?,?,?,?,?)",
                   (p.platform, p.video_id, p.remote_id, p.url, p.status, _ts(p.created_at), p.error))

    def posts_since(self, platform: str, since: datetime) -> list[Post]:
        return [self._post(r) for r in self._all(
            "SELECT * FROM posts WHERE platform=? AND created_at>=? ORDER BY created_at", (platform, _ts(since)))]

    def posted_video_ids(self, platform: str) -> set[int]:
        return {r["video_id"] for r in self._all(
            "SELECT video_id FROM posts WHERE platform=? AND status='ok'", (platform,))}

    # state
    def get_state(self, key: str) -> str | None:
        rows = self._all("SELECT value FROM state WHERE key=?", (key,))
        return rows[0]["value"] if rows else None

    def set_state(self, key: str, value: str) -> None:
        self._exec("INSERT INTO state(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, value))

    def delete_state(self, key: str) -> None:
        self._exec("DELETE FROM state WHERE key=?", (key,))
