"""Die Axialflussmaschine als CAD — Geometrie als reine Zahlen, in Millimetern.

**Warum ein eigenes Modul und nicht ein Zweig in ``ema_freecad``.** Der dortige
Erzeuger schreibt Python-TEXT fuer einen fremden Prozess. Stuende die Geometrie
nur darin, gaebe es sie genau einmal -- im erzeugten Skript -- und weder ein
Querschnittsbild noch ein Test kaeme an sie heran; derselbe Fall, der bei den
Wickelkopfradien (``ema_wicklung.hairpin_radien``) und beim Schenkelpol
(``ema_eesm_cad``) schon eingetreten ist. Also: hier die ZAHLEN, dort der Text.

**Woraus gebaut wird, und zwar ausschliesslich:**

* ``ema_axial.auslegung`` -- Ringraum, Polzahl, Nutzahl, Luftspalt, Magnetdicke,
  Polbedeckung. Dieselbe Funktion, aus der Stufe 1 rechnet.
* ``ema_axial_fdm.lagen`` -- die axiale Schichtung samt Magnetvorzeichen. Seit
  dem 07.10.2026 die EINE Quelle; vorher stand sie zweimal, und der erste
  Entwurf des Elmer-Sektors war damit prompt 25 mm zu hoch.
* ``segmente``/``ringe`` hier -- die Stueckelung der Magnete. Sie gab es bisher
  **nur in JavaScript** (``axialfluss/geometrie.js``), weil nur die Zeichenseite
  sie brauchte; das CAD braucht sie auch. Das ist die gefaehrlichste Stelle des
  Moduls und deshalb mit ``node`` gegen die JS-Fassung festgenagelt
  (``test_axial_cad.py``) -- dasselbe Verfahren wie bei ``magnetLegs`` und der
  Halbpol-Umrechnung des Handy-Pfads.

**Was dieses Modul NICHT zeichnet, und warum** (``ungeprueft``/``pruefen``):

* **Lager, Gehaeuse und die Einspannung der Scheibe.** Die Scheibe traegt ihre
  Hauptlast axial (gemessen 8,6 : 1 zum momentbildenden Schub), und was sie
  haelt, ist eine Konstruktionsentscheidung, keine Ableitung aus dem Magnetkreis.
  ``ema_axial.ruecken`` rechnet die Durchbiegung gegen eine EINSPANNUNG an
  ``axialNabeD`` -- gezeichnet wird diese Nabe, nicht ihre Verschraubung.
* **Die Bandage.** ``ema_axial.bandage`` sagt, mit welcher Kraft die Magnete in
  der Scheibenebene nach aussen ziehen und dass kein Blechsteg sie haelt -- aber
  ein Bandagenwerkstoff steht in keiner Tabelle dieses Werkzeugs, also wird auch
  kein Querschnitt gezeichnet.
* **Der jochlose Staender haengt in der Luft.** Beim YASA gibt es keinen Ring,
  der die Zaehne verbindet; sie sitzen in einem Verguss. Der wird NICHT gebaut,
  und deshalb liefert dieser Weg beim YASA bewusst **mehrere** Festkoerper statt
  eines verbundenen Staenders. Einen Ring zu erfinden hiesse, den magnetischen
  Kurzschluss zu zeichnen, den die Bauform gerade vermeidet.
"""
from __future__ import annotations

import math

#: Luft zwischen Kupfer und Zahn (Nutisolation). Zeichengroesse -- sie geht in
#: keine Kennzahl ein, aber ohne sie beruehren sich zwei Koerper, und FreeCADs
#: `fuse` macht daraus gelegentlich einen Verbund statt zweier Teile.
ISO_MM = 0.3

#: Winkelluft zwischen zwei benachbarten Spulen in der Nutmitte. Dieselbe
#: Begruendung; gemessen als Anteil der Nutbreite.
SPULEN_LUFT = 0.12

#: Ueberstand, mit dem Schnittkoerper ueber den Rand hinausgezeichnet werden.
#: Eine Gerade an einen Kreis zu legen laesst sonst Splitter von Bruchteilen
#: eines Mikrometers stehen -- gemessen 0,0006 mm am Schenkelpol, und genau
#: daran scheitert `fuse` spaeter.
RAND_UEBERSTAND_MM = 0.5

#: Polygonstuetzpunkte je Bogen. 50 war am Schenkelpol der gemessene Wert, bei
#: dem der Sehnenfehler unter dem kleinsten echten Merkmal bleibt.
BOGEN_PUNKTE = 50


