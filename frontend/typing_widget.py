"""
Widget de escritura estilo keybr.

Dibuja el texto del bloque y colorea cada letra según el motor:
  gris   = pendiente        verde = acertada
  azul   = letra actual     rojo  = error (el cursor no avanza hasta acertar)

No decide nada por sí mismo: cada tecla se la pasa a TypingEngine.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFontDatabase, QKeyEvent, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QTextEdit

from backend.typing_engine import CORRECT, DONE, IGNORED, WRONG, TypingEngine

# Paleta (oscura)
BG = "#1e1e2e"
PENDING = "#7f849c"
CORRECT_FG = "#a6e3a1"
CURRENT_FG = "#cdd6f4"
CURRENT_BG = "#45475a"
ERROR_FG = "#11111b"
ERROR_BG = "#f38ba8"


def _fmt(fg: str, bg: str | None = None) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QBrush(QColor(fg)))
    fmt.setBackground(QBrush(QColor(bg)) if bg else QBrush(Qt.BrushStyle.NoBrush))
    return fmt


class TypingWidget(QTextEdit):
    key_processed = pyqtSignal()   # tras cada tecla válida (acierto o error)
    block_finished = pyqtSignal()  # al escribir el último carácter del bloque

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine: TypingEngine | None = None

        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(f"QTextEdit {{ background: {BG}; border: none; }}")

        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(22)
        self.setFont(font)
        self.document().setDocumentMargin(32)

        self._fmt_pending = _fmt(PENDING)
        self._fmt_correct = _fmt(CORRECT_FG)
        self._fmt_current = _fmt(CURRENT_FG, CURRENT_BG)
        self._fmt_error = _fmt(ERROR_FG, ERROR_BG)

    # --- API pública -------------------------------------------------

    def load_text(self, text: str) -> None:
        """Carga un bloque nuevo y empieza desde cero."""
        self.engine = TypingEngine(text)
        self.setPlainText(text)
        self._paint_all_pending()

    def restart(self) -> None:
        """Vuelve a empezar el bloque actual (tecla Esc)."""
        if self.engine is None:
            return
        self.engine.restart()
        self._paint_all_pending()
        self.key_processed.emit()

    # --- teclado -----------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.engine is None:
            return
        if event.key() == Qt.Key.Key_Escape:
            self.restart()
            return

        text = event.text()
        if not text:
            return

        pos_before = self.engine.pos
        result = self.engine.press(text)
        if result == IGNORED:
            return

        if result in (CORRECT, DONE):
            self._paint(pos_before, pos_before + 1, self._fmt_correct)
        self._paint_current()
        self._scroll_to_current()

        self.key_processed.emit()
        if result == DONE:
            self.block_finished.emit()

    # --- pintura -----------------------------------------------------

    def _paint(self, start: int, end: int, fmt: QTextCharFormat) -> None:
        if end <= start:
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(fmt)

    def _paint_current(self) -> None:
        """Marca la letra actual: azul normal, rojo si el último intento falló."""
        e = self.engine
        if e is None or e.finished:
            return
        fmt = self._fmt_error if e.error_at_cursor else self._fmt_current
        self._paint(e.pos, e.pos + 1, fmt)

    def _paint_all_pending(self) -> None:
        e = self.engine
        self._paint(0, len(e.text), self._fmt_pending)
        self._paint_current()
        self._scroll_to_current()

    def _scroll_to_current(self) -> None:
        cursor = QTextCursor(self.document())
        cursor.setPosition(min(self.engine.pos, len(self.engine.text)))
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
