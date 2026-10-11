#!/usr/bin/env python3
"""Der magnetostatische Elmer-Loeser (`ema_em2d_stat`) -- geprueft, nicht geglaubt.

Zwei Haelften, und die Trennung ist Absicht:

* **ohne Elmer** laeuft alles, was reine Rechnung ist -- die Formen, die
  Wicklungsregel, die Auswertung und die beiden Stellen, an denen die
  Koerpernummern entschieden werden.  Das ist der Teil, der bei jedem Lauf
  mitgeht.
* **mit `--echt`** kommt der Bezugsfall dazu, und der ist der eigentliche
  Grund, warum dieser Loeser ueberhaupt geglaubt werden darf: ein **glatter**
  Laeufer hat keine Vorzugsrichtung, also MUSS die Luftspaltwelle bei
  Staenderdurchflutung in d- und in q-Richtung dieselbe Amplitude haben.  Eine
  gemessene Salienz ohne diesen Gegenbeweis waere eine Behauptung ueber einen
  Loeser, den niemand geprueft hat.

Aufruf: ``venv/bin/python test_em2d_stat.py [--echt]``
"""

import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_em2d_stat as S                                    # noqa: E402

_N = [0, 0]


def pruefe(bedingung, text):
    _N[0 if bedingung else 1] += 1
    print(("  ok   " if bedingung else "  FEHL ") + text)


def nahe(a, b, rel=1e-3, text=""):
    ok = abs(a - b) <= rel * max(abs(b), 1e-30)
    pruefe(ok, f"{text}: {a:.6g} gegen {b:.6g} "
               f"({100.0 * abs(a - b) / max(abs(b), 1e-30):.3f} %)")


def geom():
    import cae_cli
    p = cae_cli.frischer_payload()
    return dict(p["geom"]), float(p.get("axial_len") or 80.0)


# ── 1. Die Formen: dieselbe Flaeche wie beim Rastern ──────────────────────────

def test_formen():
    """`teil_flaeche` ist die DRITTE Fassung derselben Geometrie.

    Leinwand (JS), FDM-Raster (Python) und dieser Loeser zeichnen dieselben
    Teile.  Geprueft wird gegen die geschlossene Formel der Form -- ein
    Vergleich gegen den Rasterer allein pruefte nur, dass zwei Fassungen
    denselben Fehler machen.
    """
    import gmsh
    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber("General.Terminal", 0)
    try:
        gmsh.model.add("formen")
        occ = gmsh.model.occ

        def flaeche(t):
            f = S.teil_flaeche(occ, t)
            occ.synchronize()
            return occ.getMass(2, f) * 1e6                    # m^2 -> mm^2

        nahe(flaeche({"form": "ring", "r_i": 10.0, "r_a": 20.0, "rolle": "luft"}),
             math.pi * (400 - 100), 1e-4, "Ring")
        nahe(flaeche({"form": "segment", "r_a": 90.0, "dicke": 10.0,
                      "grad": 37.0, "halb": 20.0, "rolle": "pol"}),
             math.radians(40.0) / 2.0 * (90 ** 2 - 80 ** 2), 1e-4, "Segment")
        # Ein Segment ueber 170 Grad -- dort versagt der naheliegende
        # Dreiecks-Keil, weil seine Aussenkante als Sehne in den Sektor
        # schneidet.
        nahe(flaeche({"form": "segment", "r_a": 50.0, "dicke": 5.0,
                      "grad": 0.0, "halb": 85.0, "rolle": "luft"}),
             math.radians(170.0) / 2.0 * (2500 - 2025), 1e-4, "Segment 170 Grad")
        nahe(flaeche({"form": "rechteck", "r0": 30.0, "r1": 50.0,
                      "y0": -4.0, "y1": 6.0, "grad": 23.0, "rolle": "alu"}),
             20.0 * 10.0, 1e-6, "Rechteck")
        nahe(flaeche({"form": "trapez", "r0": 20.0, "r1": 40.0,
                      "y0i": -5.0, "y1i": 5.0, "y0a": -8.0, "y1a": 8.0,
                      "grad": 0.0, "rolle": "pol"}),
             20.0 * (10.0 + 16.0) / 2.0, 1e-6, "Trapez")
        nahe(flaeche({"form": "tasche", "r_pos": 40.0, "offset": 3.0,
                      "laenge": 30.0, "hoehe": 6.0, "tilt_grad": 25.0,
                      "grad": 11.0, "rolle": "luft"}),
             30.0 * 6.0 + math.pi * 9.0, 1e-4, "Tasche (Langloch)")
        nahe(flaeche({"form": "kreis", "cx": 5.0, "cy": -2.0, "r": 3.0,
                      "rolle": "luft"}), math.pi * 9.0, 1e-4, "Kreis")
    finally:
        gmsh.finalize()


