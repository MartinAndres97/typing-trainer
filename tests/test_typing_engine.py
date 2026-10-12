"""Pruebas del motor de escritura. Ejecutar:  python tests/test_typing_engine.py"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.typing_engine import CORRECT, DONE, IGNORED, WRONG, TypingEngine


def type_all(engine, text, start=0.0, step=0.2):
    t = start
    result = None
    for ch in text:
        result = engine.press(ch, now=t)
        t += step
    return result


def test_perfect_typing():
    e = TypingEngine("the cat sat")
    assert type_all(e, "the cat sat") == DONE
    assert e.finished and e.accuracy == 100.0
    assert e.words_done == 3 and e.words_total == 3
    # 11 caracteres, 10 intervalos de 0.2 s = 2.0 s  ->  (11/5) / (2/60) = 66 WPM
    assert abs(e.wpm() - 66.0) < 0.01, e.wpm()


def test_error_blocks_cursor():
    e = TypingEngine("abc")
    assert e.press("a", now=0.0) == CORRECT
    assert e.press("x", now=0.1) == WRONG
    assert e.pos == 1 and e.error_at_cursor
    assert e.press("y", now=0.2) == WRONG and e.pos == 1
    assert e.press("b", now=0.3) == CORRECT
    assert e.pos == 2 and not e.error_at_cursor
    # 2 aciertos + 2 errores hasta aquí
    assert e.total_keystrokes == 4 and e.correct_keystrokes == 2
    assert e.accuracy == 50.0
    # los errores se cuentan contra la tecla que había que escribir ('b')
    assert e.key_stats["b"].misses == 2 and e.key_stats["b"].hits == 1


def test_words_done():
    e = TypingEngine("one two")
    type_all(e, "one")
    assert e.words_done == 1
    type_all(e, " tw", start=10)
    assert e.words_done == 1
    type_all(e, "o", start=20)
    assert e.words_done == 2


def test_ignored_keys():
    e = TypingEngine("ab")
    assert e.press("\n", now=0) == IGNORED
    assert e.press("\x1b", now=0) == IGNORED
    assert e.press("ab", now=0) == IGNORED       # no es un solo carácter
    assert e.total_keystrokes == 0
    type_all(e, "ab")
    assert e.press("x", now=99) == IGNORED       # ya terminó


def test_per_key_speed():
    e = TypingEngine("ab")
    e.press("a", now=0.0)
    e.press("b", now=0.5)
    assert e.key_stats["a"].wpm == 0.0           # la primera tecla no tiene intervalo
    assert abs(e.key_stats["b"].wpm - 24.0) < 1e-9   # 12 / 0.5


def test_long_pause_is_capped():
    e = TypingEngine("ab")
    e.press("a", now=0.0)
    e.press("b", now=10.0)
    assert e.key_stats["b"].total_time == 2.0


def test_stats_are_case_insensitive():
    e = TypingEngine("Ab")
    e.press("A", now=0.0)
    assert "a" in e.key_stats and e.key_stats["a"].hits == 1


def test_wpm_zero_before_one_second_and_frozen_after_finish():
    e = TypingEngine("abcde")
    assert e.wpm() == 0.0
    type_all(e, "abcde", step=0.1)               # 0.4 s en total
    assert e.wpm() == 0.0
    e2 = TypingEngine("abcde")
    type_all(e2, "abcde", step=1.0)              # 4 s -> (5/5)/(4/60) = 15 WPM
    assert abs(e2.wpm(now=1000.0) - 15.0) < 0.01  # congelado, no depende de "ahora"


def test_restart():
    e = TypingEngine("ab")
    type_all(e, "ab")
    e.restart()
    assert e.pos == 0 and e.total_keystrokes == 0 and not e.finished


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK ", t.__name__)
    print(f"\nTodas las pruebas pasaron ({len(tests)}).")
