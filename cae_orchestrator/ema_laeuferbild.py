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


def _trapez(r0: float, r1: float, y0i: float, y1i: float,
            y0a: float, y1a: float, grad: float, rolle: str) -> dict:
    """Vier Ecken statt zwei Breiten -- fuer den kegeligen Pol.

    Sind Innen- und Aussenkante gleich breit, ist es ein Rechteck; die Seite
    zeichnet dann dasselbe wie zuvor. Ein eigenes `form` statt eines
    aufgebohrten `rechteck`, damit der Zeichner nicht raten muss.
    """
    return {"form": "trapez", "r0": round(float(r0), 4), "r1": round(float(r1), 4),
            "y0i": round(float(y0i), 4), "y1i": round(float(y1i), 4),
            "y0a": round(float(y0a), 4), "y1a": round(float(y1a), 4),
            "grad": round(float(grad), 4), "rolle": rolle}


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


def _im_kreis(teil: dict, r_max: float) -> dict:
    """Ein Rechteck/Trapez so kuerzen, dass seine ECKEN im Kreis bleiben.

    Der letzte Riegel, und er sitzt mit Absicht hier — an der EINEN Stelle, die
    alle Bauarten durchlaufen. Kern, Spule, Nut und Polblock sind Rechtecke,
    Laeufer und Staender sind Kreise: ein Rechteck der halben Breite ``y``,
    dessen Oberkante bei ``r`` liegt, hat seine Ecken bei ``sqrt(r^2 + y^2)``
    und ragt damit ueber seine eigene Oberkante hinaus. Jede Bauart hat diesen
    Fehler einzeln gemacht, und bei der EESM war er im Bild zu sehen: die
    Erregerspule stand im Staender.

    Gekuerzt wird zuerst RADIAL (die Breite bleibt), weil die Breite aus dem
    Magnetkreis kommt und der Radius aus dem Platz. Reicht das nicht — beim
    zweipoligen Laeufer belegt EIN Pol den halben Umfang —, wird zusaetzlich
    die Breite gestaucht. Ein gekuerztes Teil ist ein schlechteres Bild, ein
    Teil ausserhalb der Maschine ein falsches.
    """
    f = teil.get("form")
    if f not in ("rechteck", "trapez") or r_max <= 0:
        return teil
    if f == "rechteck":
        namen_i = namen_a = ("y0", "y1")
    else:
        namen_i, namen_a = ("y0i", "y1i"), ("y0a", "y1a")
    y_i = max(abs(teil[n]) for n in namen_i)
    y_a = max(abs(teil[n]) for n in namen_a)
    r0, r1 = float(teil["r0"]), float(teil["r1"])
    if math.hypot(r1, y_a) <= r_max + 1e-9 and math.hypot(r0, y_i) <= r_max + 1e-9:
        return teil

    r1 = min(r1, math.sqrt(max(r_max ** 2 - y_a ** 2, 0.0)))
    if r1 < r0 + 0.1:
        r1 = r0 + 0.1
    s = 1.0
    if y_a > 1e-9:
        s = min(s, math.sqrt(max(r_max ** 2 - r1 ** 2, 0.0)) / y_a)
    if y_i > 1e-9:
        s = min(s, math.sqrt(max(r_max ** 2 - r0 ** 2, 0.0)) / y_i)
    s = min(max(s, 0.0), 1.0)
    teil["r1"] = round(r1, 4)
    if s < 1.0 - 1e-9:
        for n in set(namen_i) | set(namen_a):
            teil[n] = round(teil[n] * s, 4)
    return teil


# ── je Bauart ────────────────────────────────────────────────────────────────