# ── 2. Die Wicklungsregel ist die des FDM ────────────────────────────────────

def test_nutstroeme():
    """Eingepraegt wird zeichengetreu, was `ema_analysis._rasterise` eintraegt.

    Der Vergleich soll Geometrie und Verfahren messen -- nicht zwei
    verschiedene Wicklungsmodelle gegeneinander.
    """
    g = {"slots": 54, "p": 3}
    a = S.nutstroeme(g, iq=0.0, id_=100.0)
    b = S.nutstroeme(g, iq=100.0, id_=0.0)
    pruefe(len(a) == 54, "eine Zahl je Nut")
    nahe(a[0], 100.0, 1e-12, "d-Strom in Nut 0 ist der Scheitelwert")
    nahe(b[0], 0.0 - 0.0, 1e-12, "q-Strom in Nut 0 ist null") if abs(b[0]) < 1e-9 \
        else pruefe(abs(b[0]) < 1e-9, "q-Strom in Nut 0 ist null")
    # Reine p-te Umfangswelle: die Summe ueber alle Nuten verschwindet.
    pruefe(abs(sum(a)) < 1e-9 and abs(sum(b)) < 1e-9,
           "Summe ueber alle Nuten ist null (kein Nullsystem)")
    # d und q stehen 90 Grad elektrisch auseinander.
    pruefe(abs(sum(x * y for x, y in zip(a, b))) < 1e-6,
           "d- und q-Belegung sind orthogonal")
    # Der Rotorwinkel dreht die Welle mechanisch um theta, elektrisch um p*theta.
    c = S.nutstroeme(g, iq=0.0, id_=100.0, rotor_angle=2.0 * math.pi / 54)
    nahe(c[1], a[0], 1e-9, "eine Nutteilung Rotorwinkel = eine Nut weiter")


# ── 3. Auswertung ────────────────────────────────────────────────────────────

