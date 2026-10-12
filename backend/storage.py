import json
import os
from dataclasses import asdict
from backend.models import Book, Block

DATA_DIR = 'data'

def _get_save_path(pdf_filename: str) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(pdf_filename))[0]
    return os.path.join(DATA_DIR, f'{base_name}_progress.json')

def save_session(book: Book, current_block: int) -> None:
    data = {
        'title': book.title,
        'source_path': book.source_path,
        'current_block': current_block,
        'blocks': [asdict(b) for b in book.blocks]
    }
    path = _get_save_path(book.source_path)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_session(pdf_path: str) -> tuple[Book, int] | None:
    path = _get_save_path(pdf_path)
    if not os.path.exists(path):
        return None
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    blocks = [Block(**b) for b in data['blocks']]
    book = Book(title=data['title'], source_path=data['source_path'], blocks=blocks)
    return book, data.get('current_block', 0)
