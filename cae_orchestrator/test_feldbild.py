"""Feldlinienbilder: Durchsicht, Schnitt, Polzoom, Laengsschnitt -- ohne Server.

Was hier festgenagelt wird, ist nicht „ein Bild entstand" (das sagt schon eine
Dateigroesse), sondern die vier Eigenschaften, an denen der Zweck haengt:

  1. **Alphakanal und Durchsicht.** Die Bilder MUESSEN RGBA sein, die Ecken
     MUESSEN durchsichtig sein, und die Deckkraft MUSS mit |B| steigen -- das
     ist die ganze Idee („die Luft wird unsichtbar, nicht die Flaeche blass").
     Ein Umstieg auf `savefig(facecolor=...)` faellt hier durch, nicht erst dem
     Betrachter auf.
  2. **Ein Feldlauf fuer alle Querschnitts-Ansichten.** Vier Loesungen waeren
     vierfach teuer UND vier leicht verschiedene Felder in einer Bildreihe.
  3. **Der Schnitt nimmt Material weg.** Im Sektor darf keine Flussdichte mehr
     stehen -- sonst ist es kein Schnitt, sondern eine Schraffur darueber.
  4. **Der Laengsschnitt luegt nicht.** Ohne 3-D-Ergebnis steht KEIN gerechnetes
     Feld darin, und das Bild sagt es; mit VTU wird die Ebene y=0 abgetastet.

Dazu die Seite: die Kachel muss das Schachbrett bekommen, sonst laege der
Alphakanal auf dem weissen Vorgabegrund von ``.kachel img``.
"""

import math
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import cae_cli
import ema_analysis
import ema_feldbild as FB

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


def _geom():
    """Kleine, aber baubare Maschine -- N klein halten, das ist der teure Teil."""
    p = cae_cli.frischer_payload()
    g = dict(p["geom"])
    g["p"] = 3
    return g, p


HIER = os.path.dirname(os.path.abspath(__file__))


# ── 1) Die durchsichtige Farbkarte ──────────────────────────────────────────
print("\n[1] Deckkraft = Flussdichte")

cm = FB.durchsicht_cmap()
a = np.array([cm(x)[3] for x in np.linspace(0, 1, 9)])
pruefe(a[0] < 0.02, "bei |B| = 0 ist die Farbkarte praktisch durchsichtig")
pruefe(a[-1] > 0.85, "am oberen Ende ist sie nahezu deckend")
pruefe(np.all(np.diff(a) > 0), "die Deckkraft steigt streng mit |B|")
pruefe(cm.get_bad()[3] == 0.0, "NaN (ausserhalb des Stators) bleibt unsichtbar")


# ── 2) Ein Feldlauf, aus dem alle Querschnitte kommen ───────────────────────
print("\n[2] EIN Feldlauf fuer alle Querschnitts-Ansichten")

geom, payload = _geom()
_zaehler = {"n": 0}
_echt = ema_analysis.run_em_analysis


def _gezaehlt(*a, **k):
    _zaehler["n"] += 1
    return _echt(*a, **k)


ema_analysis.run_em_analysis = _gezaehlt
try:
    with tempfile.TemporaryDirectory() as tmp:
        aus = FB.feldbilder(geom, tmp, ansichten=("linien", "schnitt", "pol"),
                            N=140, projekt_dir="")
        pruefe(_zaehler["n"] == 1,
               f"drei Querschnitts-Ansichten kosten EINEN Loeserlauf (gezaehlt "
               f"{_zaehler['n']})")
        pruefe([b["ansicht"] for b in aus] == ["linien", "schnitt", "pol"],
               "die Reihenfolge der angeforderten Ansichten bleibt erhalten")
        pruefe(all(os.path.getsize(b["pfad"]) > 5000 for b in aus),
               "alle drei Dateien sind geschrieben und nicht leer")
        pruefe(all(b["datei"].startswith("feld_") for b in aus),
               "die Dateinamen tragen den Praefix `feld_` — daran erkennt die "
               "Agentenseite die durchsichtigen Bilder")

    _zaehler["n"] = 0
    with tempfile.TemporaryDirectory() as tmp:
        FB.feldbilder(geom, tmp, ansichten=("laengs",), N=140, projekt_dir="")
        pruefe(_zaehler["n"] == 0,
               "der Laengsschnitt allein rechnet GAR kein 2-D-Feld — er braucht "
               "keines")