def test_harmonische_und_vergleich():
    import numpy as np
    th = np.linspace(0, 2 * math.pi, 2000, endpoint=False)
    p = 3
    w = 0.8 * np.cos(p * th) + 0.2 * np.cos(3 * p * th + 0.7)
    h = S._harmonische(th, w, p)
    nahe(h["grundwelle"], 0.8, 1e-3, "Grundwelle einer bekannten Welle")
    nahe(h["amplituden"][3], 0.2, 1e-2, "dritte Polpaarharmonische")
    nahe(h["klirr_pct"], 25.0, 1e-2, "Klirranteil")

    v = S.vergleiche(th, w, th, w, p)
    nahe(v["form_abweichung_pct"], 0.0, 1e-6, "gleiche Welle: keine Abweichung")
    v = S.vergleiche(th, w, th, -3.7 * w, p)
    pruefe(v["form_abweichung_pct"] < 1e-6,
           "Vorzeichen und Hoehe zaehlen NICHT (die Form wird verglichen)")
    v = S.vergleiche(th, w, th, np.roll(w, 2000 // (4 * p)), p)
    pruefe(v["form_abweichung_pct"] > 50.0,
           "eine um 90 Grad verschobene Welle faellt auf")


# ── 4. Die Koerpernummern -- beide Stellen, an denen sie kippen koennen ──────

def test_koerperreihenfolge():
    """Die `Body`-Reihenfolge der sif IST die Nummer, unter der die VTU zaehlt.

    Gemessen am 20.09.2026: sortiert man die Koerper nach WERKSTOFF, liegt das
    Statorblech auf Body 3 und die Auswertung liest unter „Luftspalt" die
    Flussbarrieren -- 0,0042 statt 0,951 T, Faktor 225, ohne Fehlermeldung.
    """
    netz = {"gid": {"welle": 1, "rotoreisen": 2, "laeuferluft": 3,
                    "luftspalt": 4, "statoreisen": 5},
            "spulen": [], "nut_gid": [6, 7], "n_nut": 2, "A_nut_m2": 1e-4}
    with tempfile.TemporaryDirectory() as d:
        pfad = S.schreibe_sif(netz, {"slots": 2, "p": 1}, d, nut_A=[1.0, -1.0])
        text = open(pfad).read()
    for i in range(1, 8):
        pruefe(f"Body {i}\n  Target Bodies(1) = {i}\n" in text,
               f"Body {i} zeigt auf Koerper {i}")
    pruefe(text.count("Current Density") == 2, "je Nut eine Stromdichte")
    nahe(float(text.split("Body Force 1\n  Current Density = Real ")[1]
               .split("\n")[0]), 1.0 / 1e-4, 1e-9, "Stromdichte = A / Flaeche")

    # Und die Gegenprobe: eine Reihenfolge, die nicht der Nummer folgt, wird
    # ABGEWIESEN statt still falsch gerechnet.
    netz2 = dict(netz, nut_gid=[6, 9])
    try:
        with tempfile.TemporaryDirectory() as d:
            S.schreibe_sif(netz2, {"slots": 2, "p": 1}, d, nut_A=[1.0, -1.0])
        pruefe(False, "Luecke in den Koerpernummern wird abgewiesen")
    except RuntimeError as e:
        pruefe("Body" in str(e), "Luecke in den Koerpernummern wird abgewiesen")


def test_zuordnung():
    """`zuordnen` erkennt die Koerper an Flaeche UND Schwerpunkt wieder.

    Die Flaeche allein genuegt nicht -- die Statornuten sind flaechengleich.
    """
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "mesh.nodes"), "w") as fh:
            # zwei Dreiecke: eines um (0|0), eines um (10|0), gleiche Flaeche
            for i, (x, y) in enumerate([(0, 0), (1, 0), (0, 1),
                                        (10, 0), (11, 0), (10, 1)], start=1):
                fh.write(f"{i} -1 {x} {y} 0\n")
        with open(os.path.join(d, "mesh.elements"), "w") as fh:
            fh.write("1 7 303 1 2 3\n2 4 303 4 5 6\n")
        netz = {"r_so": 20.0,
                "flaeche": {"a": (0.5, 1.0 / 3, 1.0 / 3),
                            "b": (0.5, 10 + 1.0 / 3, 1.0 / 3)}}
        zu = S.zuordnen(d, netz)
        pruefe(zu == {"a": 7, "b": 4},
               f"flaechengleiche Koerper ueber den Schwerpunkt getrennt: {zu}")
        # Und was NICHT wiedererkannt wird, wird gesagt statt geraten.
        try:
            S.zuordnen(d, {"r_so": 20.0, "flaeche": {"x": (99.0, 0.0, 0.0)}})
            pruefe(False, "unbekannter Koerper wird benannt statt geraten")
        except RuntimeError as e:
            pruefe("nicht wiedererkannt" in str(e),
                   "unbekannter Koerper wird benannt statt geraten")


# ── 5. Der Bezugsfall (nur mit --echt) ───────────────────────────────────────

