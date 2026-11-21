from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from reelcraft.ai.models import ai_errors

# Preset narration styles; a project picks one and may add its own instructions on top
TEMPLATES: dict[str, str] = {
    "fakta": "Video fakta menarik. Buka dengan fakta paling mengejutkan sebagai hook, lalu "
    "3-5 fakta singkat yang saling menyambung, tutup dengan pertanyaan untuk penonton.",
    "cerita": "Cerita singkat bergaya storytelling. Buka dengan situasi yang bikin penasaran, "
    "bangun ketegangan, akhiri dengan twist atau pelajaran.",
    "listicle": "Daftar top N. Sebutkan jumlahnya di awal, satu poin per segmen, "
    "simpan yang paling menarik untuk terakhir.",
    "edukasi": "Penjelasan edukatif. Mulai dari pertanyaan yang sering ditanyakan orang, "
    "jelaskan langkah demi langkah dengan bahasa sederhana, tutup dengan ringkasan satu kalimat.",
    "bebas": "",  # instructions of the project are the whole template
}

RULES = """Kamu penulis naskah narasi video pendek vertikal (Reels, Shorts, TikTok).
- Bahasa Indonesia lisan yang natural, kalimat pendek, enak dibacakan.
- Total 30-60 detik dibacakan (sekitar 80-150 kata).
- Tiap segmen 1-2 kalimat dan cocok dengan salah satu scene yang tersedia.
- Tulis hanya kata yang dibacakan: tanpa emoji, hashtag, arahan kamera, atau label."""


class ScriptDraft(BaseModel):
    title: str = Field(description="Judul video, maksimal 80 karakter")
    segments: list[str] = Field(description="Narasi berurutan, satu item per segmen")


async def write(
    model: Model, topic: str, template: str, instructions: str | None, scenes: list[str]
) -> ScriptDraft:
    """Draft a narration from the brief and what the footage shows."""
    style = "\n".join(t for t in (TEMPLATES.get(template, ""), instructions or "") if t)
    footage = "\n".join(f"- {s}" for s in scenes) or "(belum ada deskripsi scene)"
    prompt = f"Topik: {topic}\n\nGaya:\n{style or 'bebas'}\n\nScene yang tersedia:\n{footage}"
    agent = Agent(model, output_type=ScriptDraft, instructions=RULES, retries=2)
    with ai_errors():
        return (await agent.run(prompt)).output
