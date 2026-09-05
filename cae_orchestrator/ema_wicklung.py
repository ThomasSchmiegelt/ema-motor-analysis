"""Wicklung: EINE Quelle fuer Nutgeometrie, Leiter, Widerstand und Masse.

Warum dieses Modul ueberhaupt entsteht
---------------------------------------

Die Nutgeometrie ist im Werkzeug nicht EINMAL beschrieben, sondern siebenmal
abgeschrieben. Wortgleich gefunden in ``ema_freecad`` (CAD-Erzeugung),
``ema_pipeline`` (zweimal), ``ema_thermal`` (dreimal) und ``ema_bilddaten``:

    slot_w  = max(3.0, R_si * dtheta * slotWidthRatio)
    cond_w  = max(1.5, slot_w - 2 * ins)
    layer_h = max(2.0, (slot_dep - 2 - (n_layers + 1) * ins) / n_layers)

Und sie ist bereits **auseinandergelaufen**: die dritte Kopie in
``ema_thermal.mass_and_cost`` rechnet mit fest zwei Lagen und ``3*ins`` statt
mit ``n_layers`` und ``(n_layers+1)*ins``. Wer die Leiterzahl aendert, aendert
damit den Widerstand und die Verluste, aber **nicht** die Kupfermasse und die
Kosten. Das faellt nirgends auf, weil beide Zahlen fuer sich plausibel bleiben.

Genau deshalb steht die Zusammenlegung im Plan VOR der zweiten Wicklungsart:
aus sieben Kopien wuerden sonst vierzehn.

Zwei Wicklungsarten, und woran sie sich wirklich unterscheiden
---------------------------------------------------------------

``windingType = hairpin`` (bisher, Vorgabe) und ``rundraht``. Der Unterschied
ist nicht die Zeichnung, sondern drei Zahlen, die alles Weitere tragen:

* **Nutfuellfaktor.** Rechteckige Hairpin-Staebe fuellen die Nut dicht
  (gemessen ueber die Lagenrechnung rund 0,6-0,7); runder Draht kann das
  geometrisch nicht -- selbst die dichteste Kreispackung kommt auf 0,907, und
  mit Lackschicht, Nutisolation und Wickeltoleranz bleiben in der Praxis
  0,40-0,45.
* **Wickelkopf.** Der Hairpin wird gebogen und geschweisst; sein Ueberhang ist
  kurz und beherrscht. Runddraht wird gewickelt, und die Windung muss um die
  Spulenweite herum -- der Wickelkopf ist laenger, das Kupfer darin ist
  Widerstand ohne Moment.
* **Windungszahl.** Der Hairpin hat wenige dicke Leiter je Nut, der Runddraht
  viele duenne. Bei gleichem Strombelag heisst das ein anderer Strangwiderstand
  und eine andere Strangspannung.

Was hier bewusst NICHT geaendert wird
--------------------------------------

Der Wickelkopfueberhang des Hairpins bleibt bei den historischen **18 mm**
(``WICKELKOPF_HAIRPIN_M``). Er liesse sich aus der Spulenweite ausrechnen, und
das waere sauberer -- aber es wuerde jeden bestehenden PSM-Wert verschieben,
ohne dass irgendjemand danach gefragt haette. Der Runddraht bekommt seinen
Wickelkopf aus der Geometrie, weil es fuer ihn keinen historischen Wert gibt,
den man verschieben koennte. Der Unterschied steht hier, statt sich in einer
Zahl zu verstecken.

Ebenfalls nicht enthalten: Stromverdraengung im Leiter (Skin/Proximity),
Parallelzweige, Sehnung ausser ueber ``coilPitch``, Nutschlitz als eigene
Groesse.
"""

from __future__ import annotations

import math

# ── Feste Groessen der Nut ────────────────────────────────────────────────────

NUT_MIN_M      = 3.0e-3      # kleinste gerechnete Nutbreite
LEITER_MIN_M   = 1.5e-3      # kleinste gerechnete Leiterbreite
LAGE_MIN_M     = 2.0e-3      # kleinste gerechnete Lagenhoehe
ISOLIERUNG_M   = 0.8e-3      # Nutisolation je Seite / zwischen den Lagen
NUTGRUND_M     = 2.0e-3      # Abzug am Nutgrund (Keil, Radius)

# Wickelkopfueberhang je Seite. Der Hairpin-Wert ist historisch (s. Modulkopf).
WICKELKOPF_HAIRPIN_M = 0.018

