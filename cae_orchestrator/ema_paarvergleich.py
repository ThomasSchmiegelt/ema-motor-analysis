"""Paarvergleich: die Gestaltungsentscheidungen gegeneinanderstellen, BEVOR gezeichnet wird.

Wozu, wenn es die Vorauswahl schon gibt
---------------------------------------

``ema_screen`` faehrt einen Kombinationsraum ab und gibt eine **Rangliste** heraus.
Das beantwortet „welche Variante nehme ich?" -- aber nicht „woran haengt das
ueberhaupt?". Wer eine Maschine auslegt, entscheidet nacheinander ueber wenige
grosse Dinge: Magnetanordnung, Zahl der Hairpins, Werkstoffe, Kuehlung, Durchmesser,
Laenge. Dieses Modul stellt je Achse **jede Option gegen jede** und sagt bei jedem
Paar, welche Kennzahl fuer welche Seite spricht -- und welche sich gar nicht bewegt.

Der zweite, wichtigere Teil ist die **Spannweite je Achse**: um wie viel Prozent
bewegt eine Achse eine Kennzahl ueberhaupt. Das sagt, welche Entscheidung zuerst
ansteht. Eine Achse, die Kt um 3 % bewegt, waehrend eine andere es um 140 % tut,
ist keine Entwurfsentscheidung, sondern eine Feineinstellung.

Kein Sieger, keine Punkte
-------------------------

Es gibt hier **keine Gesamtnote**. Eine Gewichtung ueber Kt, Kosten und Masse ist
eine Zielentscheidung, keine Rechnung -- und ``screen --ziel`` macht sie bereits
offen. Der Paarvergleich zeigt statt dessen je Paar, welche Kennzahlen fuer A und
welche fuer B sprechen, mit der Richtung („gross ist besser" / „klein ist besser")
sichtbar in ``METRIKEN``. Die Wahl bleibt beim Menschen.

Was gerechnet wird -- und was nicht
-----------------------------------

Alles analytisch, Millisekunden je Option: Luftspaltfeld aus
``_analytical_Bgap``, Moment aus ``compute_performance``, Fliehkrafttor aus
``rotor_stress_check``, Massen/Kosten aus ``ema_screen.massen_und_kosten``,
Verluste aus ``ema_thermal.compute_losses`` an EINEM Betriebspunkt, Dauermoment
aus ``ema_thermal.rated_torque``.

**Kein Feldlauf, keine FEM, keine Thermiksimulation.** Drei Grenzen, die man kennen
muss, sonst liest man die Tabelle falsch:

* Die **Kuehlung** wirkt hier ausschliesslich ueber ``COOLING_RATING`` -- eine
  Tabelle von Schubspannungen je Kuehlart, kein gerechneter Waermeuebergang. Sie
  bewegt das Dauermoment und sonst nichts.
* **Nutzahl und Leiterzahl bewegen Kt und B_gap auf dieser Stufe nicht.**
  ``compute_performance`` rechnet psi_pm = p*(2/pi)*B_gap*R_gap*L und kennt weder
  Windungszahl noch Nutzahl. Die Hairpin-Achse ist deshalb eine Achse ueber
  Widerstand, Verlusten und Aufwand -- nicht ueber dem Moment. Das steht so auch
  im Lernspeicher.
* Beim **Durchmesser** wird geometrisch aehnlich skaliert (Stator, Rotor, Welle,
  Nuttiefe und Magnetkoerper mit demselben Faktor), aber der **Luftspalt bleibt
  stehen** -- der ist fertigungsbedingt und skaliert nicht mit. Danach laeuft
  ``ema_screen.einpassen``, damit die Taschen wirklich passen.
* **Flussbarrieren** wirken hier ausschliesslich ueber das weggenommene Eisen
  (Masse, Kosten) und ueber den **Platz im Blech**. Ihre eigentliche Wirkung ist
  magnetisch -- sie lenken den Fluss -- und die kennt erst der Feldlauf;
  ``_analytical_Bgap`` weiss von ihnen nichts. Wer sie hier nach Kt beurteilt,
  beurteilt sie nach der einen Groesse, die sie nicht abbildet.

Verschraubung und Barrieren: was hier NEU geprueft wird
-------------------------------------------------------

Beide schneiden Material aus demselben Blech wie die Magnettaschen, und bis hierher
hat das **niemand nachgemessen** -- die Doku benannte die Luecke ausdruecklich
("a passing gate does not rule out a breakthrough from those"). Ein Luftschlitz oder
eine Wuchtbohrung, die in eine Magnettasche laeuft, fiel erst in FreeCAD auf, nach
40 Sekunden Startzeit.

``ema_rotorcheck.zusatzteile_check`` schliesst das: mit **denselben** Bausteinen wie
das Taschenlayout (der Schlitz ist ein Rechteck, das Bohrloch ein Kreis, beides ein
``Pocket``), also ohne zweite Abstandsformel. Am Beispielprojekt gemessen schneiden
die q-Achsen-Barrieren dort tatsaechlich um 0,23 mm in die Tasche.

Der Befund zaehlt in der Bilanz eines Paares mit ("Platz im Blech"), obwohl er keine
Zahl ist. Ohne das laese sich ein Paar, bei dem die eine Seite durchbricht, als
"0:1 fuer rechts, weil 0,3 kg leichter" -- die Masse ist dort nicht der Punkt.
"""