finally:
    ema_analysis.run_em_analysis = _echt


# ── 3) Alphakanal im fertigen PNG ───────────────────────────────────────────
print("\n[3] Der Bildgrund ist durchsichtig")

f = FB.feld_rechnen(geom, N=140)
with tempfile.TemporaryDirectory() as tmp:
    pfad = FB.bild_linien(geom, f, os.path.join(tmp, "feld_linien.png"))
    from PIL import Image
    im = Image.open(pfad)
    pruefe(im.mode == "RGBA", f"das PNG hat einen Alphakanal (mode={im.mode})")
    px = np.asarray(im)
    ecken = [px[0, 0, 3], px[0, -1, 3], px[-1, 0, 3], px[-1, -1, 3]]
    pruefe(max(ecken) == 0, f"die vier Bildecken sind voll durchsichtig ({ecken})")
    pruefe(float((px[..., 3] == 0).mean()) > 0.25,
           "ein gutes Viertel der Flaeche ist durchsichtig — die Maschine steht "
           "nicht in einem Kasten")
    pruefe(float((px[..., 3] > 200).mean()) > 0.01,
           "und irgendwo ist es auch deckend (Linien, Text, gesaettigtes Blech)")


# ── 4) Der Schnitt nimmt wirklich Material weg ──────────────────────────────
print("\n[4] Schnittdarstellung")

sektor = (25.0, 115.0)
a0, a1 = math.radians(sektor[0]), math.radians(sektor[1])
w = np.mod(f["winkel"] - a0, 2 * math.pi)
weg = (w <= np.mod(a1 - a0, 2 * math.pi)) & (f["r_mm"] >= geom["statorID"] / 2.0)
pruefe(weg.sum() > 0, "der Schnittsektor trifft ueberhaupt Statorblech")
pruefe(np.isfinite(f["B"][weg]).any(),
       "vor dem Schnitt steht dort Flussdichte — sonst pruefte der naechste "
       "Punkt gar nichts")

with tempfile.TemporaryDirectory() as tmp:
    p_voll = FB.bild_linien(geom, f, os.path.join(tmp, "voll.png"))
    p_schn = FB.bild_schnitt(geom, f, os.path.join(tmp, "schn.png"), sektor=sektor)
    from PIL import Image
    a_voll = np.asarray(Image.open(p_voll))[..., 3]
    a_schn = np.asarray(Image.open(p_schn))[..., 3]
    pruefe(float((a_schn > 0).mean()) < float((a_voll > 0).mean()),
           "das Schnittbild deckt WENIGER Flaeche ab als das volle — der Sektor "
           "ist offen, nicht uebermalt")

quelle = open(os.path.join(HIER, "ema_feldbild.py"), encoding="utf-8").read()
pruefe("blende=weg" in quelle and "np.where(weg, np.nan, f[\"B\"])" in quelle
       or "blende=weg" in quelle,
       "Silhouette UND Heatmap werden im Sektor geblendet, nicht nur eine von beiden")
pruefe("np.where(weg, f[\"A\"], np.nan)" in quelle,
       "die Feldlinien im weggenommenen Material bleiben blass stehen — eine "
       "harte Kante ohne sie laese sich als Feldgrenze lesen")


# ── 5) Polzoom: Stufen aus dem AUSSCHNITT ───────────────────────────────────
print("\n[5] Ein Pol, vergroessert")

achse = FB._pol_nach_oben(geom, 0.0)
poles = int(geom["p"]) * 2
pruefe(abs(math.remainder(achse * poles / 2, math.pi)) < 1e-9
       or abs((achse % (2 * math.pi / poles))) < 1e-9,
       "die gewaehlte Achse ist eine echte Polachse, keine dazwischen")