# Wickelkopf aus der Geometrie: l_e = A * Spulenweite + B je Seite.
#
# Runddraht wird gewickelt; die Windung muss um die volle Spulenweite herum,
# uebliche Ansaetze liegen bei 1,1-1,4 mal Spulenweite.
# Der Hairpin geht ebenfalls ueber die Spulenweite, aber in einer kurzen,
# beherrschten Verwindung -- das ist der eigentliche Grund fuer die Bauart.
WK_RUNDDRAHT_A, WK_RUNDDRAHT_B = 1.2, 0.020
WK_HAIRPIN_A,   WK_HAIRPIN_B   = 0.6, 0.010

# Nutfuellfaktoren. Die dichteste Kreispackung liegt bei 0,9069; mit Lack,
# Nutisolation, Nutkeil und Wickeltoleranz bleiben in der Praxis 0,40-0,45.
FUELL_RUNDDRAHT = 0.42

ARTEN = ("hairpin", "rundraht")
ART_LABEL = {
    "hairpin":  "Hairpin (rechteckige Staebe, gebogen und geschweisst)",
    "rundraht": "Runddraht (gewickelt, viele duenne Windungen)",
}
VORGABE = "hairpin"


def art(geom: dict) -> str:
    """Wicklungsart aus ``geom``. Unbekannt -> Vorgabe (Hairpin, wie bisher)."""
    w = str((geom or {}).get("windingType", "") or "").strip().lower()
    return w if w in ARTEN else VORGABE


def lagen(geom: dict) -> int:
    """Leiter je Nut beim Hairpin -- geradzahlig, 2..12 (Hin und Zurueck)."""
    n = int((geom or {}).get("conductorsPerSlot", 2) or 2)
    return max(2, min(12, n + (n % 2)))


def windungen(geom: dict) -> int:
    """Windungen je Nut beim Runddraht.

    Vorgabe ist ``turnsPerSlot``; fehlt sie, wird ``conductorsPerSlot`` als
    Windungszahl gelesen. Das ist keine Umdeutung, sondern dieselbe Groesse
    unter dem Namen, den die jeweilige Bauart dafuer benutzt -- und es haelt
    einen Payload lauffaehig, der nur den Hairpin-Schluessel kennt.
    """
    n = int((geom or {}).get("turnsPerSlot", 0) or 0)
    if n <= 0:
        n = lagen(geom)
    return max(1, min(400, n))


# ── Die eine Nutgeometrie ─────────────────────────────────────────────────────

def nutgeometrie(geom: dict) -> dict:
    """Nut, Zahn und Leiterquerschnitt -- alles in **Metern**, aus EINER Formel.

    Die Zahlen sind wortgleich die bisherigen; nur stehen sie jetzt an einer
    Stelle. Die Millimeterfassung (fuer die CAD-Erzeugung) steht daneben, damit
    ``ema_freecad`` nicht wieder eine eigene Rechnung braucht.
    """
    n_slots = max(int(geom["slots"]), 1)
    r_si = float(geom["statorID"]) / 2000.0
    r_so = float(geom["statorOD"]) / 2000.0
    tiefe = float(geom["slotDepth"]) / 1000.0
    ratio = float(geom.get("slotWidthRatio", 0.5))
    dtheta = 2.0 * math.pi / n_slots
    breite = max(NUT_MIN_M, r_si * dtheta * ratio)
    zahn = max(0.0, r_si * dtheta - breite)

    n_lagen = lagen(geom)
    leiter_b = max(LEITER_MIN_M, breite - 2 * ISOLIERUNG_M)
    # Die beiden Klemmen (LEITER_MIN_M, LAGE_MIN_M) halten die Rechnung in einem
    # Bereich, in dem sie gilt -- aber sie koennen eine Wicklung ergeben, die
    # NICHT MEHR IN DIE NUT PASST. Gemessen an einer 22-mm-Nut: ab acht Leitern
    # greift LAGE_MIN_M, und die Lagen belegen zusammen 25,2 mm. Das Modell gab
    # dafuer bisher klaglos Kupfermasse, Widerstand und Verluste heraus -- und
    # die Masse lief dabei sogar wieder nach oben, was der einzige sichtbare
    # Hinweis war. Der Rest sah aus wie eine Auslegung.
    #
    # Geklemmt wird weiterhin (eine negative Lagenhoehe waere schlimmer), aber
    # es wird gesagt: ``passt`` und ``ueberfuellt_mm``.
    lage_h = max(LAGE_MIN_M,
                 (tiefe - NUTGRUND_M - (n_lagen + 1) * ISOLIERUNG_M) / n_lagen)
    belegt = n_lagen * lage_h + (n_lagen + 1) * ISOLIERUNG_M + NUTGRUND_M

    # Nutzbarer Nutquerschnitt (nach Abzug der Isolation an beiden Seiten und am
    # Grund). Der Runddraht rechnet mit ihm mal seinem Fuellfaktor.
    a_nutz = max(1e-9, (breite - 2 * ISOLIERUNG_M)
                 * (tiefe - NUTGRUND_M - ISOLIERUNG_M))

    return {
        "n_slots": n_slots, "r_si_m": r_si, "r_so_m": r_so,
        "nut_breite_m": breite, "nut_tiefe_m": tiefe, "zahn_breite_m": zahn,
        "nut_flaeche_m2": breite * tiefe, "nutz_flaeche_m2": a_nutz,
        "n_lagen": n_lagen, "leiter_breite_m": leiter_b, "lage_hoehe_m": lage_h,
        "belegt_tiefe_m": belegt,
        "passt": bool(belegt <= tiefe + 1e-12),
        "ueberfuellt_mm": round(max(0.0, belegt - tiefe) * 1000.0, 3),
        "A_leiter_m2": leiter_b * lage_h,
        # Millimeterfassung fuer die CAD-Erzeugung -- dieselben Zahlen.
        "nut_breite_mm": breite * 1000.0, "nut_tiefe_mm": tiefe * 1000.0,
        "leiter_breite_mm": leiter_b * 1000.0, "lage_hoehe_mm": lage_h * 1000.0,
        "isolierung_mm": ISOLIERUNG_M * 1000.0,
    }


