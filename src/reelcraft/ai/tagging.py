from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import Model

from reelcraft.ai.models import ai_errors

INSTRUCTIONS = """Kamu menganalisis gambar dari scene video untuk editor video pendek.
Untuk setiap gambar, tulis apa yang benar-benar terlihat: subjek, aksi, tempat, suasana.
Jangan mengarang hal yang tidak tampak. Jika gambar buram atau kosong, katakan itu."""


class SceneTag(BaseModel):
    image: int = Field(description="Nomor gambar, mulai dari 1, sesuai urutan")
    description: str = Field(description="1-2 kalimat Bahasa Indonesia tentang isi gambar")
    tags: list[str] = Field(description="3-8 kata kunci pendek, huruf kecil, Bahasa Indonesia")


class TagBatch(BaseModel):
    scenes: list[SceneTag]


async def describe(model: Model, images: list[bytes]) -> list[SceneTag | None]:
    """One request for several images; result[i] belongs to images[i] (None if skipped)."""
    prompt: list[str | BinaryContent] = [f"Ada {len(images)} gambar. Deskripsikan semuanya."]
    for i, data in enumerate(images, 1):
        prompt += [f"Gambar {i}:", BinaryContent(data=data, media_type="image/jpeg")]
    agent = Agent(model, output_type=TagBatch, instructions=INSTRUCTIONS, retries=2)
    with ai_errors():
        result = await agent.run(prompt)
    by_image = {t.image: t for t in result.output.scenes}
    return [by_image.get(i) for i in range(1, len(images) + 1)]
