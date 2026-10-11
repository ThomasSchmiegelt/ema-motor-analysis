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


def _polygon(punkte, grad: float, rolle: str) -> dict:
    """Ein freier Polygonzug -- fuer alles, was keine der Grundformen ist.

    Gebraucht wird er von der Reluktanzmaschine: eine Flussbarriere folgt einer
    FELDLINIE (`r^p cos(p phi) = const`, s. `ema_synrm_cad`), und die ist weder
    Rechteck noch Kreissegment noch Langloch. Die Punkte liegen im gedrehten
    Rahmen wie bei `rechteck`/`trapez`: x laeuft entlang der um `grad` gedrehten
    Achse, y quer dazu.
    """
    return {"form": "polygon", "grad": round(float(grad), 4),
            "punkte": [(round(float(x), 4), round(float(y), 4))
                       for x, y in punkte],
            "rolle": rolle}


def _im_polygon(x: float, y: float, pts) -> bool:
    """Strahlverfahren. **Zeichengetreu dieselbe Schleife wie in
    ``ema_laeufer.js``** -- beide Fassungen muessen dieselben Zellen treffen,
    und bei einem Punkt auf der Kante entscheidet die Reihenfolge der
    Vergleiche. Deshalb steht sie hier so und dort so."""
    drin = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            drin = not drin
        j = i
    return drin


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


def _masse(geom: dict, eintraege) -> list:
    """Die ABGELEITETEN Masse einer Bauart, als Vorgabe fuer die Maske.

    Die Millimeterfelder tragen ``0 = ableiten``. Eine 0 sagt dem Menschen vor
    der Maske aber nicht, WAS abgeleitet wurde -- er sieht eine Null und muss
    raten, was die Maschine wirklich hat. Gemeldet als „auch waeren vorgaben
    hilfreich". Gerechnet wird dafuer **nichts** Neues: hier steht, was
    ``ema_asm``/``ema_eesm_cad`` ohnehin geliefert haben, damit die Maske es
    anzeigen und auf Zuruf uebernehmen kann. Eine zweite Ableitung im
    JavaScript waere die naechste stille Drift.
    """
    aus = []
    for schluessel, label, wert, einheit in eintraege:
        try:
            w = float(wert)
        except (TypeError, ValueError):
            continue
        aus.append({"schluessel": schluessel, "label": label,
                    "wert": round(w, 2), "einheit": einheit,
                    "gesetzt": float((geom or {}).get(schluessel) or 0.0) > 0.0})
    return aus


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
        # Der Steg kommt aus `kaefig()`, nicht aus der Konstanten: seit es
        # `laeuferStegMm` gibt, sind das zwei verschiedene Zahlen, und die
        # Konstante waere genau die Stelle, an der die Vorgabe nicht ankommt.
        r_i = r_rot - float(k.get("steg_mm", ema_asm.KAEFIG_STEG_MM)) - t
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
                "masse": _masse(geom, [
                    ("laeuferNutTiefeMm", "Laeufernuttiefe", t, "mm"),
                    ("laeuferNutBreiteMm", "Laeufernutbreite", b, "mm"),
                    ("laeuferStegMm", "Laeufersteg",
                     k.get("steg_mm", ema_asm.KAEFIG_STEG_MM), "mm")]),
                "masse_befund": list(k.get("masse_befund") or []),
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
            # Die Wicklungsnut bemisst `ema_wicklung.nutgeometrie` aus dem
            # Strom; die mm-Vorgaben des Kaefigs greifen hier NICHT, und das
            # steht hier, statt sie wirkungslos anzubieten.
            "masse": _masse(geom, [
                ("", "Laeufernuttiefe", t, "mm"),
                ("", "Laeufernutbreite", b, "mm")]),
            "feld_darstellbar": False,
            "hinweis": (f"Schleifringlaeufer mit {n} Nuten. Auch hier zeigen "
                        f"die Feldlinien das Staenderfeld: der Laeuferstrom "
                        f"folgt aus dem Schlupf und steht magnetostatisch "
                        f"nicht zur Verfuegung.")}


#: Stuetzpunkte auf dem Bogen, mit dem die Zwischenpolluft oben abschliesst.
#: 20 Stuecke ueber gemessen ~19 Grad ergeben einen Sehnenfehler unter
#: 0,01 mm -- weit unter jeder hier verwendeten Zellgroesse.
_BOGEN_N = 20