from __future__ import annotations

import math
from itertools import combinations

import ema_analysis
import ema_thermal
from ema_analysis import _analytical_Bgap, compute_performance
from ema_pipeline import (HAIRPIN_MATS, LAMINATES, MAGNETS,
                          connection_assessment)
from ema_rotorcheck import (rotor_layout_check, rotor_stress_check,
                            zusatzteile_check)
from ema_screen import einpassen, massen_und_kosten, wicklung_moeglich
from ema_topology import TOPOLOGY_LABELS

# Unter dieser relativen Aenderung gilt eine Kennzahl als unbewegt. Auf einer
# analytischen Stufe ist alles darunter Rundung, kein Befund.
GLEICH_UNTER = 0.005

# name -> (Anzeige, Einheit, Richtung, zaehlt_in_der_bilanz)
#
# „zaehlt" trennt die unabhaengigen Kennzahlen von den abgeleiteten: Kt je kg ist
# Kt geteilt durch Masse, und beides steht schon einzeln da. Wer es mitzaehlt,
# gewichtet dieselbe Aussage zweimal.
METRIKEN = {
    "Kt_Nm_per_A":  ("Kt",                  "Nm/A",       "gross", True),
    "T_dauer_Nm":   ("Dauermoment (S1)",    "Nm",         "gross", True),
    "SF_n_max":     ("Sicherheit bei n_max", "-",         "gross", True),
    "P_verlust_W":  ("Verlustleistung",     "W",          "klein", True),
    "gesamt_kg":    ("Masse",               "kg",         "klein", True),
    "kosten_EUR":   ("Kosten",              "EUR",        "klein", True),
    "T_verbind_Nm": ("Welle übertragbar",   "Nm",         "gross", True),
    "B_gap_T":      ("B_gap",               "T",          "gross", False),
    "magnet_kg":    ("Magnetmasse",         "kg",         "klein", False),
    "P_Cu_W":       ("davon Kupfer",        "W",          "klein", False),
    "J_Apmm2":      ("Stromdichte",         "A/mm²",      "klein", False),
    "R_phase_mOhm": ("Phasenwiderstand",    "mOhm",       "klein", False),
    "verbind_ausl": ("Welle Auslastung",    "-",          "klein", False),
    "kt_je_kg":     ("Kt je kg",            "Nm/(A·kg)",  "gross", False),
    "kt_je_EUR":    ("Kt je EUR",           "Nm/(A·EUR)", "gross", False),
}

