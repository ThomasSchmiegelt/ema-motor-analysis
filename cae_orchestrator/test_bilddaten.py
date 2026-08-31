"""Tests fuer den Bilddatensatz (`ema_bilddaten`) und den herausgeloesten Zeichner.

Drei Zusagen werden hier festgehalten, und alle drei sind schon einmal woanders in
diesem Repo gebrochen worden:

1. **Der Zeichner ist herausgeloest, nicht nachgebaut.** ``render_cross_section``
   muss dasselbe Bild liefern wie der Berichtsweg -- sonst bewertet der Mensch eine
   Maschine, die so nie gerechnet wurde.
2. **Im Datensatz steht nur, was das Layouttor bestaetigt.** Nicht die Naeherung
   des Erzeugers, sondern ``rotor_layout_check`` selbst wird ueber jeden Satz
   gefahren.
3. **Die Regelsuche findet nur, was da ist.** Ist eine Schranke in die Urteile
   hineingelegt, muss sie herauskommen; sind die Urteile Muenzwuerfe, muss die
   Suche das sagen und die Ablage verweigern.

Alles laeuft in einem temporaeren Ablageort. Ein Test, der in ``~/cae_projekte``
schreibt, verdirbt die Daten, ueber die er urteilen soll.
"""

import hashlib
import json
import os
import random
import sys
import tempfile

import ema_bilddaten as B
import ema_text2ema as T2E
from ema_rotorcheck import rotor_layout_check

_n_ok = _n_bad = 0


def pruefe(bedingung, text):
    global _n_ok, _n_bad
    if bedingung:
        _n_ok += 1
        print(f"  ✓ {text}")
    else:
        _n_bad += 1
        print(f"  ✗ {text}")


# Ablage umlenken, BEVOR irgendetwas geschrieben wird.
_TMP = tempfile.mkdtemp(prefix="bilddaten_test_")
B.STORE  = _TMP
B.SATZ   = os.path.join(_TMP, "datensatz.jsonl")
B.BILDER = os.path.join(_TMP, "bilder")
B.SEITE  = os.path.join(_TMP, "bewerten.html")


# ── 1. Der Zeichner ist derselbe wie im Bericht ──────────────────────────────

print("1. render_cross_section -- herausgeloest, nicht nachgebaut")
import ema_pipeline as P

G = {k: s.get("def") for k, s in T2E.SCHEMA.items() if s.get("geom")}
G.update({"p": 3, "magShape": "v", "slots": 54})
bilder = P._save_cad_images(G, 120.0, os.path.join(_TMP, "bericht"))
pruefe(os.path.isfile(os.path.join(_TMP, "bericht", bilder["cross_section"])),
       "der Berichtsweg laeuft ueber den herausgeloesten Zeichner durch")

import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(10, 10))
P.render_cross_section(G, ax)
p_direkt = os.path.join(_TMP, "direkt.png")
fig.savefig(p_direkt, dpi=130, bbox_inches="tight", facecolor="#0d1117")
plt.close(fig)
h1 = hashlib.sha256(open(os.path.join(_TMP, "bericht", bilder["cross_section"]), "rb").read()).hexdigest()
h2 = hashlib.sha256(open(p_direkt, "rb").read()).hexdigest()
pruefe(h1 == h2, "direkt gezeichnet und ueber _save_cad_images: bitgleich")

fig, ax = plt.subplots(figsize=(10, 10))
P.render_cross_section(G, ax, beschriftung=False)
pruefe(len(ax.texts) == 0 and ax.get_legend() is None,
       "beschriftung=False laesst Titel, Masszeile und Legende weg")
plt.close(fig)

# Die abgeleiteten Masse duerfen nur an EINER Stelle stehen.
m = P._schnittmasse(G)
pruefe(abs(m["R_rot"] - G["rotorOD"] / 2) < 1e-9 and m["n_poles"] == 2 * G["p"],
       "_schnittmasse liefert die Masse, aus denen beide Ansichten leben")


# ── 2. Ziehen bleibt im Schema und in der radialen Ordnung ───────────────────

print("\n2. ziehe -- Schemagrenzen und radiale Ordnung")
rng = random.Random(1234)
verletzt_schema, verletzt_ordnung = [], []
for _ in range(400):
    g = B.ziehe(rng)
    for k, v in g.items():
        spec = T2E.SCHEMA.get(k)
        if spec and spec.get("kind") == "num" and isinstance(v, (int, float)):
            if not (spec["lo"] - 1e-9 <= v <= spec["hi"] + 1e-9):
                verletzt_schema.append((k, v))
        if spec and spec.get("kind") == "enum" and v not in spec["opts"]:
            verletzt_schema.append((k, v))
    if not (g["statorOD"] > g["statorID"] > g["rotorOD"] > g["shaftD"] > 0):
        verletzt_ordnung.append(g)
pruefe(not verletzt_schema, f"400 Ziehungen halten die Schemagrenzen ({verletzt_schema[:3]})")
pruefe(not verletzt_ordnung,
       f"400 Ziehungen halten statorOD > statorID > rotorOD > shaftD ({len(verletzt_ordnung)} Verstoesse)")