def _z(geom: dict, schluessel: str, ersatz: float) -> float:
    """``geom[schluessel]`` als Zahl -- ``None`` gilt als FEHLT.

    Dieselbe Falle wie in ``ema_axial_thermik._zahl`` und ``ema_thermal._z``:
    ``dict.get(k, ersatz)`` greift nur bei einem fehlenden Schluessel, nicht bei
    einem vorhandenen mit dem Wert ``None`` -- und ``ema_text2ema.SCHEMA`` traegt
    ``None`` fuer jeden Eintrag.
    """
    v = (geom or {}).get(schluessel)
    if v is None or v == "":
        return float(ersatz)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(ersatz)


def segmente(geom: dict) -> dict:
    """Die Stueckelung EINER Polteilung in Umfangsrichtung, als BRUCHTEILE.

    Python-Zwilling von ``axialfluss/geometrie.js:magnetSegmente``. Gerechnet
    wird in Bruchteilen der Polteilung, und das ist der Grund, warum eine
    Funktion fuer alle Radien genuegt: die Fuge zwischen zwei Segmenten ist eine
    RADIALE Linie, also ein fester WINKEL -- so sind Ringsektormagnete
    gefertigt. Ihre mm-Angabe gilt am mittleren Radius; aussen ist sie weiter,
    innen enger.
    """
    import ema_axial

    a = ema_axial.auslegung(geom)
    art = str((geom or {}).get("axialLaeuferart") or "sektor")
    hal = art == "halbach"
    n_u = max(1, min(16, int(round(_z(geom, "axialMagSegUmfang", 1)))))
    # Das Halbach-Array deckt die Polteilung VOLL ab -- das ist sein Zweck; eine
    # Polbedeckung < 1 waere dort ein Widerspruch und wird nicht gezeichnet.
    bed = 1.0 if hal else max(0.0, min(1.0, float(a["polbedeckung"])))
    ro, ri = a["r_aussen_m"] * 1000.0, a["r_innen_m"] * 1000.0
    rm = (ri + ro) / 2.0
    f_mm = max(0.0, _z(geom, "axialMagFugeMm", 0.0))
    fug = (f_mm * a["poles"]) / (2.0 * math.pi * rm) if rm > 0 else 0.0
    # Halbach liegt periodisch, hat also n_u Fugen je Polteilung. Bei Bedeckung
    # unter 1 sind es n_u-1 -- die Luecke zum Nachbarpol ist keine Fuge.
    n_fug = n_u if hal else n_u - 1
    breit = (bed - n_fug * fug) / n_u
    u0 = (1.0 - bed) / 2.0
    seg = []
    for k in range(n_u):
        mitte = (k / n_u) if hal else (u0 + k * (breit + fug) + breit / 2.0)
        seg.append({"k": k, "mitte": mitte, "breit": breit,
                    "u0": mitte - breit / 2.0, "u1": mitte + breit / 2.0})
    return {"seg": seg, "nU": n_u, "bed": bed, "hal": hal, "fug": fug,
            "breit": breit, "eng": breit <= 0}


def ringe(geom: dict) -> dict:
    """Die Magnetringe ueber dem Radius, in Millimetern.

    Python-Zwilling von ``axialfluss/geometrie.js:magnetRinge``. Im abgewickelten
    Schnitt sind sie NICHT sichtbar (eine radiale Fuge liegt auf konstantem
    Radius, der Schnitt steht bei EINEM Radius) -- im CAD und in der Draufsicht
    schon.
    """
    import ema_axial

    a = ema_axial.auslegung(geom)
    ro, ri = a["r_aussen_m"] * 1000.0, a["r_innen_m"] * 1000.0
    n_r = max(1, min(8, int(round(_z(geom, "axialMagSegRadial", 1)))))
    f_mm = max(0.0, _z(geom, "axialMagFugeMm", 0.0))
    h = (ro - ri - (n_r - 1) * f_mm) / n_r
    rg = []
    for k in range(n_r):
        r0 = ri + k * (h + f_mm)
        rg.append({"k": k, "r0": r0, "r1": r0 + h, "h": h})
    return {"rg": rg, "nR": n_r, "h": h, "fuge": f_mm, "eng": h <= 0}


