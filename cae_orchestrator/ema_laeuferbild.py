"""Der Laeufer als ZEICHENTEILE — fuer die Leinwand im Browser.

Warum es dieses Modul gibt
--------------------------

``ema.html`` zeichnet die Live-Vorschau selbst, in JavaScript, und holt sich die
Magnetlage aus einer **handgespiegelten** Fassung von ``ema_topology.magnet_legs``
(``magnetLegs`` in der Seite). ``CLAUDE.md`` nennt diese Stelle nicht umsonst die
gefaehrlichste im ganzen Werkzeug: laufen die beiden auseinander, rechnen Handy,
Schreibtisch und Loeser verschiedene Maschinen, und alle drei Bilder sehen
plausibel aus. ``test_topology.py`` haelt sie deshalb mit ``node`` zusammen.

Fuer Kaefig, Schenkelpol und Anker waere eine solche Abschrift **viermal** noetig
gewesen — und jede haette ihren eigenen Spiegeltest gebraucht. Statt dessen
liefert dieses Modul die Teile als **reine Zahlen**, und die Seite zeichnet nur
noch. Damit gibt es die Laeufergeometrie weiterhin genau einmal, naemlich dort,
wo sie gerechnet wird.

**Hier wird NICHTS gerechnet.** Jede Zahl kommt aus der Funktion, aus der auch
``ema_freecad`` und ``ema_pipeline.render_cross_section`` zeichnen:

    ASM Kaefig        ``ema_asm.kaefig``
    ASM Schleifring   ``ema_asm.laeuferwicklung``
    EESM              ``ema_eesm_cad.koerper``
    GSM               ``ema_gsm.ankerwicklung`` (Laeufer) + ``staenderpole``
    SynRM             ``ema_topology.magnet_legs`` — siehe unten

Der Reluktanzlaeufer ist der eine Fall ohne eigene Quelle
---------------------------------------------------------

``ema_synrm`` rechnet die Induktivitaeten aus einer **Ersatz**-Barrierenhoehe
(``magThick``) und kennt keine Barrierengeometrie. Gezeichnet wird deshalb die
Taschenlage aus ``magnet_legs`` — und das ist keine Verlegenheitsloesung,
sondern die Sache selbst: ein Reluktanzlaeufer ist derselbe gestanzte Laeufer wie
ein IPM, nur bleiben die Taschen **leer**. Dass die analytische Rechnung davon
nur die Hoehe kennt, steht als ``hinweis`` im Ergebnis, statt ein gezeichnetes
Mehrwissen vorzutaeuschen.

Das Teileformat
---------------

Alles in **Millimetern**, im Laeuferbezug (Ursprung = Wellenachse). ``grad``
dreht den oertlichen ``(r, y)``-Rahmen um den Ursprung — dieselbe Drehung, die
``render_cross_section`` von Hand ausmultipliziert::

    {"form": "ring",     "r_i", "r_a"}
    {"form": "rechteck", "r0", "r1", "y0", "y1", "grad"}
    {"form": "segment",  "r_a", "dicke", "grad", "halb"}   # Kreisbogenstueck
    {"form": "kreis",    "cx", "cy", "r"}

``rolle`` sagt, WAS das Teil ist, nicht wie es aussieht — die Farbe entscheidet
die Seite, den Stoff der Rasterer:

    ``eisen`` · ``pol`` (Eisen, aber die Polform IST die Aussage) · ``luft`` ·
    ``kupfer`` · ``alu``

Warum die Teile einzeln stehen und nicht als „n mal wiederholen": eine
Wiederholungsregel im JavaScript waere wieder Geometrie im Browser. Es sind
hoechstens einige hundert Teile, und die entstehen einmal je Geometrieaenderung.
"""

from __future__ import annotations

import math

# Wieviele Teile hoechstens herausgehen. Ein Laeufer mit 60 Nuten und Deckeln
# liegt bei rund 200; die Schranke faengt eine unsinnige Nutzahl ab, bevor die
# Seite daran haengt, statt sie zeichnen zu lassen.
MAX_TEILE = 4000


def _rechteck(r0: float, r1: float, y0: float, y1: float, grad: float,
              rolle: str) -> dict:
    return {"form": "rechteck", "r0": round(float(r0), 4),
            "r1": round(float(r1), 4), "y0": round(float(y0), 4),
            "y1": round(float(y1), 4), "grad": round(float(grad), 4),
            "rolle": rolle}