def spulenweite(geom: dict) -> float:
    """Spulenweite als Bogenlaenge auf dem mittleren Nutradius [m]."""
    n_slots = max(int(geom["slots"]), 1)
    poles = max(2 * int(geom["p"]), 2)
    schritt = int(geom.get("coilPitch", 0) or 0)
    if schritt <= 0:
        schritt = max(1, round(n_slots / poles))
    schritt = max(1, min(n_slots - 1, schritt))
    ng = nutgeometrie(geom)
    r_m = ng["r_si_m"] + ng["nut_tiefe_m"] / 2.0
    return 2.0 * math.pi * r_m * schritt / n_slots


# ── Die Wicklung selbst ───────────────────────────────────────────────────────

def wicklung(geom: dict, axial_mm: float) -> dict:
    """Leiterzahl, Querschnitt, Laenge, Kupfervolumen -- je Wicklungsart.

    ``l_leiter_m`` ist die Laenge EINES Leiters durch das Paket plus beide
    Wickelkoepfe. ``n_je_nut`` sind die stromfuehrenden Leiter in einer Nut.
    ``V_kupfer_m3`` ist das gesamte Leitervolumen der Maschine.
    """
    ng = nutgeometrie(geom)
    l_paket = float(axial_mm) / 1000.0
    a = art(geom)

    tau = spulenweite(geom)
    if a == "rundraht":
        n_je_nut = windungen(geom)
        a_leiter = max(1e-10, FUELL_RUNDDRAHT * ng["nutz_flaeche_m2"] / n_je_nut)
        l_wk = WK_RUNDDRAHT_A * tau + WK_RUNDDRAHT_B
        l_wk_geom = l_wk
        fuell = FUELL_RUNDDRAHT
        d_draht = 2.0 * math.sqrt(a_leiter / math.pi)
    else:
        n_je_nut = ng["n_lagen"]
        a_leiter = ng["A_leiter_m2"]
        # Historischer Wert (s. Modulkopf). Er ist der axiale UEBERHANG und
        # nicht die Leiterlaenge im Wickelkopf -- die geht ueber die
        # Spulenweite. ``l_wickelkopf_geom_m`` sagt daneben, was die Geometrie
        # hergibt, damit der Unterschied nicht in einer Zahl verschwindet.
        l_wk = WICKELKOPF_HAIRPIN_M
        l_wk_geom = WK_HAIRPIN_A * tau + WK_HAIRPIN_B
        fuell = n_je_nut * a_leiter / max(ng["nut_flaeche_m2"], 1e-12)
        d_draht = 0.0

    l_leiter = l_paket + 2.0 * l_wk
    v_kupfer = ng["n_slots"] * n_je_nut * a_leiter * l_leiter

    return {
        "art": a, "label": ART_LABEL[a],
        "n_je_nut": n_je_nut, "A_leiter_m2": a_leiter,
        "l_wickelkopf_m": l_wk, "l_wickelkopf_geom_m": l_wk_geom,
        "l_spulenweite_m": tau, "l_leiter_m": l_leiter,
        "wickelkopf_historisch": a == "hairpin",
        "V_kupfer_m3": v_kupfer, "fuellfaktor": fuell,
        "d_draht_m": d_draht,
        "windungen_je_strang": ng["n_slots"] * n_je_nut / 3.0,
        "nut": ng,
    }


