"""Abschnitt „Wie es zu dieser Auslegung kam“ -- aus Akte, Rechnungen und Auftrag; ohne Server."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ema_entstehung as E
ok = fehl = 0
def pruefe(b, t):
    global ok, fehl
    ok, fehl = (ok + 1, fehl) if b else (ok, fehl + 1)
    print(("  ✓ " if b else "  ✗ ") + t)

with tempfile.TemporaryDirectory() as d:
    pruefe(E.entstehung_md(d) == "", "ohne Akte: leer, kein Absturz")
    os.makedirs(os.path.join(d, "rechnungen"))
    json.dump({"ok": False, "kriterien": [
        {"name": "festigkeit", "ok": True, "text": "SF 15"},
        {"name": "saettigung", "ok": False, "schwere": "hinweis", "text": "ZAHN 102 %"}]},
        open(os.path.join(d, "rechnungen", "20261030_115005_sicherheit.json"), "w"))
    open(os.path.join(d, "rechnungen", "20261030_115005_sicherheit.txt"), "w").write("# Ausgang: ABGELEHNT / verletzt\n")
    json.dump({"lineage": {"parent": "ELTERN", "origin": "variante"}, "evolution": [
        {"ts": "2026-10-30T11:49:56", "action": "analyse", "changed_inputs": {"geom.p": 6}, "key_metrics": {"B_gap_T": 0.4}},
        {"ts": "2026-10-30T11:50:05", "action": "cli:sicherheit", "note": "sicherheit --from-project x",
         "ref": "rechnungen/20261030_115005_sicherheit.txt", "werkzeug": "aaa (git x)"},
        {"ts": "2026-10-30T11:51:05", "action": "analyse", "changed_inputs": {"geom.magThick": 5}, "werkzeug": "bbb (git y)"}]},
        open(os.path.join(d, "project.json"), "w"))
    open(os.path.join(d, "AUFTRAG.md"), "w").write(
        "# Auftrag\n\n## Ziel\n\n_noch nicht festgehalten_\n\n## Entscheidungen\n\n- **2026-10-30** (pi) — N35 gewaehlt, Ferrit verworfen: Eisen 240 %.\n")
    md = E.entstehung_md(d)
    pruefe("Ferrit verworfen: Eisen 240 %" in md, "Entscheidung samt Grund steht drin")
    pruefe("_noch nicht festgehalten_" not in md, "Platzhalter erscheinen nicht als Inhalt")
    pruefe("saettigung" in md and "ZAHN 102 %" in md, "Beanstandung der Prüfung genannt")
    pruefe("p=6" not in md and "Ausgangsstand (1 Eingaben)" in md, "erster Schritt = Ausgangsstand, kein Eingabedump")
    pruefe("magThick=5" in md, "spätere Änderung benannt")
    pruefe("ELTERN" in md, "Herkunft genannt")
    pruefe("verschiedenen Werkzeugständen" in md, "Werkzeugstand-Wechsel gemeldet")
    os.remove(os.path.join(d, "AUFTRAG.md"))
    pruefe("nicht überliefert" in E.entstehung_md(d), "ohne Auftrag: sagt, dass Gründe fehlen")
print(f"\n{ok} bestanden, {fehl} fehlgeschlagen")
sys.exit(1 if fehl else 0)
