from clipbot.render.captions import Word
from clipbot.safety import is_safe


def _w(*texts):
    return [Word(i, i + 0.5, t) for i, t in enumerate(texts)]


def test_safe_blocks_listed_word():
    assert is_safe(_w("you", "BADWORD!"), ["badword"]) is False


def test_safe_ignores_substring():
    assert is_safe(_w("class", "assessment"), ["ass"]) is True


def test_safe_empty_transcript_true():
    assert is_safe([], ["badword"]) is True
