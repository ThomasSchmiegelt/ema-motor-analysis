"""Schenkelpollaeufer der fremderregten Synchronmaschine — als reine Zahlen.

Warum ein eigenes Modul und nicht direkt in ``ema_freecad``
------------------------------------------------------------

``ema_freecad`` schreibt Python-TEXT fuer einen fremden Prozess und kann darin
nichts importieren. Steht die Geometrie nur dort, gibt es sie genau einmal — im
erzeugten Skript — und weder ``render_cross_section`` noch ein Test kommen an
sie heran. Genau dieser Fall ist bei den Wickelkopf-Radien schon einmal
eingetreten (``ema_wicklung.hairpin_radien``): die Zwillingsfassung musste
nachtraeglich herausgeloest werden, weil das Tor „Wickelkopf unter dem
Stator-Aussendurchmesser" sonst gegen eine Zeichnung prueft, die es nicht
kennt.

Also: die Masse entstehen HIER, in Millimetern, aus ``ema_eesm.polgeometrie``
und ``ema_eesm.erregung`` — und Zeichner, Querschnittsbild und Test lesen
dieselbe Funktion.

Wie der Pol gebaut ist
----------------------

Von aussen nach innen, je Pol:

    Polschuh    Kreisbogensegment am Laeuferrand, Breite ``b_pol`` aus der
                Polbedeckung. Er fuehrt den Fluss in den Luftspalt UND haelt die
                Erregerspule radial fest.
    Polkern     Rechteck darunter, SCHMALER als der Schuh — der Ueberstand ist
                genau der Platz, auf dem die Spule sitzt.
    Spule       zwei Querschnitte links und rechts des Kerns, radial ueber die
                Kernhoehe. Ihre Dicke folgt dem KUPFERQUERSCHNITT aus
                ``erregung`` (der aus der Stromdichte kommt), geteilt durch den
                Fuellfaktor — nicht dem verfuegbaren Platz. Das ist dieselbe
                Entscheidung wie bei der Laeuferwicklung der ASM und aus
                demselben Grund: eine Wicklung, die das Fenster fuellt, kam
                gemessen auf 0,7 A/mm^2 und 15,7 kg Kupfer — eine Maschine, die
                niemand baut.
    Joch        Ring zwischen Welle und Polfuss, Hoehe aus dem Fluss je Pol.

Was hier GEPRUEFT wird und was nicht
-------------------------------------

Geprueft wird, ob Kern und Spule auf die Polteilung passen (``passt``) und ob
zwischen zwei benachbarten Spulen Luft bleibt. **Nicht** geprueft wird die
Fliehkraft am Polfuss: ein Schenkelpol haengt am Schwalbenschwanz oder an
Bolzen, und dafuer gibt es hier kein Modell — es steht als ``ungeprueft`` im
Ergebnis statt als stilles Nichts.
"""

from __future__ import annotations

import math

# Anteil der Polhoehe, den der Polschuh einnimmt. Der Rest ist Kern.
SCHUH_ANTEIL = 0.22
SCHUH_MIN_MM = 3.0

# Kernbreite als Anteil der Polschuhbreite -- nur noch als OBERE Schranke.
# Bestimmt wird sie jetzt aus der Deckung (s. `koerper`).
KERN_ZU_SCHUH = 0.72

# Wie weit der Polschuh die Spule ueberragt [mm je Seite].
#
# Das ist keine Kosmetik, sondern die mechanische Aufgabe des Polschuhs:
# „salient pole tips overhang the pole body to secure the field coil in place
# against the action of centrifugal force" (US3089049A, US3728566). Ohne
# Ueberstand haelt die Spule nichts -- sie sitzt auf einem drehenden Koerper.
SCHUH_UEBERSTAND_MM = 2.0

