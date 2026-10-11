#!/usr/bin/env python3
"""Vernetzen aus einem NEBENTHREAD -- der Fall, der im Browser eintritt.

``gmsh.initialize()`` setzt ohne ``interruptible=False`` einen Signalhandler,
und das geht nur im Hauptthread. Aus einem Flask-Arbeiter scheitert die
Vernetzung mit ``signal only works in main thread of the main interpreter``
-- also **genau dann, wenn der Weg im Browser benutzt wird, und nie in einem
Test, der im Hauptthread laeuft**.

Die Falle steht seit langem im Kopf von ``ema_deck``, und ``test_deck.py``
vernetzt deshalb aus einem Nebenthread. Sie gilt aber **je Aufrufstelle**, und
das haelt keine Modulpruefung: am 20.09.2026 wurde ``ema_em3d_harm`` ueber
``run_em3d`` an den 3-D-Knopf der Oberflaeche gehaengt, und der ASM-Lauf brach
mit genau dieser Meldung ab -- ueber die Kommandozeile (Hauptthread) war
derselbe Weg gruen. Betroffen waren ``ema_em3d_harm``, ``ema_em2d_harm`` und
``ema_em2d_stat``.

Zwei Pruefungen, und die erste ist die wichtigere:

1. **Statisch ueber ALLE Aufrufstellen im Baum.** Ein neues Modul mit einem
   blanken ``gmsh.initialize()`` faellt hier sofort durch -- eine Pruefung, die
   nur die heute bekannten drei vernetzt, saehe genau den naechsten Fall nicht.
   Kostet Millisekunden und braucht weder gmsh noch Elmer.
2. **Wirklich vernetzt**, aus einem Nebenthread, je Modul einmal. Der statische
   Test prueft die Schreibweise, dieser die Sache.

Aufruf: ``venv/bin/python test_nebenthread.py`` (gmsh noetig, kein Elmer).
"""
import os
import re
import sys
import tempfile
import threading
import traceback

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)

_FEHLER = []


