import subprocess
from pathlib import Path

import pytest


def _make_clip(path: Path, seconds: float = 20, loud_at: float = 14.0, audio: bool = True,
               size: str = "1920x1080") -> Path:
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}:sample_rate=48000",
                "-filter_complex",
                f"[1:a]volume=0.03,volume=enable='between(t,{loud_at},{loud_at + 1.5})':volume=30[a]",
                "-map", "0:v", "-map", "[a]", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture
def make_clip(tmp_path):
    counter = iter(range(1000))

    def factory(seconds=20, loud_at=14.0, audio=True, size="1920x1080"):
        return _make_clip(tmp_path / f"clip{next(counter)}.mp4", seconds, loud_at, audio, size)

    return factory
