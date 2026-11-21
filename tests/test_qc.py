import json

from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from typer.testing import CliRunner

from reelcraft.api.app import create_app
from reelcraft.cli import app
from reelcraft.pipeline import qc, runner
from reelcraft.pipeline.qc import script as script_gate
from reelcraft.pipeline.qc import timeline as timeline_gate
from reelcraft.pipeline.steps import script as script_step
from reelcraft.services import media, projects
from reelcraft.services.projects import ProjectCreate
from reelcraft.storage import script
from reelcraft.storage.db import session_scope
from reelcraft.storage.files import project_dir
from reelcraft.storage.models import Media, Scene, StepRun

LONG = (
    "Batang kayu mentah diolah mesin berkecepatan tinggi menjadi ribuan bilah tipis, "
    "lalu bilah itu dikeringkan berhari-hari di ruangan panas agar tidak mudah patah "
    "saat dicelup ke cairan kimia pekat dan panas"
)


def _project(segments: list[str]) -> str:
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        runner.ensure_runs(s, pid)
    script.save(pid, script.Script("Judul", segments))
    return pid


def test_script_fix_strips_labels_splits_and_merges():
    pid = _project(
        ["Hook: [MUSIK] Lihat ini!", LONG, "Wow.", "**Penutup** yang manis #shorts", "Sekian"]
    )
    before = {i.check for i in qc.run("script", project_dir(pid)).issues}
    assert {"artifact", "long-segment"} <= before

    report = qc.run("script", project_dir(pid), fix=True)
    segments = script.load(pid).segments
    assert segments == [
        "Lihat ini! Batang kayu mentah diolah mesin berkecepatan tinggi menjadi ribuan "
        "bilah tipis.",
        "Lalu bilah itu dikeringkan berhari-hari di ruangan panas agar tidak mudah patah saat "
        "dicelup ke cairan kimia pekat dan panas",  # split at the comma before "lalu"
        "Wow. Penutup yang manis. Sekian",  # a last stub joins the one before as a sentence
    ]
    assert all(len(s.split()) <= script_gate.SEGMENT_MAX for s in segments)
    assert [i for i in report.issues if i.fixable] == []
    assert len(report.fixes) >= 3


def test_timeline_gate_finds_gaps_flashes_repeats_and_bad_footage(tmp_path):
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        m = Media(project_id=pid, source="x", status="ready", duration=60)
        s.add(m)
        s.flush()
        good = Scene(media_id=m.id, position=0, start=0, end=5, description="pandai besi menempa")
        bad = Scene(media_id=m.id, position=1, start=5, end=9, description="Gambar buram dan gelap")
        s.add_all([good, bad])
        s.flush()
        ids = good.id, bad.id

    def clip(scene, start, end):
        return {"scene_id": scene, "start": start, "end": end}

    clips = [clip(ids[0], 0, 3), clip(ids[0], 3, 3.5), clip(ids[1], 3.8, 11), clip("gone", 11, 13)]
    (tmp_path / "timeline.json").write_text(json.dumps({"duration": 15, "clips": clips}))
    found = {(i.check, i.clip) for i in timeline_gate.check(tmp_path)}
    assert found == {
        ("repeat", 1),
        ("flash", 1),
        ("gap", 2),
        ("static", 2),
        ("low-quality", 2),
        ("missing-scene", 3),
        ("length-mismatch", None),
    }


def test_a_blocker_fails_the_step(sample_video, monkeypatch):
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        media.add(s, pid, str(sample_video))
    # Everything the model wrote is a label: nothing is left to voice
    nothing = {"title": "t", "segments": ["[MUSIK]", "Narator:"]}
    monkeypatch.setattr(
        script_step, "model_for", lambda task: TestModel(custom_output_args=nothing)
    )
    assert runner.run(pid, end="script") == "failed"
    with session_scope() as s:
        assert "QC: Naskah kosong" in s.get(StepRun, (pid, "script")).error


def test_reports_after_a_run_and_fix_from_api_and_cli(sample_video):
    with session_scope() as s:
        pid = projects.create(s, ProjectCreate(name="p")).id
        media.add(s, pid, str(sample_video))
    assert runner.run(pid) == "done"
    client = TestClient(create_app())
    base = f"/api/v1/projects/{pid}"
    reports = client.get(f"{base}/qc").json()
    assert set(reports) == set(qc.GATES) and all(reports.values())
    assert reports["render"]["issues"] == []

    client.put(f"{base}/script", json={"text": f"# T\n\nNarasi: halo kamu semua\n\n{LONG}\n"})
    fresh = client.get(f"{base}/qc").json()["script"]
    assert {"artifact", "long-segment"} <= {i["check"] for i in fresh["issues"]}
    fixed = client.post(f"{base}/script/fix").json()
    assert fixed["fixes"] and not [i for i in fixed["issues"] if i["fixable"]]
    assert client.post(f"{base}/qc/voice").status_code == 400  # voice reopened by the fix

    out = CliRunner().invoke(app, ["qc", pid[:8], "--fix"])
    assert out.exit_code == 0, out.output
    assert "Tidak ada yang perlu diperbaiki" in out.output and "voice  belum" not in out.output
