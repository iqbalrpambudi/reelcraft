import pytest

from reelcraft.core.errors import ReelcraftError
from reelcraft.media import scenes
from reelcraft.media.probe import probe


def test_probe_reads_video_metadata(sample_video):
    info = probe(sample_video)
    assert (info.width, info.height) == (320, 240)
    assert info.duration == pytest.approx(4.0, abs=0.2)
    assert info.fps == pytest.approx(10.0)


def test_probe_rejects_non_video(tmp_path):
    bogus = tmp_path / "x.mp4"
    bogus.write_text("not a video")
    with pytest.raises(ReelcraftError, match="bukan video"):
        probe(bogus)


def test_detect_finds_the_cut_and_reports_progress(sample_video):
    progress = []
    spans = scenes.detect(sample_video, progress.append)
    assert len(spans) == 2
    assert spans[0].start == 0
    assert spans[0].end == pytest.approx(2.0, abs=0.2)
    assert spans[1].end == pytest.approx(4.0, abs=0.2)
    assert progress and progress[-1] == 100


def test_thumbnail_is_scaled_jpeg(sample_video, tmp_path):
    dest = tmp_path / "t" / "a.jpg"
    scenes.thumbnail(sample_video, 1.0, dest)
    assert dest.read_bytes()[:2] == b"\xff\xd8"
