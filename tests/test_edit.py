import itertools
import json

from reelcraft.pipeline import matching, runner
from reelcraft.pipeline.matching import MAX_SHOT, MIN_SHOT, Shot
from reelcraft.pipeline.steps import edit
from reelcraft.services import media, projects
from reelcraft.services.projects import ProjectCreate, ProjectUpdate
from reelcraft.storage.db import session_scope
from reelcraft.storage.files import project_dir


def test_windows_are_gapless_and_between_min_and_max():
    segments = [(0.0, 1.2, "a"), (1.5, 2.4, "b"), (2.6, 9.0, "c")]
    wins = matching.windows(segments, duration=9.2)
    assert wins[0].start == 0.0 and wins[-1].end == 9.2
    assert all(a.end == b.start for a, b in itertools.pairwise(wins))
    assert all(MIN_SHOT <= w.end - w.start <= MAX_SHOT for w in wins)
    assert wins[0].text == "a b" and wins[0].end == 2.5  # cut halfway through the pause
    assert {w.text for w in wins[1:]} == {"c"}


def test_match_follows_the_words_and_never_repeats_back_to_back():
    shots = [
        Shot("cat", "m", 0.0, 4.0, "kucing tidur di sofa"),
        Shot("dog", "m", 4.0, 8.0, "anjing berlari di taman"),
        Shot("logo", "m", 8.0, 12.0, "logo channel", filler=True),
    ]
    wins = matching.windows(
        [(0.0, 2.5, "Anjing suka berlari"), (2.6, 5.0, "Kucing suka tidur")], 5.2
    )
    clips = matching.match(wins, shots, {"m": 12.0})
    assert [c.scene_id for c in clips] == ["dog", "cat"]
    assert clips[0].start == 0.0 and clips[-1].end == 5.2
    assert clips[0].end == clips[1].start
    for c in clips:
        assert 0 <= c.source_start < c.source_end <= 12.0


def test_short_clips_merge_into_the_previous_one():
    a = matching.Clip("a", "m", 0.0, 3.0, 0.0, 3.0, "satu", 0)
    b = matching.Clip("b", "m", 5.0, 6.0, 3.0, 4.0, "dua", 1)
    healed = matching.heal([a, b], {"m": 10.0})
    assert len(healed) == 1 and (healed[0].end, healed[0].source_end) == (4.0, 4.0)
    assert healed[0].text == "satu dua"


def test_edit_step_writes_a_timeline_over_the_whole_narration(sample_video):
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        projects.update(s, pid, ProjectUpdate(topic="Warna"))
        media.add(s, pid, str(sample_video))
    assert runner.run(pid) == "done"
    timeline = json.loads((project_dir(pid) / edit.TIMELINE).read_text())
    assert timeline["clips"][0]["start"] == 0.0
    assert timeline["clips"][-1]["end"] == timeline["duration"]


def test_when_only_earlier_footage_is_left_the_last_clip_plays_on():
    shots = [Shot(f"s{i}", "m", i * 3.0, i * 3.0 + 3.0, f"adegan {i}") for i in range(6)]
    segments = [(i * 3.0, i * 3.0 + 2.8, f"kalimat {i}") for i in range(7)]
    clips = matching.match(matching.windows(segments, 21.0), shots, {"m": 18.0})
    starts = [c.source_start for c in clips]
    assert starts == sorted(starts)  # never back in the story
    assert clips[-1].end == 21.0
