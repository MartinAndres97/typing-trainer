"""Limpieza del texto crudo del PDF y división en bloques para escribir."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import TYPE_CHECKING

from backend.models import Block

if TYPE_CHECKING:
    from backend.pdf_processor import RawPage

# --- Ajustes -----------------------------------------------------------

# Una línea corta que se repite arriba/abajo en al menos esta fracción de
# las páginas se considera encabezado o pie de página y se elimina.
HEADER_FOOTER_MIN_FREQUENCY = 0.25
HEADER_MAX_CHARS = 60

# Tamaño de cada bloque, en palabras.
BLOCK_MIN_WORDS = 40
BLOCK_MAX_WORDS = 160

# --- Tipografía: lo que no se puede teclear fácil ---------------------

_TYPOGRAPHY_MAP = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-",    # raya corta
    "\u2014": "--",   # raya larga
    "\u2015": "--",
    "\u2212": "-",    # signo menos
    "\u00ad": None,   # guion blando (invisible)
    "\u200b": None,   # espacio de ancho cero
    "\u00a0": " ",    # espacio duro
    "\u2022": "*",    # viñeta
})

# True: quita acentos y descarta símbolos que no se pueden teclear fácil.
ASCII_ONLY = True

_PAGE_NUMBER_RE = re.compile(r"^[\s\-.]*(?:page\s+)?\d{1,4}[\s\-.]*$", re.IGNORECASE)
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\n([a-z])")
_DASH_BREAK_RE = re.compile(r"--\n(?=\S)")  # raya larga al final de línea
_SPACES_RE = re.compile(r"[ \t]+")
_TERMINAL_END_RE = re.compile(r"""[.!?"')\]-]$""")


def normalize_typography(text: str) -> str:
    """
    NFKC une ligaduras (fi, fl) y puntos suspensivos; luego se arreglan las
    comillas y se pasa todo a caracteres que se pueden teclear.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_TYPOGRAPHY_MAP)
    if ASCII_ONLY:
        # é -> e; lo que no tenga equivalente ASCII se descarta
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text


def _norm_line(line: str) -> str:
    return _SPACES_RE.sub(" ", line.strip()).lower()


# --- Encabezados y pies de página -------------------------------------

def detect_repeated_lines(pages: list[RawPage]) -> set[str]:
    """Líneas cortas que se repiten al inicio/fin de muchas páginas."""
    if not pages:
        return set()

    counts: Counter[str] = Counter()
    for page in pages:
        lines = [
            _norm_line(l)
            for l in normalize_typography(page.raw_text).splitlines()
            if l.strip()
        ]
        candidates = {l for l in lines[:2] + lines[-2:] if len(l) <= HEADER_MAX_CHARS}
        counts.update(candidates)

    threshold = max(3, int(len(pages) * HEADER_FOOTER_MIN_FREQUENCY))
    return {line for line, n in counts.items() if n >= threshold}


# --- Limpieza de una página -------------------------------------------

def clean_page_paragraphs(raw_text: str, repeated_lines: set[str]) -> list[str]:
    """
    Devuelve los párrafos limpios de una página:
      - quita encabezados/pies repetidos y números de página
      - une palabras partidas por guion al final de línea ("under-\\nstand")
      - une las líneas cortadas del mismo párrafo con un espacio
      - respeta los saltos de párrafo (líneas en blanco)
    """
    kept: list[str] = []
    for line in normalize_typography(raw_text).splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if _norm_line(stripped) in repeated_lines:
            continue
        if _PAGE_NUMBER_RE.match(stripped):
            continue
        kept.append(stripped)

    text = _HYPHEN_BREAK_RE.sub(r"\1\2", "\n".join(kept))
    text = _DASH_BREAK_RE.sub("--", text)  # "coming--\nbefore" -> "coming--before"

    paragraphs = []
    for chunk in re.split(r"\n{2,}", text):
        para = _SPACES_RE.sub(" ", chunk.replace("\n", " ")).strip()
        if para:
            paragraphs.append(para)
    return paragraphs


# --- Bloques -----------------------------------------------------------

def split_into_blocks(paragraphs: list[tuple[int, str]]) -> list[Block]:
    """
    Agrupa párrafos (página, texto) en bloques de BLOCK_MIN_WORDS a
    BLOCK_MAX_WORDS palabras. Un párrafo más largo que el máximo queda como
    bloque propio: es mejor que cortar una frase por la mitad.
    """
    blocks: list[Block] = []
    buffer: list[str] = []
    buffer_words = 0
    buffer_page = 1

    def flush() -> None:
        nonlocal buffer, buffer_words
        if buffer:
            blocks.append(Block(len(blocks), buffer_page, " ".join(buffer)))
        buffer, buffer_words = [], 0

    for page_number, para in paragraphs:
        words = len(para.split())
        if buffer and buffer_words + words > BLOCK_MAX_WORDS:
            flush()
        if not buffer:
            buffer_page = page_number
        buffer.append(para)
        buffer_words += words
        if buffer_words >= BLOCK_MIN_WORDS:
            flush()

    flush()
    return blocks


def fix_lone_quotes(text: str) -> str:
    """
    Una comilla doble que quedó sola, con espacios a ambos lados, es un resto
    del PDF. Se pega a la palabra anterior si cierra un diálogo, o a la
    siguiente si lo abre:
        Seldon, " said Sunmaster   ->   Seldon," said Sunmaster
    """
    tokens = text.split(" ")
    out: list[str] = []
    quotes_seen = 0       # comillas dobles ya vistas en este párrafo
    pending_open = False  # la comilla anterior abre: va pegada a este token

    for i, orig in enumerate(tokens):
        tok = '"' + orig if pending_open else orig
        pending_open = False
        if orig != '"' or tok != orig:
            out.append(tok)
            quotes_seen += orig.count('"')
            continue

        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        prev = out[-1] if out else ""
        if not out:
            closing = False                       # primera del párrafo: abre
        elif not nxt:
            closing = True                        # última del párrafo: cierra
        elif nxt[:1].islower() or nxt[:1] in ('"', "'"):
            closing = True                        # " said ...   /   " "No, ...
        elif prev.endswith("'"):
            closing = True                        # ...robot.' " R. Daneel
        else:
            closing = quotes_seen % 2 == 1        # dentro de un diálogo: cierra

        quotes_seen += 1
        if closing:
            out[-1] += '"'
        else:
            pending_open = True

    if pending_open:      # comilla de apertura sin palabra detrás
        out.append('"')
    return " ".join(out)


def clean_book(pages: list[RawPage]) -> list[Block]:
    """Pipeline completo: páginas crudas -> bloques listos para teclear."""
    repeated = detect_repeated_lines(pages)

    paragraphs: list[tuple[int, str]] = []
    for page in pages:
        for i, para in enumerate(clean_page_paragraphs(page.raw_text, repeated)):
            # Si el párrafo anterior quedó "abierto" al final de la página
            # anterior, este primer párrafo es su continuación.
            if i == 0 and paragraphs and not _TERMINAL_END_RE.search(paragraphs[-1][1]):
                prev_page, prev_text = paragraphs[-1]
                paragraphs[-1] = (prev_page, f"{prev_text} {para}")
            else:
                paragraphs.append((page.page_number, para))

    paragraphs = [(page, fix_lone_quotes(text)) for page, text in paragraphs]
    return split_into_blocks(paragraphs)