# Wie schmal der Kern hoechstens werden darf, bezogen auf die Schuhbreite am
# Kernradius. Darunter traegt der Pol den Fluss nicht mehr, und dann ist die
# Spule zu dick fuer diesen Pol -- das wird GESAGT statt gezeichnet.
KERN_MIN_ANTEIL = 0.35

# Kegelige Wicklung: der Pol ist an der JOCHseite breiter als unter dem Schuh,
# und die Wicklung folgt dieser Neigung -- „the base (rotor-side) of the motor
# pole is wider than the top (stator-side) ... the field windings will follow
# the taper" (WO2006026200A1). Der Wert ist das Verhaeltnis aussen:innen.
KEGEL_VERJUENGUNG = 0.80
SPULENFORMEN = ("rechteck", "kegel")

# Luft zwischen den Spulen zweier benachbarter Pole [mm].
SPULENLUFT_MM = 2.0

# Mindestdicke einer gezeichneten Spulenseite [mm].
SPULE_MIN_MM = 2.0

# Wie weit Kern und Spule vom Laeuferrand wegbleiben muessen [mm].
#
# Das ist die Wand, die gefehlt hat. Kern und Spule sind RECHTECKE, der Laeufer
# ist ein KREIS: ein Rechteck der halben Breite ``y``, dessen Oberkante bei
# ``r`` liegt, hat seine Ecken bei ``sqrt(r^2 + y^2)`` -- also WEITER aussen als
# seine Oberkante. Geprueft wurde bisher nur die Oberkante, und deshalb stand
# die Erregerspule einer 170-mm-Maschine gemessen mit ihren Ecken bei
# r = 88,63 mm, waehrend die Statorbohrung bei 85,8 mm anfaengt: die Spule lag
# IM Staender. Gemeldet als „in der fremderregten Maschine kollidieren Rotor
# und Stator", und genau so war es.
RAND_LUFT_MM = 1.0


def _spule_einpassen(a_wick_mm2: float, r_joch: float, y_kern: float,
                     r_max: float) -> tuple:
    """Dicke und Aussenradius der Erregerspule, so dass ihre ECKEN drinbleiben.

    Gesucht ist das Paar ``(d, r_top)`` mit

        d * (r_top - r_joch) = a_wick/2            (Wickelraum je Spulenseite)
        sqrt(r_top^2 + (y_kern + d)^2) = r_max     (die Ecke liegt auf dem Rand)

    Eingesetzt bleibt EINE Gleichung in ``d``; sie ist nicht monoton (eine
    dickere Spule muss tiefer sitzen und wird dadurch kuerzer), hat also ein
    Maximum. Genommen wird die KLEINERE Wurzel -- die duennere, hoehere Spule:
    sie sitzt naeher am Polschuh und wird von ihm gehalten.

    Gibt es keine Wurzel, passt die Wicklung nicht unter den Rand. Dann kommt
    ``ok=False`` heraus und das beste erreichbare Paar dazu -- gezeichnet wird
    etwas, das im Laeufer bleibt, und der Befund steht daneben.
    """
    ziel = max(a_wick_mm2, 0.0) / 2.0
    d_max = math.sqrt(max(r_max ** 2 - r_joch ** 2, 0.0)) - y_kern
    if d_max <= SPULE_MIN_MM:
        return SPULE_MIN_MM, max(r_joch + 1.0, 0.0), False

    def hoehe(d: float) -> float:
        return math.sqrt(max(r_max ** 2 - (y_kern + d) ** 2, 0.0)) - r_joch

    n = 400
    bestes = (SPULE_MIN_MM, hoehe(SPULE_MIN_MM))
    vorher = SPULE_MIN_MM * hoehe(SPULE_MIN_MM) - ziel
    if vorher >= 0.0:
        return SPULE_MIN_MM, r_joch + hoehe(SPULE_MIN_MM), True
    for i in range(1, n + 1):
        d = SPULE_MIN_MM + (d_max - SPULE_MIN_MM) * i / n
        f = d * hoehe(d) - ziel
        if d * hoehe(d) > bestes[0] * bestes[1]:
            bestes = (d, hoehe(d))
        if f >= 0.0:                      # Vorzeichenwechsel -> einschachteln
            lo, hi = d - (d_max - SPULE_MIN_MM) / n, d
            for _ in range(60):
                m = 0.5 * (lo + hi)
                if m * hoehe(m) - ziel < 0.0:
                    lo = m
                else:
                    hi = m
            return hi, r_joch + hoehe(hi), True
        vorher = f
    # Keine Wurzel: der Wickelraum passt nicht unter den Rand. Gezeichnet wird
    # die groesstmoegliche Spule, damit das Bild nicht leer bleibt.
    return bestes[0], r_joch + bestes[1], False