# Kurznamen fuer die Tabellenkoepfe -- 13 Zeichen je Spalte, sonst rutscht die
# Zeile auseinander und niemand liest sie mehr.
KURZ = {"Kt_Nm_per_A": "Kt [Nm/A]", "T_dauer_Nm": "T_dauer [Nm]",
        "SF_n_max": "SF n_max", "P_verlust_W": "Verlust [W]",
        "gesamt_kg": "Masse [kg]", "kosten_EUR": "Kosten [EUR]",
        "T_verbind_Nm": "Welle [Nm]"}

DURCHMESSER_FAKTOREN = (0.8, 0.9, 1.0, 1.1, 1.2)
LAENGEN_FAKTOREN     = (0.7, 0.85, 1.0, 1.15, 1.3)

KUEHLARTEN = ("natural", "forced", "water", "oil")


def _magformen() -> list:
    from ema_topology import _BUILDERS
    return [k for k in _BUILDERS if k != "custom"]


# ── Die Achsen ────────────────────────────────────────────────────────────────
#
# Jede Achse sagt, WIE eine Option in den Payload kommt. Absichtlich als Funktion
# und nicht als Schluesselname: Durchmesser und Laenge greifen mehrere Felder an,
# und der Blechwerkstoff sitzt gleich zweimal im Payload (Rotor und Stator).

def _setz_geom(schluessel):
    def f(p, wert):
        p["geom"][schluessel] = wert
    return f


def _setz_oben(schluessel):
    def f(p, wert):
        p[schluessel] = wert
    return f


def _setz_blech(p, wert):
    p["rotor_lam"] = wert
    p["stator_lam"] = wert


def _setz_durchmesser(p, wert):
    """Geometrisch aehnlich skalieren -- ausser dem Luftspalt."""
    g = p["geom"]
    basis = float(g["statorOD"])
    f = float(wert) / basis if basis else 1.0
    spalt = (float(g["statorID"]) - float(g["rotorOD"])) / 2.0
    for k in ("statorOD", "rotorOD", "shaftD", "shaftBoreD", "slotDepth",
              "magWidth", "magThick", "magTangLen", "magDist", "magLayerGap"):
        if k in g and isinstance(g[k], (int, float)):
            g[k] = round(float(g[k]) * f, 3)
    g["statorID"] = round(float(g["rotorOD"]) + 2 * spalt, 3)   # Spalt bleibt


def _setz_verschraubung(p, wert):
    """``wert`` = None (keine Verschraubung) oder ein Gewindekuerzel."""
    g = p["geom"]
    g["genBalanceBolts"] = wert is not None
    if wert is not None:
        g["balanceBoltThread"] = wert


def _setz_barrieren(p, wert):
    """``wert`` aus ``("aus", "q", "d", "qd")`` -- q = zwischen den Polen,
    d = in der Polmitte."""
    g = p["geom"]
    g["genFluxBarrierQ"] = "q" in wert
    g["genFluxBarrierD"] = "d" in wert


def _setz_laenge(p, wert):
    p["geom"]["axialLen"] = float(wert)
    p["axial_len"] = float(wert)


