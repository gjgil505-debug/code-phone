from clipbot.render.peak import find_peak, probe


def test_peak_finds_burst(make_clip):
    p = make_clip(seconds=20, loud_at=14.0)
    assert abs(find_peak(p) - 14.0) <= 0.3


def test_peak_finds_early_burst(make_clip):
    p = make_clip(seconds=20, loud_at=3.0)
    assert abs(find_peak(p) - 3.0) <= 0.3


def test_peak_no_audio_falls_back(make_clip):
    p = make_clip(seconds=12, audio=False)
    assert abs(find_peak(p) - 7.25) <= 0.1


def test_probe_reports_dimensions(make_clip):
    info = probe(make_clip(seconds=4))
    assert (info.width, info.height, info.has_audio) == (1920, 1080, True)
    assert abs(info.duration - 4.0) < 0.2
    assert probe(make_clip(seconds=4, audio=False)).has_audio is False
