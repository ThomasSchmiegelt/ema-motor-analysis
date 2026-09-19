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
    d_spule = max(SPULE_MIN_MM, a_wick / (2.0 * max(h_kern, 1e-9)))

    # ── Der Kern folgt der DECKUNG, nicht einem festen Verhaeltnis ────────
    # Vorher war `b_kern = 0.72 * b_schuh_k`, und ob der Schuh die Spule
    # ueberdeckte, ergab sich zufaellig. Der Polschuh hat aber genau diese
    # Aufgabe: er haelt die Spule gegen die Fliehkraft. Also wird der Kern so
    # schmal gemacht, dass Spule PLUS Ueberstand darunter passen -- und wenn
    # das den Kern unter `KERN_MIN_ANTEIL` druecken wuerde, ist die Spule zu
    # dick fuer diesen Pol, und das steht als Befund da.
    form = str(geom.get("erregerSpuleForm") or "rechteck")
    if form not in SPULENFORMEN:
        form = "rechteck"
    # Verhaeltnis innen:aussen des Kerns -- beim Rechteck 1,0.
    kegel = (1.0 / max(KEGEL_VERJUENGUNG, 1e-6)) if form == "kegel" else 1.0

    # ── Drei Schranken, und es gilt die engste ────────────────────────────
    # (1) DECKUNG: der Polschuh muss die Spule ueberragen, sonst haelt sie
    #     nichts gegen die Fliehkraft (US3089049A).
    # (2) PLATZ AM JOCH: die Polteilung ist am Jochradius am KLEINSTEN, der
    #     Kern aber ueber die ganze Hoehe gleich breit (beim Kegel dort sogar
    #     am breitesten). Geprueft wurde bisher nur am KERNradius, wo reichlich
    #     Platz ist -- gemessen durchdringen sich dadurch ab acht Polen die
    #     Spulen benachbarter Pole am Joch um 3,9 mm, und gezeichnet wurde es
    #     trotzdem.
    # (3) die alte obere Schranke: ein Kern fast so breit wie sein Schuh
    #     liesse keinen Platz fuer die Wicklung.
    tau_joch = 2.0 * math.pi * r_joch / poles
    schranken = {
        "deckung": b_schuh_k - 2.0 * (d_spule + SCHUH_UEBERSTAND_MM),
        "joch":    (tau_joch - SPULENLUFT_MM - 2.0 * d_spule) / kegel,
        "kernanteil": KERN_ZU_SCHUH * b_schuh_k,
    }
    bindend = min(schranken, key=lambda k: schranken[k])
    b_kern_aussen = schranken[bindend]
    b_kern_min = KERN_MIN_ANTEIL * b_schuh_k
    passt = b_kern_aussen >= b_kern_min
    b_kern_aussen = max(b_kern_aussen, b_kern_min)
    b_kern_innen = b_kern_aussen * kegel
    b_kern = b_kern_aussen                       # was ein Zeichner liest, der nur EINE Breite kennt

    # Nachgerechnet statt angenommen: beides sind ERGEBNISSE, keine Vorgaben.
    ueberstand = (b_schuh_k - (b_kern_aussen + 2.0 * d_spule)) / 2.0
    deckt = ueberstand >= 0.0
    belegt = b_kern_innen + 2.0 * d_spule
    frei = tau_joch - belegt

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
        "tau_pol_mm": round(tau_pol, 3),
        "tau_kern_mm": round(tau_kern, 3),
        "belegt_mm": round(belegt, 3),
        "frei_mm": round(frei, 3),
        "passt": bool(passt),
        "bindend": bindend,
        "grund": "" if passt else (
            (f"Die Spule ist zu dick fuer diesen Pol: die engste Schranke ist "
             f"'{bindend}' und liesse nur {schranken[bindend]:.1f} mm Kern, "
             f"unter dem Mindestmass von {b_kern_min:.1f} mm. "
             f"Mehr Polbedeckung, weniger Pole oder eine hoehere Stromdichte") +
            "" if True else (f"Der Polschuh ueberdeckt die Spule NICHT: er ist am Kernradius "
             f"{b_schuh_k:.1f} mm breit, Kern ({b_kern:.1f}) und Spule "
             f"(2 x {d_spule:.1f} mm) brauchen aber "
             f"{b_kern + 2*d_spule:.1f} mm. Die Spule haengt dann ueber und "
             f"wird von nichts gegen die Fliehkraft gehalten — mehr Polbedeckung "
             f"oder eine duennere Spule (hoehere Stromdichte)")
            if not deckt else
            (f"Kern ({b_kern_innen:.1f} mm an der engsten Stelle) und Spule "
             f"(2 x {d_spule:.1f} mm) belegen {belegt:.1f} mm — es bleiben "
             f"{frei:.1f} mm statt der geforderten {SPULENLUFT_MM:.1f} mm Luft "
             f"zum Nachbarpol")),
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
        "b_kern_aussen_mm", "b_kern_innen_mm",
    )} | {"poles": int(k["poles"])}