ACHSEN = {
    "anordnung": {
        "titel": "Anordnung der Magnete",
        "werte": lambda b: _magformen(),
        "beschriften": lambda w: TOPOLOGY_LABELS.get(w, w),
        "setzen": _setz_geom("magShape"),
    },
    "hairpins": {
        "titel": "Anzahl Hairpins (Leiter je Nut)",
        "werte": lambda b: [2, 4, 6, 8, 10, 12],
        "beschriften": lambda w: f"{w} Leiter/Nut",
        "setzen": _setz_geom("conductorsPerSlot"),
    },
    "magnetwerkstoff": {
        "titel": "Material — Magnet",
        "werte": lambda b: list(MAGNETS),
        "beschriften": lambda w: MAGNETS[w]["label"],
        "setzen": _setz_oben("magnet"),
    },
    "blech": {
        "titel": "Material — Elektroblech (Rotor und Stator)",
        "werte": lambda b: list(LAMINATES),
        "beschriften": lambda w: LAMINATES[w]["label"],
        "setzen": _setz_blech,
    },
    "leiterwerkstoff": {
        "titel": "Material — Leiter",
        "werte": lambda b: list(HAIRPIN_MATS),
        "beschriften": lambda w: HAIRPIN_MATS[w]["label"],
        "setzen": _setz_oben("hairpin_mat"),
    },
    "kuehlung": {
        "titel": "Kühlung",
        "werte": lambda b: list(KUEHLARTEN),
        "beschriften": lambda w: ema_thermal.COOLING_PRESETS.get(w, {}).get("label", w),
        "setzen": _setz_oben("cooling"),
    },
    "wellenverbindung": {
        "titel": "Welle–Blechpaket-Verbindung",
        "werte": lambda b: ["press", "spline", "polygon"],
        "beschriften": lambda w: {"press": "Querpressverband (Schrumpfsitz)",
                                  "spline": "Keilwelle (DIN 5480)",
                                  "polygon": "Polygonprofil P3G"}.get(w, w),
        "setzen": _setz_geom("shaftConnection"),
    },
    "verschraubung": {
        "titel": "Wuchtscheiben-Verschraubung",
        "werte": lambda b: [None, "M4", "M6", "M8", "M12"],
        "beschriften": lambda w: "keine Verschraubung" if w is None
                                 else f"{w} (Anzahl = Polzahl)",
        "setzen": _setz_verschraubung,
    },
    "flussbarrieren": {
        "titel": "Flussbarrieren (Luftschlitze im Rotorblech)",
        "werte": lambda b: ["aus", "q", "d", "qd"],
        "beschriften": lambda w: {"aus": "keine Barrieren",
                                  "q": "q-Achse (zwischen den Polen)",
                                  "d": "d-Achse (Polmitte)",
                                  "qd": "q- und d-Achse"}[w],
        "setzen": _setz_barrieren,
    },
    "durchmesser": {
        "titel": "Durchmesser (geometrisch ähnlich, Luftspalt bleibt)",
        "werte": lambda b: [round(float(b["geom"]["statorOD"]) * f, 1)
                            for f in DURCHMESSER_FAKTOREN],
        "beschriften": lambda w: f"{w:.0f} mm Stator-Außen-Ø",
        "setzen": _setz_durchmesser,
    },
    "laenge": {
        "titel": "Länge (Blechpaket)",
        "werte": lambda b: [round(float(b["geom"].get("axialLen")
                                        or b.get("axial_len") or 80.0) * f, 1)
                            for f in LAENGEN_FAKTOREN],
        "beschriften": lambda w: f"{w:.0f} mm Blechpaket",
        "setzen": _setz_laenge,
    },
}


# ── Eine Option bewerten ──────────────────────────────────────────────────────