pruefe(all(g["slots"] % 3 == 0 for g in (B.ziehe(rng) for _ in range(50))),
       "die Nutzahl ist immer durch 3 teilbar")

r1 = random.Random(99); r2 = random.Random(99)
pruefe(B.ziehe(r1) == B.ziehe(r2), "gleicher Seed, gleiche Geometrie -- wiederholbar")

formen = {B.ziehe(rng)["magShape"] for _ in range(400)}
pruefe(formen == set(B.BAUFORMEN), f"alle {len(B.BAUFORMEN)} Bauformen kommen vor")


# ── 3. Merkmale ──────────────────────────────────────────────────────────────

print("\n3. merkmale -- vollstaendig, endlich, nachrechenbar")
g = B.ziehe(random.Random(5))
mk = B.merkmale(g)
fehlend = [n for n in B.MERKMALSNAMEN if n not in mk]
pruefe(not fehlend, f"jedes Merkmal, ueber das die Regelsuche redet, wird berechnet ({fehlend})")
import math as _math
pruefe(all(isinstance(v, float) and _math.isfinite(v) for v in mk.values()),
       "alle Merkmale sind endliche Zahlen")
pruefe(abs(mk["nabenanteil"] - g["shaftD"] / g["rotorOD"]) < 1e-9,
       "nabenanteil ist nachgerechnet shaftD/rotorOD")
pruefe(abs(mk["luftspalt_mm"] - (g["statorID"] - g["rotorOD"]) / 2) < 1e-6,
       "luftspalt_mm ist der halbe Durchmesserunterschied")
pruefe(abs(mk["nuten_je_pol"] - g["slots"] / (2 * g["p"])) < 1e-9,
       "nuten_je_pol ist nachgerechnet slots/2p")


# ── 4. Erzeugen -- nur was das ECHTE Tor bestaetigt ──────────────────────────

print("\n4. erzeuge -- jeder Satz besteht das echte Layouttor")
erg = B.erzeuge(anzahl=40, seed=2026)
pruefe(erg["neu"] == 40, f"{erg['neu']} Varianten erzeugt (aus {erg['ziehungen']} Ziehungen)")
pruefe(0.05 < erg["ausbeute"] < 0.95,
       f"Ausbeute {erg['ausbeute']:.0%} -- gemeldet, nicht behauptet")

saetze = B._lies()
falsch = [s["id"] for s in saetze if not rotor_layout_check(s["geom"])["ok"]]
pruefe(not falsch, f"alle {len(saetze)} abgelegten Geometrien bestehen rotor_layout_check ({falsch[:3]})")
pruefe(all(os.path.isfile(os.path.join(B.STORE, s["bild"])) for s in saetze),
       "zu jedem Satz liegt ein Bild")
pruefe(len({s["id"] for s in saetze}) == len(saetze), "keine doppelten Kennungen")
pruefe(all(s["urteil"] is None for s in saetze),
       "kein Satz kommt vorbewertet auf die Welt -- keine Heuristik-Vorbelegung")

vorher = len(saetze)
erg2 = B.erzeuge(anzahl=5, seed=2026)          # derselbe Seed: alles schon bekannt
pruefe(len(B._lies()) == vorher + erg2["neu"] and erg2["doppelt"] > 0,
       f"ein zweiter Lauf haengt an, statt zu ueberschreiben ({erg2['doppelt']} Doppel erkannt)")


# ── 5. Bewertungsseite verraet nichts ────────────────────────────────────────

print("\n5. bewerten.html -- Bild und sonst nichts")
pfad = B.bewertungsseite()
html = open(pfad, encoding="utf-8").read()
daten = json.loads(html.split("const D = ", 1)[1].split(";\nconst K", 1)[0])
pruefe(len(daten) == len(B._lies()), f"{len(daten)} offene Varianten auf der Seite")
pruefe(all(set(d) == {"id", "bild"} for d in daten),
       "je Eintrag nur Kennung und Bildpfad -- keine Masse, keine Kennzahlen")
verraeter = [w for w in ("statorOD", "magWidth", "steg_min", "polbedeckung",
                         "auto_label", "urteil\":") if w in html]
pruefe(not verraeter, f"kein Geometrie- oder Heuristikwort im Quelltext ({verraeter})")


# ── 6. Urteile einlesen ──────────────────────────────────────────────────────

print("\n6. einlesen -- Rueckweg aus dem Browser")
ids = [s["id"] for s in B._lies()]
datei = os.path.join(_TMP, "urteile.json")
urteile = {kid: ("gut" if i % 3 == 0 else "schlecht") for i, kid in enumerate(ids)}
urteile["gibtesnicht"] = "gut"
urteile[ids[0]] = "voellig_daneben"
with open(datei, "w", encoding="utf-8") as f:
    json.dump(urteile, f)
e = B.einlesen(datei)
pruefe(e["gesetzt"] == len(ids) - 1, f"{e['gesetzt']} Urteile uebernommen")
pruefe(e["unbekannt"] == 1 and e["ungueltig"] == 1,
       "unbekannte Kennung und unzulaessiges Urteil werden gezaehlt, nicht geschluckt")
