"""Modelos de datos compartidos por el backend."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Block:
    """Un trozo de texto (aprox. un párrafo) para escribir de una sentada."""

    index: int        # posición en el libro, desde 0
    page_number: int  # página del PDF donde empieza, desde 1
    text: str         # texto limpio, listo para teclear

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class Book:
    title: str
    source_path: str
    blocks: list[Block] = field(default_factory=list)

    @property
    def total_blocks(self) -> int:
        return len(self.blocks)

    @property
    def total_words(self) -> int:
        return sum(b.word_count for b in self.blocks)