def _bewerte(payload: dict, n_max: float, rpm: float, last_nm: float) -> dict:
    """Kennzahlen EINER Option. Rein analytisch, keine Simulation.

    Der Magnetwerkstoff kommt ueber dieselbe Stelle herein wie in der Pipeline:
    ``ema_analysis.Br_NdFeB``/``MU_R_MAG`` sind Modul-Globale und werden
    umgesetzt und im ``finally`` **zurueckgesetzt**. Ohne das waere die
    Magnetwerkstoff-Achse still wirkungslos -- ``_analytical_Bgap`` liest die
    Globale, nicht den Payload.
    """
    geom = payload["geom"]
    axial = float(geom.get("axialLen") or payload.get("axial_len") or 80.0)
    poles = 2 * int(geom["p"])

    if not wicklung_moeglich(int(geom["slots"]), poles):
        return {"ok": False, "grund": "keine symmetrische Drehstromwicklung"}
    lay = rotor_layout_check(geom)
    if not lay["ok"]:
        return {"ok": False, "grund": "Taschenlayout: " + "; ".join(lay["fatal"])[:110]}

    mat  = LAMINATES.get(payload.get("rotor_lam", "m270_35a"), LAMINATES["m270_35a"])
    st   = LAMINATES.get(payload.get("stator_lam", "m270_35a"), LAMINATES["m270_35a"])
    hp   = HAIRPIN_MATS.get(payload.get("hairpin_mat", "cu_etp"), HAIRPIN_MATS["cu_etp"])
    mag  = MAGNETS.get(payload.get("magnet", "ndfeb_n42"), MAGNETS["ndfeb_n42"])
    kuehl = payload.get("cooling", "water")

    stress = rotor_stress_check(geom, mat, {"n_max": n_max})
    if not stress.get("ok", True):
        return {"ok": False,
                "grund": f"Fliehkraft bei {n_max:.0f} 1/min: SF "
                         f"{stress.get('safety_factor', 0):.2f}"}

    br_alt, mu_alt = ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG
    try:
        ema_analysis.Br_NdFeB = float(mag["Br"])
        ema_analysis.MU_R_MAG = float(mag["mu_r"])
        b_gap = _analytical_Bgap(geom)
        perf  = compute_performance(geom, b_gap, axial_mm=axial)
        t_dauer = ema_thermal.rated_torque(geom, axial, kuehl)
        # design_point_losses und NICHT compute_losses(iq, id_): der Kupferanker
        # dort ist Stromdichte x Kupfervolumen und damit **windungszahl- und
        # Kt-unabhaengig**. Mit den rohen dq-Stroemen behauptete die Hairpin-Achse
        # das 28-Fache an Verlusten zwischen 2 und 12 Leitern je Nut -- denn
        # compute_performance normiert auf EINE Windung je Nut, waehrend R_phase
        # mit der Leiterzahl quadratisch waechst. Bei gleichen Amperewindungen ist
        # der Kupferverlust in Wahrheit fast unabhaengig davon; was bleibt, ist der
        # Fuellfaktor, und genau den traegt copper_volume.
        verl = ema_thermal.design_point_losses(geom, axial, rpm, last_nm, perf,
                                               mat, st, hp, mag, kuehl)
    finally:
        ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG = br_alt, mu_alt

    # Welle-Blechpaket-Verbindung: analytisch vorhanden, bisher nur im Bericht.
    # Ohne sie waere die Achse "Verschraubung/Verbindung" eine Achse ohne Kennzahl.
    verb = connection_assessment(geom, mat, n_max, axial, kuehl)

    # Flussbarrieren und Wuchtbohrungen gegen die Magnettaschen. Das Layouttor
    # meldet das als WARNUNG; fuer einen Vergleich von Optionen ist es aber die
    # entscheidende Auskunft -- eine Schraube, die in die Tasche laeuft, ist keine
    # Variante, sondern ein Fehler. Deshalb steht sie hier als eigenes Feld.
    zus = zusatzteile_check(geom)

    mk = massen_und_kosten(payload)
    kt = float(perf["Kt_Nm_per_A"])
    return {
        "ok": True, "grund": "",
        "zusatz_ok": bool(zus["ok"]),
        "zusatz_hinweis": "; ".join(zus["befunde"])[:160],
        "T_verbind_Nm": round(float(verb.get("T_capacity_Nm", 0.0)), 1),
        "verbind_ausl": round(float(verb.get("utilization", 0.0)), 3),
        "Kt_Nm_per_A":  round(kt, 5),
        "B_gap_T":      round(float(b_gap), 4),
        "T_dauer_Nm":   round(float(t_dauer), 1),
        "SF_n_max":     round(float(stress.get("safety_factor", 0.0)), 2),
        "P_verlust_W":  round(float(verl["P_total"]), 1),
        "P_Cu_W":       verl["P_Cu"],
        "J_Apmm2":      verl["J_Apmm2"],
        "R_phase_mOhm": verl["R_phase_mOhm"],
        "gesamt_kg":    mk["gesamt_kg"],
        "magnet_kg":    mk["magnet_kg"],
        "kosten_EUR":   mk["kosten"]["gesamt_EUR"],
        "kt_je_kg":     round(kt / max(mk["gesamt_kg"], 1e-6), 6),
        "kt_je_EUR":    round(kt / max(mk["kosten"]["gesamt_EUR"], 1e-6), 8),
    }