def _asm(geom: dict, axial: float) -> dict:
    import ema_asm

    art = ema_asm.laeufer_art(geom)
    r_rot = float(geom["rotorOD"]) / 2.0
    if art == "kaefig":
        k = ema_asm.kaefig(geom, axial)
        # Ein nicht BEMESSBARER Kaefig wird trotzdem gezeichnet.
        #
        # Frueher kam hier eine leere Liste heraus, und die Leinwand fiel
        # daraufhin auf `magnetLegs` zurueck: eine Asynchronmaschine zeigte die
        # Magnete einer PSM. Von allen moeglichen Bildern ist das das einzige,
        # das eine andere Maschine zeigt -- schlimmer als jede Ungenauigkeit.
        # `ema_asm.kaefig` gibt die Geometrie ausdruecklich auch dann heraus
        # ("der Zeichner und das Netz brauchen etwas"); sie ist dann der
        # Fertigungsboden und keine Auslegung, und genau das steht im Hinweis.
        # Das harte Nein bleibt, wo es hingehoert: beim Vernetzen
        # (`ema_em2d_harm`) und beim CAD (`ema_freecad`).
        n, b, t = int(k["n_stab"]), float(k["stabbreite_mm"]), float(k["nuttiefe_mm"])
        r_i = r_rot - ema_asm.KAEFIG_STEG_MM - t
        teile = _nutkranz(n, r_i, t, b, "alu")
        _warn = ""
        if k.get("bemessung") == "nicht auslegbar":
            _warn = (" \u26a0 NICHT auslegbar: " + (
                ema_asm.nicht_erreichbar_text(k)
                if hasattr(ema_asm, "nicht_erreichbar_text")
                else str(k.get("grund") or "")) +
                " Gezeichnet ist der Fertigungsboden (2 mm Nuttiefe), keine "
                "Auslegung.")
        return {"teile": teile, "laeufer_art": art,
                "zaehlung": f"Kaefigstaebe ({n})",
                "warnung": _warn,
                # Der Kaefig ist im magnetostatischen Raster nicht darstellbar --
                # kein sigma, kein dA/dt. Dieselbe Grenze, aus der `feld2d`
                # (Elmer, harmonisch) entstanden ist.
                "feld_darstellbar": False,
                "hinweis": (f"Kaefiglaeufer mit {n} Staeben. Die Feldlinien "
                            f"zeigen das STAENDERfeld — ein Kaefig laesst sich "
                            f"magnetostatisch nicht rechnen (kein sigma, kein "
                            f"dA/dt). Dafuer gibt es cae_cli.py feld2d." + _warn)}

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
    # Zwei Breiten: beim Rechteck gleich (dann ist das Trapez ein Rechteck und
    # die Zeichnung Ziffer fuer Ziffer die alte), beim Kegel zur Jochseite hin
    # breiter -- und die Spule folgt der Neigung.
    b_i = float(k.get("b_kern_innen_mm", b_k))
    b_a = float(k.get("b_kern_aussen_mm", b_k))
    # Die Spule endet WEITER INNEN als der Kern. Sie sitzt neben ihm, ist also
    # ein Rechteck im Kreis: mit der Kernoberkante als Oberkante laege ihre
    # ECKE bei sqrt(r^2 + y^2) und damit ausserhalb des Laeufers -- gemessen
    # 88,63 mm gegen eine Statorbohrung bei 85,8 mm. `ema_eesm_cad` rechnet
    # den zulaessigen Radius jetzt aus (`r_spule_aussen_mm`), hier wird er nur
    # gelesen.
    r_sp = float(k.get("r_spule_aussen_mm", r_k))
    b_e = float(k.get("b_kern_spulenende_mm", k.get("b_kern_aussen_mm", b_k)))
    # Die Erregung ist GLEICHSTROM und damit magnetostatisch darstellbar --
    # anders als der Kaefig. Je Pol traegt die eine Spulenseite +F, die andere
    # -F Amperewindungen (das ist die Windung um den Kern), und die Polfolge
    # wechselt das Vorzeichen.
    f_pol = float(k.get("F_pol_A") or 0.0)
    for i in range(poles):
        g = 360.0 * i / max(poles, 1)
        s = 1.0 if i % 2 == 0 else -1.0
        teile.append(_segment(r_rot, r_rot - r_k, g, halb, "pol"))
        teile.append(_trapez(r_j, r_k, -b_i / 2.0, b_i / 2.0,
                             -b_a / 2.0, b_a / 2.0, g, "pol"))
        _p = _trapez(r_j, r_sp, b_i / 2.0, b_i / 2.0 + d_s,
                     b_e / 2.0, b_e / 2.0 + d_s, g, "kupfer")
        _p["durchflutung_A"] = round(s * f_pol, 2)
        teile.append(_p)
        _m = _trapez(r_j, r_sp, -b_i / 2.0 - d_s, -b_i / 2.0,
                     -b_e / 2.0 - d_s, -b_e / 2.0, g, "kupfer")
        _m["durchflutung_A"] = round(-s * f_pol, 2)
        teile.append(_m)
    hin = (f"Schenkelpollaeufer, {poles} Pole, Erregerspule aus dem "
           f"Kupferquerschnitt ({k['A_cu_mm2']:.0f} mm² je Pol) statt aus dem "
           f"verfuegbaren Platz. Die Erregung ist mit {f_pol:.0f} A je Pol "
           f"eingepraegt — Gleichstrom ist magnetostatisch darstellbar.")
    if not k.get("passt", True):
        hin += " ⚠ " + str(k.get("grund", ""))
    return {"teile": teile, "poles": poles,
            "zaehlung": f"Erregerspulen ({poles} Pole)",
            # Gleichstrom in den Erregerspulen ist magnetostatisch der
            # EIGENTLICHE Fall des Loesers, nicht seine Grenze: die Spulen
            # tragen `durchflutung_A`, und `LAEUFER.rastere` traegt sie als
            # Quelle ein. Was hier fehlt, ist nichts.
            "feld_darstellbar": True,
            "hinweis": hin}