def passt(geom: dict) -> tuple:
    """``(passt, ueberfuellung_mm)`` -- passt die Wicklung ueberhaupt in die Nut?

    Getrennt abrufbar, weil das ein **Ausschlussgrund** ist und keine Kennzahl:
    eine Wicklung, die 3,2 mm zu hoch baut, hat keinen Widerstand, den man mit
    einer anderen vergleichen koennte.
    """
    ng = nutgeometrie(geom)
    return bool(ng["passt"]), float(ng["ueberfuellt_mm"])


def r_strang(geom: dict, axial_mm: float, mat: dict) -> float:
    """Strangwiderstand [Ohm] -- alle Leiter eines Strangs in Reihe.

    Dieselbe Rechnung wie bisher in ``ema_thermal.lptn_temperatures``, nur mit
    dem Querschnitt und der Laenge aus ``wicklung`` statt aus einer eigenen
    Kopie: ``R = rho * l * n_slots * n_je_nut / (3 * A)``.
    """
    w = wicklung(geom, axial_mm)
    return (float(mat["rho_el"]) * w["l_leiter_m"] * w["nut"]["n_slots"]
            * w["n_je_nut"] / (3.0 * max(w["A_leiter_m2"], 1e-12)))


def kupfermasse(geom: dict, axial_mm: float, mat: dict) -> float:
    """Kupfermasse [kg] -- aus DEMSELBEN Volumen wie Widerstand und Verluste.

    Vorher stand die Masse in einer eigenen Kopie mit fest zwei Lagen; wer
    ``conductorsPerSlot`` aenderte, bekam neue Verluste, aber die alte Masse.
    """
    return wicklung(geom, axial_mm)["V_kupfer_m3"] * float(mat["density"])


def vergleich(geom: dict, axial_mm: float, mat: dict) -> dict:
    """Beide Wicklungsarten an DERSELBEN Nut nebeneinander.

    Die Zahl, auf die es ankommt, ist nicht der Fuellfaktor allein, sondern das
    Kupfer im Wickelkopf: es traegt Widerstand und Masse und macht kein Moment.
    """
    aus = {"_hinweis": (
        "Der Hairpin-Wickelkopf ist der HISTORISCHE Ueberhang von 18 mm, nicht "
        "die Leiterlaenge; sie stuende bei "
        f"{1000.0 * (WK_HAIRPIN_A * spulenweite(geom) + WK_HAIRPIN_B):.0f} mm. "
        "Wer beide Spalten unbesehen vergleicht, rechnet dem Runddraht einen "
        "Nachteil zu, den er so nicht hat. Der Wert bleibt stehen, weil sein "
        "Aendern jede bestehende PSM-Zahl verschoebe.")}
    for a in ARTEN:
        g = dict(geom, windingType=a)
        w = wicklung(g, axial_mm)
        l_paket = float(axial_mm) / 1000.0
        aus[a] = {
            "label": w["label"],
            "n_je_nut": w["n_je_nut"],
            "A_leiter_mm2": round(w["A_leiter_m2"] * 1e6, 3),
            "fuellfaktor": round(w["fuellfaktor"], 3),
            "l_wickelkopf_mm": round(w["l_wickelkopf_m"] * 1000.0, 1),
            "l_wickelkopf_geometrisch_mm": round(w["l_wickelkopf_geom_m"] * 1000.0, 1),
            "wickelkopf_historisch": w["wickelkopf_historisch"],
            "wickelkopf_anteil_pct": round(
                100.0 * 2 * w["l_wickelkopf_m"] / max(w["l_leiter_m"], 1e-12), 1),
            "R_strang_mOhm": round(r_strang(g, axial_mm, mat) * 1000.0, 3),
            "kupfer_kg": round(kupfermasse(g, axial_mm, mat), 3),
        }
    return aus