def _option(basis: dict, achse: dict, wert, n_max: float, rpm: float,
            last_nm: float, min_web: float | None) -> dict:
    p = {k: v for k, v in basis.items() if k != "geom"}
    p["geom"] = dict(basis["geom"])
    achse["setzen"](p, wert)

    # Einpassen fuer JEDE Option, nicht nur fuer die geometrischen Achsen. Bei den
    # uebrigen ist es ein Nullschritt; bei Anordnung und Durchmesser entscheidet es
    # darueber, ob eine Option ueberhaupt eine Chance bekommt. Eine Variante, die
    # nur an einem Zehntelmillimeter scheitert, ist keine unbaubare Variante.
    pas = einpassen(p["geom"], None, min_web) if min_web is not None \
        else einpassen(p["geom"], None)
    p["geom"] = pas["geom"]

    erg = {"wert": wert, "name": achse["beschriften"](wert),
           "s_koerper": pas["s_koerper"], "s_lage": pas["s_lage"]}
    if not pas["ok"]:
        return {**erg, "ok": False, "grund": pas["grund"]}
    return {**erg, **_bewerte(p, n_max, rpm, last_nm)}


# ── Paare bilden ──────────────────────────────────────────────────────────────

def _delta(a: dict, b: dict, schluessel: str) -> dict | None:
    va, vb = a.get(schluessel), b.get(schluessel)
    if va is None or vb is None:
        return None
    if abs(va) < 1e-12 and abs(vb) < 1e-12:
        return {"a": va, "b": vb, "pct": 0.0, "gleich": True, "fuer": None}
    nenner = abs(va) if abs(va) > 1e-12 else abs(vb)
    pct = 100.0 * (vb - va) / nenner
    gleich = abs(pct) < 100.0 * GLEICH_UNTER
    _, _, richtung, _ = METRIKEN[schluessel]
    if gleich:
        fuer = None
    elif richtung == "gross":
        fuer = "b" if vb > va else "a"
    else:
        fuer = "b" if vb < va else "a"
    return {"a": va, "b": vb, "pct": round(pct, 2), "gleich": gleich, "fuer": fuer}


def _paar(a: dict, b: dict) -> dict:
    deltas, fuer_a, fuer_b, unbewegt = {}, [], [], []
    for m, (_lab, _e, _r, zaehlt) in METRIKEN.items():
        d = _delta(a, b, m)
        if d is None:
            continue
        deltas[m] = d
        if not zaehlt:
            continue
        if d["gleich"]:
            unbewegt.append(m)
        elif d["fuer"] == "a":
            fuer_a.append(m)
        else:
            fuer_b.append(m)

    # „Platz im Blech" ist keine Zahl und steht deshalb nicht in METRIKEN -- in der
    # Bilanz muss es trotzdem zaehlen. Sonst liest sich ein Paar, bei dem die eine
    # Seite mit ihrem Luftschlitz in die Magnettasche laeuft, als "0:1 fuer die
    # rechte Seite, weil sie 0,3 kg leichter ist". Die Masse ist dort nicht der
    # Punkt; der Durchbruch ist es.
    za, zb = a.get("zusatz_ok", True), b.get("zusatz_ok", True)
    if za != zb:
        (fuer_a if za else fuer_b).append("_zusatz")
    return {"a": a["name"], "b": b["name"], "a_wert": a["wert"], "b_wert": b["wert"],
            "deltas": deltas, "spricht_fuer_a": fuer_a, "spricht_fuer_b": fuer_b,
            "unbewegt": unbewegt, "zusatz_a": za, "zusatz_b": zb,
            "bilanz": f"{len(fuer_a)}:{len(fuer_b)}"}