def _gsm(geom: dict, axial: float) -> dict:
    import ema_gsm

    a = ema_gsm.ankerwicklung(geom, axial)
    r_rot = float(geom["rotorOD"]) / 2.0
    n, b, t = int(a["n_nut"]), float(a["nut_breite_mm"]), float(a["nut_tiefe_mm"])
    # Die Nut ist ein RECHTECK im Kreis: mit der Oberkante auf r_rot laegen
    # ihre Ecken bei sqrt(r_rot^2 + (b/2)^2) und damit ausserhalb des Laeufers
    # (gemessen 85,07 gegen 85,00 mm). Gelegt wird sie deshalb an die SEHNE.
    r_nut = math.sqrt(max(r_rot ** 2 - (b / 2.0) ** 2, 1.0))
    teile = _nutkranz(n, r_nut - t, t, b, "kupfer")

    # Die GSM ist die EESM von innen nach aussen: die Schenkelpole sitzen am
    # STAENDER, und der hat deshalb keine Nuten. ``staender`` ist die einzige
    # Bauart, die das braucht -- bei allen anderen bleibt die Liste leer und die
    # Seite zeichnet ihren gewohnten genuteten Staender.
    staender = []
    f_pol = 0.0
    try:
        import ema_eesm
        sp = ema_gsm.staenderpole(geom, axial)
        f_pol = float(ema_eesm.erregung(geom, axial)["F_pol_A"])
        r_so = float(geom["statorOD"]) / 2.0
        r_si = float(geom["statorID"]) / 2.0
        r_ji = max(r_so - float(sp["h_joch_mm"]), r_si)
        poles = int(sp["poles"])
        b_pol = float(sp["b_pol_mm"])
        fb = float(sp["fenster_b_mm"])
        staender.append(_ring(r_ji, r_so, "eisen"))

        # ZWISCHEN den Polen ist Luft, und sie muss ins Raster.
        #
        # Der Grundraster von ``ema.html`` legt ueber das ganze Band
        # [statorID/2, statorOD/2] Eisen -- richtig fuer einen genuteten
        # Drehstromstaender, falsch fuer Schenkelpole: dort steht zwischen zwei
        # Polen der Wickelraum, magnetisch Luft. Ohne diese Teile fuehrte das
        # Feld so, als waere der Staender ein Vollring, und die gezeichneten
        # Pole waeren bloss Farbe. Gemessen wird der Winkel an der BOHRUNG, wo
        # der rechteckige Polblock am breitesten wirkt.
        w_blk = b_pol / 2.0 + fb / 2.0
        halb_blk = math.degrees(math.atan2(w_blk, max(r_si, 1e-9)))
        schritt = 360.0 / max(poles, 1)
        luecke = schritt - 2.0 * halb_blk
        for i in range(poles):
            if luecke > 0.1:
                staender.append(_segment(
                    r_ji, r_ji - r_si,
                    schritt * i + halb_blk + luecke / 2.0,
                    luecke / 2.0, "luft"))

        for i in range(poles):
            g = schritt * i
            # Gleichstrom, Polfolge wechselnd -- dieselbe Regel wie beim
            # Schenkelpollaeufer der EESM, nur sitzt der Pol hier am STAENDER.
            s = 1.0 if i % 2 == 0 else -1.0
            # Pol: vom Joch nach INNEN bis an die Bohrung.
            staender.append(_rechteck(r_si, r_ji, -b_pol / 2.0, b_pol / 2.0,
                                      g, "pol"))
            _p = _rechteck(r_si, r_ji, b_pol / 2.0, b_pol / 2.0 + fb / 2.0,
                           g, "kupfer")
            _p["durchflutung_A"] = round(s * f_pol, 2)
            staender.append(_p)
            _m = _rechteck(r_si, r_ji, -b_pol / 2.0 - fb / 2.0, -b_pol / 2.0,
                           g, "kupfer")
            _m["durchflutung_A"] = round(-s * f_pol, 2)
            staender.append(_m)
    except Exception:                                        # noqa: BLE001
        staender = []

    k = int(a["k_lamellen"])
    return {"teile": teile, "staender": staender,
            "zaehlung": f"Ankerwicklung ({n} Nuten)",
            # Der Staender dieser Maschine ist KEINE Drehstromwicklung. Das
            # dreiphasige Nutfeld der Vorschau gehoert hier nicht hin -- es
            # zeigte ein Drehfeld auf einer Gleichstrommaschine, und genau so
            # wurde es gemeldet ("die Magnetfelder in der fremderregten
            # Gleichstrommaschine sind auch falsch"). Statt dessen sind die
            # Erregerspulen mit Gleichstrom eingepraegt; das kann der
            # magnetostatische Loeser.
            "staenderfeld": False,
            "feld_darstellbar": True,
            "hinweis": (f"Gewickelter Anker, {n} Nuten, {k} Lamellen; die "
                        f"Schenkelpole sitzen am STAENDER und sind mit "
                        f"{f_pol:.0f} A je Pol eingepraegt. Die Feldlinien "
                        f"zeigen das ERREGERfeld — die Ankerdurchflutung haelt "
                        f"der Kommutator im Raum fest und ist hier nicht "
                        f"eingepraegt (keine Ankerrueckwirkung im Bild).")}


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
    _lagen = len({getattr(lg, "layer", 0) for lg in legs}) or 1
    hin = (f"Reluktanzlaeufer: {len(legs)} Flussbarrieren je Pol in "
           f"{_lagen} Lage{'n' if _lagen != 1 else ''} — dieselben gestanzten "
           f"Taschen wie beim IPM, nur bleiben sie LEER. Ihre Lage kommt aus "
           f"der Magnet-Anordnung (magShape), die fuer diese Bauart deshalb "
           f"bedienbar bleibt.")
    if _lagen < 2:
        # Ein einlagiger Reluktanzlaeufer ist gebaut worden, taugt aber wenig:
        # das Salienzverhaeltnis lebt von der Zahl der Barrieren. Wer eine
        # einzelne V-Tasche sieht und „da fehlen die Magnete" denkt, hat recht
        # mit dem Eindruck und unrecht mit der Ursache -- also steht hier, wo
        # der Griff dafuer sitzt.
        hin += (" Mit EINER Lage ist die Reluktanzwirkung schwach; ein "
                "mehrlagiger Laeufer entsteht ueber die Anordnung "
                "'pmasynrm' (Lagen aus magLayers) oder 'vv'.")
    hin += (" Die analytische Rechnung kennt von alledem nur die "
            "Barrierenhoehe magThick (ema_synrm.induktivitaeten).")
    return {"teile": teile, "poles": poles,
            "zaehlung": f"Flussbarrieren ({len(legs)} je Pol)",
            # Reluktanz ist reine Geometrie: sobald die Barrieren als Luft im
            # Raster stehen, ist das Feld darstellbar -- anders als beim Kaefig.
            "feld_darstellbar": True,
            "hinweis": hin}


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
           "hinweis": "", "feld_darstellbar": True, "fehler": "",
           # Zwei Angaben, ohne die die Leinwand raten muesste -- und beide
           # kommen aus der EINEN Quelle, die es dafuer gibt:
           #
           # `hat_magnete`  entscheidet, ob `magnetLegs` ueberhaupt gezeichnet
           #     wird. Vorher haing das daran, ob TEILE ankamen: blieb die
           #     Liste leer (nicht auslegbarer Kaefig, Netzfehler, Bauart noch
           #     im Abruf), fiel die Seite auf die PSM-Magnete zurueck und
           #     zeigte eine andere Maschine. Das ist der gemeldete Fehler
           #     „in der Asynchronmaschine werden keine Staebe sondern Magnete
           #     angezeigt" -- eine leere Liste heisst „nichts zu zeichnen",
           #     niemals „zeichne Magnete".
           # `staenderfeld` sagt, ob der dreiphasige Nutstrom der Vorschau fuer
           #     diese Bauart ueberhaupt etwas bedeutet. Bei der GSM nicht.
           "hat_magnete": bool(art.hat_magnete),
           "staenderfeld": True}
    # Ohne Maschine kein Bild. Das ist keine Spitzfindigkeit: seit der Kaefig
    # auch am Fertigungsboden gezeichnet wird, kommt aus jeder Bauart etwas
    # heraus -- auch aus einer Geometrie, die es nicht gibt. Ein Laeufer mit
    # rotorOD = 0 ergaebe Nuten bei negativem Radius, und die saehen im Bild
    # aus wie eine Maschine.
    _r_l = float(geom.get("rotorOD") or 0.0) / 2.0
    _r_s = float(geom.get("statorOD") or 0.0) / 2.0
    if _r_l <= 0.0 or _r_s <= _r_l:
        aus["fehler"] = (f"Geometrie unbrauchbar: rotorOD = "
                         f"{2 * _r_l:.1f} mm, statorOD = {2 * _r_s:.1f} mm")
        aus["n_teile"] = 0
        return aus

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
    # Nichts verlaesst die Maschine. Eine Bauart, die es doch versucht, wird
    # hier gekuerzt statt im Bild zu kollidieren (s. `_im_kreis`).
    aus["teile"] = [_im_kreis(t, _r_l) for t in (aus.get("teile") or [])]
    aus["staender"] = [_im_kreis(t, _r_s) for t in aus["staender"]]
    aus["n_teile"] = len(aus["teile"]) + len(aus["staender"])
    return aus
