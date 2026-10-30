"""Magnetheilung und Magnetsuche -- ohne Messlauf (die Messung selbst ist ``test_magnetschluss``/echt)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cae_cli, ema_magnetheilung as H, ema_magnetsuche as S, ema_magnetschluss as MS, ema_rotorcheck as RC
ok = fehl = 0
def pruefe(b, t):
    global ok, fehl
    ok, fehl = (ok + 1, fehl) if b else (ok, fehl + 1)
    print(("  ✓ " if b else "  ✗ ") + t)

basis = cae_cli.frischer_payload()["geom"]
kaputt = dict(basis, magShape="u", magWidth=40, magThick=12, magDist=0, magDepthRel=0.45, magTangLen=100)
pruefe(RC.rotor_layout_check(kaputt)["ok"] is False, "Ausgangslage: Layout ungueltig")
h = H.heile(kaputt)
pruefe(h["set"] and RC.rotor_layout_check(h["geom"])["ok"], f"Heilung liefert ein gueltiges Layout ({h['set']})")
pruefe(len(h["aenderung"]) <= 3 and all(k in H.PARAMETER for k in h["aenderung"]), "hoechstens drei Magnetparameter geaendert")
pruefe(H.heile(basis)["aenderung"] == {} and H.heile(basis)["gueltig"], "gueltiges Layout bleibt unberuehrt")
pruefe("Nur die Geometrie ist geprueft" in h["hinweis"], "sagt, dass Magnetschluss damit NICHT beurteilt ist")
g = MS.messen(kaputt)
pruefe(g["ok"] is False and "--set magWidth" in g["grund"] and g["heilung"]["set"], "magnetschluss nennt die naechste gueltige Einstellung")
# die Heilung veraendert die Eingabe nicht
pruefe(kaputt["magWidth"] == 40, "Eingabe-Geometrie nicht veraendert")

b = dict(basis, magShape="v")
p = S.suche(b, kandidaten=200, nur_planen=True, seed=3)
pruefe(p["ok"] and p["plan"]["gueltig"] + p["plan"]["abgelehnt_layout"] == 200 and p["plan"]["abgelehnt_layout"] > 0,
       "Ziehen: gueltig + abgewiesen = gezogen, das Layouttor weist ab")
pruefe(S.suche(b, kandidaten=200, nur_planen=True, seed=3)["plan"] == p["plan"], "gleicher Seed -> gleicher Plan")
pruefe(all(lo <= hi for lo, hi in p["plan"]["bereiche"].values()), "Bereiche geordnet")
pruefe("warnung" in S.suche(dict(basis, magShape="spoke"), kandidaten=20, nur_planen=True)["plan"], "Speiche: Warnung, Streuzahl ungeprueft")
n = S.suche(b, {"magWidth": (80, 90), "magThick": (14, 15), "magDist": (0, 0)}, kandidaten=30, nur_planen=True)
pruefe(n["ok"] is False and n["plan"]["gueltig"] == 0, "Bereich ohne gueltiges Layout: ok=False, nichts gemessen")
idx = S._fern([[0.0], [0.1], [1.0], [0.5]], 3, __import__("random").Random(1))
pruefe(len(set(idx)) == 3 and 2 in idx, "Farthest-Point waehlt auseinanderliegende Punkte")
print(f"\n{ok} bestanden, {fehl} fehlgeschlagen")
sys.exit(1 if fehl else 0)
