from clipbot.config import Settings
from clipbot.hype import ChatMessage, HypeDetector

S = Settings()


def _steady(det, ch, start, end, rate, text="hello there", users=50):
    """Feed `rate` msgs/sec from start to end; returns triggers."""
    out = []
    n = int((end - start) * rate)
    for i in range(n):
        t = start + i / rate
        r = det.feed(ChatMessage(ch, f"u{i % users}", text, t))
        if r:
            out.append(r)
    return out


def _run(det, end):
    return det.tick(end)


def test_no_trigger_during_warmup():
    det = HypeDetector(S)
    trig = _steady(det, "a", 0, 60, 2)
    trig += _steady(det, "a", 60, 72, 30, text="KEKW", users=1000)
    trig += _run(det, 80)
    assert trig == []


def test_steady_chat_never_triggers():
    det = HypeDetector(S)
    trig = _steady(det, "a", 0, 1200, 2)
    trig += _run(det, 1205)
    assert trig == []


def test_spike_triggers_funny():
    det = HypeDetector(S)
    trig = _steady(det, "a", 0, 360, 2)
    trig += _steady(det, "a", 360, 372, 30, text="KEKW LMAO", users=1000)
    trig += _steady(det, "a", 372, 400, 2)
    trig += _run(det, 405)
    assert len(trig) == 1
    t = trig[0]
    assert t.channel == "a" and t.trigger_type == "funny" and t.score >= 3.0
    assert 360 <= t.ts <= 380
    assert t.snippet and len(t.snippet) <= 8


def test_spike_type_shock():
    det = HypeDetector(S)
    trig = _steady(det, "a", 0, 360, 2)
    trig += _steady(det, "a", 360, 372, 30, text="WHAT ???", users=1000)
    trig += _run(det, 380)
    assert [t.trigger_type for t in trig] == ["shock"]


def test_spike_without_emotes_is_general():
    det = HypeDetector(S)
    trig = _steady(det, "a", 0, 360, 2)
    trig += _steady(det, "a", 360, 372, 30, text="no way bro", users=1000)
    trig += _run(det, 380)
    assert [t.trigger_type for t in trig] == ["general"]


def test_single_bucket_spike_does_not_trigger():
    det = HypeDetector(S)
    trig = _steady(det, "a", 0, 360, 2)
    trig += _steady(det, "a", 360, 365, 30, text="KEKW", users=1000)
    trig += _steady(det, "a", 365, 400, 2)
    trig += _run(det, 405)
    assert trig == []


def test_cooldown_suppresses_second_spike_within_120s():
    det = HypeDetector(S)
    trig = _steady(det, "a", 0, 360, 2)
    trig += _steady(det, "a", 360, 372, 30, text="KEKW", users=1000)
    trig += _steady(det, "a", 372, 420, 2)
    trig += _steady(det, "a", 420, 432, 60, text="Pog", users=1000)
    trig += _steady(det, "a", 432, 450, 2)
    trig += _run(det, 455)
    assert len(trig) == 1


def test_small_and_big_channel_scored_relative_to_own_baseline():
    det = HypeDetector(S)
    trig = []
    trig += _steady(det, "small", 0, 360, 0.2, users=1000)
    trig += _steady(det, "small", 360, 372, 2, text="KEKW", users=1000)
    trig += _steady(det, "small", 372, 420, 0.2, users=1000)
    trig += _steady(det, "big", 0, 360, 40, users=5000)
    trig += _steady(det, "big", 360, 372, 45, text="KEKW", users=5000)
    trig += _steady(det, "big", 372, 420, 40, users=5000)
    trig += _run(det, 425)
    assert [t.channel for t in trig] == ["small"]
