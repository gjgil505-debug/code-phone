from clipbot.render.captions import Word, build_ass


def _events(ass):
    return [l for l in ass.splitlines() if l.startswith("Dialogue:")]


def test_ass_offsets_and_highlight():
    ass = build_ass([Word(1.0, 1.4, "no"), Word(1.4, 1.9, "way")], offset_s=1.5, caption_bottom_y=1590)
    ev = _events(ass)
    assert len(ev) == 2
    assert ev[0].startswith("Dialogue: 0,0:00:02.50,0:00:02.90,")
    assert "{\\c&H00FFFF&}NO{\\c&HFFFFFF&} WAY" in ev[0]
    assert "NO {\\c&H00FFFF&}WAY{\\c&HFFFFFF&}" in ev[1]
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert ",2,40,40,330," in ass  # bottom-centre alignment, MarginV = 1920 - 1590


def test_ass_chunks_max_three_words():
    words = [Word(i * 0.2, i * 0.2 + 0.2, f"w{i}") for i in range(7)]
    ev = _events(build_ass(words, 0, caption_bottom_y=1590))
    assert len(ev) == 7
    assert all(e.count("W") <= 3 for e in [x.split(",", 9)[9].replace("{\\c&H00FFFF&}", "").replace("{\\c&HFFFFFF&}", "") for x in ev])


def test_ass_breaks_chunk_on_long_pause():
    words = [Word(0, 0.3, "a"), Word(3.0, 3.3, "b")]
    ev = _events(build_ass(words, 0, caption_bottom_y=1590))
    assert "B" not in ev[0].split(",", 9)[9]


def test_ass_escapes_braces():
    ev = _events(build_ass([Word(0, 0.5, "{x}")], 0, caption_bottom_y=1590))
    assert "{X}" not in ev[0] and "X" in ev[0]


def test_ass_empty_words_has_header_only():
    ass = build_ass([], 1.5, caption_bottom_y=1590)
    assert "[Events]" in ass and _events(ass) == []
