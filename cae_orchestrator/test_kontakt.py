#!/usr/bin/env python3
"""Der Mehrkoerperlauf -- ohne Loeser, ohne gmsh, ohne FreeCAD.

Geprueft wird, was gelten MUSS, bevor ein Loeser ueberhaupt startet:

* die Anlagen liegen auf der Magnetflaeche und nicht daneben,
* eine Anlage ist eine ANLAGE und nicht die ganze Wand (sonst waere dieser
  Weg dasselbe Modell wie der verschmierte, nur teurer),
* die groesste Hauptspannung aus der geschlossenen Formel trifft die aus der
  Eigenwertzerlegung,
* der Magnet wird am ZUG beurteilt und nicht an der Vergleichsspannung,
* der Rechensatz traegt beide Werkstoffe und beide Koerpermengen,
* und die Linearitaetsprobe erkennt eine Nichtlinearitaet, statt sie
  durchzuwinken.

``--echt`` rechnet zusaetzlich einen wirklichen Kontaktlauf (Minuten, braucht
gmsh und CalculiX) und faehrt die Linearitaetsprobe ueber zwei Drehzahlen.

Lauf: ``python test_kontakt.py`` oder unter pytest.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_kontakt as K                                          # noqa: E402

_OK, _FEHL = [], []


def pruefe(name, fn):
    try:
        info = fn()
        _OK.append(name)
        print(f"  ✓ {name}" + (f"  — {info}" if info else ""))
    except Exception as e:                                       # noqa: BLE001
        _FEHL.append((name, e))
        print(f"  ✗ {name}  — {type(e).__name__}: {e}")


def _geom(**zusatz):
    import cae_cli
    g = dict(cae_cli.frischer_payload()["geom"])
    g.update(zusatz)
    return g


# ── 1. Die Anlagen ───────────────────────────────────────────────────────────

print("\n[1] Anlageflaechen")


def _je_magnet_sechs():
    g = _geom()
    an = K.anlagen(g, 80.0)
    je = {}
    for a in an:
        je.setdefault(a["magnet"], []).append(a)
    assert len({len(v) for v in je.values()}) == 1, "ungleich viele je Magnet"
    n = len(next(iter(je.values())))
    v = K.anlage_vorgaben(g)
    assert n == 2 * v["je_flanke"] + 2, (n, v)
    return f"{len(je)} Magnete x {n} Anlagen (2x{v['je_flanke']} Flanke + 2 Enden)"


pruefe("je Magnet so viele Anlagen wie vorgegeben", _je_magnet_sechs)


def _ohne_endanschlag():
    an = K.anlagen(_geom(anlageEndeMm=0.0), 80.0)
    assert an and not [a for a in an if a["art"] == "kappe"], \
        "Endanschlag trotz anlageEndeMm = 0"
    return "anlageEndeMm = 0 laesst die Enden weg (dann haelt nur Reibung)"


pruefe("der Endanschlag laesst sich abschalten", _ohne_endanschlag)


def _anlage_liegt_auf_der_magnetflaeche():
    """Der Beruehrpunkt muss auf der Flaeche liegen, die er beruehren soll."""
    g = _geom()
    an = K.anlagen(g, 80.0)
    mf = K.magnetflaechen(g, 80.0)
    schlimmste = 0.0
    for a in an:
        mx, my = mf[(a["magnet"], a["flaeche"])]
        if a["art"] == "kappe":
            d = math.dist((a["cx"], a["cy"]), (mx, my))
        else:
            # Flankenanlage sitzt laengs versetzt, aber in DERSELBEN Ebene:
            # der Abstand quer zur Flanke muss null sein.
            th = a["winkel"]
            nx, ny = -math.sin(th), math.cos(th)
            d = abs((a["cx"] - mx) * nx + (a["cy"] - my) * ny)
        schlimmste = max(schlimmste, d)
        assert d < 1e-9, (a["flaeche"], a["art"], d)
    return f"{len(an)} Anlagen, groesster Abstand zur Magnetflaeche {schlimmste:.1e} mm"


pruefe("jede Anlage liegt IN der Magnetflaeche, die sie traegt",
       _anlage_liegt_auf_der_magnetflaeche)


def _anlage_ist_keine_ganze_wand():
    """Der ganze Zweck: die Last geht durch WENIG Flaeche."""
    g = _geom()
    k = K.anlage_kennzahlen(g, 80.0)
    assert 0 < k["anteil_an_der_wand_pct"] < 40.0, k
    return (f"{k['anteil_an_der_wand_pct']:.1f} % der Taschenwand tragen — "
            f"verschmiert waeren es 100 %")


pruefe("die Anlagen tragen einen BRUCHTEIL der Wand", _anlage_ist_keine_ganze_wand)


def _kurzer_magnet_bekommt_kurze_anlagen():
    """Eine Anlage darf nie laenger werden als der Magnet, den sie traegt."""
    for w in (6.0, 12.0, 45.0):
        g = _geom(magWidth=w, pocketMode="position")
        an = K.anlagen(g, 80.0)
        if not an:
            continue
        import ema_topology as T
        lg = [l for l in T.magnet_legs(g)[0] if l.placement == "interior"][0]
        for a in an:
            if a["art"] == "flanke":
                assert a["laenge"] <= lg.length / 2.0 + 1e-9, (w, a["laenge"], lg.length)
    return "geklemmt auf laenge/(2*je_flanke) — sonst waere die Anlage die Wand"


pruefe("die Anlagenbreite wird am Magneten geklemmt",
       _kurzer_magnet_bekommt_kurze_anlagen)


def _endanschlag_kostet_luftkappe():
    g = _geom()
    k = K.anlage_kennzahlen(g, 80.0)
    assert k["endanschlag"] is True
    assert k["endanschlag_anteil_luftkappe_pct"] > 0, k
    assert any("Feldmodell" in t for t in K.grenzen()), \
        "der magnetische Nebenschluss wird nicht benannt"
    return (f"{k['endanschlag_anteil_luftkappe_pct']:.0f} % der Luftkappe — "
            f"und das Feldmodell weiss davon nichts (steht in grenzen())")


pruefe("was der Endanschlag magnetisch kostet, wird BENANNT",
       _endanschlag_kostet_luftkappe)


def _ohne_magnete_klare_absage():
    try:
        K.baue(_geom(magShape="spm"), 80.0, mesh_mm=8.0)
    except K.KontaktFehler as e:
        assert "Oberflaechenmagnete" in str(e) or "keine eingelassenen" in str(e)
        return "SPM -> KontaktFehler mit Begruendung statt stillem Durchlauf"
    raise AssertionError("ein Oberflaechenmagnet-Laeufer kam durch")


pruefe("ohne eingelassene Magnete gibt es eine Absage mit Grund",
       _ohne_magnete_klare_absage)


def _gezeichnet_geom():
    """Ein Halbpol wie der Designer ihn baut: Magnet + d-Achsen-Spiegel.

    Die Spiegelung ist (x,y)->(x,-y) und tilt->-tilt. Dabei bleibt die
    LAENGSachse u erhalten, die QUERachse v kippt -- also tauschen flanke+ und
    flanke-, waehrend u und die Kappen stehenbleiben. Genau diese Regel steht
    im Designer (`_spiegel`), und wer sie verwechselt, legt die Anlagen der
    gespiegelten Haelfte auf die falsche Flanke; im Ergebnis sieht man das
    nicht.
    """
    import cae_cli
    g = dict(cae_cli.frischer_payload()["geom"])
    g["magShape"] = "custom"
    g["p"] = 1                                   # zwei Pole: uebersichtlich
    g["customLegs"] = [
        {"r_pos": 40.0, "offset": 5.0, "tilt_deg": 30.0,
         "length": 30.0, "thickness": 6.0, "mag_sign": 1},
        {"r_pos": 40.0, "offset": -5.0, "tilt_deg": -30.0,
         "length": 30.0, "thickness": 6.0, "mag_sign": 1},
    ]
    g["customAnlagen"] = [
        [{"f": "flanke+", "u": -8.0, "b": 3.0},
         {"f": "flanke+", "u": 8.0, "b": 3.0},
         {"f": "kappe+", "u": 0.0, "b": 2.0}],
        # der Spiegel: Flanke getauscht, u und Kappe gleich
        [{"f": "flanke-", "u": -8.0, "b": 3.0},
         {"f": "flanke-", "u": 8.0, "b": 3.0},
         {"f": "kappe+", "u": 0.0, "b": 2.0}],
    ]
    return g


print("\n[1b] Gezeichnete Anlagen (Designer)")


def _gezeichnet_schlaegt_parametrisch():
    g = _gezeichnet_geom()
    an = K.anlagen(g, 80.0)
    q = {a["quelle"] for a in an}
    assert q == {"gezeichnet"}, q
    je0 = [a for a in an if a["magnet"] == 0]
    assert len(je0) == 3, je0
    assert sorted(a["flaeche"] for a in je0) == ["flanke+", "flanke+", "kappe+"]
    return f"{len(an)} Anlagen, alle aus der Zeichnung"


pruefe("gezeichnete Anlagen schlagen die parametrischen",
       _gezeichnet_schlaegt_parametrisch)


def _ohne_eintrag_weiter_parametrisch():
    g = _gezeichnet_geom()
    g["customAnlagen"] = [g["customAnlagen"][0], None]
    an = K.anlagen(g, 80.0)
    q0 = {a["quelle"] for a in an if a["leg"] == 0} if "leg" in an[0] else None
    _ = q0
    quellen = {}
    for a in an:
        quellen.setdefault(a["quelle"], 0)
        quellen[a["quelle"]] += 1
    assert set(quellen) == {"gezeichnet", "parametrisch"}, quellen
    return (f"gezeichnet {quellen['gezeichnet']}, parametrisch "
            f"{quellen['parametrisch']} — `null` heisst Vorgabe, nicht „keine\"")


pruefe("ein `null`-Eintrag faellt auf die Vorgabe zurueck",
       _ohne_eintrag_weiter_parametrisch)


def _spiegelung_liegt_spiegelbildlich():
    """Die Probe auf die Spiegelregel: Punkte und Normalen sind Spiegelbilder."""
    g = _gezeichnet_geom()
    an = K.anlagen(g, 80.0)
    # ``magnet`` zaehlt (Leg x Pol) und NICHT die Legs: bei 2 Polen ist der
    # GESPIEGELTE Leg die Nummer 2. Nummer 1 ist derselbe Leg am naechsten Pol
    # -- um 180 Grad gedreht, und mit dem Spiegel hat er nichts zu tun.
    a0 = sorted((a for a in an if a["magnet"] == 0),
                key=lambda a: (a["art"], round(a["cx"], 6), round(a["cy"], 6)))
    a1 = sorted((a for a in an if a["magnet"] == 2),
                key=lambda a: (a["art"], round(a["cx"], 6), round(-a["cy"], 6)))
    assert len(a0) == len(a1) == 3, (len(a0), len(a1))
    schlimmste = 0.0
    for x, y in zip(a0, a1):
        assert x["art"] == y["art"], (x["art"], y["art"])
        # Beruehrpunkt UND Pad-Mitte muessen spiegelbildlich liegen. Nur den
        # Beruehrpunkt zu pruefen liesse ein Pad durchgehen, das auf der
        # richtigen Linie, aber auf der falschen Seite davon sitzt.
        d = max(abs(x["cx"] - y["cx"]), abs(x["cy"] + y["cy"]),
                abs(x["mitte_x"] - y["mitte_x"]),
                abs(x["mitte_y"] + y["mitte_y"]))
        schlimmste = max(schlimmste, d)
    assert schlimmste < 1e-9, schlimmste
    return (f"3 Paare, groesste Abweichung vom Spiegelbild {schlimmste:.1e} mm "
            f"— die Flanken tauschen, u bleibt")


pruefe("der d-Achsen-Spiegel legt die Anlagen spiegelbildlich",
       _spiegelung_liegt_spiegelbildlich)


def _falsche_spiegelung_faellt_auf():
    """Gegenprobe: NICHT getauschte Flanke liegt nachweislich woanders."""
    g = _gezeichnet_geom()
    g["customAnlagen"][1] = [{"f": "flanke+", "u": -8.0, "b": 3.0},
                             {"f": "flanke+", "u": 8.0, "b": 3.0},
                             {"f": "kappe+", "u": 0.0, "b": 2.0}]
    an = K.anlagen(g, 80.0)
    # Gleich sortiert vergleichen. Ein Minimum ueber ALLE Paare faende immer
    # irgendein zufaellig passendes und waere kein Test.
    a0 = sorted((a for a in an if a["magnet"] == 0 and a["art"] == "flanke"),
                key=lambda a: round(a["cx"], 6))
    a1 = sorted((a for a in an if a["magnet"] == 2 and a["art"] == "flanke"),
                key=lambda a: round(a["cx"], 6))
    abstand = max(abs(x["cy"] + y["cy"]) for x, y in zip(a0, a1))
    assert abstand > 1.0, abstand
    return (f"ohne Flankentausch liegen sie {abstand:.2f} mm neben dem "
            f"Spiegelbild — der Test hat Trennschaerfe")


pruefe("und eine falsche Spiegelung waere sichtbar (Gegenprobe)",
       _falsche_spiegelung_faellt_auf)


def _designer_spiegelregel_im_js():
    """Die Regel steht im Designer — und sie wird hier mit `node` AUSGEFUEHRT."""
    import json
    import re
    import subprocess
    quelle = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "oberflaeche", "designer.js"),
                  encoding="utf-8").read()
    # Nicht-gieriges `.*?` traf hier zu WENIG: der Rumpf enthaelt `}` schon
    # in `({ ... })`, gefangen wurde deshalb der halbe Designer. Gesucht
    # wird jetzt bis zu der Stelle, die den Ausdruck wirklich schliesst.
    m = re.search(r"const _spiegel = as => as && as\.map\(a => \(\{"
                  r".*?b: a\.b \}\)\);", quelle, re.S)
    assert m, "_spiegel nicht gefunden"
    js = (m.group(0) + "\n"
          "const ein=[{f:'flanke+',u:-8,b:3},{f:'flanke-',u:2,b:3},"
          "{f:'kappe+',u:0,b:2},{f:'kappe-',u:0,b:2}];"
          "console.log(JSON.stringify(_spiegel(ein)));")
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                       timeout=30)
    assert r.returncode == 0, r.stderr[:300]
    aus = json.loads(r.stdout)
    assert [a["f"] for a in aus] == ["flanke-", "flanke+", "kappe+", "kappe-"], aus
    assert [a["u"] for a in aus] == [-8, 2, 0, 0], aus
    return "node fuehrt _spiegel aus: Flanken tauschen, u und Kappen bleiben"


pruefe("die Spiegelregel des Designers tut, was sie soll (mit node geprueft)",
       _designer_spiegelregel_im_js)


# ── 2. Die groesste Hauptspannung ────────────────────────────────────────────

print("\n[2] Hauptspannung (geschlossene Form)")


def _hauptzug_gegen_eigenwerte():
    import random

    import numpy as np
    random.seed(7)
    schlimmste = 0.0
    for _ in range(3000):
        s = tuple(random.uniform(-500, 500) for _ in range(6))
        T = np.array([[s[0], s[3], s[4]], [s[3], s[1], s[5]], [s[4], s[5], s[2]]])
        schlimmste = max(schlimmste,
                         abs(K._hauptzug(s) - float(np.linalg.eigvalsh(T)[-1])))
    assert schlimmste < 1e-6, schlimmste
    return f"3000 Zufallstensoren, groesste Abweichung {schlimmste:.1e} MPa"


pruefe("die geschlossene Form trifft die Eigenwertzerlegung",
       _hauptzug_gegen_eigenwerte)


def _hydrostatisch_und_schub():
    assert abs(K._hauptzug((100, 100, 100, 0, 0, 0)) - 100.0) < 1e-9
    assert abs(K._hauptzug((0, 0, 0, 50, 0, 0)) - 50.0) < 1e-9
    assert abs(K._hauptzug((-200, -200, -200, 0, 0, 0)) + 200.0) < 1e-9
    return "hydrostatisch, reiner Schub und reiner Druck stimmen"


pruefe("die Sonderfaelle stimmen (auch reiner DRUCK bleibt negativ)",
       _hydrostatisch_und_schub)


# ── 3. Kennzahlen: der Magnet wird am ZUG beurteilt ─────────────────────────

print("\n[3] Kennzahlen je Koerper")


def _netz_stellen(n_fe=40, n_mg=10):
    """Ein gestelltes Netz -- nur fuer die Auswertung, ohne gmsh."""
    kn = {i: (float(i), 0.0, 0.0) for i in range(1, 200)}
    el, ist, mag = {}, {}, {}
    for e in range(1, n_fe + n_mg + 1):
        el[e] = (e, e + 1, e + 2, e + 3)
        ist[e] = e <= n_fe
        mag[e] = None if e <= n_fe else 0
    return K.KontaktNetz(knoten=kn, elemente=el, ist_eisen=ist, magnet_von=mag,
                         n_magnete=1, axial_len=80.0, r_rot=94.3, r_shaft=30.0)


def _magnet_am_zug_nicht_an_mises():
    """Reiner DRUCK im Magneten: von Mises gross, Zug negativ -> kein Befund."""
    from ema_pipeline import LAMINATES, MAGNETS
    netz = _netz_stellen()
    sp = {}
    for e in netz.elemente:
        if netz.ist_eisen[e]:
            sp[e] = (100.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        else:
            sp[e] = (-600.0, -600.0, 0.0, 0.0, 0.0, 0.0)   # einachsiger Druck
    k = K.kennzahlen(netz, sp, LAMINATES["m270_35a"], MAGNETS["ndfeb_n35"])
    m = k["magnet"]
    assert m["von_mises_max_MPa"] > 500, m
    assert m["hauptzug_max_MPa"] <= 0.0 + 1e-9, m
    return (f"von Mises {m['von_mises_max_MPa']:.0f} MPa, Hauptzug "
            f"{m['hauptzug_max_MPa']:.1f} MPa -> der Druckfall macht keinen "
            f"Bruchbefund")


pruefe("ein gedrueckter Magnet gilt nicht als gefaehrdet (von Mises waere es)",
       _magnet_am_zug_nicht_an_mises)


def _zuggrenze_kommt_aus_der_tabelle():
    from ema_pipeline import LAMINATES, MAGNETS
    netz = _netz_stellen()
    sp = {e: ((100.0, 0, 0, 0, 0, 0) if netz.ist_eisen[e]
              else (20.0, 0, 0, 0, 0, 0)) for e in netz.elemente}
    a = K.kennzahlen(netz, sp, LAMINATES["m270_35a"], MAGNETS["ndfeb_n35"])
    b = K.kennzahlen(netz, sp, LAMINATES["m270_35a"], MAGNETS["ferrite"])
    assert a["magnet"]["zug_grenze_MPa"] > b["magnet"]["zug_grenze_MPa"]
    assert a["magnet"]["sf_zug_p99"] > b["magnet"]["sf_zug_p99"]
    return (f"NdFeB SF {a['magnet']['sf_zug_p99']} gegen Ferrit "
            f"{b['magnet']['sf_zug_p99']} bei gleicher Spannung")


pruefe("der Werkstoff bewegt das Urteil ueber den Magneten",
       _zuggrenze_kommt_aus_der_tabelle)


def _eisen_und_magnet_getrennt():
    from ema_pipeline import LAMINATES, MAGNETS
    netz = _netz_stellen(n_fe=40, n_mg=10)
    sp = {e: ((300.0, 0, 0, 0, 0, 0) if netz.ist_eisen[e]
              else (5.0, 0, 0, 0, 0, 0)) for e in netz.elemente}
    k = K.kennzahlen(netz, sp, LAMINATES["m270_35a"], MAGNETS["ndfeb_n35"])
    assert k["n_elemente_eisen"] == 40, k
    assert k["magnet"]["n_elemente"] == 10, k
    # das Blech darf die Magnetwerte NICHT mitzaehlen
    assert abs(k["stress_mean_MPa"] - 300.0) < 1e-6, k
    return "40 Blech- und 10 Magnetelemente, getrennt gemittelt"


pruefe("Blech und Magnet werden getrennt ausgewertet", _eisen_und_magnet_getrennt)


# ── 4. Der Rechensatz ────────────────────────────────────────────────────────

print("\n[4] CalculiX-Satz")


def _satz_traegt_beides():
    from ema_pipeline import LAMINATES, MAGNETS
    netz = _netz_stellen(n_fe=6, n_mg=3)
    netz.kontakte = [([(1, "S1"), (2, "S3")], [(7, "S2")])]
    netz.nset_stirn = [1, 2, 3]
    netz.fesseln = [(1, 1), (2, 2), (3, 2)]
    d = tempfile.mkdtemp()
    pf = K.schreibe_inp(netz, LAMINATES["m270_35a"], MAGNETS["ndfeb_n35"],
                        12000.0, os.path.join(d, "k.inp"), mesh_mm=6.0)
    t = open(pf).read()
    for muss in ("*MATERIAL, NAME=BLECH", "*MATERIAL, NAME=MAGNETWERKSTOFF",
                 "*ELSET, ELSET=E_EISEN", "*ELSET, ELSET=E_MAGNET",
                 "*SURFACE, NAME=SL0", "*SURFACE, NAME=MA0",
                 "*CONTACT PAIR", "*SURFACE INTERACTION", "*FRICTION",
                 "CENTRIF"):
        assert muss in t, muss
    # Die Magnetdichte MUSS die des Werkstoffs sein, nicht die des Blechs.
    assert f"{MAGNETS['ndfeb_n35']['density'] / 1e12:.9g}" in t
    assert f"{LAMINATES['m270_35a']['density'] / 1e12:.9g}" in t
    return f"{len(t.splitlines())} Zeilen, beide Werkstoffe, Kontakt + Reibung"


pruefe("der Satz traegt beide Werkstoffe, Kontakt und Reibung", _satz_traegt_beides)


def _reibung_abschaltbar():
    from ema_pipeline import LAMINATES, MAGNETS
    netz = _netz_stellen(n_fe=6, n_mg=3)
    netz.kontakte = [([(1, "S1")], [(7, "S2")])]
    netz.nset_stirn = [1]
    d = tempfile.mkdtemp()
    t = open(K.schreibe_inp(netz, LAMINATES["m270_35a"], MAGNETS["ndfeb_n35"],
                            9000.0, os.path.join(d, "k.inp"),
                            reibung=0.0)).read()
    assert "*FRICTION" not in t
    return "reibung = 0 schreibt keinen *FRICTION-Block"


pruefe("reibungsfrei ist wirklich reibungsfrei", _reibung_abschaltbar)


def _fliehkraft_auf_alle_koerper():
    """Die Magnete bringen ihre Fliehkraft SELBST mit -- keine Ersatzlast."""
    from ema_pipeline import LAMINATES, MAGNETS
    netz = _netz_stellen(n_fe=6, n_mg=3)
    netz.kontakte = [([(1, "S1")], [(7, "S2")])]
    netz.nset_stirn = [1]
    d = tempfile.mkdtemp()
    t = open(K.schreibe_inp(netz, LAMINATES["m270_35a"], MAGNETS["ndfeb_n35"],
                            12000.0, os.path.join(d, "k.inp"))).read()
    assert "Eall, CENTRIF" in t, "die Fliehkraft wirkt nicht auf ALLE Elemente"
    assert "*CLOAD" not in t, ("Knotenlasten im Mehrkoerpersatz — das waere die "
                               "Magnetlast ZUSAETZLICH zu den Magnetkoerpern, "
                               "also die doppelte Last")
    return "CENTRIF auf Eall, kein *CLOAD daneben"


pruefe("keine Ersatzlast neben den Magnetkoerpern (sonst doppelt)",
       _fliehkraft_auf_alle_koerper)


# ── 4b. Der EBENE Satz ───────────────────────────────────────────────────────

print("\n[4b] Ebener Satz (dim = 2)")


def _netz_stellen_eben(n_fe=6, n_mg=3, zustand="dehnung"):
    """Ein gestelltes EBENES Netz -- Dreiecke mit bekannter Flaeche."""
    kn = {}
    el, ist, mag = {}, {}, {}
    nr = 0
    for e in range(1, n_fe + n_mg + 1):
        # Rechtwinkliges Dreieck mit Katheten 2 und 3 -> Flaeche 3,0 mm²
        kn[nr + 1] = (0.0, 0.0, 0.0)
        kn[nr + 2] = (2.0, 0.0, 0.0)
        kn[nr + 3] = (0.0, 3.0, 0.0)
        el[e] = (nr + 1, nr + 2, nr + 3)
        ist[e] = e <= n_fe
        mag[e] = None if e <= n_fe else 0
        nr += 3
    return K.KontaktNetz(knoten=kn, elemente=el, ist_eisen=ist, magnet_von=mag,
                         n_magnete=1, axial_len=80.0, r_rot=94.3, r_shaft=30.0,
                         dim=2, ebener_zustand=zustand)


def _ebenes_element_wiegt_sein_volumen():
    """Das Gewicht der Mittelung ist in BEIDEN Dimensionen ein mm³.

    Sonst waeren die Mittelwerte der beiden Laeufe nicht gegeneinander
    lesbar -- und genau das ist der Zweck des ebenen Laufs.
    """
    netz = _netz_stellen_eben()
    v = K._elvol(netz, 1)
    assert abs(v - 3.0 * 80.0) < 1e-9, v      # Flaeche x Dicke
    return f"Dreieck 3,0 mm² x 80 mm Dicke = {v:.1f} mm³"


pruefe("ein ebenes Element wiegt Flaeche x Paketlaenge",
       _ebenes_element_wiegt_sein_volumen)


def _ebener_satz_traegt_dicke_und_typ():
    from ema_pipeline import LAMINATES, MAGNETS
    netz = _netz_stellen_eben()
    netz.kontakte = [([(1, "S1")], [(7, "S2")])]
    netz.fesseln = [(1, 1), (2, 2), (3, 2)]
    d = tempfile.mkdtemp()
    t = open(K.schreibe_inp(netz, LAMINATES["m270_35a"], MAGNETS["ndfeb_n35"],
                            12000.0, os.path.join(d, "k.inp"))).read()
    assert "TYPE=CPE3" in t, "ebener Verzerrungszustand -> CPE3"
    assert "C3D4" not in t
    # Die DICKE muss direkt unter jeder *SOLID SECTION stehen -- ohne sie
    # rechnet ccx mit 1 mm, und jede Kraft waere um die Baulaenge zu klein,
    # waehrend die Spannungen richtig aussehen.
    zl = t.splitlines()
    for i, z in enumerate(zl):
        if z.startswith("*SOLID SECTION"):
            assert zl[i + 1].strip() == "80", zl[i + 1]
    # Ein z-Freiheitsgrad gibt es am ebenen Element nicht.
    assert "Nstirn" not in t, "eine axiale Fesselung am ebenen Element"
    assert ", 3, 3," not in t
    return f"CPE3, Dicke 80 mm unter jeder *SOLID SECTION, keine z-Fesselung"


pruefe("der ebene Satz traegt Elementtyp UND Scheibendicke",
       _ebener_satz_traegt_dicke_und_typ)


def _ebener_zustand_waehlt_den_typ():
    from ema_pipeline import LAMINATES, MAGNETS
    aus = {}
    for zustand, erwartet in (("dehnung", "CPE3"), ("spannung", "CPS3")):
        netz = _netz_stellen_eben(zustand=zustand)
        netz.kontakte = [([(1, "S1")], [(7, "S2")])]
        netz.fesseln = [(1, 1)]
        d = tempfile.mkdtemp()
        t = open(K.schreibe_inp(netz, LAMINATES["m270_35a"],
                                MAGNETS["ndfeb_n35"], 9000.0,
                                os.path.join(d, "k.inp"))).read()
        assert f"TYPE={erwartet}" in t, (zustand, erwartet)
        aus[zustand] = erwartet
    return f"dehnung -> {aus['dehnung']}, spannung -> {aus['spannung']}"


pruefe("der ebene Zustand waehlt den Elementtyp", _ebener_zustand_waehlt_den_typ)


def _ebener_zustand_wird_geprueft():
    try:
        K.baue_eben(_geom(), 80.0, ebener_zustand="irgendwas")
    except K.KontaktFehler as e:
        assert "dehnung" in str(e) and "spannung" in str(e), str(e)
        return f"abgewiesen und benannt: {str(e)[:52]}…"
    raise AssertionError("ein unbekannter ebener Zustand ging durch")


pruefe("ein unbekannter ebener Zustand wird ABGEWIESEN, nicht geraten",
       _ebener_zustand_wird_geprueft)


def _kantennummern_sind_die_von_calculix():
    """CPE3/CPS3: S1 = 1-2, S2 = 2-3, S3 = 3-1.

    Eine verdrehte Zuordnung legt den Kontakt auf die FALSCHE Kante, und das
    sieht man dem Ergebnis nicht an -- es rechnet weiter und gibt Zahlen.
    """
    erwartet = {frozenset((0, 1)): "S1", frozenset((1, 2)): "S2",
                frozenset((0, 2)): "S3"}
    assert K._KANTE == erwartet, K._KANTE
    # Und jede Kante kommt genau einmal vor.
    assert len(set(K._KANTE.values())) == 3
    return "S1 = 1-2, S2 = 2-3, S3 = 3-1, jede genau einmal"


pruefe("die Kantennummern sind die von CalculiX",
       _kantennummern_sind_die_von_calculix)


def _ebene_grenzen_benennen_was_fehlt():
    g2, g3 = K.grenzen(2), K.grenzen(3)
    assert len(g2) > len(g3), (len(g2), len(g3))
    assert all(z in g2 for z in g3), "eine raeumliche Grenze fiel eben weg"
    text = " ".join(g2[len(g3):]).lower()
    for wort in ("stirnseiten", "schraegung", "ebene", "cpe3"):
        assert wort in text, wort
    return (f"{len(g3)} gemeinsame + {len(g2) - len(g3)} ebene Grenzen "
            f"(Stirnseiten, Schraegung, Elementgrad)")


pruefe("die ebenen Grenzen benennen, was die Scheibe NICHT sagt",
       _ebene_grenzen_benennen_was_fehlt)


def _ebene_konvergenz_nennt_die_klammer():
    """Die belastbare Aussage ist die Klammer, nicht eine der beiden Zahlen."""
    k = K.konvergenz(2)
    lo, hi = k["klammer_p99_MPa"]
    assert lo < hi, (lo, hi)
    assert "stress_p99_vol_MPa" in k["belastbar"]
    assert "stress_peak_MPa" in k["nicht_konvergent"]
    assert "GEGENEINANDER" in k["gemessen"], k["gemessen"]
    assert "ebener_zustand" in k, "der Zustandsvergleich fehlt"
    return (f"Klammer {lo}…{hi} MPa, beide P99 belastbar, Spitze nicht, "
            f"Zustandsvergleich dabei")


pruefe("die ebene Konvergenz nennt die KLAMMER statt einer Zahl",
       _ebene_konvergenz_nennt_die_klammer)


def _raeumliche_konvergenz_warnt_am_magneten():
    """Der raeumliche Weg darf seine Magnetzahl nicht als belastbar ausgeben.

    Gemessen 7,18 gegen 16,4 MPa, und die Ursache ist benannt: das
    Verfeinerungsfeld sitzt auf den Anlagen, und die liegen auf der
    Eisenseite. Eine Zahl, die um Faktor 2 zu optimistisch ist, muss das AN
    SICH tragen -- sie wird sonst gelesen wie jede andere daneben.
    """
    k3, k2 = K.konvergenz(3), K.konvergenz(2)
    assert "magnet_nicht_belastbar" in k3, "der raeumliche Vorbehalt fehlt"
    assert "magnet_belegt" in k2, "der ebene Beleg fehlt"
    t = k3["magnet_nicht_belastbar"].lower()
    for wort in ("optimistisch", "kontakt_eben", "mesh_magnet_mm"):
        assert wort in t, wort
    # Der ebene Beleg nennt DREI Wege.
    assert k2["magnet_belegt"].count("|") >= 2, k2["magnet_belegt"]
    # Und der raeumliche traegt den Teillast-Vorbehalt.
    assert "vorbehalt" in k3
    return ("raeumlich: Vorbehalt samt Ausweg | eben: drei belegte Wege")


pruefe("die raeumliche Konvergenz warnt am Magneten und nennt den Ausweg",
       _raeumliche_konvergenz_warnt_am_magneten)


def _volumen_p99_laesst_sich_nicht_kippen():
    """Gegenprobe zum elementgewichteten P99 -- der eigentliche Befund.

    Vielen kleinen heissen Elementen gegenueber einem grossen kalten: das
    Hundertstel ueber ELEMENTE folgt der Anzahl, das ueber das VOLUMEN dem
    Koerper. Genau diese zwei Zahlen laufen in der ebenen Reihe gegeneinander.
    """
    import ema_deck as deck
    kn = {}
    el, ist, mag = {}, {}, {}
    nr, sp = 0, {}
    # 99 winzige Dreiecke (Flaeche 0,005 mm²) mit 500 MPa, 1 grosses (50 mm²)
    # mit 10 MPa.
    for e in range(1, 101):
        gross = e == 100
        a, b = ((10.0, 10.0) if gross else (0.1, 0.1))
        kn[nr + 1] = (0.0, 0.0, 0.0)
        kn[nr + 2] = (a, 0.0, 0.0)
        kn[nr + 3] = (0.0, b, 0.0)
        el[e] = (nr + 1, nr + 2, nr + 3)
        ist[e], mag[e] = True, None
        s = 10.0 if gross else 500.0
        sp[e] = (s, 0.0, 0.0, 0.0, 0.0, 0.0)
        nr += 3
    netz = K.KontaktNetz(knoten=kn, elemente=el, ist_eisen=ist, magnet_von=mag,
                         n_magnete=0, axial_len=80.0, r_rot=94.3, r_shaft=30.0,
                         dim=2, ebener_zustand="dehnung")
    from ema_pipeline import LAMINATES, MAGNETS
    k = K.kennzahlen(netz, sp, LAMINATES["m270_35a"], MAGNETS["ndfeb_n35"])
    # Das grosse kalte Dreieck traegt 50 von 50,495 mm² = 99,0 % der Flaeche,
    # also liegt das 99. Hundertstel des VOLUMENS noch bei ihm.
    assert k["stress_p99_vol_MPa"] < 100.0, k["stress_p99_vol_MPa"]
    assert k["stress_p99_MPa"] > 400.0, k["stress_p99_MPa"]
    return (f"P99 je Element {k['stress_p99_MPa']:.0f} gegen P99 je Volumen "
            f"{k['stress_p99_vol_MPa']:.0f} MPa — dieselben Spannungen")


pruefe("das Volumen-Hundertstel folgt dem Koerper, nicht der Elementzahl",
       _volumen_p99_laesst_sich_nicht_kippen)


# ── 4c. Der Teillast-Waechter ────────────────────────────────────────────────

print("\n[4c] Teillast-Waechter (ema_deck)")


def _teillast_wird_erkannt():
    """Ein nicht durchgelaufener Lastschritt ist KEIN Ergebnis.

    ccx halbiert das Inkrement, wenn die Kontaktiteration nicht konvergiert,
    laeuft in das Inkrementlimit und **beendet sich mit 0** -- mit gueltiger
    `.frd` und einer `.dat`, in der die Spannungen des erreichten Teils der
    Last stehen. Gemessen kamen die Kennzahlen dadurch um Faktor 8 zu niedrig
    heraus, der Form nach plausibel. Spalte 6 der `.sta` ist die Schrittzeit.
    """
    import ema_deck as deck
    kopf = ("SUMMARY OF JOB INFORMATION\n"
            "  STEP      INC     ATT  ITRS     TOT TIME     STEP TIME"
            "      INC TIME\n")
    d = tempfile.mkdtemp()
    gut = os.path.join(d, "gut.sta")
    with open(gut, "w") as f:
        f.write(kopf + "     1          1     1    15  0.250000E+00  "
                       "0.250000E+00  0.250000E+00\n"
                       "     1          4     1     2  0.100000E+01  "
                       "0.100000E+01  0.125000E+00\n")
    teil = os.path.join(d, "teil.sta")
    with open(teil, "w") as f:
        f.write(kopf + "     1         14     1U   15  0.136418E+00  "
                       "0.136418E+00  0.325888E-04\n")
    assert deck._ccx_schrittzeit(gut) == 1.0
    assert abs(deck._ccx_schrittzeit(teil) - 0.136418) < 1e-9
    # Keine Auskunft ist KEIN Fehlschlag -- nicht jeder Satz schreibt eine
    # .sta, und ein Wert, den es nicht gibt, darf keinen gueltigen Lauf
    # abweisen.
    assert deck._ccx_schrittzeit(os.path.join(d, "fehlt.sta")) is None
    return "1,0 = durchgelaufen, 0,136 = Teillast, fehlende Datei = None"


pruefe("ein nicht durchgelaufener Lastschritt wird ERKANNT",
       _teillast_wird_erkannt)


def _teillast_meldet_den_anteil():
    """Die Meldung muss den Anteil NENNEN -- sonst sucht man am Netz."""
    import ema_deck as deck
    kopf = ("SUMMARY OF JOB INFORMATION\n  STEP      INC     ATT  ITRS"
            "     TOT TIME     STEP TIME      INC TIME\n")
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "x.sta"), "w") as f:
        f.write(kopf + "     1    14     1U   15  0.5E+00  0.5E+00  0.3E-04\n")
    # Der Waechter sitzt in loese_ccx; hier wird nur geprueft, dass der Anteil
    # ueberhaupt als Zahl herauskommt und die Schwelle unter 1,0 greift.
    z = deck._ccx_schrittzeit(os.path.join(d, "x.sta"))
    assert z is not None and z < 0.999
    return f"Schrittzeit {z} < 0,999 -> TEILLAST"


pruefe("die Teillast-Meldung traegt den erreichten Anteil",
       _teillast_meldet_den_anteil)


# ── 5. Die Linearitaetsprobe ─────────────────────────────────────────────────

print("\n[5] Linearitaetsprobe")


def _probe_erkennt_linear():
    a = {"stress_peak_MPa": 100.0, "stress_p99_MPa": 50.0,
         "stress_mean_MPa": 10.0, "magnet": {"hauptzug_max_MPa": 4.0}}
    b = {"stress_peak_MPa": 400.0, "stress_p99_MPa": 200.0,
         "stress_mean_MPa": 40.0, "magnet": {"hauptzug_max_MPa": 16.0}}
    p = K.linearitaetsprobe(a, b, 6000.0, 12000.0)
    assert p["linear"] is True and p["abweichung_pct"] < 1e-6, p
    return f"exakt vierfach -> linear, Abweichung {p['abweichung_pct']} %"


pruefe("exakte rpm²-Skalierung wird als linear erkannt", _probe_erkennt_linear)


def _probe_erkennt_nichtlinear():
    a = {"stress_peak_MPa": 100.0, "stress_p99_MPa": 50.0, "stress_mean_MPa": 10.0}
    b = {"stress_peak_MPa": 520.0, "stress_p99_MPa": 200.0, "stress_mean_MPa": 40.0}
    p = K.linearitaetsprobe(a, b, 6000.0, 12000.0)
    assert p["linear"] is False, p
    assert "NICHT linear" in p["bedeutung"]
    return (f"ein Ausreisser (5,2 statt 4,0) -> {p['abweichung_pct']} % "
            f"Abweichung, als nichtlinear gemeldet")


pruefe("eine Nichtlinearitaet wird GEMELDET statt durchgewunken",
       _probe_erkennt_nichtlinear)


def _konvergenz_benennt_die_singularitaet():
    """Die Spitze darf NICHT als belastbar gelten -- sie ist eine Singularitaet."""
    k = K.konvergenz()
    assert "stress_peak_MPa" in k["nicht_konvergent"], k
    assert "stress_peak_MPa" not in k["belastbar"], k
    assert "stress_p99_MPa" in k["belastbar"], k
    assert "stress_mean_MPa" in k["mesh_abhaengig"], k
    assert "stress_mean_vol_MPa" in k["belastbar"], k
    assert "magnet.hauptzug_max_MPa" in k["nicht_konvergent"], k
    assert "magnet.hauptzug_p99_MPa" in k["belastbar"], k
    # keine Groesse darf in zwei Toepfen stehen
    alle = (k["belastbar"], k["nicht_konvergent"], k["mesh_abhaengig"])
    flach = [x for t in alle for x in t]
    assert len(flach) == len(set(flach)), flach
    return (f"{len(k['belastbar'])} belastbar, "
            f"{len(k['nicht_konvergent'])} nicht konvergent, "
            f"{len(k['mesh_abhaengig'])} mesh-abhaengig")


pruefe("konvergenz() nennt die Spitze als NICHT belastbar",
       _konvergenz_benennt_die_singularitaet)


def _volumenmittel_ist_wirklich_volumengewichtet():
    """Gegenprobe: viele kleine Elemente duerfen das Volumenmittel nicht kippen."""
    from ema_pipeline import LAMINATES, MAGNETS
    # Zwei Elemente gleicher Spannung, eines winzig -- und dann hundert winzige
    # mit einer ANDEREN Spannung. Das Elementmittel kippt, das Volumenmittel
    # darf es nicht.
    kn = {1: (0, 0, 0), 2: (10, 0, 0), 3: (0, 10, 0), 4: (0, 0, 10),
          5: (0, 0, 0), 6: (0.2, 0, 0), 7: (0, 0.2, 0), 8: (0, 0, 0.2)}
    el, ist = {1: (1, 2, 3, 4)}, {1: True}
    sp = {1: (100.0, 0, 0, 0, 0, 0)}
    for e in range(2, 102):
        el[e] = (5, 6, 7, 8)
        ist[e] = True
        sp[e] = (10.0, 0, 0, 0, 0, 0)
    netz = K.KontaktNetz(knoten=kn, elemente=el, ist_eisen=ist,
                         magnet_von={e: None for e in el}, axial_len=10.0)
    k = K.kennzahlen(netz, sp, LAMINATES["m270_35a"], MAGNETS["ndfeb_n35"])
    assert k["stress_mean_MPa"] < 12.0, k["stress_mean_MPa"]     # von den 100 erdrueckt
    assert k["stress_mean_vol_MPa"] > 95.0, k["stress_mean_vol_MPa"]  # Volumen zaehlt
    return (f"Elementmittel {k['stress_mean_MPa']:.1f} gegen Volumenmittel "
            f"{k['stress_mean_vol_MPa']:.1f} MPa — genau der Effekt, der die "
            f"Konvergenzreihe um 19 % verschob")


pruefe("das Volumenmittel laesst sich nicht von vielen kleinen Elementen kippen",
       _volumenmittel_ist_wirklich_volumengewichtet)


def _grenzen_benennen_das_wesentliche():
    g = " ".join(K.grenzen()).lower()
    for wort in ("entwurfsannahme", "feldmodell", "klebung", "reib",
                 "calculix", "schrumpf"):
        assert wort in g, wort
    return f"{len(K.grenzen())} benannte Grenzen"


pruefe("grenzen() benennt Annahme, Nebenschluss, Klebung, Reibung, Loeser",
       _grenzen_benennen_das_wesentliche)


# ── 6. (optional) ein echter Lauf ────────────────────────────────────────────

if "--echt" in sys.argv:
    print("\n[6] echter Kontaktlauf (Minuten)")

    def _echt():
        import ema_deck as deck
        from ema_pipeline import LAMINATES, MAGNETS
        g = _geom()
        mat, mag = LAMINATES["m270_35a"], MAGNETS["ndfeb_n35"]
        erg = {}
        for rpm in (6000.0, 12000.0):
            netz = K.baue(g, 80.0, mesh_mm=6.0)
            d = tempfile.mkdtemp()
            pf = K.schreibe_inp(netz, mat, mag, rpm, os.path.join(d, "k.inp"),
                                mesh_mm=6.0)
            r = deck.loese_ccx(pf, timeout=5400)
            assert r["solver_status"] == "OK", r
            erg[rpm] = K.kennzahlen(netz, deck.lies_dat_spannungen(r["dat"]),
                                    mat, mag)
        p = K.linearitaetsprobe(erg[6000.0], erg[12000.0], 6000.0, 12000.0)
        assert p["linear"], p
        return (f"P99 {erg[6000.0]['stress_p99_MPa']} -> "
                f"{erg[12000.0]['stress_p99_MPa']} MPa, "
                f"Abweichung von omega² {p['abweichung_pct']} %")

    pruefe("zwei echte Kontaktlaeufe skalieren mit omega²", _echt)

    def _echt_eben():
        """Der EBENE Lauf, wirklich gerechnet -- und gegen den raeumlichen.

        Verglichen wird das volumengewichtete Mittel, nicht das P99: das P99
        ist gemessen weder netz- noch elementgradunabhaengig (BEFUNDE.md
        23.10.2026 (b)), das Volumenmittel schon. Dazu das Eisenvolumen als
        unabhaengige Gegenprobe, dass beide denselben Koerper beschreiben.
        """
        import ema_deck as deck
        from ema_pipeline import LAMINATES, MAGNETS
        g = _geom()
        mat, mag = LAMINATES["m270_35a"], MAGNETS["ndfeb_n35"]
        aus = {}
        for name, netz in (("eben", K.baue_eben(g, 80.0, mesh_mm=2.0,
                                                mesh_anlage_mm=0.6)),
                           ("raeumlich", K.baue(g, 80.0, mesh_mm=6.0))):
            d = tempfile.mkdtemp()
            pf = K.schreibe_inp(netz, mat, mag, 12000.0,
                                os.path.join(d, "k.inp"),
                                mesh_mm=netz.netz_grund_mm)
            r = deck.loese_ccx(pf, timeout=5400)
            # Ein TEILLAST-Lauf ist kein Ergebnis -- und sieht wie eines aus.
            assert r["solver_status"] == "OK", (name, r)
            aus[name] = K.kennzahlen(netz, deck.lies_dat_spannungen(r["dat"]),
                                     mat, mag)
        me, mr = (aus["eben"]["stress_mean_vol_MPa"],
                  aus["raeumlich"]["stress_mean_vol_MPa"])
        ve, vr = (aus["eben"]["volumen_eisen_mm3"],
                  aus["raeumlich"]["volumen_eisen_mm3"])
        assert abs(ve - vr) / vr < 0.02, (ve, vr)       # derselbe Koerper
        assert abs(me - mr) / mr < 0.15, (me, mr)
        return (f"Mittel je Volumen eben {me:.2f} gegen raeumlich {mr:.2f} MPa "
                f"({abs(me - mr) / mr * 100:.1f} %), Eisenvolumen "
                f"{ve / 1e6:.3f} gegen {vr / 1e6:.3f}e6 mm³")

    pruefe("der ebene Lauf trifft den raeumlichen am Volumenmittel",
           _echt_eben)
else:
    print("\n[6] (echter Kontaktlauf uebersprungen — mit --echt anfordern)")


print("\n" + "=" * 62)
print(f"{len(_OK)} bestanden, {len(_FEHL)} fehlgeschlagen")
if _FEHL:
    for n, e in _FEHL:
        print(f"  ✗ {n}: {e}")
    sys.exit(1)