def _nabe_r(geom: dict) -> float:
    """Einspannradius der Laeuferscheibe [mm]. ``axialNabeD`` sonst ``shaftD``.

    DER Haupthebel gegen die Durchbiegung (so steht es am Schemaschluessel), und
    deshalb wird er gezeichnet und nicht aus der Welle geraten.
    """
    nd = _z(geom, "axialNabeD", 0.0)
    return (nd if nd > 0 else _z(geom, "shaftD", 60.0)) / 2.0


def teile(geom: dict, axial_mm: float | None = None) -> dict:
    """Alle Koerper der Scheibenmaschine als reine Zahlen, in Millimetern.

    Form je Teil: ``ring`` (Kreisring), ``ringsektor`` (Ringsektor ueber einen
    Winkelbereich), ``zylinder``, ``kasten`` (Quader, fuer die parallelflankige
    Nut). ``z0``/``z1`` sind die axialen Grenzen aus ``ema_axial_fdm.lagen``.

    **Die Winkelteilung ist nicht beliebig.** Der Zahn sitzt auf ``s*2pi/Q``,
    die Nut dazwischen -- genau wie im FDM-Raster, das ``|u - tau_s/2| <=
    b_nut/2`` je Zelle schneidet. Ohne diese Uebereinstimmung zeichnet das CAD
    eine um eine halbe Nutteilung verdrehte Maschine, und das faellt in keinem
    Bild auf.
    """
    import ema_axial
    import ema_axial_fdm as AF

    a = ema_axial.auslegung(geom, axial_mm)
    lg = AF.lagen(geom)
    ro = a["r_aussen_m"] * 1000.0
    ri = a["r_innen_m"] * 1000.0
    poles = int(a["poles"])
    q = max(3, int(a["slots"]))
    r_nabe = _nabe_r(geom)
    r_welle = _z(geom, "shaftD", 60.0) / 2.0
    wk = max(0.0, _z(geom, "axialWickelkopfMm", 14.0))
    sg = segmente(geom)
    rg = ringe(geom)
    art = str((geom or {}).get("axialLaeuferart") or "sektor")
    keil = a["zahnform"] != "parallel"
    b_nut_ro = ema_axial.nutbreite_mm(geom, ro)
    tau_q = 2.0 * math.pi / q
    pol_t = 2.0 * math.pi / poles

    aus: list = []
    n_mag = 0
    for i, l in enumerate(lg):
        z0, z1 = l["z0"], l["z1"]
        if l["art"] == "ruecken":
            # Die Laeuferscheibe traegt die Magnete UND fuehrt den Fluss
            # umfangs; sie reicht deshalb von der Nabe bis zum Aussenrand.
            aus.append({"art": "eisen", "rolle": "laeufer", "form": "ring",
                        "name": f"Laeuferscheibe_{i}", "r0": r_nabe, "r1": ro,
                        "z0": z0, "z1": z1})
        elif l["art"] == "magnet":
            for pol in range(poles):
                for s in sg["seg"]:
                    for r in rg["rg"]:
                        n_mag += 1
                        aus.append({
                            "art": "magnet", "rolle": "magnet",
                            "form": "ringsektor",
                            "name": f"Magnet_{i}_{pol}_{s['k']}_{r['k']}",
                            "r0": r["r0"], "r1": r["r1"], "z0": z0, "z1": z1,
                            "th_mitte": pol * pol_t + s["mitte"] * pol_t,
                            "th_halb": max(1e-6, s["breit"] * pol_t / 2.0),
                            # Das Vorzeichen der LAGE mal das des Pols -- genau
                            # dieses Produkt unterscheidet YASA (NS) von TORUS
                            # (NN), und es kommt aus `lagen`, nicht von hier.
                            "pol": (1 if pol % 2 == 0 else -1) * int(l["kenn"] or 1),
                        })
        elif l["art"] == "stator":
            h_joch = AF._jochhoehe(geom) if AF._BAUFORMEN[a["bauform"]]["joch"] else 0.0
            # Das Joch liegt auf der dem Luftspalt ABGEWANDTEN Seite. Welche das
            # ist, sagt die Lage: `seite` steht in der Bauformtabelle.
            z_zahn0, z_zahn1 = z0, z1 - h_joch
            if h_joch > 0:
                aus.append({"art": "eisen", "rolle": "joch", "form": "ring",
                            "name": f"Staenderjoch_{i}", "r0": ri, "r1": ro,
                            "z0": z1 - h_joch, "z1": z1})
            for sl in range(q):
                aus.append({"art": "eisen", "rolle": "zahn", "form": "zahn",
                            "name": f"Zahn_{i}_{sl}", "r0": ri, "r1": ro,
                            "z0": z_zahn0, "z1": z_zahn1,
                            "th_mitte": sl * tau_q,
                            "th_halb": tau_q / 2.0,
                            "keil": keil, "b_nut_ro": b_nut_ro, "ro": ro})
                aus.append({"art": "kupfer", "rolle": "spule", "form": "spule",
                            "name": f"Spule_{i}_{sl}", "r0": max(1.0, ri - wk),
                            "r1": ro + wk, "z0": z_zahn0, "z1": z_zahn1,
                            "th_mitte": sl * tau_q,
                            "th_halb": tau_q / 2.0 * (1.0 - SPULEN_LUFT),
                            "iso": ISO_MM,
                            "keil": keil, "b_nut_ro": b_nut_ro, "ro": ro,
                            "fenster_r0": ri, "fenster_r1": ro})
    h_ges = lg[-1]["z1"] if lg else 0.0
    aus.append({"art": "stahl", "rolle": "welle", "form": "zylinder",
                "name": "Welle", "r1": r_welle,
                "z0": -0.25 * h_ges, "z1": h_ges + 0.25 * h_ges})
    return {"teile": aus, "hoehe_mm": h_ges, "r_innen_mm": ri,
            "r_aussen_mm": ro, "r_nabe_mm": r_nabe, "r_welle_mm": r_welle,
            "poles": poles, "slots": q, "n_magnet": n_mag,
            "wickelkopf_mm": wk, "zahnform": "keil" if keil else "parallel",
            "b_nut_aussen_mm": b_nut_ro, "laeuferart": art,
            "segmente": sg, "ringe": rg, "lagen": lg}