def _spannweite(optionen: list) -> dict:
    """Um wie viel bewegt diese Achse jede Kennzahl? Der eigentliche Befund."""
    gut = [o for o in optionen if o.get("ok")]
    aus = {}
    for m in METRIKEN:
        werte = [o[m] for o in gut if o.get(m) is not None]
        if len(werte) < 2:
            continue
        lo, hi = min(werte), max(werte)
        if abs(lo) < 1e-12:
            continue
        aus[m] = {"min": lo, "max": hi, "spanne_pct": round(100.0 * (hi - lo) / abs(lo), 1)}
    return aus


def vergleiche(basis: dict, achsen: list | None = None, n_max: float | None = None,
               rpm: float | None = None, last_nm: float | None = None,
               min_web: float | None = None) -> dict:
    """Alle Achsen durchspielen und je Achse jede Option gegen jede stellen."""
    if not basis.get("geom"):
        raise ValueError("Der Paarvergleich braucht einen Payload mit geom.")
    namen = achsen or list(ACHSEN)
    unbekannt = [n for n in namen if n not in ACHSEN]
    if unbekannt:
        raise ValueError(f"Unbekannte Achse(n): {', '.join(unbekannt)}. "
                         f"Bekannt: {', '.join(ACHSEN)}")

    ziel = basis.get("target") or {}
    n_max = float(n_max or ziel.get("n_max") or 12000.0)
    rpm = float(rpm or basis.get("rpm_from") or 5000.0)
    # EIN gemeinsamer Betriebspunkt fuer alle Optionen. Jede Option an IHREM eigenen
    # Dauermoment zu rechnen waere kein Vergleich -- dann stuende links eine andere
    # Frage als rechts.
    last_nm = float(last_nm or basis.get("load_nm") or 100.0)

    aus = {}
    for name in namen:
        achse = ACHSEN[name]
        werte = achse["werte"](basis)
        optionen = [_option(basis, achse, w, n_max, rpm, last_nm, min_web)
                    for w in werte]
        gut = [o for o in optionen if o.get("ok")]
        aus[name] = {
            "titel": achse["titel"],
            "optionen": optionen,
            "brauchbar": len(gut), "geprueft": len(optionen),
            "paare": [_paar(a, b) for a, b in combinations(gut, 2)],
            "spannweite": _spannweite(optionen),
        }

    # Welche Achse bewegt welche Kennzahl am staerksten -- die Reihenfolge der
    # Entscheidungen faellt hier heraus, nicht aus einer Meinung.
    rangfolge = {}
    for m in METRIKEN:
        eintraege = [(name, a["spannweite"][m]["spanne_pct"])
                     for name, a in aus.items() if m in a["spannweite"]]
        eintraege.sort(key=lambda t: -t[1])
        if eintraege:
            rangfolge[m] = eintraege

    return {"n_max": n_max, "rpm_betriebspunkt": rpm, "last_nm": last_nm,
            "basis_geom": dict(basis["geom"]),
            "achsen": aus, "rangfolge": rangfolge,
            "hinweis": ("Analytischer Paarvergleich — kein Feldlauf, keine FEM, keine "
                        "Thermiksimulation. Die Kühlung wirkt nur über die Tabelle "
                        "COOLING_RATING, und Nutzahl/Leiterzahl bewegen Kt auf dieser "
                        "Stufe nicht. FLUSSBARRIEREN wirken hier ausschliesslich über "
                        "das weggenommene Eisen (Masse, Kosten) und über den Platz im "
                        "Blech — ihre magnetische Wirkung kennt erst der Feldlauf. "
                        "Was hier oben steht, muss danach gerechnet werden.")}


