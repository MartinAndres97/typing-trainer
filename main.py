import sys
import os
import re
import json
import time
from dataclasses import dataclass, field
from bisect import bisect_right
import pymupdf

from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                             QPushButton, QFileDialog, QLabel, QHBoxLayout, QMessageBox)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFontDatabase, QKeyEvent, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QTextEdit

# --- 1. MODELOS ---
@dataclass
class Block:
    index: int
    page_number: int
    text: str

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

# --- 2. PROCESADOR Y LIMPIADOR DE PDF ---

    # Limpieza automática de caché JSON al abrir el libro para evitar datos viejos
    import os, glob
    for f in glob.glob('*_progress.json') + glob.glob('data/*_progress.json') + glob.glob('*.local/share/typing_trainer/*_progress.json'):
        try:
            os.remove(f)
        except:
            pass

def extract_pages(path):
    import pypdf
    import re
    import os, glob
    
    # Limpieza automática de caché
    for f in glob.glob('*_progress.json') + glob.glob('data/*_progress.json') + glob.glob(os.path.expanduser('~/.local/share/typing_trainer/*_progress.json')):
        try:
            os.remove(f)
        except:
            pass

    text_pages = []
    try:
        reader = pypdf.PdfReader(path)
        for page in reader.pages:
            try:
                txt = page.extract_text()
                if txt:
                    cleaned = re.sub(r'[^a-zA-Z0-9\s.,!?\'\"-]', ' ', txt)
                    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
                    if len(cleaned) > 15:
                        text_pages.append(cleaned)
            except:
                continue
    except Exception as e:
        print(f"Error leyendo PDF: {e}")
    
    if not text_pages:
        text_pages = ["No se pudo extraer texto legible del PDF."]
    return text_pages
def guess_title(pdf_path: str) -> str:
    return os.path.splitext(os.path.basename(pdf_path))[0]

def clean_book(raw_pages: list[str]) -> list[Block]:
    blocks = []
    for page_num, text in enumerate(raw_pages, start=1):
        # Normalizar comillas tipográficas a estándar
        text = text.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
        cleaned = re.sub(r'\s+', ' ', text).strip()
        if not cleaned:
            continue
        # Dividir en bloques de ~100 palabras
        words = cleaned.split()
        chunk_size = 100
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            blocks.append(Block(index=len(blocks), page_number=page_num, text=chunk))
    return blocks

# --- 3. MOTOR DE TIPEO ---
CORRECT = "correct"
WRONG = "wrong"
DONE = "done"
IGNORED = "ignored"

class TypingEngine:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.error_at_cursor = False
        self.total_keystrokes = 0
        self.correct_keystrokes = 0
        self._start: float | None = None
        self._end: float | None = None
        self._word_ends = [m.end() for m in re.finditer(r"\S+", text)]

    @property
    def finished(self) -> bool:
        return self.pos >= len(self.text)

    def press(self, ch: str) -> str:
        if self.finished or len(ch) != 1 or not ch.isprintable():
            return IGNORED
        
        if self._start is None:
            self._start = time.monotonic()

        expected = self.text[self.pos]
        self.total_keystrokes += 1

        if ch != expected:
            self.error_at_cursor = True
            return WRONG

        self.correct_keystrokes += 1
        self.error_at_cursor = False
        self.pos += 1

        if self.finished:
            self._end = time.monotonic()
            return DONE
        return CORRECT

    def elapsed(self) -> float:
        if self._start is None:
            return 0.0
        return (self._end if self._end else time.monotonic()) - self._start

    def wpm(self) -> float:
        elapsed_min = self.elapsed() / 60.0
        if elapsed_min <= 0:
            return 0.0
        return (self.pos / 5.0) / elapsed_min

    @property
    def accuracy(self) -> float:
        if self.total_keystrokes == 0:
            return 100.0
        return 100.0 * self.correct_keystrokes / self.total_keystrokes

    @property
    def words_total(self) -> int:
        return len(self._word_ends)

    @property
    def words_done(self) -> int:
        return bisect_right(self._word_ends, self.pos)

# --- 4. GESTOR DE GUARDADO ---
DATA_DIR = "data"