def _ring(r_i: float, r_a: float, rolle: str) -> dict:
    return {"form": "ring", "r_i": round(float(r_i), 4),
            "r_a": round(float(r_a), 4), "rolle": rolle}


def _segment(r_a: float, dicke: float, grad: float, halb: float,
             rolle: str) -> dict:
    return {"form": "segment", "r_a": round(float(r_a), 4),
            "dicke": round(float(dicke), 4), "grad": round(float(grad), 4),
            "halb": round(float(halb), 4), "rolle": rolle}


def _kreis(cx: float, cy: float, r: float, rolle: str) -> dict:
    return {"form": "kreis", "cx": round(float(cx), 4),
            "cy": round(float(cy), 4), "r": round(float(r), 4), "rolle": rolle}


def _nutkranz(n: int, r_innen: float, tiefe: float, breite: float,
              rolle: str) -> list:
    """``n`` gleiche Nuten ueber den Umfang — Kaefig, Laeuferwicklung, Anker.

    Alle drei Bauarten legen ihre Nut als Rechteck zwischen ``r_innen`` und
    ``r_innen + tiefe`` mit der Breite ``breite`` an; das ist dieselbe Form, die
    ``render_cross_section`` je Bauart einzeln ausschreibt.
    """
    n = max(int(n), 0)
    return [_rechteck(r_innen, r_innen + tiefe, -breite / 2.0, breite / 2.0,
                      360.0 * j / n, rolle)
            for j in range(min(n, MAX_TEILE))]


# ── je Bauart ────────────────────────────────────────────────────────────────

def _asm(geom: dict, axial: float) -> dict:
    import ema_asm

    art = ema_asm.laeufer_art(geom)
    r_rot = float(geom["rotorOD"]) / 2.0
    if art == "kaefig":
        k = ema_asm.kaefig(geom, axial)
        if k.get("bemessung") == "nicht auslegbar":
            return {"teile": [], "laeufer_art": art,
                    "fehler": ema_asm.nicht_erreichbar_text(k)
                    if hasattr(ema_asm, "nicht_erreichbar_text")
                    else "Kaefig nicht auslegbar"}
        n, b, t = int(k["n_stab"]), float(k["stabbreite_mm"]), float(k["nuttiefe_mm"])
        r_i = r_rot - ema_asm.KAEFIG_STEG_MM - t
        teile = _nutkranz(n, r_i, t, b, "alu")
        return {"teile": teile, "laeufer_art": art,
                "zaehlung": f"Kaefigstaebe ({n})",
                # Der Kaefig ist im magnetostatischen Raster nicht darstellbar --
                # kein sigma, kein dA/dt. Dieselbe Grenze, aus der `feld2d`
                # (Elmer, harmonisch) entstanden ist.
                "feld_darstellbar": False,
                "hinweis": (f"Kaefiglaeufer mit {n} Staeben. Die Feldlinien "
                            f"zeigen das STAENDERfeld — ein Kaefig laesst sich "
                            f"magnetostatisch nicht rechnen (kein sigma, kein "
                            f"dA/dt). Dafuer gibt es cae_cli.py feld2d.")}

    w = ema_asm.laeuferwicklung(geom, axial)
    n, b, t = int(w["n_nut"]), float(w["nut_breite_mm"]), float(w["nut_tiefe_mm"])
    r_i = float(w["r_nut_aussen_mm"]) - t
    return {"teile": _nutkranz(n, r_i, t, b, "kupfer"), "laeufer_art": art,
            "zaehlung": f"Laeuferwicklung ({n} Nuten)",
            "feld_darstellbar": False,
            "hinweis": (f"Schleifringlaeufer mit {n} Nuten. Auch hier zeigen "
                        f"die Feldlinien das Staenderfeld: der Laeuferstrom "
                        f"folgt aus dem Schlupf und steht magnetostatisch "
                        f"nicht zur Verfuegung.")}


