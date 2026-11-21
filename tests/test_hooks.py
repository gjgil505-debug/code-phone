from clipbot.render.hooks import DEFAULT_HOOKS, HookPicker


def test_hook_avoids_recent():
    ids = [i for i, _ in DEFAULT_HOOKS["funny"]]
    recent = ids[:-1]
    hid, _ = HookPicker(DEFAULT_HOOKS, recent).pick("funny", "Bob")
    assert hid == ids[-1]


def test_hook_all_recent_still_returns_one():
    ids = [i for i, _ in DEFAULT_HOOKS["shock"]]
    hid, text = HookPicker(DEFAULT_HOOKS, ids).pick("shock", "Bob")
    assert hid in ids and text


def test_hook_unknown_type_uses_general():
    hid, _ = HookPicker(DEFAULT_HOOKS, []).pick("weird", "Bob")
    assert hid in [i for i, _ in DEFAULT_HOOKS["general"]]


def test_hook_fills_name():
    templates = {"general": [("g1", "{name} DID WHAT")]}
    assert HookPicker(templates, []).pick("general", "Bob") == ("g1", "BOB DID WHAT")


def test_templates_have_enough_and_no_emoji():
    for cat in ("funny", "hype", "shock", "general"):
        assert len(DEFAULT_HOOKS[cat]) >= 8
        for _, text in DEFAULT_HOOKS[cat]:
            assert all(ord(ch) < 0x2000 for ch in text), text
            assert text.replace("{name}", "") == text.replace("{name}", "").upper()
    all_ids = [i for v in DEFAULT_HOOKS.values() for i, _ in v]
    assert len(all_ids) == len(set(all_ids))
