from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
from scenedetect import ContentDetector, SceneManager, open_video

PROGRESS_CHUNKS = 20
THUMB_WIDTH = 320


@dataclass(frozen=True)
class Span:
    start: float  # seconds
    end: float


def detect(path: Path, on_progress: Callable[[int], None]) -> list[Span]:
    """Shot boundaries by content change; a video without cuts is one scene."""
    video = open_video(str(path))
    manager = SceneManager()
    manager.add_detector(ContentDetector())
    total = video.duration.frame_num if video.duration else 0
    chunk = max(total // PROGRESS_CHUNKS, 1)
    # Detect in chunks only to report progress; the manager keeps state across calls
    while total and video.frame_number < total:
        manager.detect_scenes(video, end_time=min(video.frame_number + chunk, total))
        on_progress(video.frame_number * 100 // total)
    return [
        Span(start.seconds, end.seconds)
        for start, end in manager.get_scene_list(start_in_scene=True)
    ]


def thumbnail(video: Path, at: float, dest: Path) -> None:
    cap = cv2.VideoCapture(str(video))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, at * 1000)
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok:
        return  # a missing thumbnail is cosmetic; the scene itself is still valid
    h, w = frame.shape[:2]
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), cv2.resize(frame, (THUMB_WIDTH, h * THUMB_WIDTH // w)))
