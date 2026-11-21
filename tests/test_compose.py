from pathlib import Path

from clipbot.render.compose import CAPTION_BOTTOM, TAG_BOTTOM, build_ffmpeg_cmd
from clipbot.render.peak import ProbeInfo

INFO = ProbeInfo(30.0, 1920, 1080, True)


def _cmd(tmp_path, info=INFO, facecam=None, hook="NOBODY EXPECTED THIS", peak=12.0):
    return build_ffmpeg_cmd(Path("in.mp4"), tmp_path / "out.mp4", peak, info, hook, "@StreamerName",
                            tmp_path / "subs.ass", facecam, tmp_path)


def _filter(cmd):
    return cmd[cmd.index("-filter_complex") + 1]


def test_layout_constants():
    assert TAG_BOTTOM == 1700 and CAPTION_BOTTOM < TAG_BOTTOM


def test_cmd_contains_tag_at_bottom(tmp_path):
    f = _filter(_cmd(tmp_path))
    assert "y=1700-text_h" in f
    tagfiles = [p for p in tmp_path.glob("tag*.txt")]
    assert [p.read_text() for p in tagfiles] == ["@StreamerName"]
    tag_part = next(seg for seg in f.split("drawtext=") if "tag.txt" in seg)
    assert "y=1700-text_h" in tag_part
    assert "box=1" in tag_part and "enable" not in tag_part  # always on screen


def test_cmd_hook_enabled_first_3s_and_wrapped(tmp_path):
    f = _filter(_cmd(tmp_path, hook="THIS IS A VERY LONG HOOK LINE THAT WRAPS"))
    assert "lt(t,3.0)" in f
    lines = sorted(tmp_path.glob("hook*.txt"))
    assert len(lines) >= 2 and all(len(p.read_text()) <= 18 for p in lines)


def test_cmd_cold_open_trims_peak(tmp_path):
    f = _filter(_cmd(tmp_path, peak=12.0))
    assert "trim=start=12.0:duration=1.5" in f
    assert "atrim=start=12.0:duration=1.5" in f
    assert "concat=n=3:v=1:a=1" in f


def test_cmd_facecam_layout_crops(tmp_path):
    f = _filter(_cmd(tmp_path, facecam=(1500, 40, 380, 220)))
    assert "crop=380:220:1500:40" in f


def test_cmd_no_audio_uses_anullsrc(tmp_path):
    f = _filter(_cmd(tmp_path, info=ProbeInfo(30.0, 1920, 1080, False)))
    assert "[0:a]" not in f and "anullsrc" in f


def test_cmd_output_encoding(tmp_path):
    cmd = _cmd(tmp_path)
    s = " ".join(cmd)
    assert "loudnorm=I=-14" in _filter(cmd)
    for part in ("-c:v libx264", "-crf 18", "-pix_fmt yuv420p", "-c:a aac", "+faststart"):
        assert part in s
    assert cmd[-1].endswith("out.mp4")