def _eesm(geom: dict, axial: float) -> dict:
    import ema_eesm_cad

    k = ema_eesm_cad.koerper(geom, axial)
    r_rot = float(k["r_rotor_mm"])
    r_j, r_k = float(k["r_joch_aussen_mm"]), float(k["r_kern_aussen_mm"])
    b_k, d_s = float(k["b_kern_mm"]), float(k["d_spule_mm"])
    poles = int(k["poles"])
    # Zwischen den Polen ist LUFT. Der Vollring darueber waere genau der
    # Reluktanzunterschied zugemalt, der die Bauart ausmacht -- deshalb traegt
    # der Laeufer hier NUR das Joch als Eisen, und die Pole stehen darauf.
    teile = [_ring(float(k["r_welle_mm"]), r_j, "eisen")]
    halb = math.degrees((float(k["b_schuh_mm"]) / 2.0) / max(r_rot, 1e-9))
    # ZWISCHEN den Polen ist Luft, und die gehoert nicht nur ins Bild, sondern
    # auch ins Feldraster: die Reluktanz des Schenkelpollaeufers IST die
    # Bauart. Ohne diese Teile zeigte die Leinwand Pole und die Feldlinien
    # verhielten sich, als waere der Laeufer eine Vollscheibe -- ein Bild, das
    # sich selbst widerspricht.
    _schritt = 360.0 / max(poles, 1)
    for i in range(poles):
        _g0 = 360.0 * i / max(poles, 1) + halb
        _luecke = _schritt - 2.0 * halb
        if _luecke > 0.1:
            teile.append(_segment(r_rot, r_rot - r_j, _g0 + _luecke / 2.0,
                                  _luecke / 2.0, "luft"))
    for i in range(poles):
        g = 360.0 * i / max(poles, 1)
        teile.append(_segment(r_rot, r_rot - r_k, g, halb, "pol"))
        teile.append(_rechteck(r_j, r_k, -b_k / 2.0, b_k / 2.0, g, "pol"))
        teile.append(_rechteck(r_j, r_k, b_k / 2.0, b_k / 2.0 + d_s, g, "kupfer"))
        teile.append(_rechteck(r_j, r_k, -b_k / 2.0 - d_s, -b_k / 2.0, g, "kupfer"))
    hin = (f"Schenkelpollaeufer, {poles} Pole, Erregerspule aus dem "
           f"Kupferquerschnitt ({k['A_cu_mm2']:.0f} mm² je Pol) statt aus dem "
           f"verfuegbaren Platz.")
    if not k.get("passt", True):
        hin += " ⚠ " + str(k.get("grund", ""))
    return {"teile": teile, "poles": poles,
            "zaehlung": f"Erregerspulen ({poles} Pole)",
            # Gleichstrom in den Erregerspulen ist magnetostatisch sehr wohl
            # darstellbar -- das Raster kann es, sobald die Spulen als Strom
            # eingetragen werden. Solange das nicht geschieht, steht hier False
            # und die Seite sagt es, statt ein Staenderfeld als Maschinenfeld
            # auszugeben.
            "feld_darstellbar": False,
            "hinweis": hin + (" Die Feldlinien zeigen das Staenderfeld; die "
                              "Erregung ist in der Vorschau nicht eingepraegt.")}


def _gsm(geom: dict, axial: float) -> dict:
    import ema_gsm

    a = ema_gsm.ankerwicklung(geom, axial)
    r_rot = float(geom["rotorOD"]) / 2.0
    n, b, t = int(a["n_nut"]), float(a["nut_breite_mm"]), float(a["nut_tiefe_mm"])
    teile = _nutkranz(n, r_rot - t, t, b, "kupfer")

    # Die GSM ist die EESM von innen nach aussen: die Schenkelpole sitzen am
    # STAENDER, und der hat deshalb keine Nuten. ``staender`` ist die einzige
    # Bauart, die das braucht -- bei allen anderen bleibt die Liste leer und die
    # Seite zeichnet ihren gewohnten genuteten Staender.
    staender = []
    try:
        sp = ema_gsm.staenderpole(geom, axial)
        r_so = float(geom["statorOD"]) / 2.0
        r_si = float(geom["statorID"]) / 2.0
        r_ji = max(r_so - float(sp["h_joch_mm"]), r_si)
        poles = int(sp["poles"])
        staender.append(_ring(r_ji, r_so, "eisen"))
        halb = math.degrees((float(sp["b_pol_mm"]) / 2.0) / max(r_si, 1e-9))
        fb = float(sp["fenster_b_mm"])
        for i in range(poles):
            g = 360.0 * i / max(poles, 1)
            # Pol: vom Joch nach INNEN bis an die Bohrung.
            staender.append(_rechteck(r_si, r_ji,
                                      -float(sp["b_pol_mm"]) / 2.0,
                                      float(sp["b_pol_mm"]) / 2.0, g, "pol"))
            staender.append(_rechteck(r_si, r_ji,
                                      float(sp["b_pol_mm"]) / 2.0,
                                      float(sp["b_pol_mm"]) / 2.0 + fb / 2.0,
                                      g, "kupfer"))
            staender.append(_rechteck(r_si, r_ji,
                                      -float(sp["b_pol_mm"]) / 2.0 - fb / 2.0,
                                      -float(sp["b_pol_mm"]) / 2.0, g, "kupfer"))
        _ = halb
    except Exception:                                        # noqa: BLE001
        staender = []

    k = int(a["k_lamellen"])
    return {"teile": teile, "staender": staender,
            "zaehlung": f"Ankerwicklung ({n} Nuten)",
            "feld_darstellbar": False,
            "hinweis": (f"Gewickelter Anker, {n} Nuten, {k} Lamellen; die "
                        f"Schenkelpole sitzen am STAENDER. Der Kommutator haelt "
                        f"die Ankerdurchflutung im Raum fest — das Drehfeld der "
                        f"Vorschau bildet diese Maschine nicht ab.")}


