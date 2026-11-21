from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from reelcraft.ai.models import ai_errors

RULES = """Kamu kurator ide untuk channel video pendek vertikal (Shorts, Reels).
- Satu ide yang bisa dinarasikan 30-60 detik dan footage-nya mudah dicari.
- Faktanya harus benar; jangan mengarang angka.
- Berbeda dari ide-ide terakhir yang diberikan."""


class Idea(BaseModel):
    title: str = Field(
        description="Judul video yang memancing rasa penasaran, maksimal 80 karakter"
    )
    topic: str = Field(description="Satu-dua kalimat: isi video dan sudut ceritanya")
    query: str = Field(
        description="2-4 kata kunci bahasa Inggris untuk mencari footage, mis. 'blacksmith forging'"
    )


async def suggest(model: Model, niche: str, recent: list[str]) -> Idea:
    """A fresh video idea within the niche, unlike the recent ones."""
    done = "\n".join(f"- {t}" for t in recent) or "(belum ada)"
    prompt = f"Niche channel:\n{niche}\n\nIde terakhir (jangan diulang):\n{done}"
    agent = Agent(model, output_type=Idea, instructions=RULES, retries=2)
    with ai_errors():
        return (await agent.run(prompt)).output
