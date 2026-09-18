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

# Kernbreite als Anteil der Polschuhbreite. Der Ueberstand traegt die Spule.
KERN_ZU_SCHUH = 0.72

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
    b_kern = KERN_ZU_SCHUH * b_schuh * (r_kern_aussen / max(r_rot, 1e-9))

    # Spulendicke aus dem KUPFERquerschnitt, nicht aus dem Platz.
    kf = ema_eesm._fuellfaktor()
    a_cu = float(er["A_cu_mm2"])
    a_wick = a_cu / max(kf, 1e-6)                       # mm^2, Wickelraum je Pol
    d_spule = max(SPULE_MIN_MM, a_wick / (2.0 * max(h_kern, 1e-9)))

    belegt = b_kern + 2.0 * d_spule
    frei = tau_kern - belegt
    passt = frei >= SPULENLUFT_MM

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
        "d_spule_mm": round(d_spule, 3),
        "tau_pol_mm": round(tau_pol, 3),
        "tau_kern_mm": round(tau_kern, 3),
        "belegt_mm": round(belegt, 3),
        "frei_mm": round(frei, 3),
        "passt": bool(passt),
        "grund": "" if passt else (
            f"Kern ({b_kern:.1f} mm) und Spule (2 x {d_spule:.1f} mm) belegen "
            f"{belegt:.1f} mm der {tau_kern:.1f} mm Polteilung am Kernradius — "
            f"es bleiben {frei:.1f} mm statt der geforderten "
            f"{SPULENLUFT_MM:.1f} mm Luft zum Nachbarpol"),
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
    )} | {"poles": int(k["poles"])}
