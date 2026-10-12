"""Extracción de texto crudo de un PDF, página por página."""

from __future__ import annotations

import os
from dataclasses import dataclass

import pymupdf


class PDFLoadError(Exception):
    """El PDF no se pudo abrir o no tiene texto extraíble."""


@dataclass
class RawPage:
    page_number: int  # empieza en 1
    raw_text: str     # texto tal como sale del PDF, con saltos de línea


def extract_pages(pdf_path: str) -> list[RawPage]:
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as exc:
        raise PDFLoadError(f"No se pudo abrir '{pdf_path}': {exc}") from exc

    pages = [
        RawPage(page_number=i + 1, raw_text=doc.load_page(i).get_text("text"))
        for i in range(doc.page_count)
    ]
    doc.close()

    if not any(p.raw_text.strip() for p in pages):
        raise PDFLoadError(
            "El PDF no tiene texto extraíble (probablemente es un escaneo; "
            "necesitaría OCR)."
        )
    return pages


def guess_title(pdf_path: str, pages: list[RawPage]) -> str:
    try:
        doc = pymupdf.open(pdf_path)
        title = (doc.metadata or {}).get("title", "").strip()
        doc.close()
        if title:
            return title.removeprefix("Microsoft Word - ").strip()
    except Exception:
        pass
    return os.path.splitext(os.path.basename(pdf_path))[0] or "Untitled Book"
