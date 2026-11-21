"""Probe clips and locate their loudest moment."""
from __future__ import annotations

import json
import subprocess
from array import array
from dataclasses import dataclass
from pathlib import Path

SAMPLE_RATE = 8000
STEP_S = 0.1


@dataclass(frozen=True)
class ProbeInfo:
    duration: float
    width: int
    height: int
    has_audio: bool


def probe(path: Path) -> ProbeInfo:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         check=True, capture_output=True, text=True).stdout
    data = json.loads(out)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    return ProbeInfo(float(data["format"]["duration"]), int(video["width"]), int(video["height"]), has_audio)


def _fallback(duration: float, window_s: float) -> float:
    return max(0.0, duration * 2 / 3 - window_s / 2)


def find_peak(path: Path, window_s: float = 1.5) -> float:
    """Start time (s) of the loudest `window_s` stretch of audio."""
    info = probe(path)
    if not info.has_audio:
        return _fallback(info.duration, window_s)
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
                          "-f", "s16le", "-"], check=True, capture_output=True).stdout
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    step = int(SAMPLE_RATE * STEP_S)
    energy = [sum(x * x for x in samples[i:i + step]) for i in range(0, len(samples), step)]
    k = max(1, round(window_s / STEP_S))
    if len(energy) <= k or max(energy, default=0) == 0:
        return _fallback(info.duration, window_s)
    run = sum(energy[:k])
    best, best_i = run, 0
    for i in range(1, len(energy) - k + 1):
        run += energy[i + k - 1] - energy[i - 1]
        if run > best:
            best, best_i = run, i
    return min(best_i * STEP_S, max(0.0, info.duration - window_s))
