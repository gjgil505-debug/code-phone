"""Speech-to-text and word-by-word ASS subtitles."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

MAX_WORDS = 3
MAX_CHUNK_S = 1.2
HIGHLIGHT = "{\\c&H00FFFF&}"
NORMAL = "{\\c&HFFFFFF&}"
FONT = "Montserrat ExtraBold"


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel  # heavy import; only when rendering
    return WhisperModel("base", device="cpu", compute_type="int8")


def transcribe(path: Path) -> list[Word]:
    segments, _ = _model().transcribe(str(path), word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(float(w.start), float(w.end), text))
    return words


def _fmt(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _clean(text: str) -> str:
    return text.replace("{", "").replace("}", "").replace("\\", "").upper()


def _chunks(words: list[Word]) -> list[list[Word]]:
    out: list[list[Word]] = []
    for w in words:
        if out and len(out[-1]) < MAX_WORDS and w.end - out[-1][0].start <= MAX_CHUNK_S:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def build_ass(words: list[Word], offset_s: float, play_res: tuple[int, int] = (1080, 1920),
              caption_bottom_y: int = 1590) -> str:
    w, h = play_res
    margin_v = h - caption_bottom_y
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Caption,{FONT},112,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,8,3,"
        f"2,40,40,{margin_v},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for chunk in _chunks(words):
        texts = [_clean(x.text) for x in chunk]
        for i, word in enumerate(chunk):
            end = chunk[i + 1].start if i + 1 < len(chunk) else word.end
            shown = " ".join(f"{HIGHLIGHT}{t}{NORMAL}" if j == i else t for j, t in enumerate(texts))
            lines.append(f"Dialogue: 0,{_fmt(word.start + offset_s)},{_fmt(end + offset_s)},Caption,,0,0,0,,{shown}")
    return "\n".join(lines) + "\n"
