from dataclasses import dataclass

from reelcraft.storage.files import project_dir

FILE = "script.md"  # plain text so it edits well in $EDITOR and a textarea


@dataclass
class Script:
    title: str
    segments: list[str]  # read one after another; Edit matches a scene to each


def parse(text: str) -> Script:
    """`# Title` on the first line, then one paragraph per segment."""
    lines = text.strip().splitlines()
    title = lines[0].removeprefix("#").strip() if lines and lines[0].startswith("#") else ""
    body = "\n".join(lines[1:] if title else lines)
    segments = [" ".join(p.split()) for p in body.split("\n\n") if p.strip()]
    return Script(title, segments)


def to_text(script: Script) -> str:
    return f"# {script.title}\n\n" + "\n\n".join(script.segments) + "\n"


def load(project_id: str) -> Script | None:
    path = project_dir(project_id) / FILE
    return parse(path.read_text()) if path.is_file() else None


def save(project_id: str, script: Script) -> None:
    path = project_dir(project_id) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_text(script))
