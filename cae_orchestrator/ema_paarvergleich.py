"""Paarvergleich: die Gestaltungsentscheidungen gegeneinanderstellen, BEVOR gezeichnet wird.

Wozu, wenn es die Vorauswahl schon gibt
---------------------------------------

``ema_screen`` faehrt einen Kombinationsraum ab und gibt eine **Rangliste** heraus.
Das beantwortet „welche Variante nehme ich?" -- aber nicht „woran haengt das
ueberhaupt?". Wer eine Maschine auslegt, entscheidet nacheinander ueber wenige
grosse Dinge: Magnetanordnung, V-Oeffnungswinkel, Zahl der Hairpins, Werkstoffe,
Kuehlung, Durchmesser, Laenge, Wellendurchmesser. Dieses Modul stellt je Achse
**jede Option gegen jede** und sagt bei jedem
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
* **Kt ist reines MAGNETmoment** -- und deshalb allein untauglich, um Anordnungen
  zu vergleichen (s. den naechsten Abschnitt).
* Beim **Durchmesser** wird geometrisch aehnlich skaliert (Stator, Rotor, Welle,
  Nuttiefe und Magnetkoerper mit demselben Faktor), aber der **Luftspalt bleibt
  stehen** -- der ist fertigungsbedingt und skaliert nicht mit. Danach laeuft
  ``ema_screen.einpassen``, damit die Taschen wirklich passen.
* **Flussbarrieren** wirken hier ausschliesslich ueber das weggenommene Eisen
  (Masse, Kosten) und ueber den **Platz im Blech**. Ihre eigentliche Wirkung ist
  magnetisch -- sie lenken den Fluss -- und die kennt erst der Feldlauf;
  ``_analytical_Bgap`` weiss von ihnen nichts. Wer sie hier nach Kt beurteilt,
  beurteilt sie nach der einen Groesse, die sie nicht abbildet.

Das Reluktanzmoment: warum Kt die Anordnungen NICHT unterscheidet
----------------------------------------------------------------

``compute_performance`` gibt ``Kt = 1.5*p*psi_pm`` heraus -- das Moment aus dem
Magnetfluss. Der zweite Momentanteil, das **Reluktanzmoment** aus der Anisotropie
des Rotors, kommt darin nicht vor. Genau daran unterscheiden sich aber V,
asymmetrisches V, U, Delta, Doppel-V und PMa-SynRM in erster Linie; ueber Kt
verglichen sahen sie sich aehnlicher, als sie sind, und die reluktanzgetriebenen
Formen kamen als die schwaechsten heraus.

Zwei Aenderungen schliessen das, beide belegt in ``ema_referenz``:

1. ``ema_analysis.estimate_saliency`` war **topologieblind** -- sie las nur
   Luftspalt und Magnetdicke. Sie passt ihr Ergebnis jetzt in das recherchierte
   **Band je Anordnung** ein: das Band sagt, wie weit eine Form ueberhaupt
   getrieben werden kann, die Geometrie sagt, wo in ihrem Band dieser Rotor liegt.
2. Neue **gezaehlte** Kennzahl ``I_s_A``: der Strangstrom, den diese Option fuer
   den gemeinsamen Betriebspunkt braucht (MTPA ueber ``estimate_dq_currents``,
   also mit Reluktanzmoment). Dort -- und nur dort -- zeigt sich der Nutzen.
   Daneben ``xi_LqLd`` und ``T_rel_pct`` als Einordnung, beide ungezaehlt.

Der Beleg, an dem das haengt (gleicher Stator, gleiche Laenge, gleiches Moment):
Speiche und Doppel-V liefern beide ~400 Nm, die Speiche braucht 393,9 A, das
Doppel-V 291,8 A. Ueber Kt allein waere dieser Unterschied unsichtbar geblieben.

**Wo I_s aufhoert, eine Zahl zu sein:** am Umrichter-Limit
(``INVERTER_I_MAX``) wird der Strom gedeckelt -- die Option erreicht das
Sollmoment dann gar nicht, und zwei gedeckelte Optionen sehen mit demselben Wert
gleich aus. Solche Zeilen tragen deshalb eine eigene Warnung.

Die Bauverhaeltnisse: wo hoert das Vorbild auf
----------------------------------------------

Durchmesser, Laenge und Welle koennen den Entwurf beliebig weit von allem
wegtragen, was je gebaut wurde. Jede Option wird darum gegen die Verhaeltnisse
von sieben abgerufenen Maschinen gehalten (``ema_referenz.BAUBAND``) -- Rotor/
Stator, Wellenbohrung/Rotor, Laenge/Durchmesser, Luftspalt. Das ist **kein Tor**:
ausserhalb heisst nicht falsch, sondern nur, dass die Vorbilder dort keine
Auskunft geben. Was schon fuer die Grundgeometrie gilt, steht einmal am Kopf;
unter einer Option steht nur, was diese Option neu herbeifuehrt.

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
import ema_asm
import ema_maschinenart
import ema_wicklung
import ema_referenz
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
    # Der Strom fuer den GEMEINSAMEN Betriebspunkt -- die einzige gezaehlte Kennzahl,
    # in der sich das Reluktanzmoment ueberhaupt zeigt. Kt ist reines Magnetmoment
    # (``compute_performance`` rechnet 1.5*p*psi_pm), und genau daran unterscheiden
    # sich V, U, Delta, Doppel-V und PMa-SynRM NICHT nennenswert. Wer weniger Strom
    # fuer dasselbe Moment braucht, braucht weniger Umrichter und macht weniger
    # Kupferverlust -- das ist der Unterschied, den die Anordnung wirklich macht.
    "I_s_A":        ("Strangstrom @ Punkt", "A",          "klein", True),
    "B_gap_T":      ("B_gap",               "T",          "gross", False),
    "xi_LqLd":      ("Salienz Lq/Ld",       "-",          "gross", False),
    "T_rel_pct":    ("davon Reluktanzmoment", "%",        "gross", False),
    "magnet_kg":    ("Magnetmasse",         "kg",         "klein", False),
    # Nur die ASM hat sie -- bei jeder anderen Art fehlen sie, und ``_delta``
    # ueberspringt fehlende Kennzahlen. Genau so soll es sein: eine 0 stuende da
    # wie ein Messwert, das Fehlen steht da wie das, was es ist.
    "mag_anteil":   ("Magnetisierungsanteil an I_s", "-", "klein", False),
    "schlupf_pct":  ("Schlupf",              "%",          "klein", False),
    "P_Kaefig_W":   ("davon Läuferkäfig",    "W",          "klein", False),
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
        "T_verbind_Nm": "Welle [Nm]", "I_s_A": "I_s [A]"}

DURCHMESSER_FAKTOREN = (0.8, 0.9, 1.0, 1.1, 1.2)
LAENGEN_FAKTOREN     = (0.7, 0.85, 1.0, 1.15, 1.3)
WELLEN_FAKTOREN      = (0.7, 0.85, 1.0, 1.15, 1.3)

# V-Oeffnungswinkel. Die Reihe umfasst den recherchierten Kompromiss (115 Grad)
# nach beiden Seiten -- Momentdichte steigt mit dem Winkel, Reluktanzmoment faellt,
# es gibt also ein Optimum und keine Richtung (``ema_referenz.V_OEFFNUNG_GRAD``).
V_WINKEL = (90.0, 105.0, 115.0, 130.0, 145.0)

# Welche Anordnungen ``magAngle`` ueberhaupt lesen. Bei den uebrigen (Balken,
# Oberflaeche, Speiche) ist die Achse kein schwacher Befund, sondern gar keiner --
# und "bewegt NICHT" waere dort eine irrefuehrende Auskunft.
V_FAMILIE = ("v", "vasym", "u", "vv", "delta", "pmasynrm")

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


def _setz_welle(p, wert):
    """Nur die Welle -- Rotor und Stator bleiben stehen.

    Das ist der Punkt der Achse: der Wellendurchmesser ist eine eigene
    Entscheidung und nicht der Skalierungsfaktor des Durchmessers. Eine
    vorhandene Hohlbohrung wird mitskaliert, damit die Wandstaerke der Welle
    ihr Verhaeltnis behaelt.
    """
    g = p["geom"]
    alt_d = float(g["shaftD"])
    g["shaftD"] = round(float(wert), 3)
    bohr = float(g.get("shaftBoreD") or 0.0)
    if bohr > 0 and alt_d > 0:
        g["shaftBoreD"] = round(bohr * float(wert) / alt_d, 3)


def _setz_laenge(p, wert):
    p["geom"]["axialLen"] = float(wert)
    p["axial_len"] = float(wert)


ACHSEN = {
    # Die erste aller Entscheidungen: woher kommt der Luftspaltfluss ueberhaupt.
    # Sie steht vorn, weil sie ueber die Bedeutung fast aller uebrigen Achsen
    # entscheidet -- eine Maschine ohne Magnete hat keine Magnetanordnung, keinen
    # Magnetwerkstoff und keinen V-Oeffnungswinkel.
    "maschinenart": {
        "titel": "Maschinenart (woher der Luftspaltfluss kommt)",
        "werte": lambda b: list(ema_maschinenart.ARTEN),
        "beschriften": lambda w: ema_maschinenart.LABELS.get(w, w),
        "setzen": _setz_geom("machineType"),
    },
    "anordnung": {
        "titel": "Anordnung der Magnete",
        "werte": lambda b: _magformen(),
        "beschriften": lambda w: TOPOLOGY_LABELS.get(w, w),
        "setzen": _setz_geom("magShape"),
        "braucht_magnete": True,
    },
    # Wicklungsart. Sie steht neben der Leiterzahl und nicht in ihr: die Zahl
    # der Leiter je Nut heisst beim Hairpin „Lagen" und beim Runddraht
    # „Windungen", und beide Bauarten unterscheiden sich in drei Groessen, die
    # die Leiterzahl nicht ausdrueckt -- Nutfuellfaktor, Wickelkopflaenge und
    # Leiterquerschnitt (s. ``ema_wicklung``).
    "wicklungsart": {
        "titel": "Wicklungsart (Hairpin oder Runddraht)",
        "werte": lambda b: list(ema_wicklung.ARTEN),
        "beschriften": lambda w: ema_wicklung.ART_LABEL.get(w, w),
        "setzen": _setz_geom("windingType"),
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
        "braucht_magnete": True,
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
    "v_oeffnung": {
        "titel": ("V-Öffnungswinkel (nur V-/U-/Delta-/Doppel-V-/PMa-SynRM-Formen; "
                  "Literatur-Kompromiss 115°)"),
        "werte": lambda b: list(V_WINKEL),
        "beschriften": lambda w: (f"{w:.0f}° Öffnung"
                                  + (" (Literatur-Kompromiss)"
                                     if abs(w - ema_referenz.V_OEFFNUNG_GRAD["kompromiss"]) < 1e-6
                                     else "")),
        "setzen": _setz_geom("magAngle"),
        "braucht_magnete": True,
    },
    "wellendurchmesser": {
        "titel": "Wellendurchmesser (Rotor und Stator bleiben)",
        "werte": lambda b: [round(float(b["geom"]["shaftD"]) * f, 1)
                            for f in WELLEN_FAKTOREN],
        "beschriften": lambda w: f"{w:.0f} mm Welle-Ø",
        "setzen": _setz_welle,
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
    """Kennzahlen EINER Option -- Weiche nach Maschinenart.

    Die Verzweigung steht hier und nicht in den einzelnen Kennzahlen, weil eine
    Maschine ohne Magnete nicht „dieselbe Rechnung mit Br=0" ist: sie hat einen
    anderen Magnetkreis, eine andere Stromaufteilung und eine andere kritische
    Stelle im Laeuferblech. Eine nicht getragene Art wird als **unbaubare
    Option mit Begruendung** zurueckgegeben, nicht als Ausnahme -- sonst risse
    eine einzige nicht getragene Art den ganzen Vergleich ab, und die Achse
    „Maschinenart" koennte ihren eigenen Ausbaustand nicht zeigen.
    """
    art = ema_maschinenart.art_code(payload)
    try:
        ema_maschinenart.pruefe_stufe(art, "analytisch")
    except ema_maschinenart.ArtNichtUnterstuetzt as e:
        return {"ok": False, "grund": str(e)}
    if art == "asm":
        return _bewerte_asm(payload, n_max, rpm, last_nm)
    return _bewerte_pmsm(payload, n_max, rpm, last_nm)


def _bewerte_asm(payload: dict, n_max: float, rpm: float, last_nm: float) -> dict:
    """Kennzahlen einer ASM-Option -- Kaefiglaeufer, analytisch (``ema_asm``).

    Dieselben Kennzahlen, dieselben Einheiten, derselbe Betriebspunkt wie bei der
    PSM -- sonst waere die Achse „Maschinenart" kein Vergleich. Drei Dinge sind
    zwangslaeufig anders:

    * **``rotor_layout_check`` entfaellt.** Es prueft Magnettaschen; die gibt es
      hier nicht. An seine Stelle tritt ``ema_asm.steg_check`` (Steg ueber der
      Kaefignut). Die Bohrungs-Ringspannung (``rotor_stress_check``) gilt
      unveraendert weiter -- sie ist reine Ringformel.
    * **``einpassen`` entfaellt** (im Aufrufer): es passt Magnetkoerper ein.
    * **I_s traegt den Magnetisierungsstrom mit.** Das ist der eigentliche
      Unterschied und die Kennzahl, in der er sichtbar wird.
    """
    geom  = payload["geom"]
    axial = float(geom.get("axialLen") or payload.get("axial_len") or 80.0)
    poles = 2 * int(geom["p"])

    if not wicklung_moeglich(int(geom["slots"]), poles):
        return {"ok": False, "grund": "keine symmetrische Drehstromwicklung"}

    mat  = LAMINATES.get(payload.get("rotor_lam", "m270_35a"), LAMINATES["m270_35a"])
    st   = LAMINATES.get(payload.get("stator_lam", "m270_35a"), LAMINATES["m270_35a"])
    hp   = HAIRPIN_MATS.get(payload.get("hairpin_mat", "cu_etp"), HAIRPIN_MATS["cu_etp"])
    kuehl = payload.get("cooling", "water")

    kf = ema_asm.kaefig(geom, axial)
    if kf["eng"]:
        return {"ok": False,
                "grund": (f"Kein Platz fuer den Kaefig: zwischen Steg und Joch "
                          f"bleiben {kf['nutraum_mm']:.1f} mm")}

    stress = rotor_stress_check(geom, mat, {"n_max": n_max})
    if not stress.get("ok", True):
        return {"ok": False,
                "grund": f"Fliehkraft bei {n_max:.0f} 1/min: SF "
                         f"{stress.get('safety_factor', 0):.2f}"}
    steg = ema_asm.steg_check(geom, axial, mat, n_max)
    if not steg["ok"]:
        return {"ok": False,
                "grund": (f"Steg ueber der Kaefignut bei {n_max:.0f} 1/min: SF "
                          f"{steg['safety_factor']:.2f}")}

    bp   = ema_asm.betriebspunkt(geom, axial, rpm, last_nm)
    verl = ema_asm.verluste(geom, axial, rpm, last_nm, bp, mat, st, hp, kuehl)
    t_dauer = ema_asm.dauermoment(geom, axial, kuehl, bp)
    verb = connection_assessment(geom, mat, n_max, axial, kuehl)
    mk   = ema_asm.massen_und_kosten(payload)
    kt   = float(bp["Kt_Nm_per_A"])

    return {
        "ok": True, "grund": "",
        # Luftschlitze und Wuchtbohrungen gegen Magnettaschen zu pruefen ergibt
        # ohne Taschen keinen Sinn; die Kaefignut ist ueber steg_check erfasst.
        "zusatz_ok": True,
        "zusatz_hinweis": "",
        "T_verbind_Nm": round(float(verb.get("T_capacity_Nm", 0.0)), 1),
        "verbind_ausl": round(float(verb.get("utilization", 0.0)), 3),
        "Kt_Nm_per_A":  round(kt, 5),
        "I_s_A":        float(bp["I_s_A"]),
        "strom_limit":  bool(bp["strom_limit"]),
        # Der Kaefiglaeufer ist magnetisch glatt: keine Salienz, kein
        # Reluktanzmoment. xi steht als 1.0 da (eine Aussage), T_rel_pct fehlt
        # ganz (die Groesse ist gegen psi_pm definiert und existiert hier nicht).
        "xi_LqLd":      1.0,
        "mag_anteil":   float(bp["mag_anteil"]),
        "schlupf_pct":  float(bp["schlupf_pct"]),
        "P_Kaefig_W":   float(verl["P_Kaefig"]),
        "B_gap_T":      float(bp["B_m_T"]),
        "T_dauer_Nm":   round(float(t_dauer), 1),
        "SF_n_max":     round(min(float(stress.get("safety_factor", 0.0)),
                                  float(steg["safety_factor"])), 2),
        "P_verlust_W":  round(float(verl["P_total"]), 1),
        "P_Cu_W":       verl["P_Cu"],
        "J_Apmm2":      verl["J_Apmm2"],
        "R_phase_mOhm": verl["R_phase_mOhm"],
        "gesamt_kg":    mk["gesamt_kg"],
        "magnet_kg":    0.0,
        "kosten_EUR":   mk["kosten"]["gesamt_EUR"],
        "kt_je_kg":     round(kt / max(mk["gesamt_kg"], 1e-6), 6),
        "kt_je_EUR":    round(kt / max(mk["kosten"]["gesamt_EUR"], 1e-6), 8),
    }


def _bewerte_pmsm(payload: dict, n_max: float, rpm: float, last_nm: float) -> dict:
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
        # Salienz und der Strom, den DIESE Anordnung fuer den gemeinsamen
        # Betriebspunkt braucht. ``estimate_dq_currents`` faehrt MTPA, nutzt also
        # das Reluktanzmoment -- ohne diese beiden Zeilen verglich der
        # Paarvergleich V, U, Delta und Doppel-V ueber Kt, und Kt ist reines
        # Magnetmoment.
        xi = ema_analysis.estimate_saliency(geom)
        iq, id_ = ema_analysis.estimate_dq_currents(geom, rpm, last_nm,
                                                    b_gap_t=b_gap)
        i_s = math.hypot(iq, id_)
        # Am Umrichter-Limit ist I_s KEINE vergleichbare Zahl mehr: der Strom wird
        # dort gedeckelt, also erreicht die Option das Sollmoment gar nicht -- und
        # zwei gedeckelte Optionen sehen mit denselben 800 A gleich aus, obwohl die
        # eine 900 und die andere 1500 braeuchte. Das muss als Befund dastehen,
        # nicht als Messwert.
        am_limit = i_s >= 0.999 * ema_analysis.INVERTER_I_MAX
        # Anteil des Reluktanzmoments am Sollmoment. Der Magnetanteil ist exakt
        # 1.5*p*psi_pm*i_q; das Gesamtmoment am zurueckgegebenen Arbeitspunkt ist
        # per Konstruktion das Sollmoment einschliesslich des Zuschlags, den
        # ``estimate_dq_currents`` aufschlaegt -- deshalb steht der als benannte
        # Konstante dort und wird hier gelesen statt nachgebaut.
        t_soll = last_nm + ema_analysis.DQ_TORQUE_MARGIN_NM
        t_mag = 1.5 * int(geom["p"]) * float(perf["psi_pm_Wb"]) * iq
        t_rel_pct = max(0.0, min(95.0, 100.0 * (1.0 - t_mag / max(t_soll, 1e-9))))
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
        "I_s_A":        round(float(i_s), 1),
        "strom_limit":  bool(am_limit),
        "xi_LqLd":      round(float(xi), 2),
        "T_rel_pct":    round(float(t_rel_pct), 1),
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


def _bandhinweise(optionen: list, basis_geom: dict) -> None:
    """``band_hinweis`` je Option -- aber nur, was diese Achse WIRKLICH bewegt.

    Der ungefilterte Befund steht sonst wortgleich unter jeder Zeile jeder Achse
    (die Grundgeometrie verletzt ihn ja schon), und dann liest ihn niemand mehr.
    Was schon fuer die Grundgeometrie gilt, gehoert einmal an den Kopf; unter die
    Option gehoert nur, was diese Option neu herbeifuehrt.
    """
    vom_start = set(ema_referenz.bauband_pruefen(basis_geom))
    for o in optionen:
        neu = [h for h in o.get("band_alle", []) if h not in vom_start]
        o["band_hinweis"] = "; ".join(neu)
        o.pop("band_alle", None)


def _option(basis: dict, achse: dict, wert, n_max: float, rpm: float,
            last_nm: float, min_web: float | None) -> dict:
    p = {k: v for k, v in basis.items() if k != "geom"}
    p["geom"] = dict(basis["geom"])
    achse["setzen"](p, wert)

    # Einpassen fuer JEDE Option, nicht nur fuer die geometrischen Achsen. Bei den
    # uebrigen ist es ein Nullschritt; bei Anordnung und Durchmesser entscheidet es
    # darueber, ob eine Option ueberhaupt eine Chance bekommt. Eine Variante, die
    # nur an einem Zehntelmillimeter scheitert, ist keine unbaubare Variante.
    #
    # ``einpassen`` passt **Magnetkoerper** ein. Bei einer Maschine ohne Magnete
    # gibt es nichts einzupassen -- und schlimmer: die geerbten Taschenmasse
    # koennten die Option verwerfen, obwohl an ihr gar keine Tasche sitzt. Fuer
    # magnetlose Arten entfaellt der Schritt deshalb ausdruecklich.
    if ema_maschinenart.hole(ema_maschinenart.art_code(p)).hat_magnete:
        pas = einpassen(p["geom"], None, min_web) if min_web is not None \
            else einpassen(p["geom"], None)
        p["geom"] = pas["geom"]
    else:
        pas = {"ok": True, "geom": p["geom"], "grund": "",
               "s_koerper": 0.0, "s_lage": 0.0}

    erg = {"wert": wert, "name": achse["beschriften"](wert),
           "s_koerper": pas["s_koerper"], "s_lage": pas["s_lage"],
           # Kein Tor, nur eine Einordnung: liegt diese Option noch in dem Bereich,
           # in dem die abgerufenen Traktionsmaschinen tatsaechlich gebaut wurden?
           # Wichtig gerade fuer Durchmesser, Laenge und Welle, wo die Achse den
           # Entwurf beliebig weit von jedem Vorbild wegtragen kann.
           "band_alle": ema_referenz.bauband_pruefen(p["geom"])}
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

    basis_art = ema_maschinenart.hole(ema_maschinenart.art_code(basis))

    aus = {}
    for name in namen:
        achse = ACHSEN[name]
        # Eine Achse ueber die Magnetanordnung an einer Maschine ohne Magnete ist
        # kein schwacher Befund, sondern gar keiner -- alle Optionen kaemen mit
        # denselben Zahlen heraus und die Tabelle behauptete „macht keinen
        # Unterschied". Sie wird darum benannt und uebersprungen.
        if achse.get("braucht_magnete") and not basis_art.hat_magnete:
            aus[name] = {
                "titel": achse["titel"],
                "hinweis": (f"{basis_art.label} hat keine Permanentmagnete — diese "
                            f"Achse ist hier ohne Bedeutung und wird nicht "
                            f"gerechnet."),
                "optionen": [], "brauchbar": 0, "geprueft": 0,
                "paare": [], "spannweite": {},
            }
            continue
        werte = achse["werte"](basis)
        optionen = [_option(basis, achse, w, n_max, rpm, last_nm, min_web)
                    for w in werte]
        _bandhinweise(optionen, basis["geom"])
        gut = [o for o in optionen if o.get("ok")]
        form = str(basis["geom"].get("magShape", "v"))
        hinweis = ""
        if name == "maschinenart":
            hinweis = (
                "Zwei Zahlen stehen hier NICHT auf gleicher Grundlage, und das ist "
                "keine Ungenauigkeit, sondern der Unterschied selbst: das "
                "Luftspaltfeld der PSM ist durch die Magnete FESTGELEGT "
                "(_analytical_Bgap aus Br und magThick), das der ASM wird "
                "EINGESTELLT (Zielwert "
                f"{ema_asm.B_ZIEL_T:.2f} T, ueber den Magnetisierungsstrom). "
                "Ob dieser Strom auch aufzubringen ist, sagt die Spalte I_s und "
                "die Warnung am Umrichter-Limit — sonst waere das Feld geschenkt. "
                "Der Preis dafuer steht daneben: I_s traegt den "
                "Magnetisierungsstrom dauernd mit, und der Schlupfverlust faellt "
                "im Laeufer an, also an der thermisch schlechtesten Stelle.")
        if name == "v_oeffnung" and form not in V_FAMILIE:
            hinweis = (f"Die Grundform ist „{TOPOLOGY_LABELS.get(form, form)}“ — sie "
                       f"liest magAngle gar nicht. Diese Achse ist hier ohne Bedeutung, "
                       f"nicht ohne Wirkung.")
        aus[name] = {
            "titel": achse["titel"],
            "hinweis": hinweis,
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
            "band_basis": ema_referenz.bauband_pruefen(basis["geom"]),
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

    if erg.get("band_basis"):
        z.append("Die Grundgeometrie liegt schon ausserhalb der Vorbilder bei: "
                 + "; ".join(erg["band_basis"])
                 + ".  [recherchiert, kein Tor — s. ema_referenz]")
        z.append("")

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
        if a.get("hinweis"):
            z.append(f"    ⓘ {a['hinweis']}")
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
            if o.get("strom_limit"):
                z.append(f"        ⚠ Strom am Umrichter-Limit "
                         f"({ema_analysis.INVERTER_I_MAX:.0f} A bei 1 Wdg/Nut) — "
                         f"diese Option erreicht {erg['last_nm']:.0f} Nm dort NICHT; "
                         f"I_s ist gedeckelt und nicht vergleichbar")
            if o.get("band_hinweis"):
                z.append(f"        ⓘ neu gegenüber der Grundgeometrie: "
                         f"{o['band_hinweis']} [recherchiert, kein Tor]")
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
