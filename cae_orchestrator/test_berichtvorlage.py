"""Berichtsvorlage (LaTeX): Felder, Maskierung, Rueckfall -- ohne Ollama; PDF nur wenn pandoc/xelatex da sind."""
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ema_report as R
ok = fehl = 0
def pruefe(b, t):
    global ok, fehl
    ok, fehl = (ok + 1, fehl) if b else (ok, fehl + 1)
    print(("  ✓ " if b else "  ✗ ") + t)

pruefe(R._tex("a_b & 50 % #1 {x}") == r"a\_b \& 50 \% \#1 \{x\}", "Sonderzeichen werden maskiert")
pruefe(R._tex(None) == "—", "leer -> Strich")
with tempfile.TemporaryDirectory() as d:
    f = R.titelseite_felder(d, "m")
    pruefe(f["PROJEKT"] == os.path.basename(d) and f["MASCHINE"] == "—", "ohne Akte: nichts erfunden")
    t = R.titelseite_tex(dict(f, AUFGABE="20 kW & 6000 1/min_x"))
    pruefe("@@" not in t and r"20 kW \& 6000 1/min\_x" in t, "alle Felder gefuellt, Werte maskiert")
    if shutil.which("pandoc") and shutil.which("xelatex"):
        pdf = R.render_pdf("# Titel\n\nText mit 5 % und a_b.\n", d, titelseite=f)
        pruefe(os.path.getsize(pdf) > 5000, "PDF mit Vorlage entsteht")
        os.rename(R.VORLAGE_DIR, R.VORLAGE_DIR + "_weg")
        try:
            pdf = R.render_pdf("# Titel\n\nText\n", d, out_filename="b2.pdf", titelseite=f)
            pruefe(os.path.getsize(pdf) > 2000, "ohne Vorlagenordner: Rueckfall aufs bisherige Layout")
        finally:
            os.rename(R.VORLAGE_DIR + "_weg", R.VORLAGE_DIR)
print(f"\n{ok} bestanden, {fehl} fehlgeschlagen")
sys.exit(1 if fehl else 0)