def pruefen(geom: dict, axial_mm: float | None = None) -> dict:
    """Geht diese Scheibe als CAD -- und was ist daran NICHT gezeichnet.

    Ein Nein ist hier ein Ergebnis: ``kaefig`` und ``eisenlos`` sind andere
    Maschinen (Laeuferzaehne mit Kurzschlussring bzw. ein Scheibenanker, der die
    WICKLUNG traegt), und sie als Sektormagnete zu zeichnen waere eine Zeichnung
    unter fremdem Namen -- genau der Fehler, gegen den ``ema_fluss`` gebaut ist.
    """
    import ema_axial

    t = teile(geom, axial_mm)
    a = ema_axial.auslegung(geom, axial_mm)
    befunde: list = []
    ok = True
    art = t["laeuferart"]
    if art in ("kaefig", "eisenlos"):
        ok = False
        befunde.append(
            f"Laeuferart '{art}' ist nicht gezeichnet: "
            + ("ein Kaefiglaeufer traegt Laeuferzaehne und einen "
               "Kurzschlussring, keine Sektormagnete."
               if art == "kaefig" else
               "ein Scheibenanker traegt die WICKLUNG auf dem Laeufer, nicht "
               "Magnete.")
            + " Sektormagnete an ihre Stelle zu zeichnen waere eine Zeichnung "
              "unter fremdem Namen.")
    if t["segmente"]["eng"]:
        ok = False
        befunde.append(
            f"Die Magnetsegmente haetten die Breite {t['segmente']['breit']:.4f} "
            f"Polteilungen, also keine: {t['segmente']['nU']} Stueck plus Fugen "
            f"passen nicht in die Polbedeckung {t['segmente']['bed']:.2f}.")
    if t["ringe"]["eng"]:
        ok = False
        befunde.append(
            f"Die Magnetringe haetten die Hoehe {t['ringe']['h']:.3f} mm: "
            f"{t['ringe']['nR']} Ringe plus Fugen passen nicht in den Ringraum "
            f"{t['r_aussen_mm'] - t['r_innen_mm']:.1f} mm.")
    # Der Zahn am INNENrand ist die Engstelle jeder Scheibe: die Nutteilung
    # waechst mit r, die Nut (bei `parallel`) nicht.
    tau_ri = 2.0 * math.pi * t["r_innen_mm"] / t["slots"]
    b_zahn_ri = tau_ri - ema_axial.nutbreite_mm(geom, t["r_innen_mm"])
    b_min = max(0.1, _z(geom, "axialBminMm", 2.0))
    if b_zahn_ri < b_min:
        ok = False
        befunde.append(
            f"Der Zahn ist am Innenrand {b_zahn_ri:.2f} mm breit, der "
            f"Fertigungsboden fordert {b_min:.2f} mm. Die Nutteilung ist dort "
            f"{tau_ri:.2f} mm und die Nut {ema_axial.nutbreite_mm(geom, t['r_innen_mm']):.2f} mm "
            f"-- entweder weniger Nuten, eine schmalere Nut oder ein groesseres "
            f"lambda.")
    if t["r_nabe_mm"] >= t["r_innen_mm"]:
        befunde.append(
            f"Die Nabe (r = {t['r_nabe_mm']:.1f} mm) reicht bis unter den "
            f"Innenrand des Ringraums ({t['r_innen_mm']:.1f} mm) — die "
            f"Laeuferscheibe ist dort eine Vollscheibe, das ist zeichenbar, aber "
            f"der innere Wickelkopf hat keinen Platz mehr.")
    return {"ok": ok, "befunde": befunde, "teile": t,
            "nutbreite": ema_axial.nutbreite_befund(geom),
            "ungeprueft": ungeprueft()}


