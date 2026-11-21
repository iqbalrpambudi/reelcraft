import re
from pathlib import Path

from pysubs2 import Alignment, Color, SSAEvent, SSAFile, SSAStyle

from reelcraft.core.errors import ReelcraftError

WIDTH, HEIGHT = 1080, 1920
GROUP = 3  # words on screen at once
FONT_SIZE = 84
# Above the caption and buttons the Shorts / Reels UI draws over the bottom quarter
MARGIN_BOTTOM = 480
POP = r"\t(0,60,\fscx116\fscy116)\t(60,120,\fscx110\fscy110)"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_color):
        raise ReelcraftError(f"Warna subtitle '{hex_color}' harus berformat #RRGGBB")
    return int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)


def karaoke(segments: list[dict], font: str, highlight: str, dest: Path) -> None:
    """Words in groups of three, uppercase; the word being spoken is coloured and pops."""
    r, g, b = _rgb(highlight)
    color = f"&H{b:02X}{g:02X}{r:02X}&"
    subs = SSAFile()
    subs.info.update({"PlayResX": str(WIDTH), "PlayResY": str(HEIGHT)})
    subs.styles["Default"] = SSAStyle(
        fontname=font,
        fontsize=FONT_SIZE,
        bold=True,
        primarycolor=Color(255, 255, 255),
        outlinecolor=Color(0, 0, 0),
        outline=4,
        shadow=0,
        alignment=Alignment.BOTTOM_CENTER,
        marginv=MARGIN_BOTTOM,
    )
    for seg in segments:
        # Braces would open an override block; drop them from spoken text
        words = [(re.sub(r"[{}\\]", "", w["text"]).upper(), w) for w in seg["words"]]
        words = [(text, w) for text, w in words if text.strip()]
        for i in range(0, len(words), GROUP):
            group = words[i : i + GROUP]
            for j, (_, w) in enumerate(group):
                end = group[j + 1][1]["start"] if j < len(group) - 1 else w["end"]
                text = " ".join(
                    f"{{\\c{color}{POP}}}{t}{{\\r}}" if k == j else t
                    for k, (t, _) in enumerate(group)
                )
                start_ms = round(w["start"] * 1000)
                subs.append(
                    SSAEvent(start=start_ms, end=max(round(end * 1000), start_ms + 100), text=text)
                )
    subs.save(str(dest))