# ── Textausgabe ───────────────────────────────────────────────────────────────

def als_text(erg: dict, paare: bool = True, max_paare: int = 10) -> str:
    z = [f"Paarvergleich — gemeinsamer Betriebspunkt "
         f"{erg['last_nm']:.0f} Nm @ {erg['rpm_betriebspunkt']:.0f} 1/min, "
         f"Fliehkrafttor bei {erg['n_max']:.0f} 1/min", ""]

    z.append("WAS BEWEGT WAS  —  Spannweite über die Optionen EINER Achse, in %.")
    z.append("Die oberste Zeile je Kennzahl ist die Entscheidung, die zuerst ansteht.")
    z.append(f"  {'Kennzahl':<26} {'stärkste Achse':<18} {'Spanne':>8}   danach")
    for m, eintraege in erg["rangfolge"].items():
        lab, einheit, _r, zaehlt = METRIKEN[m]
        if not zaehlt:
            continue
        erste = eintraege[0]
        rest = ", ".join(f"{n} {p:.0f} %" for n, p in eintraege[1:4])
        z.append(f"  {(lab + ' [' + einheit + ']')[:26]:<26} {erste[0][:18]:<18} "
                 f"{erste[1]:>7.0f} %   {rest}")
    z.append("")

    for name, a in erg["achsen"].items():
        z.append(f"── {a['titel']}  ({a['brauchbar']} von {a['geprueft']} baubar)")
        kopf = f"  {'Option':<34}"
        for m, (lab, einheit, _r, zaehlt) in METRIKEN.items():
            if zaehlt:
                kopf += f"{KURZ.get(m, lab)[:12]:>13}"
        z.append(kopf)
        for o in a["optionen"]:
            if not o.get("ok"):
                z.append(f"  {o['name'][:34]:<34}  ✗ {o.get('grund', '')[:70]}")
                continue
            zeile = f"  {o['name'][:34]:<34}"
            for m, (_lab, _e, _r, zaehlt) in METRIKEN.items():
                if zaehlt:
                    zeile += f"{o[m]:>13.4g}"
            z.append(zeile)
            # Der Zusatzteil-Befund steht UNTER der Zeile und nicht als Spalte: er
            # ist kein Messwert, sondern ein Ausschlussgrund, und er muss im Klartext
            # dastehen. Das Layouttor meldet ihn nur als Warnung -- fuer die Wahl
            # zwischen zwei Optionen ist er aber das Entscheidende.
            if not o.get("zusatz_ok", True):
                z.append(f"        ⚠ {o.get('zusatz_hinweis', '')}")
        if a["spannweite"]:
            unbewegt = [METRIKEN[m][0] for m, s in a["spannweite"].items()
                        if METRIKEN[m][3] and s["spanne_pct"] < 100 * GLEICH_UNTER]
            if unbewegt:
                z.append(f"    bewegt NICHT: {', '.join(unbewegt)}")
        if paare and a["paare"]:
            z.append(f"    Paare ({len(a['paare'])}, gezeigt {min(max_paare, len(a['paare']))}):")
            for p in a["paare"][:max_paare]:
                def _lab(m):
                    return ("Platz im Blech (kein Durchbruch)" if m == "_zusatz"
                            else METRIKEN[m][0])
                fa = ", ".join(_lab(m) for m in p["spricht_fuer_a"]) or "—"
                fb = ", ".join(_lab(m) for m in p["spricht_fuer_b"]) or "—"
                z.append(f"      {p['a'][:24]:<24} vs {p['b'][:24]:<24} {p['bilanz']:>5}")
                z.append(f"          für links:  {fa}")
                z.append(f"          für rechts: {fb}")
        z.append("")

    z.append(erg["hinweis"])
    return "\n".join(z)