def ungeprueft() -> list:
    """Was an dieser Zeichnung NICHT gerechnet und nicht gebaut ist.

    Schweigen liesse sich als „geprueft" lesen -- dieselbe Regel wie
    ``ema_eesm_cad.ungeprueft``.
    """
    return [
        "Lager, Gehaeuse und die Verschraubung der Nabe sind nicht gebaut: was "
        "die Scheibe haelt, ist eine Konstruktionsentscheidung und keine "
        "Ableitung aus dem Magnetkreis. Gezeichnet wird die Nabe, an der "
        "`ema_axial.ruecken` die Durchbiegung einspannt.",
        "Die BANDAGE ist nicht gebaut. `ema_axial.bandage` rechnet, mit welcher "
        "Kraft die Magnete in der Scheibenebene nach aussen ziehen und dass kein "
        "Blechsteg sie haelt — ein Bandagenwerkstoff steht in keiner Tabelle "
        "dieses Werkzeugs, also wird auch kein Querschnitt gezeichnet.",
        "Der jochlose Staender (YASA) bleibt MEHRERE Festkoerper: die Zaehne "
        "sitzen in einem Verguss, der nicht gebaut wird. Einen Ring zu erfinden "
        "hiesse den magnetischen Kurzschluss zu zeichnen, den die Bauform "
        "gerade vermeidet.",
        "Die Spule ist ein VOLUMEN, keine Wicklung: Windungen, Isolation und "
        "Verschaltung sind nicht gezeichnet. Fuer Kupfermasse und Widerstand "
        "rechnet `ema_axial_thermik` aus dem Querschnitt, nicht aus dieser "
        "Zeichnung.",
        "Keine Schraegung und keine Stufung der Magnete ueber dem Radius: die "
        "Segmente liegen auf konstanten Radien (`ringe`).",
    ]


# ── Der FreeCAD-Erzeuger ─────────────────────────────────────────────────────
#
# ACHTUNG: dieser Block schreibt Python-TEXT fuer einen fremden Prozess. Ein
# dreifaches Anfuehrungszeichen darin beendet die umschliessende Zeichenkette --
# in diesem Repo zweimal passiert (`ema_freecad._pol_spule` traegt dieselbe
# Warnung). Deshalb stehen in den erzeugten Funktionen nur `#`-Kommentare.

