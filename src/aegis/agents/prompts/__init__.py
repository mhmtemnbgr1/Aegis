"""Versiyonlu prompt şablonları. Her sürüm `prompts/<sürüm>/` altında değişmeden saklanır;
davranışı değiştiren her düzenleme yeni bir sürüm klasörü açar.
"""

from importlib import resources

from pydantic import BaseModel

DEFAULT_VERSION = "v1"


class PromptSet(BaseModel):
    version: str
    system: str
    user: str
    examples: str


def load_prompts(version: str = DEFAULT_VERSION) -> PromptSet:
    root = resources.files(__package__).joinpath(version)
    if not root.is_dir():
        raise ValueError(f"bilinmeyen prompt sürümü: {version}")

    def read(name: str) -> str:
        return root.joinpath(name).read_text(encoding="utf-8")

    return PromptSet(
        version=version,
        system=read("system.md"),
        user=read("user.md"),
        examples=read("examples.md"),
    )
