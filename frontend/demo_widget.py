"""
Demo del widget de escritura con un texto fijo (sin PDF).

Ejecutar desde la raíz del proyecto:   python -m frontend.demo_widget
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from frontend.typing_widget import TypingWidget

SAMPLE = (
    "The old lighthouse keeper looked at the horizon and said, \"A storm is coming "
    "before night.\" He knew the sea better than anyone, and he was never wrong "
    "about the signs of the weather. His assistant nodded slowly, climbed the "
    "stairs to the lamp room, and lit the great lantern just as the first drops "
    "of rain began to fall."
)


class Demo(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Typing widget demo  (Esc = reiniciar)")
        self.resize(900, 480)
        self.setStyleSheet("background: #1e1e2e;")

        self.typing = TypingWidget()
        self.stats = QLabel()
        self.stats.setStyleSheet("color: #cdd6f4; font-size: 16px; padding: 8px 32px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.typing, 1)
        layout.addWidget(self.stats)

        self.typing.key_processed.connect(self.refresh)
        self.typing.block_finished.connect(self.on_finished)

        self.timer = QTimer(self)          # el WPM sigue subiendo/bajando aunque no teclees
        self.timer.timeout.connect(self.refresh)
        self.timer.start(200)

        self.typing.load_text(SAMPLE)
        self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.typing.setFocus()

    def refresh(self) -> None:
        e = self.typing.engine
        if e is None:
            return
        self.stats.setText(
            f"WPM {e.wpm():5.1f}    |    Accuracy {e.accuracy:5.1f}%    |    "
            f"Words {e.words_done}/{e.words_total}"
        )

    def on_finished(self) -> None:
        e = self.typing.engine
        print(f"\nBloque terminado: {e.wpm():.1f} WPM, {e.accuracy:.1f}% de precisión")
        rows = [(k, s) for k, s in e.key_stats.items() if k.strip() and s.hits + s.misses >= 3]
        rows.sort(key=lambda r: (r[1].accuracy, r[1].wpm))
        print("Teclas más débiles (precisión, WPM):")
        for key, s in rows[:8]:
            print(f"  {key!r}: {s.accuracy:5.1f}%   {s.wpm:5.1f} WPM   ({s.hits} aciertos, {s.misses} fallos)")


def main() -> None:
    app = QApplication(sys.argv)
    window = Demo()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