_KOPF = '''# erzeugt von ema_axial_cad -- Axialflussmaschine (Scheibenlaeufer)
import FreeCAD as App, Part, math
doc = App.newDocument("AxialMotor")
Z = App.Vector(0, 0, 1)

def _ring(r0, r1, z0, z1):
    # Kreisring als Rohr. r0 = 0 ergibt einen Vollzylinder.
    h = z1 - z0
    aus = Part.makeCylinder(r1, h, App.Vector(0, 0, z0), Z)
    if r0 > 1e-9:
        aus = aus.cut(Part.makeCylinder(r0, h + 2.0,
                                        App.Vector(0, 0, z0 - 1.0), Z))
    return aus

def _sektor(r0, r1, z0, z1, th_m, th_h):
    # Ringsektor. makeCylinder(..., angle) laeuft von 0 bis angle, also wird er
    # um (th_m - th_h) gedreht -- NICHT um th_m, das war der erste Fehlgriff.
    h = z1 - z0
    a = math.degrees(2.0 * th_h)
    aus = Part.makeCylinder(r1, h, App.Vector(0, 0, z0), Z, a)
    if r0 > 1e-9:
        aus = aus.cut(Part.makeCylinder(r0, h + 2.0,
                                        App.Vector(0, 0, z0 - 1.0), Z))
    aus.rotate(App.Vector(0, 0, 0), Z, math.degrees(th_m - th_h))
    return aus

def _kasten(laenge, breite, z0, z1, th_m, r_mitte):
    # Quader der Breite `breite`, laengs der Radialen bei th_m -- die
    # parallelflankige Nut. Er wird am Ursprung gebaut, dann geschoben, dann
    # gedreht; die Reihenfolge ist nicht beliebig.
    h = z1 - z0
    b = Part.makeBox(laenge, breite, h,
                     App.Vector(r_mitte - laenge / 2.0, -breite / 2.0, z0))
    b.rotate(App.Vector(0, 0, 0), Z, math.degrees(th_m))
    return b

def _zahn(t):
    ri, ro, z0, z1 = t["r0"], t["r1"], t["z0"], t["z1"]
    th_m, th_h = t["th_mitte"], t["th_halb"]
    if t["keil"]:
        # Keilzahn: die Nut hat konstanten WINKEL, also laesst sich der Zahn
        # direkt als Ringsektor bauen -- ohne eine einzige Boolesche.
        dth = t["b_nut_ro"] / (2.0 * t["ro"])
        return _sektor(ri, ro, z0, z1, th_m, max(1e-5, th_h - dth))
    # Parallele Nut: voller Sektor minus die beiden halben Nuten an den
    # Teilungsgrenzen. Die Schnittkoerper ragen ueber den Rand hinaus, sonst
    # bleiben Splitter von Bruchteilen eines Mikrometers stehen.
    aus = _sektor(ri, ro, z0, z1, th_m, th_h)
    lang = (ro - ri) + 4.0 * RAND
    rm = (ri + ro) / 2.0
    for s in (-1.0, +1.0):
        aus = aus.cut(_kasten(lang, t["b_nut_ro"], z0 - RAND, z1 + RAND,
                              th_m + s * th_h, rm))
    return aus

def _spule(t):
    # Die Spule umfasst den Zahn: aeusserer Sektor (ueber den Ringraum hinaus
    # nach innen UND aussen -- der Wickelkopf der Scheibe liegt radial, nicht
    # axial) minus dem um die Isolation vergroesserten Zahn.
    aus = _sektor(t["r0"], t["r1"], t["z0"], t["z1"], t["th_mitte"], t["th_halb"])
    zg = dict(t)
    zg["r0"] = max(0.5, t["fenster_r0"] - t["iso"])
    zg["r1"] = t["fenster_r1"] + t["iso"]
    zg["th_halb"] = t["th_halb_zahn"] + t["iso"] / max(t["fenster_r0"], 1.0)
    return aus.cut(_zahn(zg))

GEBAUT = {}
'''

