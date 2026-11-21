"""Hype detection from chat velocity, normalised per channel."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from clipbot.config import Settings

TriggerType = Literal["funny", "hype", "shock", "general"]

# A bucket needs at least this many messages to count as a spike, so a couple of
# stray messages in a near-silent chat can't trigger a clip.
MIN_BUCKET_MSGS = 5
# Idle gaps longer than this many buckets are fast-forwarded instead of replayed.
MAX_GAP_BUCKETS = 120


@dataclass(frozen=True)
class ChatMessage:
    channel: str
    user: str
    text: str
    ts: float


@dataclass(frozen=True)
class Trigger:
    channel: str
    score: float
    trigger_type: TriggerType
    ts: float
    snippet: list[str]


class _EmoteMatcher:
    def __init__(self, emotes: dict[str, list[str]]):
        self.words: dict[str, set[str]] = {}
        self.subs: dict[str, list[str]] = {}
        for cat, items in emotes.items():
            self.words[cat] = {e.lower() for e in items if e.isalnum()}
            self.subs[cat] = [e.lower() for e in items if not e.isalnum()]

    def categories(self, text: str) -> set[str]:
        low = text.lower()
        tokens = set(low.split())
        return {cat for cat in self.words
                if tokens & self.words[cat] or any(s in low for s in self.subs[cat])}


@dataclass
class _Channel:
    first_ts: float
    idx: int
    msgs: list[ChatMessage] = field(default_factory=list)
    baseline: float | None = None
    streak: list[tuple[float, dict[str, int], float]] = field(default_factory=list)
    cooldown_until: float = float("-inf")
    recent: deque = field(default_factory=lambda: deque(maxlen=8))


class HypeDetector:
    def __init__(self, settings: Settings):
        self.s = settings
        self.alpha = settings.bucket_s / settings.baseline_window_s
        self.matcher = _EmoteMatcher(settings.emotes)
        self.channels: dict[str, _Channel] = {}

    def _idx(self, ts: float) -> int:
        return int(ts // self.s.bucket_s)

    def feed(self, msg: ChatMessage) -> Trigger | None:
        ch = self.channels.get(msg.channel)
        idx = self._idx(msg.ts)
        if ch is None:
            ch = self.channels[msg.channel] = _Channel(first_ts=msg.ts, idx=idx)
        trig = self._advance(msg.channel, ch, idx) if idx > ch.idx else None
        ch.msgs.append(msg)
        ch.recent.append(msg.text)
        return trig

    def tick(self, now: float) -> list[Trigger]:
        idx = self._idx(now)
        out = []
        for name, ch in self.channels.items():
            if idx > ch.idx:
                t = self._advance(name, ch, idx)
                if t:
                    out.append(t)
        return out

    def forget(self, channel: str) -> None:
        self.channels.pop(channel, None)

    def _advance(self, name: str, ch: _Channel, new_idx: int) -> Trigger | None:
        trig = self._close(name, ch)
        gap = new_idx - ch.idx - 1
        for _ in range(min(gap, MAX_GAP_BUCKETS)):
            ch.idx += 1
            trig = self._close(name, ch) or trig
        ch.idx = new_idx
        return trig

    def _close(self, name: str, ch: _Channel) -> Trigger | None:
        msgs, ch.msgs = ch.msgs, []
        count = len(msgs)
        start = ch.idx * self.s.bucket_s
        end = start + self.s.bucket_s
        if ch.baseline is None:
            ch.baseline = float(count)
            return None

        cats: dict[str, int] = {}
        emote_msgs = 0
        for m in msgs:
            found = self.matcher.categories(m.text)
            if found:
                emote_msgs += 1
            for c in found:
                cats[c] = cats.get(c, 0) + 1
        raw = count / max(ch.baseline, 1.0)
        emote_share = emote_msgs / count if count else 0.0
        unique_share = len({m.user for m in msgs}) / count if count else 0.0
        score = raw * (1 + 0.5 * emote_share) * (0.5 + 0.5 * unique_share)
        ch.baseline += self.alpha * (count - ch.baseline)

        warm = end - ch.first_ts >= self.s.baseline_window_s
        if warm and count >= MIN_BUCKET_MSGS and score >= self.s.hype_threshold and start >= ch.cooldown_until:
            ch.streak.append((score, cats, start))
        else:
            ch.streak.clear()
            return None
        if len(ch.streak) < self.s.trigger_buckets:
            return None

        total: dict[str, int] = {}
        for _, c, _ in ch.streak:
            for k, v in c.items():
                total[k] = total.get(k, 0) + v
        ttype: TriggerType = max(total, key=total.get) if total else "general"  # type: ignore[assignment]
        trig = Trigger(name, max(s for s, _, _ in ch.streak), ttype, ch.streak[0][2], list(ch.recent))
        ch.streak.clear()
        ch.cooldown_until = end + self.s.channel_cooldown_s
        return trig