def test_echt(work: str):
    """Glatter Laeufer: d/q MUSS 1 sein, und die Hoehe muss stimmen."""
    g, ax = geom()
    g["machineType"] = "synrm"                # nur als Traeger der Geometrie
    I = 300.0
    ctx = S.vorbereiten(g, os.path.join(work, "glatt"), axial_mm=ax,
                        gap_lagen=6, teile=[], melde=print)
    d = S.loese(ctx, id_=I)
    q = S.loese(ctx, iq=I)
    print(f"  glatt: d {d['grundwelle']:.5f} T  q {q['grundwelle']:.5f} T  "
          f"klirr {d['klirr_pct']:.2f} %")
    nahe(d["grundwelle"] / q["grundwelle"], 1.0, 2e-3,
         "glatter Laeufer hat KEINE Vorzugsrichtung (d/q = 1)")
    pruefe(d["klirr_pct"] < 3.0,
           f"glatter Laeufer liefert eine saubere Welle "
           f"(Klirranteil {d['klirr_pct']:.2f} % < 3 %)")

    # Geschlossene Gegenrechnung: die Nutdurchflutung ergibt eine Welle
    # F(theta) = I_scheitel * n_nut / (2*pi*p) * sin(p*theta), und die
    # Luftspaltinduktion ist mu0*F/(k_c*g).  k_c ist die Carterzahl der
    # GEZEICHNETEN offenen Nut; geprueft wird deshalb ein Band, nicht ein Wert
    # -- eine engere Schranke waere eine Aussage ueber die Carterzahl, und die
    # gehoert nach `ema_em2d_harm`.
    f1 = I * float(g["slots"]) / (2.0 * math.pi * float(g["p"]))
    b_ideal = S.MU0 * f1 / (ctx["netz"]["gap_m"])
    k_c = b_ideal / d["grundwelle"]
    print(f"  ideal (k_c = 1): {b_ideal:.4f} T  ->  gemessene Carterzahl "
          f"{k_c:.3f}")
    pruefe(1.1 < k_c < 2.5,
           f"Hoehe passt zur offenen Nut dieser Zeichnung (k_c = {k_c:.2f})")

    # Und jetzt derselbe Staender auf dem RELUKTANZlaeufer: dieselbe
    # Durchflutung, andere Antwort -- sonst waere die Bauart nicht im Modell.
    ctx2 = S.vorbereiten(g, os.path.join(work, "synrm"), axial_mm=ax,
                         gap_lagen=6, melde=print)
    d2 = S.loese(ctx2, id_=I)
    q2 = S.loese(ctx2, iq=I)
    xi = d2["grundwelle"] / q2["grundwelle"]
    print(f"  synrm: d {d2['grundwelle']:.5f} T  q {q2['grundwelle']:.5f} T  "
          f"d/q {xi:.4f}")
    pruefe(abs(xi - 1.0) > 0.05,
           f"der Reluktanzlaeufer hat eine Vorzugsrichtung (d/q = {xi:.3f})")



def test_entartete_ecken():
    """Ein Zeichenteil ist nicht notwendig ein Viereck.

    Die Zwischenpolluft des Schenkelpollaeufers kommt als ``trapez`` mit der
    inneren Breite **null** herein und ist damit ein DREIECK. Fuer den Rasterer
    ist das harmlos (Punkt-in-Polygon), ``occ.addLine`` auf zwei gleiche Punkte
    dagegen scheitert -- und zwar erst beim Netzbau. Gemessen am 20.09.2026:
    die EESM brach in ``vorbereiten`` mit ``Could not create line`` ab,
    waehrend Leinwand und FDM-Raster dieselbe Geometrie klaglos zeichneten.
    """
    import gmsh
    gmsh.initialize(interruptible=False)
    try:
        gmsh.model.add("entartet")
        occ = gmsh.model.occ

        # 1. Das Dreieck, das als Viereck hereinkommt -- der gemessene Fall.
        f = S._polygon(occ, [(0.0, 0.0), (1.0, -1.0), (1.0, 1.0), (0.0, 0.0)])
        occ.synchronize()
        a = gmsh.model.occ.getMass(2, f)
        pruefe(abs(a - 1.0) < 1e-9,
               f"Dreieck mit doppelter Ecke wird gebaut (Flaeche {a:.6f}, soll 1)")

        # 2. Der Ringschluss zaehlt mit: letzte Ecke auf der ersten.
        f2 = S._polygon(occ, [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0),
                              (0.0, 0.0)])
        occ.synchronize()
        a2 = gmsh.model.occ.getMass(2, f2)
        pruefe(abs(a2 - 2.0) < 1e-9,
               f"geschlossener Zug wird nicht doppelt gezaehlt (Flaeche {a2:.6f})")

        # 3. Eine LINIE ist kein Koerper -- und sagt das, statt gmsh raten zu
        #    lassen. Eine kryptische Loesermeldung schickt die Suche ans
        #    falsche Ende; das war der ganze Aufwand dieses Befunds.
        try:
            S._polygon(occ, [(0.0, 0.0), (1.0, 0.0), (1.0, 0.0), (0.0, 0.0)])
            pruefe(False, "zwei verschiedene Ecken werden abgewiesen")
        except ValueError as e:
            pruefe("Ecken" in str(e),
                   "zwei verschiedene Ecken werden benannt abgewiesen")
    finally:
        gmsh.finalize()