def save_session(book: Book, current_block: int):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{guess_title(book.source_path)}_progress.json")
    data = {
        "title": book.title,
        "source_path": book.source_path,
        "current_block": current_block,
        "blocks": [{"index": b.index, "page_number": b.page_number, "text": b.text} for b in book.blocks]
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_session(pdf_path: str):
    path = os.path.join(DATA_DIR, f"{guess_title(pdf_path)}_progress.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    blocks = [Block(**b) for b in data["blocks"]]
    book = Book(title=data["title"], source_path=data["source_path"], blocks=blocks)
    return book, data.get("current_block", 0)

# --- 5. WIDGET DE INTERFAZ ---
def _fmt(fg: str, bg: str | None = None):
    fmt = QTextCharFormat()
    fmt.setForeground(QBrush(QColor(fg)))
    if bg:
        fmt.setBackground(QBrush(QColor(bg)))
    return fmt

class TypingWidget(QTextEdit):
    key_processed = pyqtSignal()
    block_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine: TypingEngine | None = None
        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QTextEdit { background: #1e1e2e; border: none; color: #cdd6f4; }")

        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(20)
        self.setFont(font)
        self.document().setDocumentMargin(32)

        self._fmt_pending = _fmt("#7f849c")
        self._fmt_correct = _fmt("#a6e3a1")
        self._fmt_current = _fmt("#cdd6f4", "#45475a")
        self._fmt_error = _fmt("#11111b", "#f38ba8")

    def load_text(self, text: str):
        self.engine = TypingEngine(text)
        self.setPlainText(text)
        self._paint_all_pending()

    def keyPressEvent(self, event: QKeyEvent):
        if self.engine is None:
            return
        if event.key() == Qt.Key.Key_Escape:
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

    def _paint(self, start: int, end: int, fmt: QTextCharFormat):
        if end <= start:
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(fmt)

    def _paint_current(self):
        e = self.engine
        if e is None or e.finished:
            return
        fmt = self._fmt_error if e.error_at_cursor else self._fmt_current
        self._paint(e.pos, e.pos + 1, fmt)

    def _paint_all_pending(self):
        e = self.engine
        self._paint(0, len(e.text), self._fmt_pending)
        self._paint_current()
        self._scroll_to_current()

    def _scroll_to_current(self):
        cursor = QTextCursor(self.document())
        cursor.setPosition(min(self.engine.pos, len(self.engine.text)))
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

# --- 6. VENTANA PRINCIPAL ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Typing Trainer - PDF Reader")
        self.resize(1000, 650)
        self.setStyleSheet("background: #1e1e2e; color: #cdd6f4;")

        self.book = None
        self.current_block_index = 0

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top_bar = QHBoxLayout()
        self.btn_load = QPushButton("Cargar / Reanudar PDF")
        self.btn_load.setStyleSheet("background: #89b4fa; color: #11111b; padding: 10px; font-weight: bold; font-size: 14px;")
        self.btn_load.clicked.connect(self.select_and_load_pdf)
        
        self.lbl_info = QLabel("Ningún libro cargado")
        self.lbl_info.setStyleSheet("font-size: 14px;")
        
        self.lbl_stats = QLabel("WPM: 0.0 | Precisión: 0.0%")
        self.lbl_stats.setStyleSheet("font-size: 14px; font-weight: bold; color: #a6e3a1;")

        top_bar.addWidget(self.btn_load)
        top_bar.addWidget(self.lbl_info, stretch=1)
        top_bar.addWidget(self.lbl_stats)

        layout.addLayout(top_bar)

        self.typing = TypingWidget()
        layout.addWidget(self.typing, stretch=1)

        self.typing.block_finished.connect(self.on_block_finished)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_live_stats)
        self.timer.start(200)

    def select_and_load_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar PDF", "", "Archivos PDF (*.pdf)")
        if not path:
            return

        saved = load_session(path)
        if saved:
            self.book, self.current_block_index = saved
            self.lbl_info.setText(f"Reanudando: {self.book.title}")
        else:
            try:
                raw_pages = extract_pages(path)
                title = guess_title(path)
                blocks = clean_book(raw_pages)
                if not blocks:
                    raise ValueError("No se pudo extraer texto.")
                self.book = Book(title=title, source_path=path, blocks=blocks)
                self.current_block_index = 0
                save_session(self.book, self.current_block_index)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo cargar el PDF:\n{e}")
                return

        self.load_current_block()

    def load_current_block(self):
        if not self.book:
            return
        if self.current_block_index >= self.book.total_blocks:
            self.lbl_info.setText("¡Felicidades! Libro completado.")
            self.typing.setPlainText("¡Has terminado el libro completo!")
            return

        block = self.book.blocks[self.current_block_index]
        self.typing.load_text(block.text)
        self.lbl_info.setText(f"Libro: {self.book.title} | Bloque {self.current_block_index + 1}/{self.book.total_blocks}")
        self.typing.setFocus()

    def on_block_finished(self):
        self.current_block_index += 1
        if self.book:
            save_session(self.book, self.current_block_index)
        self.load_current_block()

    def update_live_stats(self):
        e = self.typing.engine
        if e:
            self.lbl_stats.setText(f"WPM: {e.wpm():.1f} | Precisión: {e.accuracy:.1f}%")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