def _synrm(geom: dict, axial: float) -> dict:
    from ema_topology import magnet_legs

    legs, _meta = magnet_legs(geom)
    gap = float(geom.get("magGapMm", 0.1) or 0.1)
    poles = 2 * max(1, int(geom.get("p", 3)))
    teile = []
    for i in range(poles):
        g = 360.0 * i / poles
        for lg in legs:
            if getattr(lg, "placement", "interior") != "interior":
                continue
            h = float(lg.thickness) + 2.0 * gap
            L = float(lg.length)
            # Dieselbe Langloch-Tasche wie beim IPM -- nur bleibt sie LEER.
            # Gezeichnet wird sie im Schenkelrahmen: Ursprung am inneren Ende,
            # um `tilt` gedreht, genau wie `drawRotor` es fuer den IPM tut.
            teile.append({"form": "tasche",
                          "r_pos": round(float(lg.r_pos), 4),
                          "offset": round(float(lg.offset), 4),
                          "tilt_grad": round(math.degrees(float(lg.tilt)), 4),
                          "laenge": round(L, 4), "hoehe": round(h, 4),
                          "grad": round(g, 4), "rolle": "luft"})
    return {"teile": teile, "poles": poles,
            "zaehlung": f"Flussbarrieren ({len(legs)} je Pol)",
            # Reluktanz ist reine Geometrie: sobald die Barrieren als Luft im
            # Raster stehen, ist das Feld darstellbar -- anders als beim Kaefig.
            "feld_darstellbar": True,
            "hinweis": ("Reluktanzlaeufer: dieselben gestanzten Taschen wie "
                        "beim IPM, nur bleiben sie leer. Die Lage folgt "
                        "magShape; die analytische Rechnung kennt davon nur die "
                        "Barrierenhoehe magThick (ema_synrm.induktivitaeten).")}


_BAUER = {"asm": _asm, "eesm": _eesm, "gsm": _gsm, "synrm": _synrm}


def teile(geom: dict, axial_mm: float | None = None) -> dict:
    """Zeichenteile des Laeufers (und ggf. des Staenders) fuer ``geom``.

    Fuer die PSM kommt **nichts** heraus: ihre Magnete zeichnet die Seite
    weiterhin aus ihrer eigenen, mit ``test_topology.py`` festgenagelten
    ``magnetLegs``-Fassung. Diesen Weg anzufassen hiesse, an der einzigen
    Darstellung zu drehen, die seit jeher stimmt.

    Scheitert eine Bauart, steht der Grund in ``fehler`` und ``teile`` ist leer —
    die Leinwand zeichnet dann den nackten Laeufer weiter. Ein Zeichner darf nie
    der Grund sein, warum die Oberflaeche stehenbleibt.
    """
    import ema_maschinenart as MA

    code = MA.art_code(geom or {})
    art = MA.hole(code)
    axial = float(axial_mm or geom.get("axialLen") or 80.0)
    aus = {"art": code, "label": art.label, "teile": [], "staender": [],
           "hinweis": "", "feld_darstellbar": True, "fehler": ""}
    bauer = _BAUER.get(code)
    if bauer is not None:
        try:
            aus.update(bauer(geom, axial))
        except Exception as e:                               # noqa: BLE001
            # Ein Zeichner darf nie der Grund sein, warum die Oberflaeche
            # stehenbleibt: der Grund wird GENANNT, die Liste bleibt leer, und
            # die Leinwand zeichnet den nackten Laeufer weiter.
            aus["fehler"] = f"{type(e).__name__}: {e}"
            aus["teile"] = []
    aus.setdefault("staender", [])
    aus["n_teile"] = len(aus.get("teile") or []) + len(aus["staender"])
    return aus