_FUSS = '''
# ── Messen am FERTIGEN Koerper, nicht an den Zahlen davor ────────────────────
vol = 0.0
for nm, o in GEBAUT.items():
    try:
        vol += float(o.Shape.Volume)
    except Exception:
        pass
print("CAD_VOLUME:%.2f" % vol)
# `CAD_FACES` erwartet `freecad_runner` -- ohne den Marker meldet der Lauf
# "0 Flaechen", was wie ein leeres Dokument aussieht und keines ist.
import json as _js0
_f = []
for nm, o in GEBAUT.items():
    try:
        _f.append(len(o.Shape.Faces))
    except Exception:
        pass
print("CAD_FACES:" + _js0.dumps({"n": sum(_f), "teile": len(_f)}))
import json
_z = {}
for nm, o in GEBAUT.items():
    try:
        sh = o.Shape
        _z[nm] = {"v": round(float(sh.Volume), 3),
                  "solids": len(sh.Solids), "gueltig": bool(sh.isValid())}
    except Exception as e:
        _z[nm] = {"fehler": str(e)[:80]}
print("AX_TEILE:" + json.dumps(_z))
doc.recompute()
doc.saveAs(SAVE)
print("SAVED:" + SAVE)
try:
    import Import
    Import.export([o for o in GEBAUT.values()], STEP)
    print("STEP_SAVED:" + STEP)
except Exception as e:
    print("STEP_FAIL:" + str(e)[:200])

# ── Durchdringung: nur die Paare, die etwas bedeuten ─────────────────────────
#
# Paarweise ueber alle 131 Teile waeren 8515 Schnitte. Geprueft wird deshalb
# gezielt: der LUFTSPALT (Zahn gegen Magnet -- beruehren sie sich, ist die
# Maschine magnetisch kurzgeschlossen), Zahn gegen seine eigene und gegen die
# NACHBARspule (dort sitzt die Isolation), Spule gegen Nachbarspule (in der
# Nutmitte), Magnet gegen Nachbarmagnet (die Fuge) und Scheibe gegen Welle.
def _ueberlapp(a, b):
    # `common().Volume` allein ist untauglich: OCC liefert bei einem
    # gescheiterten Schnitt bitgleich das Volumen eines Operanden (gemessen am
    # Planetengetriebe). Deshalb erst der Huellquader als Vorfilter -- schneiden
    # sich die nicht, kann es auch die Koerper nicht.
    ba, bb = a.BoundBox, b.BoundBox
    if (ba.XMax < bb.XMin - 1e-7 or bb.XMax < ba.XMin - 1e-7
            or ba.YMax < bb.YMin - 1e-7 or bb.YMax < ba.YMin - 1e-7
            or ba.ZMax < bb.ZMin - 1e-7 or bb.ZMax < ba.ZMin - 1e-7):
        return 0.0
    try:
        c = a.common(b)
        v = float(c.Volume)
    except Exception:
        return -1.0
    # Ein Schnitt, der so gross ist wie ein ganzer Operand, ist der
    # Fehlschlagfall und KEINE Durchdringung.
    if v >= 0.999 * min(float(a.Volume), float(b.Volume)):
        return -1.0
    return v

_paare = []
def _hol(n):
    o = GEBAUT.get(n)
    return o.Shape if o is not None else None

_zaehne = sorted([n for n in GEBAUT if n.startswith("Zahn_")])
_spulen = sorted([n for n in GEBAUT if n.startswith("Spule_")])
_mags = sorted([n for n in GEBAUT if n.startswith("Magnet_")])
_schb = sorted([n for n in GEBAUT if n.startswith("Laeuferscheibe_")])
for i, zn in enumerate(_zaehne[:6]):
    sp = zn.replace("Zahn_", "Spule_")
    if sp in GEBAUT:
        _paare.append((zn, sp))
    if i + 1 < len(_zaehne):
        _paare.append((zn, _zaehne[i + 1]))
for i, sp in enumerate(_spulen[:6]):
    if i + 1 < len(_spulen):
        _paare.append((sp, _spulen[i + 1]))
for zn in _zaehne[:4]:
    for mn in _mags[:4]:
        _paare.append((zn, mn))
for i, mn in enumerate(_mags[:6]):
    if i + 1 < len(_mags):
        _paare.append((mn, _mags[i + 1]))
for sb in _schb:
    _paare.append((sb, "Welle"))
    for mn in _mags[:2]:
        _paare.append((sb, mn))

_bef = []
for n1, n2 in _paare:
    s1, s2 = _hol(n1), _hol(n2)
    if s1 is None or s2 is None:
        continue
    v = _ueberlapp(s1, s2)
    if v > 1e-6:
        _bef.append({"a": n1, "b": n2, "v": round(v, 4)})
    elif v < 0:
        _bef.append({"a": n1, "b": n2, "unklar": True})
print("AX_UEBERLAPP:" + json.dumps({"geprueft": len(_paare), "befunde": _bef}))
print("CAD_SUCCESS")
'''