def koerper(geom: dict, axial_mm: float) -> dict:
    """Alle Masse des Schenkelpollaeufers in Millimetern.

    Radien sind absolut (von der Wellenachse), Breiten in Millimetern **am
    jeweiligen Radius** — der Zeichner setzt daraus Rechtecke und Kreisbogen-
    segmente, das Querschnittsbild dieselben.
    """
    import ema_eesm

    pg = ema_eesm.polgeometrie(geom, axial_mm)
    er = ema_eesm.erregung(geom, axial_mm)

    poles = int(pg["poles"])
    r_rot = float(geom["rotorOD"]) / 2.0
    r_wel = max(float(geom["shaftD"]) / 2.0, 1.0)
    h_joch = float(pg["h_joch_mm"])
    r_joch = min(r_wel + h_joch, r_rot - 2.0)          # Aussenradius des Jochs

    h_pol = max(r_rot - r_joch, 2.0)                    # Schuh + Kern
    h_schuh = max(SCHUH_MIN_MM, min(SCHUH_ANTEIL * h_pol, 0.6 * h_pol))
    h_kern = max(h_pol - h_schuh, 1.0)
    r_kern_aussen = r_rot - h_schuh

    b_schuh = float(pg["b_pol_mm"])                     # Bogenlaenge am Rand
    tau_pol = float(pg["tau_pol_mm"])
    # Die Kernbreite wird am KERNradius gemessen, die Polbedeckung aber am
    # Rand. Ohne die Umrechnung waere der Kern bei kleinem Laeufer breiter als
    # die Teilung, die ihm dort zusteht.
    tau_kern = 2.0 * math.pi * r_kern_aussen / poles
    # Die Schuhbreite AM KERNRADIUS -- derselbe Bogenwinkel, kleinerer Radius.
    b_schuh_k = b_schuh * (r_kern_aussen / max(r_rot, 1e-9))

    # Spulendicke aus dem KUPFERquerschnitt, nicht aus dem Platz.
    kf = ema_eesm._fuellfaktor()
    a_cu = float(er["A_cu_mm2"])
    a_wick = a_cu / max(kf, 1e-6)                       # mm^2, Wickelraum je Pol

    form = str(geom.get("erregerSpuleForm") or "rechteck")
    if form not in SPULENFORMEN:
        form = "rechteck"
    # Verhaeltnis innen:aussen des Kerns -- beim Rechteck 1,0.
    kegel = (1.0 / max(KEGEL_VERJUENGUNG, 1e-6)) if form == "kegel" else 1.0

    tau_joch = 2.0 * math.pi * r_joch / poles
    r_max = max(r_rot - RAND_LUFT_MM, r_joch + 1.0)

    # ── Kern und Spule haengen voneinander ab, also wird gekoppelt geloest ──
    #
    # Die Kernbreite folgt der Spulendicke (Deckung, Platz am Joch), die
    # Spulendicke aber der verbleibenden Hoehe -- und die haengt wieder an der
    # Kernbreite, weil die Spulenecke auf dem Laeuferrand landen muss. Vier
    # Durchgaenge genuegen (gemessen: der zweite bewegt noch 0,3 mm, der
    # vierte 1e-4 mm); der Startwert ist der alte, aus der vollen Kernhoehe
    # gerechnete -- damit bleibt eine Auslegung, bei der die Ecke nie stoerte,
    # Ziffer fuer Ziffer dieselbe.
    d_spule = max(SPULE_MIN_MM, a_wick / (2.0 * max(h_kern, 1e-9)))
    r_spule = r_kern_aussen
    spule_passt = True
    for _durchgang in range(4):
        # ── Vier Schranken, und es gilt die engste ────────────────────────
        # (1) DECKUNG: der Polschuh muss die Spule ueberragen, sonst haelt sie
        #     nichts gegen die Fliehkraft (US3089049A).
        # (2) PLATZ AM JOCH: die Polteilung ist am Jochradius am KLEINSTEN, der
        #     Kern aber ueber die ganze Hoehe gleich breit (beim Kegel dort
        #     sogar am breitesten). Geprueft wurde bisher nur am KERNradius, wo
        #     reichlich Platz ist -- gemessen durchdringen sich dadurch ab acht
        #     Polen die Spulen benachbarter Pole am Joch um 3,9 mm.
        # (3) LAEUFERRAND: der Kern ist ein Rechteck im Kreis, seine ECKEN
        #     liegen weiter aussen als seine Oberkante (s. RAND_LUFT_MM).
        # (4) die alte obere Schranke: ein Kern fast so breit wie sein Schuh
        #     liesse keinen Platz fuer die Wicklung.
        schranken = {
            "deckung": b_schuh_k - 2.0 * (d_spule + SCHUH_UEBERSTAND_MM),
            "joch":    (tau_joch - SPULENLUFT_MM - 2.0 * d_spule) / kegel,
            "rotorrand": 2.0 * math.sqrt(
                max(r_max ** 2 - r_kern_aussen ** 2, 0.0)),
            "kernanteil": KERN_ZU_SCHUH * b_schuh_k,
        }
        bindend = min(schranken, key=lambda k: schranken[k])
        b_kern_aussen = schranken[bindend]
        b_kern_min = KERN_MIN_ANTEIL * b_schuh_k
        passt = b_kern_aussen >= b_kern_min
        b_kern_aussen = max(b_kern_aussen, b_kern_min)
        # Der Laeuferrand ist die EINE Schranke, die das Mindestmass nicht
        # ueberstimmen darf: ein zu schmaler Kern ist ein Befund, ein Kern
        # ausserhalb des Laeufers ist eine falsche Zeichnung. Passt es nicht,
        # steht `passt=False` schon oben -- gezeichnet wird trotzdem etwas,
        # das im Blech bleibt.
        b_kern_aussen = min(b_kern_aussen, schranken["rotorrand"] / kegel)
        b_kern_innen = b_kern_aussen * kegel
        # Die Spule sitzt NEBEN dem Kern: massgeblich ist die breiteste Stelle
        # (beim Kegel die Jochseite), sonst waere gerade dort die Ecke draussen.
        y_kern = max(b_kern_aussen, b_kern_innen) / 2.0
        d_neu, r_spule, spule_passt = _spule_einpassen(
            a_wick, r_joch, y_kern, r_max)
        if abs(d_neu - d_spule) < 1e-4:
            d_spule = d_neu
            break
        d_spule = d_neu
    d_spule = max(d_spule, SPULE_MIN_MM)
    r_spule = min(max(r_spule, r_joch + 1.0), r_kern_aussen)
    # Letzter Riegel: auch im Fehlerfall bleibt die gezeichnete Ecke drin.
    _y_aussen = max(b_kern_aussen, b_kern_innen) / 2.0 + d_spule
    r_spule = min(r_spule, math.sqrt(max(r_max ** 2 - _y_aussen ** 2, 1.0)))
    h_spule = r_spule - r_joch
    b_kern = b_kern_aussen                   # was ein Zeichner liest, der nur EINE Breite kennt

    # Nachgerechnet statt angenommen: alles drei sind ERGEBNISSE, keine Vorgaben.
    ueberstand = (b_schuh_k - (b_kern_aussen + 2.0 * d_spule)) / 2.0
    deckt = ueberstand >= 0.0
    belegt = b_kern_innen + 2.0 * d_spule
    frei = tau_joch - belegt
    # Die Kernbreite AM SPULENENDE -- eine Zahl, drei Zeichner.
    #
    # Die Spule liegt am Kern an, endet aber weiter innen als er. Beim Kegel
    # ist der Kern dort schmaler als an seiner Oberkante; ohne diesen Wert
    # muesste jeder Zeichner die Verjuengung selbst ausmultiplizieren, und beim
    # dritten stuende eine andere Spule im Bild als im CAD.
    _u = (r_spule - r_joch) / max(r_kern_aussen - r_joch, 1e-9)
    b_kern_spulenende = b_kern_innen + (b_kern_aussen - b_kern_innen) * min(max(_u, 0.0), 1.0)

    # Die Ecke, an der es frueher hinauslief -- jetzt gemessen statt angenommen.
    r_ecke_kern = math.hypot(r_kern_aussen, max(b_kern_aussen, b_kern_innen) / 2.0)
    r_ecke_spule = math.hypot(r_spule, max(b_kern_aussen, b_kern_innen) / 2.0
                              + d_spule)
    im_laeufer = max(r_ecke_kern, r_ecke_spule) <= r_rot + 1e-6
    if not spule_passt:
        passt = False

    if passt:
        grund = ""
    elif not spule_passt:
        grund = (f"Der Wickelraum ({a_wick:.0f} mm² je Pol) passt nicht unter "
                 f"den Laeuferrand: mehr als {d_spule * h_spule * 2:.0f} mm² "
                 f"sind zwischen Joch (r = {r_joch:.1f} mm) und Rand "
                 f"(r = {r_max:.1f} mm) nicht unterzubringen, ohne dass die "
                 f"Spulenecke aus dem Laeufer tritt. Groesserer Laeufer, "
                 f"hoehere Stromdichte oder weniger Pole")
    elif bindend == "rotorrand":
        grund = (f"Der Polkern bleibt mit seinen Ecken nicht im Laeufer: bei "
                 f"r = {r_kern_aussen:.1f} mm duerfte er hoechstens "
                 f"{schranken['rotorrand']:.1f} mm breit sein, das Mindestmass "
                 f"sind aber {b_kern_min:.1f} mm. Ein dickerer Polschuh "
                 f"(kleinerer Kernradius) oder weniger Polbedeckung")
    elif not deckt:
        grund = (f"Der Polschuh ueberdeckt die Spule NICHT: er ist am "
                 f"Kernradius {b_schuh_k:.1f} mm breit, Kern ({b_kern:.1f}) "
                 f"und Spule (2 x {d_spule:.1f} mm) brauchen aber "
                 f"{b_kern + 2 * d_spule:.1f} mm. Die Spule haengt dann ueber "
                 f"und wird von nichts gegen die Fliehkraft gehalten — mehr "
                 f"Polbedeckung oder eine duennere Spule (hoehere Stromdichte)")
    elif frei < SPULENLUFT_MM:
        grund = (f"Kern ({b_kern_innen:.1f} mm an der engsten Stelle) und "
                 f"Spule (2 x {d_spule:.1f} mm) belegen {belegt:.1f} mm — es "
                 f"bleiben {frei:.1f} mm statt der geforderten "
                 f"{SPULENLUFT_MM:.1f} mm Luft zum Nachbarpol")
    else:
        grund = (f"Die Spule ist zu dick fuer diesen Pol: die engste Schranke "
                 f"ist '{bindend}' und liesse nur {schranken[bindend]:.1f} mm "
                 f"Kern, unter dem Mindestmass von {b_kern_min:.1f} mm. "
                 f"Mehr Polbedeckung, weniger Pole oder eine hoehere "
                 f"Stromdichte")

    return {
        "poles": poles,
        "r_welle_mm": round(r_wel, 3),
        "r_joch_aussen_mm": round(r_joch, 3),
        "h_joch_mm": round(h_joch, 3),
        "r_kern_aussen_mm": round(r_kern_aussen, 3),
        "r_rotor_mm": round(r_rot, 3),
        "h_pol_mm": round(h_pol, 3),
        "h_schuh_mm": round(h_schuh, 3),
        "h_kern_mm": round(h_kern, 3),
        "b_schuh_mm": round(b_schuh, 3),
        "b_kern_mm": round(b_kern, 3),
        # Kegel: zwei Breiten statt einer. Bei `rechteck` sind sie gleich, und
        # jeder Zeichner, der nur `b_kern_mm` liest, bleibt richtig.
        "spulenform": form,
        "b_kern_aussen_mm": round(b_kern_aussen, 3),
        "b_kern_innen_mm": round(b_kern_innen, 3),
        "schuh_ueberstand_mm": round(ueberstand, 3),
        "deckt_spule": bool(deckt),
        "d_spule_mm": round(d_spule, 3),
        # Der Aussenradius der SPULE ist nicht der des Kerns: die Spule sitzt
        # neben ihm und muesste mit ihrer Ecke sonst aus dem Laeufer treten.
        "r_spule_aussen_mm": round(r_spule, 3),
        "b_kern_spulenende_mm": round(b_kern_spulenende, 3),
        "h_spule_mm": round(h_spule, 3),
        "r_ecke_kern_mm": round(r_ecke_kern, 3),
        "r_ecke_spule_mm": round(r_ecke_spule, 3),
        "im_laeufer": bool(im_laeufer),
        "tau_pol_mm": round(tau_pol, 3),
        "tau_kern_mm": round(tau_kern, 3),
        "belegt_mm": round(belegt, 3),
        "frei_mm": round(frei, 3),
        "passt": bool(passt),
        "bindend": bindend,
        "grund": grund,
        "A_cu_mm2": round(a_cu, 2),
        "A_wickelraum_mm2": round(a_wick, 2),
        "fuellfaktor": round(kf, 3),
        "I_f_A": float(er["I_f_A"]),
        "F_pol_A": float(er["F_pol_A"]),
        "fenster_reicht": bool(er["fenster_reicht"]),
        # Was dieses Modul NICHT weiss. Ein Schenkelpol haengt am
        # Schwalbenschwanz oder an Bolzen; die Fliehkraft daran rechnet hier
        # niemand, und ein Schweigen darueber laese sich als „geprueft" lesen.
        "ungeprueft": ("Polbefestigung (Schwalbenschwanz/Bolzen) und die "
                       "Fliehkraft am Polfuss sind NICHT gerechnet"),
    }


def zeichenmasse(k: dict) -> dict:
    """Nur die Zahlen, die ein erzeugtes Skript braucht.

    Urteile (``passt``, ``grund``, ``ungeprueft``) bleiben draussen: sie
    gehoeren ins Protokoll, und ein ``true``/``null`` aus JSON waere im
    erzeugten **Python**-Skript ein NameError — gemessen genau daran
    gescheitert (s. ``ema_schleifring.zeichenmasse``).
    """
    return {n: float(k[n]) for n in (
        "r_welle_mm", "r_joch_aussen_mm", "r_kern_aussen_mm", "r_rotor_mm",
        "h_schuh_mm", "h_kern_mm", "b_schuh_mm", "b_kern_mm", "d_spule_mm",
        "b_kern_aussen_mm", "b_kern_innen_mm", "r_spule_aussen_mm",
        "b_kern_spulenende_mm",
    )} | {"poles": int(k["poles"])}
