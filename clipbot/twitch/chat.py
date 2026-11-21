"""Anonymous read-only Twitch chat over IRC/WebSocket."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Callable

import websockets

from clipbot.hype import ChatMessage

log = logging.getLogger(__name__)
IRC_URL = "wss://irc-ws.chat.twitch.tv:443"


def _parse_tags(raw: str) -> dict[str, str]:
    out = {}
    for part in raw.split(";"):
        k, _, v = part.partition("=")
        out[k] = v
    return out


def parse_irc_line(line: str, now: float | None = None) -> ChatMessage | None:
    line = line.rstrip("\r\n")
    tags: dict[str, str] = {}
    if line.startswith("@"):
        raw, _, line = line.partition(" ")
        tags = _parse_tags(raw[1:])
    if not line.startswith(":"):
        return None
    prefix, _, rest = line[1:].partition(" ")
    cmd, _, rest = rest.partition(" ")
    if cmd != "PRIVMSG":
        return None
    target, _, text = rest.partition(" :")
    if not target.startswith("#"):
        return None
    user = prefix.split("!", 1)[0]
    ts = now if now is not None else time.time()
    if tags.get("tmi-sent-ts", "").isdigit():
        ts = int(tags["tmi-sent-ts"]) / 1000
    return ChatMessage(target[1:].lower(), user.lower(), text, ts)


class ChatListener:
    def __init__(self, channels_provider: Callable[[], set[str]],
                 on_message: Callable[[ChatMessage], None], sync_every_s: float = 30):
        self.channels_provider = channels_provider
        self.on_message = on_message
        self.sync_every_s = sync_every_s
        self.joined: set[str] = set()

    async def run(self) -> None:
        backoff = 1
        while True:
            try:
                async with websockets.connect(IRC_URL, ping_interval=60, max_size=2**22) as ws:
                    backoff = 1
                    self.joined = set()
                    await ws.send("CAP REQ :twitch.tv/tags")
                    await ws.send("PASS SCHMOOPIIE")
                    await ws.send(f"NICK justinfan{random.randint(10000, 99999)}")
                    await self._session(ws)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # network errors: reconnect
                log.warning("chat connection lost: %s; reconnecting in %ss", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _sync(self, ws) -> None:
        want = {c.lower() for c in self.channels_provider()}
        for c in sorted(want - self.joined):
            await ws.send(f"JOIN #{c}")
            await asyncio.sleep(0.4)  # stay under Twitch's join rate limit
        for c in sorted(self.joined - want):
            await ws.send(f"PART #{c}")
        self.joined = want

    async def _session(self, ws) -> None:
        await self._sync(ws)
        last_sync = time.monotonic()
        while True:
            try:
                data = await asyncio.wait_for(ws.recv(), timeout=self.sync_every_s)
            except asyncio.TimeoutError:
                data = ""
            for line in str(data).split("\r\n"):
                if not line:
                    continue
                if line.startswith("PING"):
                    await ws.send("PONG" + line[4:])
                    continue
                if " RECONNECT" in line:
                    raise ConnectionError("server asked to reconnect")
                msg = parse_irc_line(line)
                if msg:
                    self.on_message(msg)
            if time.monotonic() - last_sync >= self.sync_every_s:
                await self._sync(ws)
                last_sync = time.monotonic()