def baue_skript(geom: dict, axial_mm: float | None, save_path: str) -> str:
    """Das FreeCAD-Skript fuer die Scheibenmaschine.

    Gebaut wird aus ``teile()`` -- die Geometrie steht also an EINER Stelle und
    ist ohne FreeCAD pruefbar. Was hier dazukommt, sind nur die Booleschen und
    das Nachmessen am fertigen Koerper.
    """
    t = teile(geom, axial_mm)
    step = save_path.replace(".FCStd", ".step")
    z = [_KOPF, f"RAND = {RAND_UEBERSTAND_MM!r}\n",
         f"SAVE = {save_path!r}\nSTEP = {step!r}\n"]
    farben = {"magnet": "(0.85, 0.20, 0.20)", "eisen": "(0.55, 0.57, 0.60)",
              "kupfer": "(0.80, 0.50, 0.20)", "stahl": "(0.40, 0.42, 0.45)"}
    for p in t["teile"]:
        nm = p["name"]
        if p["form"] == "ring":
            bau = (f'_ring({p["r0"]!r}, {p["r1"]!r}, {p["z0"]!r}, {p["z1"]!r})')
        elif p["form"] == "zylinder":
            bau = (f'_ring(0.0, {p["r1"]!r}, {p["z0"]!r}, {p["z1"]!r})')
        elif p["form"] == "ringsektor":
            bau = (f'_sektor({p["r0"]!r}, {p["r1"]!r}, {p["z0"]!r}, '
                   f'{p["z1"]!r}, {p["th_mitte"]!r}, {p["th_halb"]!r})')
        elif p["form"] == "zahn":
            bau = ("_zahn({" + ", ".join(
                f'{k!r}: {p[k]!r}' for k in
                ("r0", "r1", "z0", "z1", "th_mitte", "th_halb", "keil",
                 "b_nut_ro", "ro")) + "})")
        elif p["form"] == "spule":
            d = dict(p)
            d["th_halb_zahn"] = p["th_halb"] / (1.0 - SPULEN_LUFT)
            bau = ("_spule({" + ", ".join(
                f'{k!r}: {d[k]!r}' for k in
                ("r0", "r1", "z0", "z1", "th_mitte", "th_halb", "keil",
                 "b_nut_ro", "ro", "iso", "fenster_r0", "fenster_r1",
                 "th_halb_zahn")) + "})")
        else:                                                   # pragma: no cover
            continue
        z.append(
            f'_o = doc.addObject("Part::Feature", {nm!r})\n'
            f'_o.Shape = {bau}\n'
            # `FreeCADCmd` hat kein ViewObject -- headless ist es None, und ein
            # Zugriff darauf laesst das GANZE Skript scheitern (gemessen:
            # "'NoneType' object has no attribute 'ShapeColor'", 131 Teile
            # gebaut und keines gespeichert). Die Farbe ist Zierat, der Bau ist
            # es nicht.
            f'_vo = getattr(_o, "ViewObject", None)\n'
            f'if _vo is not None:\n'
            f'    _vo.ShapeColor = {farben.get(p["art"], "(0.6,0.6,0.6)")}\n'
            f'GEBAUT[{nm!r}] = _o\n')
    z.append(_FUSS)
    return "".join(z)


def messung_aus_stdout(text: str) -> dict:
    """Die Nachmessung aus den Markern des FreeCAD-Laufs lesen.

    Gelesen wird mit ``raw_decode``, nicht mit ``json.loads``: hinter dem Objekt
    kann in derselben Zeile weiterer Text stehen (gemessen „Extra data: column
    8205"), weil FreeCAD seine eigenen Meldungen ohne Ruecksicht auf
    Zeilengrenzen schreibt -- derselbe Fallstrick wie bei ``ema_agent._zerlegen``
    und der ``\\r``-Fortschrittszeile von FluidX3D.
    """
    import json

    dec = json.JSONDecoder()
    aus: dict = {"teile": {}, "ueberlapp": None, "ueberlapp_text": None}
    for ln in (text or "").splitlines():
        for marke, schluessel in (("AX_TEILE:", "teile"),
                                  ("AX_UEBERLAPP:", "_u")):
            i = ln.find(marke)
            if i < 0:
                continue
            try:
                d, _ = dec.raw_decode(ln[i + len(marke):])
            except ValueError:
                continue
            if schluessel == "teile":
                aus["teile"] = d
            else:
                bf = d.get("befunde") or []
                aus["ueberlapp"] = len(bf)
                aus["ueberlapp_geprueft"] = d.get("geprueft")
                aus["ueberlapp_befunde"] = bf
                aus["ueberlapp_text"] = (
                    f"{d.get('geprueft')} bedeutsame Paare geprueft, KEINE "
                    f"Durchdringung — der Luftspalt steht, die Isolation haelt, "
                    f"die Fugen sind offen"
                    if not bf else
                    f"{len(bf)} von {d.get('geprueft')} Paaren durchdringen "
                    f"sich: " + ", ".join(
                        f"{x.get('a')}∩{x.get('b')}" for x in bf[:5]))
    t = aus.get("teile") or {}
    aus["n_teile"] = len(t)
    aus["ungueltig"] = [n for n, d in t.items()
                        if d.get("fehler") or not d.get("gueltig", True)
                        or d.get("v", 0) <= 0]
    return aus