e2 = B.einlesen(datei)
pruefe(e2["gesetzt"] == 0 and e2["unveraendert"] == len(ids) - 1,
       "nochmal einlesen aendert nichts")


# ── 7. Regelsuche -- findet eine gelegte Schranke ────────────────────────────

print("\n7. regel_suchen -- gelegte Schranke muss herauskommen")
B.SATZ = os.path.join(_TMP, "gelegt.jsonl")
gelegt = B.erzeuge(anzahl=150, seed=77)
saetze = B._lies()
SCHWELLE = 0.35
for s in saetze:                       # Urteil kuenstlich an EIN Merkmal gehaengt
    s["urteil"] = "gut" if s["merkmale"]["nabenanteil"] <= SCHWELLE else "schlecht"
B._schreibe(saetze)
b = B.regel_suchen()
pruefe(b["genug"], f"{b['verwendet']} Urteile reichen fuer die Suche")
beste = b["regeln"][0]
pruefe(beste["test_ausgewogen"] > 0.9,
       f"gelegte Schranke wiedergefunden: {beste['regel']} "
       f"(Pruefteil {beste['test_ausgewogen']})")
pruefe(any(t["merkmal"] == "nabenanteil" for t in beste["teile"]),
       "und zwar ueber das Merkmal, an dem sie haengt")
pruefe(any(abs(t["schwelle"] - SCHWELLE) < 0.05
           for t in beste["teile"] if t["merkmal"] == "nabenanteil"),
       f"die Schwelle liegt bei {SCHWELLE} (+-0,05)")

print("\n8. regel_suchen -- Muenzwuerfe muessen als solche auffallen")
rw = random.Random(4711)
for s in saetze:
    s["urteil"] = rw.choice(("gut", "schlecht"))
B._schreibe(saetze)
b_zufall = B.regel_suchen()
pruefe(b_zufall["genug"], "genug Urteile, aber ohne Zusammenhang")
pruefe(max(r["test_ausgewogen"] for r in b_zufall["regeln"]) < 0.75,
       f"keine Regel erreicht den Pruefteil "
       f"({max(r['test_ausgewogen'] for r in b_zufall['regeln'])}) -- "
       f"im Lernteil sah die beste noch nach "
       f"{max(r['train_ausgewogen'] for r in b_zufall['regeln'])} aus")

print("\n9. zu wenige Urteile -- die Suche sagt es, statt zu raten")
B.SATZ = os.path.join(_TMP, "wenig.jsonl")
B.erzeuge(anzahl=12, seed=5)
kl = B._lies()
for i, s in enumerate(kl):
    s["urteil"] = "gut" if i % 2 else "schlecht"
B._schreibe(kl)
b_klein = B.regel_suchen()
pruefe(not b_klein["genug"] and b_klein["regeln"] == [],
       "12 Urteile: keine Regel, sondern ein Hinweis")


# ── 10. Ablegen im Erfahrungsspeicher -- und die Weigerung ───────────────────

print("\n10. merke_regel -- legt nur ab, was den Pruefteil haelt")
import ema_lernen as L


class _FakeConn:
    def execute(self, *a, **k):
        class _R:
            def fetchone(self_inner):
                return {"c": 0}
        return _R()


_echt = L.ERFAHRUNGEN
L.ERFAHRUNGEN = os.path.join(_TMP, "erfahrungen.jsonl")
try:
    r_nix = B.merke_regel(b_klein, quelle="test", conn=_FakeConn())
    pruefe(not r_nix["abgelegt"] and "Urteile" in r_nix["grund"],
           "zu wenige Urteile: nichts abgelegt, mit Begruendung")

    r_zufall = B.merke_regel(b_zufall, quelle="test", conn=_FakeConn())
    pruefe(not r_zufall["abgelegt"],
           f"Muenzwurf-Urteile: nichts abgelegt ({r_zufall['grund'][:50]}...)")

    r_gut = B.merke_regel(b, quelle="test", conn=_FakeConn())
    pruefe(r_gut["abgelegt"], "die gehaltene Schranke wird abgelegt")
    pruefe("Pruefteil" in r_gut["beleg"] and "ausgewogen 0,5" in r_gut["beleg"],
           "der Beleg nennt Pruefteil UND was blosses Raten erreicht")
    zeilen = [json.loads(z) for z in open(L.ERFAHRUNGEN, encoding="utf-8") if z.strip()]
    pruefe(len(zeilen) == 1 and zeilen[0]["quelle"] == "test",
           "genau ein Satz im Speicher -- die Weigerungen haben nichts geschrieben")
finally:
    L.ERFAHRUNGEN = _echt

pruefe(_echt != L.ERFAHRUNGEN or not os.path.dirname(_echt).startswith(_TMP),
       "der echte Erfahrungsspeicher ist wiederhergestellt")
pruefe(B.STORE.startswith(tempfile.gettempdir()),
       f"der ganze Test lief in {B.STORE} -- nicht in ~/cae_projekte")

print("\n" + "=" * 60)
print(f"{_n_ok} bestanden, {_n_bad} fehlgeschlagen")
sys.exit(1 if _n_bad else 0)