def _eesm(geom: dict, axial: float) -> dict:
    import ema_eesm_cad

    k = ema_eesm_cad.koerper(geom, axial)
    r_rot = float(k["r_rotor_mm"])
    r_j, r_k = float(k["r_joch_aussen_mm"]), float(k["r_kern_aussen_mm"])
    b_k, d_s = float(k["b_kern_mm"]), float(k["d_spule_mm"])
    poles = int(k["poles"])
    # Zwischen den Polen ist LUFT. Der Vollring darueber waere genau der
    # Reluktanzunterschied zugemalt, der die Bauart ausmacht.
    #
    # Einen JOCHRING gibt es nur noch fuer gespeicherte Masssaetze aus der Zeit
    # davor: der Polkoerper laeuft bis auf die Wellenbohrung durch, und die
    # Nabe entsteht dort, wo sich zwei Koerper ueberdecken (`r_nabe_mm`) --
    # gezeichnet wird sie von den Koerpern selbst.
    teile = []
    if r_j > float(k["r_welle_mm"]) + 0.05:
        teile.append(_ring(float(k["r_welle_mm"]), r_j, "eisen"))
    halb = math.degrees((float(k["b_schuh_mm"]) / 2.0) / max(r_rot, 1e-9))
    # ZWISCHEN den Polen ist Luft, und die gehoert nicht nur ins Bild, sondern
    # auch ins Feldraster: die Reluktanz des Schenkelpollaeufers IST die
    # Bauart. Ohne diese Teile zeigte die Leinwand Pole und die Feldlinien
    # verhielten sich, als waere der Laeufer eine Vollscheibe -- ein Bild, das
    # sich selbst widerspricht.
    #
    # **Der Zwischenpolraum folgt der FLANKE des Polkoerpers, nicht einem
    # festen Winkel.** Bis zum 20.09.2026 war er EIN Kreissektor ueber die
    # volle Laeuferhoehe, dessen Winkel aus der Polschuhbreite am Rand kam.
    # Am Rand stimmte das (Schuh 20,40 Grad + Luft 9,60 Grad = halbe
    # Polteilung), darunter nicht: der Polkern ist ein Koerper fester BREITE,
    # sein Halbwinkel schrumpft mit dem Radius, und dazwischen blieb
    # Laeufereisen stehen -- gemessen 3,20 mm je Flanke bei r = 60 mm, 6,83
    # bei r = 70 und 10,44 bei r = 80, zwoelfmal, also 25 % des Umfangs als
    # Bruecke direkt unter den Polschuhen. Umgekehrt schnitt derselbe Sektor
    # unterhalb von r_nabe in die NABE, die die Polkoerper miteinander bilden.
    # Beides zugleich, und beides sichtbar, sobald jemand eine Kernbreite
    # eingibt und das Bild sich nicht ruehrt.
    #
    # Zwei Baender statt eines:
    #   * unter dem Schuh liegt die Luft zwischen zwei GERADEN Flanken, ist
    #     also ein Trapez (die Flanke des Nachbarpols bleibt nach dem Drehen
    #     in den Zwischenpolrahmen eine Gerade);
    #   * im Schuhband gibt der Schuh die Breite vor, dort bleibt es ein
    #     Kreissektor.
    _schritt = 360.0 / max(poles, 1)
    _h = math.pi / max(poles, 1)                     # halbe Polteilung [rad]
    _r_kern_a = float(k.get("r_kern_aussen_mm", r_k))
    _wi = float(k.get("b_kern_innen_mm", b_k)) / 2.0
    _wa = float(k.get("b_kern_aussen_mm", b_k)) / 2.0
    _t0 = float(k.get("r_welle_mm", 0.0))
    _t1 = _r_kern_a

    def _flanke(t):
        """Ein Punkt der Nachbarflanke im Zwischenpolrahmen: (u, v)."""
        w = _wi + (_wa - _wi) * ((t - _t0) / max(_t1 - _t0, 1e-9))
        return (t * math.cos(_h) + w * math.sin(_h),
                t * math.sin(_h) - w * math.cos(_h))

    # Die Flanke ist eine Gerade -- zwei Punkte legen sie fest, und daraus
    # folgt die halbe Luftbreite bei jedem Radius.
    (_ua, _va), (_ub, _vb) = _flanke(_t0), _flanke(_t1)
    _stg = (_vb - _va) / (_ub - _ua) if abs(_ub - _ua) > 1e-9 else 0.0

    def _halbbreite(u):
        return _va + _stg * (u - _ua)

    # Wo die Flanken sich treffen (v = 0), beginnt die Nabe; darunter gibt es
    # keinen Zwischenpolraum, weil die Polkoerper einander ueberdecken.
    _u_nabe = float(k.get("r_nabe_mm", 0.0)) or (
        (_ua - _va / _stg) if abs(_stg) > 1e-12 else _t0)
    # Der Zwischenpolraum beginnt am JOCH -- nicht an der Nabe und nicht an der
    # Welle. Seit das Joch wieder ein flussbemessener Ring ist (20.09.2026),
    # ist es die aeussere der drei Schranken; die beiden anderen bleiben
    # stehen, damit gespeicherte Masssaetze ohne Joch weiter richtig zeichnen.
    _u0 = max(_u_nabe, r_j, float(k.get("r_welle_mm", 0.0)))
    # **Der Zwischenpolraum endet am BOGEN, nicht an einer Sehne** (20.09.2026).
    #
    # Er war ein Trapez, und ein Trapez ist oben von einer SEHNE begrenzt. Damit
    # die Sehne nicht in den Polschuh schneidet, endete sie dort, wo ihre ECKEN
    # den Schuhboden `r_kern_aussen` gerade beruehren. Die Ecken lagen dann
    # richtig -- die MITTE der Sehne aber um ihre Pfeilhoehe tiefer, und genau
    # diese Pfeilhoehe blieb als Laeufereisen stehen.
    #
    # Gemeldet als „in Canvas gibt es einen Metallbereich von Polschuh zu
    # Polschuh, das ist falsch, das geht auch so in die Feldanalyse ein".
    # Nachgemessen an der Vorgabemaschine (2p = 6, Rotor 94,3 mm), Strahl
    # genau zwischen zwei Polen:
    #
    #   r 35,97 … 80,92 mm  Luft   (das Trapez)
    #   r 81,08 … 84,85 mm  EISEN  <- 3,93 mm geschlossener Ring
    #   r 85,01 … 94,28 mm  Luft   (das Schuhband)
    #
    # Das ist kein Schoenheitsfehler: der Ring laeuft um den ganzen Umfang und
    # schliesst SAEMTLICHE Pole magnetisch kurz -- er steht genau dort, wo der
    # Reluktanzunterschied der Bauart entstehen soll, und er steht im Raster
    # wie im Bild.
    #
    # Also ein Polygon mit Bogenoberkante statt eines Trapezes: die beiden
    # Flanken sind Geraden, der Abschluss oben ist der Kreis `r_kern_aussen`
    # selbst. Dann treffen sich Zwischenpolluft und Schuhband exakt, ohne
    # Ueberlappung und ohne Luecke -- und weil nichts ueberlappt, ist die
    # Reihenfolge der Teile hier auch egal.
    _A = _va - _stg * _ua
    _q = 1.0 + _stg * _stg

    def _flanke_auf_kreis(r):
        """Wo schneidet die Flankengerade den Kreis ``r``? ``(u, v)`` oder None.

        Beide Abschluesse des Zwischenpolraums sind KREISE -- oben der
        Schuhboden, unten der Jochaussenrand --, die Flanken dagegen Geraden.
        Damit Bogen und Flanke stetig aneinanderpassen, muss der
        Flankenendpunkt auf dem Kreis liegen. Ihn zu raten war zweimal
        derselbe Fehler: oben blieb ein Eisenring stehen, unten eine Luecke.
        """
        disk = _stg * _stg * _A * _A - _q * (_A * _A - r * r)
        if disk <= 0.0:
            return None
        u = (-_stg * _A + math.sqrt(disk)) / _q
        return (u, _A + _stg * u)

    _s1 = _flanke_auf_kreis(_r_kern_a)
    _u1 = min(_s1[0], _r_kern_a) if _s1 else _u0
    # Der untere Abschluss ist der JOCHKREIS, nicht die Gerade u = r_joch. Der
    # Flankenendpunkt bei u = r_joch liegt gemessen bei r = 47,19 mm, also
    # 0,43 mm UEBER dem Joch (46,76) -- und weil die Flanke nach aussen laeuft,
    # klafft die Luecke zur Seite hin bis auf 3,1 mm auf. Genau dort stand der
    # Laeufergrund der Leinwand, gemeldet als „das neue dunkle Grau sollte
    # eigentlich schwarz sein".
    _r_unten = float(_u0)

    def _bogenpunkte(r, phi, n=None):
        """Stuetzpunkte auf dem Kreis ``r`` von ``-phi`` bis ``+phi``."""
        n = n or _BOGEN_N
        return [(r * math.cos(-phi + 2.0 * phi * i / n),
                 r * math.sin(-phi + 2.0 * phi * i / n)) for i in range(n + 1)]

    def _zwischenpol_polygon(u0, u1, v0, v1, grad):
        """Zwei gerade Flanken, oben UND unten je ein Bogen.

        Die Flanken sind Geraden (die Nachbarpolkoerper haben feste Breite),
        die beiden Abschluesse dagegen Kreise -- oben der Schuhboden
        ``r_kern_aussen``, unten der Jochaussenkreis ``u0``. Die vier
        Flankenendpunkte liegen per Konstruktion auf dem jeweiligen Kreis, die
        Boegen schliessen also stetig an.

        **Beide Boegen sind gemessen noetig, und zwar aus demselben Grund.**
        Ein gerader Abschluss ist eine SEHNE, und zwischen ihr und dem Kreis,
        an den sie grenzen soll, bleibt ihre Pfeilhoehe stehen:

        * oben (bis 20.09.2026): 3,93 mm Laeufereisen als geschlossener Ring
          zwischen allen Polschuhen -- ein magnetischer Kurzschluss saemtlicher
          Pole;
        * unten (bis zur zweiten Meldung desselben Tages): bis 3,1 mm ueber dem
          Joch, zwischen den Polen, von KEINEM Teil abgedeckt. Dort blieb der
          Laeufergrund der Leinwand stehen -- gemeldet als „das neue dunkle
          Grau sollte eigentlich schwarz sein", denn dort gehoert Luft hin.

        ``_BOGEN_N`` Stuetzpunkte: der Sehnenfehler eines Stuecks liegt damit
        unter einem Hundertstel Millimeter, also weit unter jeder Zellgroesse,
        die dieses Werkzeug je verwendet.
        """
        phi0 = math.atan2(v0, u0)                 # Winkel des unteren Endes
        phi1 = math.atan2(v1, u1)                 # Winkel des oberen Endes
        # Unten gegen den Uhrzeigersinn, oben zurueck -- ein einfacher Zug.
        unten = _bogenpunkte(math.hypot(u0, v0) if v0 > 1e-9 else u0, phi0)
        oben = list(reversed(_bogenpunkte(_r_kern_a, phi1)))
        return _polygon(unten + oben, grad, "luft")

    for i in range(poles):
        _g = 360.0 * i / max(poles, 1) + _schritt / 2.0    # Zwischenpolachse
        _luecke = _schritt - 2.0 * halb
        if _luecke > 0.1 and r_rot > _r_kern_a + 0.05:
            # Schuhband: hier gibt der Polschuh die Breite vor.
            teile.append(_segment(r_rot, r_rot - _r_kern_a, _g,
                                  _luecke / 2.0, "luft"))
        _s0 = _flanke_auf_kreis(_r_unten)
        _u0e, _v0e = _s0 if _s0 else (_u0, _halbbreite(_u0))
        if _u1 > _u0e + 0.05:
            _v0, _v1 = max(_v0e, 0.0), _halbbreite(_u1)
            if _v1 > 0.02:
                teile.append(_zwischenpol_polygon(_u0e, _u1, _v0, _v1, _g))
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
    # Die Spule ist ein BUENDEL unter dem Polschuh: eigener Anfang, eigene
    # Breite dort -- nicht mehr der ganze Kern von unten bis oben.
    r_si = float(k.get("r_spule_innen_mm", k.get("r_fuss_mm", r_j)))
    b_si = float(k.get("b_kern_spuleanfang_mm", b_i))
    # ZWEI Dicken: bei der Rechteckspule gleich, bei der ausgefuellten innen
    # duenner -- die Polteilung schrumpft nach innen.
    d_si = float(k.get("d_spule_innen_mm", d_s))
    d_sa = float(k.get("d_spule_aussen_mm", d_s))
    # Die Erregung ist GLEICHSTROM und damit magnetostatisch darstellbar --
    # anders als der Kaefig. Je Pol traegt die eine Spulenseite +F, die andere
    # -F Amperewindungen (das ist die Windung um den Kern), und die Polfolge
    # wechselt das Vorzeichen.
    f_pol = float(k.get("F_pol_A") or 0.0)
    # Der POLFUSS wird NICHT gezeichnet: er liegt UNTER `r_fuss_mm`, also im
    # Joch (Schwalbenschwanz in einer Nut, `ema_schenkelpol.befestigung`) --
    # und Joch und Pol sind dasselbe Eisen, eine Nut darin waere im Schnitt
    # unsichtbar. Frueher oeffnete er sich OBERHALB des Jochrings von der
    # Kernbreite auf die halbe Polteilung und stand damit als Keil im
    # Zwischenpolraum. Der Zweig bleibt fuer aeltere Masssaetze stehen, in
    # denen `r_fuss_mm` noch ueber dem Joch lag.
    r_f = float(k.get("r_fuss_mm", r_j))
    b_f = float(k.get("b_fuss_mm", b_i))
    hat_fuss = r_f > r_j + 0.2
    # **Der Polkoerper GREIFT IN DAS JOCH HINEIN.** Seine Unterkante ist eine
    # Gerade bei ``r_f``, der Jochaussenrand ein Kreis -- eine Gerade beruehrt
    # ihn nur in EINEM Punkt, auf der Polachse. Daneben klaffte eine Linse, die
    # kein Teil abdeckte: gemessen 0,88 % des Laeufers bei r = 46,79…49,88 mm,
    # und zwar bei 5…25 Grad, also weder auf der Polachse noch auf der
    # Zwischenpolachse. Auf der Leinwand stand dort der Laeufergrund.
    #
    # Behoben wie im CAD (`ema_freecad.POL_UEBERLAPP_MM`): der Koerper beginnt
    # so weit INNEN, dass seine Ecken auf dem Jochkreis liegen --
    # ``sqrt(r_joch^2 - (b/2)^2)``. Die Ueberdeckung mit dem Joch ist
    # harmlos, beide sind dasselbe Eisen, und die Reihenfolge-Regel macht sie
    # eindeutig. Ueberlappen ist hier richtig; Stossen war der Fehler.
    _r_fuss_z = math.sqrt(max(r_j * r_j - (b_i / 2.0) ** 2,
                              float(k.get("r_welle_mm", 0.0)) ** 2))
    r_f_z = min(r_f, _r_fuss_z) if not hat_fuss else r_f
    for i in range(poles):
        g = 360.0 * i / max(poles, 1)
        s = 1.0 if i % 2 == 0 else -1.0
        teile.append(_segment(r_rot, r_rot - r_k, g, halb, "pol"))
        if hat_fuss:
            teile.append(_trapez(r_j, r_f, -b_f / 2.0, b_f / 2.0,
                                 -b_i / 2.0, b_i / 2.0, g, "pol"))
        teile.append(_trapez(r_f_z, r_k, -b_i / 2.0, b_i / 2.0,
                             -b_a / 2.0, b_a / 2.0, g, "pol"))
        _p = _trapez(r_si, r_sp, b_si / 2.0, b_si / 2.0 + d_si,
                     b_e / 2.0, b_e / 2.0 + d_sa, g, "kupfer")
        _p["durchflutung_A"] = round(s * f_pol, 2)
        teile.append(_p)
        _m = _trapez(r_si, r_sp, -b_si / 2.0 - d_si, -b_si / 2.0,
                     -b_e / 2.0 - d_sa, -b_e / 2.0, g, "kupfer")
        _m["durchflutung_A"] = round(-s * f_pol, 2)
        teile.append(_m)
    # Der DAEMPFERKAEFIG sitzt im Polschuh — Rundstaebe, quer zur Polflaeche.
    #
    # Gezeichnet wird er nur, wenn er auch GERECHNET ist: die Zahlen kommen aus
    # `ema_schenkelpol.daempferkaefig`, derselben Funktion, die das Tor prueft.
    # Passt er nicht in den Schuh, wird er NICHT gezeichnet — ein Bild, das
    # Staebe zeigt, die das Tor gerade abgewiesen hat, ist schlimmer als keines.
    try:
        import ema_schenkelpol
        dae = ema_schenkelpol.daempferkaefig(geom, axial)
    except Exception:                                        # noqa: BLE001
        dae = None
    if dae and dae["aktiv"] and dae["passt"]:
        r_d = float(dae["r_ring_mm"])
        n_d = int(dae["n_stab_je_pol"])
        d_d = float(dae["d_stab_mm"])
        # Der Stab ist magnetisch Luft (Kupfer/Alu, mu_r ~ 1) und gehoert
        # deshalb ins Raster — genau wie die Kaefignut der ASM.
        rolle = "alu" if "al" in str(dae["werkstoff"]).lower() else "kupfer"
        halb_d = math.degrees((float(dae["teilung_mm"]) * (n_d - 1) / 2.0)
                              / max(r_d, 1e-9))
        for i in range(poles):
            g0 = 360.0 * i / max(poles, 1)
            for j in range(n_d):
                frac = 0.0 if n_d == 1 else (j / (n_d - 1.0) - 0.5) * 2.0
                a = math.radians(g0 + frac * halb_d)
                teile.append(_kreis(r_d * math.cos(a), r_d * math.sin(a),
                                    d_d / 2.0, rolle))

    hin = (f"Schenkelpollaeufer, {poles} Pole, Erregerspule aus dem "
           f"Kupferquerschnitt ({k['A_cu_mm2']:.0f} mm² je Pol) statt aus dem "
           f"verfuegbaren Platz. Die Erregung ist mit {f_pol:.0f} A je Pol "
           f"eingepraegt — Gleichstrom ist magnetostatisch darstellbar.")
    if dae and dae["aktiv"]:
        hin += (f" Daempferkaefig: {dae['n_stab_je_pol']} x "
                f"{dae['d_stab_mm']} mm je Pol, {dae['masse_kg']} kg."
                + ("" if dae["passt"] else
                   " ⚠ NICHT gezeichnet — " + str(dae["grund"])))
        if dae["passt"] and dae["hinweis"]:
            hin += " ⚠ " + dae["hinweis"]
    if not k.get("passt", True):
        hin += " ⚠ " + str(k.get("grund", ""))
    return {"teile": teile, "poles": poles,
            "zaehlung": f"Erregerspulen ({poles} Pole)",
            "masse": _masse(geom, [
                ("polSchuhBreiteMm", "Polschuhbreite",
                 k.get("b_schuh_mm"), "mm"),
                ("polKernBreiteMm", "Polkernbreite",
                 k.get("b_kern_aussen_mm"), "mm"),
                ("erregerSpuleDickeMm", "Spulendicke",
                 k.get("d_spule_mm"), "mm"),
                ("erregerSpuleHoeheMm", "Spulenhoehe",
                 k.get("h_spule_mm"), "mm"),
                ("polKegelWinkelGrad", "Kegelwinkel",
                 k.get("kegelwinkel_grad"), "\u00b0")]),
            "masse_befund": list(k.get("masse_befund") or []),
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
    """Der Reluktanzlaeufer -- Flussbarrieren nach Auslegungsregeln.

    **Nicht mehr die IPM-Tasche ohne Magnet.** Bis zum 20.09.2026 nahm diese
    Funktion die Lage aus ``ema_topology.magnet_legs`` und liess sie leer;
    gemeldet als „in der reluktanzmaschine sind nur die magnete entfernt. das
    ist doch nicht richtig." Eine Magnettasche sitzt dort, wo ein Magnet Platz
    braucht — eine Flussbarriere dort, wo der q-Fluss durch muss. Die Regeln
    dafuer stehen in ``ema_synrm_cad`` samt Quelle.
    """
    import ema_synrm_cad

    b = ema_synrm_cad.barrieren(geom, axial)
    poles = 2 * max(1, int(geom.get("p", 3)))
    teile = []
    # Eine Barriere gehoert zur **q-Achse** und ist symmetrisch zu ihr: ihre
    # beiden Enden liegen links und rechts davon am Luftspalt. Die q-Achsen
    # liegen zwischen den Polen.
    for i in range(poles):
        g = 360.0 * (i + 0.5) / poles
        for bar in b["barrieren"]:
            teile.append(_polygon(bar["punkte"], g, "luft"))

    if not b["barrieren"]:
        return {"teile": [], "poles": poles,
                "zaehlung": "Flussbarrieren (keine)",
                "feld_darstellbar": True,
                "fehler": "", "hinweis": "\u26a0 " + str(b.get("grund") or
                "Der Laeufer traegt keine Barrieren.")}

    # Kurz halten. Die Regeln samt Quelle stehen im Modulkopf von
    # `ema_synrm_cad` und als Hilfetext an der Bediengruppe; was HIER steht,
    # muss neben der Leinwand lesbar sein.
    hin = (f"Reluktanzlaeufer: {b['k']} Flussbarrieren je Pol, Endpunkte bei "
           f"konstanter Laeufernutteilung ({b['alpha_m_grad']:.2f}\u00b0), "
           f"Form nach den Feldlinien des Luftspaltfeldes. Isolationsgrad "
           f"q-Achse {b['kw_ist']:.2f} (Luft {b['luft_mm']:.1f} mm gegen Eisen "
           f"{b['eisen_mm']:.1f} mm), Tangentialsteg "
           f"{b['steg_rand_mm']:.1f} mm.")
    for f in b.get("befund") or []:
        hin += " \u26a0 " + f
    hin += (" Die analytische Rechnung kennt davon nur die "
            "Ersatz-Barrierenhoehe magThick.")
    return {"teile": teile, "poles": poles,
            "zaehlung": f"Flussbarrieren ({b['k']} je Pol)",
            # Reluktanz ist reine Geometrie: sobald die Barrieren als Luft im
            # Raster stehen, ist das Feld darstellbar -- anders als beim Kaefig.
            "feld_darstellbar": True,
            "masse": _masse(geom, [
                ("synrmBarrieren", "Barrieren je Pol", b["k"], ""),
                ("synrmIsolationsgrad", "Isolationsgrad", b["kw_ist"], ""),
                ("synrmStegMm", "Tangentialsteg", b["steg_rand_mm"], "mm"),
                ("synrmBetaGrad", "Freiwinkel", 
                 float(geom.get("synrmBetaGrad") or 0.0), "\u00b0")]),
            "masse_befund": list(b.get("befund") or []),
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
    # **Was neben der LEINWAND steht, und was daneben nicht hinpasst.**
    # `hinweis` beschreibt die Bauart und ist bei der Reluktanzmaschine
    # gemessen 558 Zeichen lang; der Kasten unter der Vorschau ist 224 px
    # breit und kuerzt bei 85 Zeichen. Heraus kam ein Satz, der mitten in der
    # Begruendung abbricht -- gemeldet als „man kann die beschreibung nicht
    # lesen". Die Beschreibung gehoert deshalb in den Geometrie-Reiter, wo sie
    # umbrechen darf; am Bild steht nur, WAS gezeichnet ist und WAS daran
    # nicht stimmt. Die Warnungen werden dabei NICHT gekuerzt: sie sind der
    # Grund, warum dort ueberhaupt etwas steht.
    _warn = [t.strip() for t in str(aus.get("hinweis") or "").split("\u26a0")[1:]]
    _warn += [str(x) for x in (aus.get("masse_befund") or [])]
    aus["kurz"] = " \u26a0 ".join([str(aus.get("zaehlung") or "")]
                                 + [w for w in _warn if w])

    # Ein Befund ohne Weg ist eine Sackgasse. Gemeldet als: „ich bekomme diese
    # Meldung und kann damit nichts anfangen." Die Entlastung des jeweiligen
    # Tors rechnet die Wege aus -- DIESELBE Funktion, die auch der Lauf
    # benutzt, damit die Maske nichts vorschlaegt, was das Tor danach abweist.
    # Gerechnet wird nur, wenn es wirklich etwas zu sagen gibt.
    if aus.get("masse_befund") and code == "eesm":
        try:
            import ema_eesm_cad as _EC
            _e = _EC.entlastung(geom, float(axial_mm or 80.0))
            aus["vorschlaege"] = list(_e.get("wege") or [])
            aus["vorschlag_hinweise"] = list(_e.get("hinweise") or [])
        except Exception:                                    # noqa: BLE001
            pass
    return aus


# Die Rollen, die KEIN Eisen sind. Genau diese werden aus dem Laeuferblech
# herausgestempelt -- Kupfer und Aluminium eingeschlossen: mu_r ~ 1, die Nut IST
# magnetisch Luft, ob ein Stab darin liegt oder nicht.
UNMAGNETISCH = ("luft", "kupfer", "alu")


def rastere(teile, setz, schritt_mm: float, a0: float = 0.0,
            sammle=None, mu_eisen: float = 500.0) -> int:
    """Die Teile der REIHE NACH in ein Raster stempeln -- die PYTHON-Fassung.

    Sie ist der Zwilling von ``rastere``/``_stempel`` in ``ema_laeufer.js``, und
    beide muessen dieselben Zellen treffen. Warum es sie zweimal gibt: die eine
    laeuft im Browser fuer die Live-Vorschau, die andere im 2-D-FDM auf dem
    Rechner. Die GEOMETRIE kommt dabei nur einmal vor (``teile()`` hier), aber
    das Eintragen ins Gitter muss jede Seite selbst tun.

    Das ist dieselbe Lage wie bei ``magnet_legs`` und seinem JS-Spiegel, und sie
    wird genauso abgesichert: ``test_laeuferbild.py`` fuehrt die JS-Fassung mit
    ``node`` aus und vergleicht Zelle fuer Zelle.

    ``setz(x, y, mu)``   traegt eine Zelle ein; ``mu`` ist 1 fuer alles
                         Unmagnetische und ``mu_eisen`` fuer Eisen und Pol.
                         **Was spaeter in der Liste steht, gewinnt** -- dieselbe
                         Regel wie in ``zeichne``, das die Teile der Reihe nach
                         uebermalt. Frueher stempelte diese Funktion NUR das
                         Unmagnetische; dann gewann im Raster immer die Luft,
                         waehrend im Bild der Pol gewann, und aus EINER Quelle
                         kamen zwei Laeufer (gemessen am Schenkelpol, wo die
                         Zwischenpolluft unter dem Polschuh in den Schuh
                         schneidet).
    ``schritt_mm``       Abtastschritt; der Aufrufer waehlt ihn aus seiner
                         Zellgroesse (eine halbe Zelle, wie im JS).
    ``a0``               Rotorwinkel in Bogenmass: der Laeufer dreht, die Teile
                         drehen mit.
    ``sammle``           optional: wird je Zelle EINES Teils gerufen, damit der
                         Aufrufer die Durchflutung auf genau diese Zellen legen
                         kann (die Spule braucht ihre Zellenzahl).

    Gibt die Zahl der eingetragenen Teile zurueck.
    """
    n = 0
    for t in teile:
        mu = 1.0 if str(t.get("rolle")) in UNMAGNETISCH else float(mu_eisen)
        _stempel(t, lambda x, y, _m=mu: setz(x, y, _m),
                 schritt_mm, a0, sammle if mu == 1.0 else None)
        n += 1
    return n


def _stempel(t, setz, schritt: float, a0: float, sammle=None) -> None:
    """Ein Teil abtasten. Formen wie in ``ema_laeufer.js._stempel``."""
    def _punkt(x, y):
        setz(x, y)
        if sammle is not None:
            sammle(x, y)

    form = str(t.get("form"))
    schritt = max(float(schritt), 1e-6)

    if form == "ring":
        r = float(t["r_i"])
        while r <= float(t["r_a"]) + 1e-9:
            n = max(8, int(math.ceil(2.0 * math.pi * r / schritt)))
            for i in range(n):
                a = a0 + 2.0 * math.pi * i / n
                _punkt(r * math.cos(a), r * math.sin(a))
            r += schritt
        return

    if form == "segment":
        g0 = math.radians(float(t["grad"]) - float(t["halb"]))
        g1 = math.radians(float(t["grad"]) + float(t["halb"]))
        r = float(t["r_a"]) - float(t["dicke"])
        while r <= float(t["r_a"]) + 1e-9:
            m = max(4, int(math.ceil(r * (g1 - g0) / schritt)))
            for i in range(m + 1):
                a = a0 + g0 + (g1 - g0) * i / m
                _punkt(r * math.cos(a), r * math.sin(a))
            r += schritt
        return

    if form == "rechteck":
        a = a0 + math.radians(float(t["grad"]))
        ca, sa = math.cos(a), math.sin(a)
        r = float(t["r0"])
        while r <= float(t["r1"]) + 1e-9:
            w = float(t["y0"])
            while w <= float(t["y1"]) + 1e-9:
                _punkt(r * ca - w * sa, r * sa + w * ca)
                w += schritt
            r += schritt
        return

    if form == "trapez":
        a = a0 + math.radians(float(t["grad"]))
        ca, sa = math.cos(a), math.sin(a)
        r0, r1 = float(t["r0"]), float(t["r1"])
        r = r0
        while r <= r1 + 1e-9:
            u = (r - r0) / max(r1 - r0, 1e-9)
            wa = float(t["y0i"]) + (float(t["y0a"]) - float(t["y0i"])) * u
            wb = float(t["y1i"]) + (float(t["y1a"]) - float(t["y1i"])) * u
            w = wa
            while w <= wb + 1e-9:
                _punkt(r * ca - w * sa, r * sa + w * ca)
                w += schritt
            r += schritt
        return

    if form == "tasche":
        # Langloch im Schenkelrahmen -- dieselbe Form wie die IPM-Tasche:
        # Ursprung am inneren Ende, um `tilt` gedreht, zwei Halbkreiskappen.
        # Beim Reluktanzlaeufer bleibt sie leer, und genau das ist die Bauart:
        # ohne diese Form war der SynRM-Laeufer im Raster ein VOLLZYLINDER
        # (gemessen 0,0 % Luft) und hatte damit keinen Reluktanzunterschied --
        # also gar keine Maschine.
        a = a0 + math.radians(float(t["grad"]))
        ca, sa = math.cos(a), math.sin(a)
        tc = math.cos(math.radians(float(t["tilt_grad"])))
        ts = math.sin(math.radians(float(t["tilt_grad"])))
        lng, hr = float(t["laenge"]), float(t["hoehe"]) / 2.0
        i = -hr
        while i <= lng + hr + 1e-9:
            j = -hr
            while j <= hr + 1e-9:
                nimm = True
                if i < 0 and (i * i + j * j) > hr * hr:
                    nimm = False
                elif i > lng:
                    d = i - lng
                    if (d * d + j * j) > hr * hr:
                        nimm = False
                if nimm:
                    x = float(t["r_pos"]) + i * tc - j * ts
                    y = float(t["offset"]) + i * ts + j * tc
                    _punkt(x * ca - y * sa, x * sa + y * ca)
                j += schritt
            i += schritt
        return

    if form == "polygon":
        a = a0 + math.radians(float(t["grad"]))
        ca, sa = math.cos(a), math.sin(a)
        pts = [(float(u), float(v)) for u, v in t["punkte"]]
        x0 = min(q[0] for q in pts)
        x1 = max(q[0] for q in pts)
        y0 = min(q[1] for q in pts)
        y1 = max(q[1] for q in pts)
        u = x0
        while u <= x1:
            v = y0
            while v <= y1:
                if _im_polygon(u, v, pts):
                    _punkt(u * ca - v * sa, u * sa + v * ca)
                v += schritt
            u += schritt
        return

    if form == "kreis":
        cx, cy, rr = float(t["cx"]), float(t["cy"]), float(t["r"])
        ca, sa = math.cos(a0), math.sin(a0)
        gx, gy = cx * ca - cy * sa, cx * sa + cy * ca
        k = -rr
        while k <= rr + 1e-9:
            h = -rr
            while h <= rr + 1e-9:
                if k * k + h * h <= rr * rr:
                    _punkt(gx + k, gy + h)
                h += schritt
            k += schritt
        return


# ── Umrisse ───────────────────────────────────────────────────────────────────
#
# Ein Teil als POLYGONZUG, im Laeuferbezug und in Millimetern. Gedacht fuer
# alles, was die Teile nur UMRANDEN will statt sie zu fuellen: das Feldbild
# zeichnet damit, was im Laeufer liegt, ohne die Geometrie ein viertes Mal
# auszuschreiben (Leinwand fuellt in Canvas, `rastere` stempelt ins Gitter,
# `ema_em2d_stat` baut OCC-Flaechen -- und der Umriss ist die vierte Sicht auf
# DIESELBEN Zahlen, nicht auf eine neue Rechnung).
#
# `n_bogen` ist die Zahl der Stuetzstellen je Bogen; 24 sind bei den hier
# vorkommenden Oeffnungswinkeln unter einem halben Prozent Flaechenfehler.

def umriss(t: dict, n_bogen: int = 24) -> list:
    """Ein Zeichenteil als geschlossener Polygonzug [(x, y), …] in mm."""
    form = str(t.get("form"))
    grad = math.radians(float(t.get("grad") or 0.0))
    ca, sa = math.cos(grad), math.sin(grad)

    def dreh(p):
        return [(x * ca - y * sa, x * sa + y * ca) for x, y in p]

    if form == "ring":
        # Ein Ring hat zwei Raender; als EIN Zug waere er entweder falsch
        # geschlossen oder ein Schlitz. Der aeussere genuegt als Umriss.
        r = float(t["r_a"])
        n = max(n_bogen, 48)
        return [(r * math.cos(2.0 * math.pi * i / n),
                 r * math.sin(2.0 * math.pi * i / n)) for i in range(n)]

    if form == "segment":
        r_a = float(t["r_a"])
        r_i = max(r_a - float(t["dicke"]), 0.0)
        g0 = grad - math.radians(float(t["halb"]))
        g1 = grad + math.radians(float(t["halb"]))
        n = max(int(n_bogen), 2)
        aus = [(r_a * math.cos(g0 + (g1 - g0) * i / n),
                r_a * math.sin(g0 + (g1 - g0) * i / n)) for i in range(n + 1)]
        aus += [(r_i * math.cos(g1 - (g1 - g0) * i / n),
                 r_i * math.sin(g1 - (g1 - g0) * i / n)) for i in range(n + 1)]
        return aus

    if form in ("rechteck", "trapez"):
        r0, r1 = float(t["r0"]), float(t["r1"])
        if form == "rechteck":
            y0i = y0a = float(t["y0"])
            y1i = y1a = float(t["y1"])
        else:
            y0i, y1i = float(t["y0i"]), float(t["y1i"])
            y0a, y1a = float(t["y0a"]), float(t["y1a"])
        return dreh([(r0, y0i), (r1, y0a), (r1, y1a), (r0, y1i)])

    if form == "tasche":
        lng = float(t["laenge"])
        hr = float(t["hoehe"]) / 2.0
        tc = math.cos(math.radians(float(t["tilt_grad"])))
        ts = math.sin(math.radians(float(t["tilt_grad"])))
        n = max(int(n_bogen) // 2, 2)
        roh = []
        for i in range(n + 1):                       # Kappe am aeusseren Ende
            a = -math.pi / 2.0 + math.pi * i / n
            roh.append((lng + hr * math.cos(a), hr * math.sin(a)))
        for i in range(n + 1):                       # Kappe am inneren Ende
            a = math.pi / 2.0 + math.pi * i / n
            roh.append((hr * math.cos(a), hr * math.sin(a)))
        lok = [(float(t["r_pos"]) + u * tc - v * ts,
                float(t["offset"]) + u * ts + v * tc) for u, v in roh]
        return dreh(lok)

    if form == "polygon":
        return dreh([(float(u), float(v)) for u, v in t["punkte"]])

    if form == "kreis":
        cx, cy, rr = float(t["cx"]), float(t["cy"]), float(t["r"])
        n = max(int(n_bogen), 16)
        lok = [(cx + rr * math.cos(2.0 * math.pi * i / n),
                cy + rr * math.sin(2.0 * math.pi * i / n)) for i in range(n)]
        return dreh(lok)

    raise ValueError(f"unbekannte Form '{form}'")
