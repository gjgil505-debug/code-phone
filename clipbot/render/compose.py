"""Build the ffmpeg command that turns a 16:9 clip into a hooked 9:16 short."""
from __future__ import annotations

import textwrap
from pathlib import Path

from clipbot.render.peak import ProbeInfo

W, H = 1080, 1920
TAG_BOTTOM = H - 220          # streamer tag sits above the platforms' bottom UI
CAPTION_BOTTOM = TAG_BOTTOM - 110
HOOK_TOP = 220
HOOK_SECONDS = 3.0
COLD_OPEN = 1.5
FLASH = 0.15
FPS = 30
HOOK_FONT_SIZE = 84
HOOK_LINE_H = 118
HOOK_WRAP = 18
FONT_FILE = Path(__file__).parent / "fonts" / "Montserrat-ExtraBold.ttf"


def _esc(path: Path) -> str:
    """Quote a path for use inside an ffmpeg filtergraph."""
    return "'" + str(Path(path).resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "") + "'"


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def build_ffmpeg_cmd(src: Path, out: Path, peak_s: float, info: ProbeInfo, hook_text: str, tag_text: str,
                     ass_path: Path, facecam: tuple[int, int, int, int] | None, work_dir: Path,
                     fonts_dir: Path = FONT_FILE.parent) -> list[str]:
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    peak = round(peak_s, 3)
    font = _esc(FONT_FILE)
    norm_v = f"fps={FPS},scale={info.width}:{info.height},setsar=1,format=yuv420p"
    norm_a = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    parts = [
        f"[0:v]split=2[va][vb]",
        f"[va]trim=start={peak}:duration={COLD_OPEN},setpts=PTS-STARTPTS,{norm_v}[cold]",
        f"color=c=white:s={info.width}x{info.height}:r={FPS}:d={FLASH},fade=t=out:st=0:d={FLASH},"
        f"setsar=1,format=yuv420p[flash]",
        f"[vb]setpts=PTS-STARTPTS,{norm_v}[full]",
        f"anullsrc=r=48000:cl=stereo,atrim=duration={FLASH},{norm_a}[fa]",
    ]
    if info.has_audio:
        parts += [
            "[0:a]asplit=2[xa][xb]",
            f"[xa]atrim=start={peak}:duration={COLD_OPEN},asetpts=PTS-STARTPTS,{norm_a}[ca]",
            f"[xb]asetpts=PTS-STARTPTS,{norm_a}[fulla]",
        ]
    else:
        parts += [
            f"anullsrc=r=48000:cl=stereo,atrim=duration={COLD_OPEN},{norm_a}[ca]",
            f"anullsrc=r=48000:cl=stereo,atrim=duration={info.duration},{norm_a}[fulla]",
        ]
    parts.append("[cold][ca][flash][fa][full][fulla]concat=n=3:v=1:a=1[v0][a0]")

    bg = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=20:2,eq=brightness=-0.12"
    if facecam:
        x, y, w, h = facecam
        cam_h, game_h = 640, H - 640
        parts += [
            "[v0]split=3[bg0][fg0][cam0]",
            f"[bg0]{bg}[bg]",
            f"[cam0]crop={w}:{h}:{x}:{y},scale={W}:{cam_h}:force_original_aspect_ratio=increase,"
            f"crop={W}:{cam_h}[cam]",
            f"[fg0]scale={W}:{game_h}:force_original_aspect_ratio=decrease[fg]",
            f"[bg][fg]overlay=(W-w)/2:{cam_h}+({game_h}-h)/2[base0]",
            "[base0][cam]overlay=0:0[base]",
        ]
    else:
        parts += [
            "[v0]split=2[bg0][fg0]",
            f"[bg0]{bg}[bg]",
            f"[fg0]scale={W}:-2[fg]",
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[base]",
        ]

    text = f"subtitles=filename={_esc(ass_path)}:fontsdir={_esc(fonts_dir)}"
    for i, line in enumerate(textwrap.wrap(hook_text, HOOK_WRAP) or [hook_text]):
        f = _write(work_dir / f"hook{i}.txt", line)
        text += (f",drawtext=fontfile={font}:textfile={_esc(f)}:fontsize={HOOK_FONT_SIZE}:fontcolor=white"
                 f":box=1:boxcolor=black@0.6:boxborderw=16:x=(w-text_w)/2:y={HOOK_TOP + i * HOOK_LINE_H}"
                 f":enable='lt(t,{HOOK_SECONDS})'")
    tag = _write(work_dir / "tag.txt", tag_text)
    text += (f",drawtext=fontfile={font}:textfile={_esc(tag)}:fontsize=56:fontcolor=white:borderw=4"
             f":bordercolor=black:box=1:boxcolor=black@0.55:boxborderw=18:x=(w-text_w)/2:y={TAG_BOTTOM}-text_h")
    parts.append(f"[base]{text}[vout]")
    parts.append("[a0]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")

    return ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", ";".join(parts),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)]
