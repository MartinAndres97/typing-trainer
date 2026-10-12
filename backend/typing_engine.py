"""
Motor de escritura: decide si cada tecla es correcta y calcula las métricas.
No depende de ninguna interfaz; la ventana solo le pasa las teclas.
"""

from __future__ import annotations

import re
import time
from bisect import bisect_right
from dataclasses import dataclass

# Resultado de cada tecla
CORRECT = "correct"   # acierto, el cursor avanza
WRONG = "wrong"       # error, el cursor NO avanza hasta acertar
DONE = "done"         # acierto y se terminó el bloque
IGNORED = "ignored"   # tecla no imprimible, o el bloque ya terminó

# Una pausa más larga que esto no cuenta para la velocidad por tecla
# (si te levantas por un café, no debe arruinar tus estadísticas).
MAX_KEY_INTERVAL = 2.0


@dataclass
class KeyStat:
    """Estadísticas de una tecla (por la letra que había que escribir)."""

    hits: int = 0
    misses: int = 0
    timed_hits: int = 0      # aciertos que tienen un tiempo medido
    total_time: float = 0.0  # suma de esos tiempos, en segundos

    @property
    def accuracy(self) -> float:
        total = self.hits + self.misses
        return 100.0 * self.hits / total if total else 100.0

    @property
    def wpm(self) -> float:
        """Velocidad equivalente de la tecla (5 caracteres = 1 palabra)."""
        if self.timed_hits == 0 or self.total_time <= 0:
            return 0.0
        avg = self.total_time / self.timed_hits
        return 12.0 / avg  # 60 s / (5 caracteres * avg)


class TypingEngine:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0                     # índice del siguiente carácter a escribir
        self.error_at_cursor = False     # True si la última tecla fue un error
        self.total_keystrokes = 0
        self.correct_keystrokes = 0
        self.key_stats: dict[str, KeyStat] = {}
        self._start: float | None = None
        self._last_correct: float | None = None
        self._end: float | None = None
        # posición (exclusiva) donde termina cada palabra
        self._word_ends = [m.end() for m in re.finditer(r"\S+", text)]

    # --- estado ------------------------------------------------------

    @property
    def finished(self) -> bool:
        return self.pos >= len(self.text)

    @property
    def current_char(self) -> str:
        return "" if self.finished else self.text[self.pos]

    def restart(self) -> None:
        self.__init__(self.text)

    # --- teclas ------------------------------------------------------

    def press(self, ch: str, now: float | None = None) -> str:
        """Procesa una tecla. `now` solo se pasa en las pruebas."""
        if self.finished or len(ch) != 1 or not ch.isprintable():
            return IGNORED

        now = time.monotonic() if now is None else now
        if self._start is None:
            self._start = now

        expected = self.text[self.pos]
        stat = self.key_stats.setdefault(expected.lower(), KeyStat())
        self.total_keystrokes += 1

        if ch != expected:
            stat.misses += 1
            self.error_at_cursor = True
            return WRONG

        stat.hits += 1
        self.correct_keystrokes += 1
        if self._last_correct is not None:
            stat.timed_hits += 1
            stat.total_time += min(now - self._last_correct, MAX_KEY_INTERVAL)
        self._last_correct = now
        self.error_at_cursor = False
        self.pos += 1

        if self.finished:
            self._end = now
            return DONE
        return CORRECT

    # --- métricas ----------------------------------------------------

    def elapsed(self, now: float | None = None) -> float:
        """Segundos desde la primera tecla (se congela al terminar el bloque)."""
        if self._start is None:
            return 0.0
        if self._end is not None:
            return self._end - self._start
        return (time.monotonic() if now is None else now) - self._start

    def wpm(self, now: float | None = None) -> float:
        """Palabras por minuto netas (5 caracteres correctos = 1 palabra)."""
        elapsed = self.elapsed(now)
        if elapsed < 1.0:
            return 0.0
        return (self.pos / 5.0) / (elapsed / 60.0)

    @property
    def accuracy(self) -> float:
        """Porcentaje de teclas que fueron acierto (100 si aún no has escrito)."""
        if self.total_keystrokes == 0:
            return 100.0
        return 100.0 * self.correct_keystrokes / self.total_keystrokes

    @property
    def words_total(self) -> int:
        return len(self._word_ends)

    @property
    def words_done(self) -> int:
        """Palabras ya escritas por completo."""
        return bisect_right(self._word_ends, self.pos)