def check(text, ok, detail=""):
    print(f"  {'✓' if ok else '✗'} {text}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        _FEHLER.append(text)


# ---------------------------------------------------------------- 1. statisch

#: Ein echter Aufruf ist eine ANWEISUNG -- die Zeile beginnt (nach der
#: Einrueckung) mit dem Aufruf selbst. Alles andere ist Prosa: dieselbe
#: Zeichenkette steht in Modulkoepfen, in Fehlertexten und in genau diesem
#: Docstring. Eine Suche auf "kommt in der Zeile vor" faellt ueber ihren
#: eigenen Text (gemessen beim Bauen dieses Tests).
_AUFRUF = re.compile(r"^\s*gmsh\.initialize\(")


def test_alle_aufrufstellen_tragen_die_flagge():
    """Jedes ``gmsh.initialize(`` im Baum traegt ``interruptible=False``."""
    print("1. Jede Aufrufstelle im Baum traegt die Flagge")
    treffer, ohne = [], []
    for name in sorted(os.listdir(HIER)):
        if not name.endswith(".py") or name == os.path.basename(__file__):
            continue
        pfad = os.path.join(HIER, name)
        try:
            with open(pfad, encoding="utf-8") as f:
                zeilen = f.readlines()
        except OSError:
            continue
        for i, zeile in enumerate(zeilen, 1):
            if not _AUFRUF.match(zeile):
                continue
            treffer.append(f"{name}:{i}")
            if "interruptible=False" not in zeile:
                ohne.append(f"{name}:{i}: {zeile.strip()}")
    check(f"{len(treffer)} Aufrufstellen gefunden", len(treffer) >= 6,
          "zu wenige — sucht der Test noch, wonach er suchen soll?")
    check("keine ohne `interruptible=False`", not ohne, "; ".join(ohne))


# ------------------------------------------------------------- 2. wirklich

def _im_nebenthread(fn, timeout=900):
    """Fuehrt ``fn`` in einem Nebenthread aus, liefert ``None`` oder den Fehler."""
    erg = {}

    def arbeit():
        try:
            fn()
            erg["ok"] = True
        except Exception as e:                                # noqa: BLE001
            erg["fehler"] = f"{type(e).__name__}: {e}"
            erg["spur"] = traceback.format_exc()[-600:]

    t = threading.Thread(target=arbeit)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return "Thread haengt (Zeitueberschreitung)"
    if "fehler" in erg:
        # Der eine Fehler, gegen den dieser Test gebaut ist, braucht keine Spur.
        if "signal only works" in erg["fehler"]:
            return erg["fehler"] + "  <- GENAU DIESE FALLE"
        return erg["fehler"] + "\n" + erg.get("spur", "")
    return None


def _geom():
    import cae_cli
    return dict(cae_cli.frischer_payload()["geom"])


def _kaefig(geom):
    """Die Kaefiggroessen, wie die beiden ASM-Netzbauer sie erwarten."""
    import ema_asm
    kf = dict(ema_asm.kaefig(geom, 80.0))
    kf.setdefault("steg_mm", ema_asm.KAEFIG_STEG_MM)
    return kf


def test_em2d_harm_vernetzt_im_nebenthread():
    print("2. ema_em2d_harm (ASM 2-D, harmonisch) vernetzt im Nebenthread")
    ordner = tempfile.mkdtemp(prefix="nebenthread_")
    geom = dict(_geom(), machineType="asm")

    def arbeit():
        import ema_em2d_harm as E
        E.baue_netz(geom, _kaefig(geom), os.path.join(ordner, "h2.msh"),
                    gap_lagen=2, lc_eisen_mm=6.0)

    fehler = _im_nebenthread(arbeit)
    check("laeuft durch", fehler is None, fehler or "")


def test_em3d_harm_vernetzt_im_nebenthread():
    print("3. ema_em3d_harm (ASM 3-D, harmonisch) vernetzt im Nebenthread")
    ordner = tempfile.mkdtemp(prefix="nebenthread_")
    geom = dict(_geom(), machineType="asm")

    def arbeit():
        import ema_em3d_harm as E
        E.baue_netz(geom, _kaefig(geom), 80.0, os.path.join(ordner, "h3.msh"),
                    gap_lagen=1, lagen_axial=2, lagen_ring=1, lagen_stirn=1,
                    lc_eisen_mm=14.0)

    fehler = _im_nebenthread(arbeit)
    check("laeuft durch", fehler is None, fehler or "")


def test_em2d_stat_vernetzt_im_nebenthread():
    print("4. ema_em2d_stat (SynRM/EESM 2-D, magnetostatisch) vernetzt im Nebenthread")
    ordner = tempfile.mkdtemp(prefix="nebenthread_")
    geom = dict(_geom(), machineType="synrm")

    def arbeit():
        import ema_em2d_stat as E
        E.baue_netz(geom, os.path.join(ordner, "s2.msh"), axial_mm=80.0,
                    gap_lagen=2, lc_eisen_mm=6.0)

    fehler = _im_nebenthread(arbeit)
    check("laeuft durch", fehler is None, fehler or "")


def main():
    print("=== Vernetzen aus dem Nebenthread (der Browser-Fall) ===\n")
    tests = [test_alle_aufrufstellen_tragen_die_flagge]
    if "--nur-statisch" not in sys.argv:
        try:
            import gmsh                                        # noqa: F401
            tests += [test_em2d_harm_vernetzt_im_nebenthread,
                      test_em3d_harm_vernetzt_im_nebenthread,
                      test_em2d_stat_vernetzt_im_nebenthread]
        except ImportError:
            print("  (gmsh fehlt — nur die statische Pruefung; "
                  "mit der venv laufen lassen)\n")
    for t in tests:
        t()
        print()
    if _FEHLER:
        print(f"FEHLGESCHLAGEN: {len(_FEHLER)}")
        for f in _FEHLER:
            print(f"  - {f}")
        return 1
    print("ALLE PRUEFUNGEN BESTANDEN ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