pruefe(abs(math.degrees(achse) - 90.0) <= 180.0 / poles + 1e-6,
       "und sie liegt so nah an der Senkrechten, wie es die Polteilung zulaesst")
pruefe("quelle=aus" in quelle,
       "die Hoehenlinien des Zooms kommen aus dem sichtbaren Ausschnitt — ueber "
       "das ganze Bild bestimmt laegen dort eine Handvoll Linien")


# ── 6) Laengsschnitt ohne 3-D-Ergebnis: sagt es ─────────────────────────────
print("\n[6] Laengsschnitt ohne 3-D-Lauf")

with tempfile.TemporaryDirectory() as tmp:
    pfad, hinweis = FB.bild_laengs(geom, os.path.join(tmp, "l.png"), axial_mm=80.0,
                                   vtu=None)
    pruefe(os.path.getsize(pfad) > 3000, "auch ohne Feld entsteht ein Bild")
    pruefe("kein 3-D" in hinweis or "nur Geometrie" in hinweis,
           f"der Hinweis sagt, dass kein gerechnetes Feld drin ist ({hinweis!r})")
pruefe("KEIN gerechnetes Feld" in quelle and "kennt kein z" in quelle,
       "und es steht IM BILD, nicht nur im Rueckgabewert — wer nur das Bild "
       "sieht, muss es sehen")
pruefe(FB.finde_vtu(tempfile.gettempdir() + "/gibt_es_nicht") is None,
       "finde_vtu haelt ein fehlendes Projekt aus")


# ── 7) Der CLI-Aufsatz ──────────────────────────────────────────────────────
print("\n[7] cae_cli.py feldbild")

pars = cae_cli.build_parser()
args = pars.parse_args(["feldbild", "--from-project", "irgendwas",
                        "--ansicht", "pol", "--n", "200"])
pruefe(args.fn is cae_cli.cmd_feldbild, "das Verb ist verdrahtet")
pruefe(args.ansicht == "pol" and args.n == 200 and args.sektor == "25,115",
       "Ansicht, Aufloesung und der Schnittsektor kommen an (Sektor mit Vorgabe)")
pruefe(hasattr(args, "last") and hasattr(args, "iq") and hasattr(args, "id_"),
       "der Betriebspunkt ist waehlbar: --last oder --iq/--id")

cli = open(os.path.join(HIER, "cae_cli.py"), encoding="utf-8").read()
pruefe("estimate_dq_currents" in cli.split("def cmd_feldbild")[1].split("\ndef ")[0],
       "--last nimmt DIESELBE MTPA-Schaetzung wie die Pipeline, kein zweites Modell")
pruefe('"charts"' in cli.split("def cmd_feldbild")[1].split("\ndef ")[0],
       "die Bilder landen in <projekt>/charts — dort findet sie die rechte Spalte "
       "beider Agentenkoepfe, ohne einen eigenen Meldeweg je Kopf")

skill = open(os.path.join(os.path.dirname(HIER),
                          ".agents/skills/cae-orchestrator/SKILL.md"),
             encoding="utf-8").read()
pruefe("`feldbild`" in skill, "das Verb steht in der EINEN SKILL.md, die beide "
                              "Koepfe lesen")


# ── 8) Die Agentenseite zeigt die Durchsicht als solche ─────────────────────
print("\n[8] Kachel im Agentenreiter")

html = open(os.path.join(HIER, "ema_agent.html"), encoding="utf-8").read()
pruefe(".kachel img.durchsicht{" in html,
       "es gibt eine eigene Regel fuer die durchsichtigen Bilder")
pruefe(re.search(r"/\^feld_/i\.test\(e\.datei\)", html) is not None,
       "und sie wird genau an `feld_*` gehaengt")
pruefe("linear-gradient" in html.split(".kachel img.durchsicht{")[1][:400],
       "hinterlegt wird ein Schachbrett — auf dem weissen Vorgabegrund von "
       "`.kachel img` waere die Durchsicht nicht zu erkennen")

print(f"\n{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