def test_eesm_vernetzt():
    """Der Schenkelpollaeufer kommt ueberhaupt ins Netz.

    Das ist die Gegenprobe zum Befund oben, eine Ebene hoeher: nicht die
    Polygonfunktion, sondern die echte EESM-Geometrie aus
    ``ema_laeuferbild.teile()``. Sie scheiterte, und der Modulkopf behauptete
    die ganze Zeit „SynRM/EESM".
    """
    import cae_cli
    g = dict(cae_cli.frischer_payload()["geom"])
    g["machineType"] = "eesm"
    g["axialLen"] = 80.0
    with tempfile.TemporaryDirectory() as w:
        netz = S.baue_netz(g, os.path.join(w, "eesm.msh"), axial_mm=80.0,
                           gap_lagen=2, lc_eisen_mm=6.0)
    pruefe(netz["dreiecke"] > 1000 and netz["n_koerper"] > 10,
           f"die EESM vernetzt ({netz['dreiecke']} Dreiecke, "
           f"{netz['n_koerper']} Koerper)")
    pruefe(bool(netz.get("spulen")),
           f"und ihre Erregerspulen stehen im Netz ({len(netz.get('spulen') or [])})")


def test_anisotropie_ohne_erregung():
    """Die Anisotropie wird OHNE Erregung gemessen -- und der Aufrufer weiss das.

    ``loese`` hat fuer ``erregung`` die Vorgabe **1,0**. Wer sie beim Messen der
    Salienz nicht ausdruecklich auf 0 setzt, misst nicht die Antwort des EISENS
    auf den Staenderstrom, sondern die Summe aus ihr und dem Laeuferfeld.
    Gemessen am 20.09.2026: 1,154 bei 70,1 % Klirranteil statt 1,738 bei 16 %.
    Bei der SynRM faellt es nicht auf -- sie hat keine Spulen, und genau deshalb
    ging es durch die erste Messung hindurch.

    Geprueft wird beides: dass die Falle noch existiert (sonst prueft der Test
    ins Leere), und dass die Aufrufstelle sie umgeht.
    """
    import inspect
    sig = inspect.signature(S.loese)
    pruefe(sig.parameters["erregung"].default == 1.0,
           "die Falle besteht: `loese` erregt per Vorgabe (1,0)")

    import cae_cli
    quelle = inspect.getsource(cae_cli._feld2d_magnetostatisch)
    # Die vier Loeseraufrufe des Anisotropie-Teils -- die mit iq/id_ --
    # muessen `erregung=0.0` tragen.
    zeilen = [z.strip() for z in quelle.splitlines()
              if "ES.loese(" in z and ("iq=" in z or "id_=" in z)]
    pruefe(len(zeilen) == 4,
           f"vier Anisotropie-Aufrufe gefunden ({len(zeilen)})")
    ohne = [z for z in zeilen if "erregung=0.0" not in z]
    pruefe(not ohne,
           "alle tragen `erregung=0.0`"
           + (f" -- OHNE: {'; '.join(ohne)}" if ohne else ""))


if __name__ == "__main__":
    echt = "--echt" in sys.argv
    print("== Formen ==");             test_formen()
    print("== Nutstroeme ==");         test_nutstroeme()
    print("== Auswertung ==");         test_harmonische_und_vergleich()
    print("== Koerperreihenfolge =="); test_koerperreihenfolge()
    print("== Zuordnung ==");          test_zuordnung()
    print("== Entartete Ecken ==");    test_entartete_ecken()
    print("== EESM vernetzt ==");      test_eesm_vernetzt()
    print("== Erregung ==");           test_anisotropie_ohne_erregung()
    if echt:
        import elmer_runner
        if not elmer_runner.ELMER_OK:
            print("== Bezugsfall == uebersprungen (Elmer fehlt)")
        else:
            print("== Bezugsfall (echter Loeserlauf) ==")
            with tempfile.TemporaryDirectory() as w:
                test_echt(w)
    else:
        print("(Bezugsfall uebersprungen -- mit --echt laeuft Elmer wirklich)")
    print(f"\n{_N[0]} bestanden, {_N[1]} fehlgeschlagen")
    sys.exit(1 if _N[1] else 0)
