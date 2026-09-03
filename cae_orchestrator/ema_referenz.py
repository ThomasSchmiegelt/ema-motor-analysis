"""Recherchierte Vergleichswerte fuer die Gestaltungsentscheidungen -- FREMDTEXT.

Warum es diese Datei gibt
-------------------------

Der Paarvergleich (``ema_paarvergleich``) stellt die Magnetanordnungen
gegeneinander -- aber seine einzige Momentenzahl kam aus
``compute_performance``, und die rechnet ``Kt = 1.5*p*psi_pm``: **reines
Magnetmoment**. Genau das, worin sich V, Doppel-V, U, Delta und PMa-SynRM
unterscheiden -- das **Reluktanzmoment** -- kam darin nicht vor. Und
``estimate_saliency`` war fuer alle Innenlaeufer ausser PMa-SynRM und Speiche
**topologieblind**: sie las nur Luftspalt und Magnetdicke, so dass V, U, Delta,
Doppel-V und Balken bei gleicher Magnetdicke dasselbe xi bekamen.

Die Recherche schliesst diese Luecke. Sie liefert je Anordnung ein **Band** fuer
xi = Lq/Ld, in das die geometrische Schaetzung eingepasst wird.

Was hier steht -- und was ausdruecklich nicht
---------------------------------------------

``MESSPUNKTE`` sind **woertlich uebernommene Zahlen aus abgerufenen
Veroeffentlichungen**. Kein Wert daraus ist von uns gerechnet, keiner ist
nachgerechnet. Sie stehen mit Quelle und Fundstelle da, damit man sie pruefen
kann -- dieselbe Trennung, die ``ema_recherche`` zwischen Netztext und
Rechenergebnis macht, und derselbe Grund, aus dem ``ema_db`` recherchierte Werte
in ``referenzwerte`` und nicht zu den Kennwerten legt.

``SALIENZ_BAND`` und ``BAUBAND`` sind **abgeleitet**: unsere Einordnung der
Messpunkte, keine zitierbare Zahl. Jeder Eintrag nennt die Messpunkte, auf denen
er ruht. Wo die Belege duenn sind, ist das Band weit -- nicht schmal und
erfunden.

Drei Befunde, die das Bild aendern
----------------------------------

1. **Das Reluktanzmoment ist kein Zuschlag, sondern die Hauptsache.** In der
   einzigen Gegenueberstellung, die denselben Stator, dieselbe Baulaenge und
   dasselbe Moment festhaelt (Sheffield, Tab. 6-17/6-20), traegt es **63 bis
   73 %** des Moments. Ein Vergleich ueber Kt allein misst also den kleineren
   Teil.

2. **Der Nutzen zeigt sich im Strom, nicht im Moment.** Speiche und Doppel-V
   liefern dort beide ~400 Nm -- die Speiche braucht dafuer **393,9 A**, das
   Doppel-V **291,8 A**. 26 % weniger Strom bei 6 % weniger Magnetmasse. Genau
   deshalb traegt der Paarvergleich jetzt ``I_s_A`` als gezaehlte Kennzahl.

3. **Der Reluktanzanteil folgt NICHT dem Salienzverhaeltnis.** Dieselbe Quelle:
   die Speiche hat das **kleinere** xi (2,61 gegen 3,30) und trotzdem den
   **groesseren** Reluktanzanteil (68,2 % gegen 63,0 %) -- weil ihr Ferrit
   weniger psi_pm stellt. Wer xi als Mass fuer den Reluktanzanteil liest, liest
   es falsch.
"""

from __future__ import annotations

# ── Die Quellen ───────────────────────────────────────────────────────────────
#
# Alle am 02.09.2026 abgerufen und im Volltext gelesen -- nicht nur der Anriss
# aus einer Trefferliste. Was nur als Trefferanriss vorlag, steht hier bewusst
# NICHT drin; ein Anriss ist keine Fundstelle.

QUELLEN = {
    "ornl2011": {
        "titel": "Evaluation of the 2010 Toyota Prius Hybrid Synergy Drive System",
        "kennung": "ORNL/TM-2010/253",
        "url": "https://info.ornl.gov/sites/publications/files/Pub26762.pdf",
        "stelle": "Tab. 2.7 (2010 Prius, LS 600h, Camry, 2004 Prius)",
    },
    "sheffield": {
        "titel": ("Modelling and Design of Permanent-magnet Machines for Electric "
                  "Vehicle Traction (Xiao Chen, 2015)"),
        "kennung": "Dissertation, The University of Sheffield (White Rose 11512)",
        "url": ("https://etheses.whiterose.ac.uk/id/eprint/11512/1/"
                "Thesis_full_XC_final_single_side_submit.pdf"),
        "stelle": "Tab. 6-15/6-17/6-20 (Speiche gegen Doppel-V, gleicher Stator); Kap. 1.3",
    },
    "pierm2018": {
        "titel": ("Comparative Study of IPM Synchronous Machines with Different "
                  "Saliency Ratios Considering EVs Operating Conditions"),
        "kennung": "Progress In Electromagnetics Research M 71, 19-29 (2018)",
        "url": "https://www.jpier.org/ac_api/download.php?id=18053004",
        "stelle": "Tab. 1 (drei Rotoren, gleicher Stator)",
    },
    "saujs2021": {
        "titel": ("Analysis of the Saliency Ratio Effect on the Output Torque and "
                  "the System Efficiency in IPM Drives"),
        "kennung": "Sakarya University Journal of Science 25(6), 1417-1426 (2021)",
        "url": "https://dergipark.org.tr/en/download/article-file/1823308",
        "stelle": "Tab. 1 und Abschnitt 4",
    },
    "scirep2025": {
        "titel": ("Optimization design and torque performance research of interior "
                  "permanent magnet synchronous motors"),
        "kennung": "Scientific Reports 15 (2025), s41598-025-93285-x",
        "url": "https://www.nature.com/articles/s41598-025-93285-x",
        "stelle": "Abschnitt 'Optimization of rotor topology structures', Fig. 11-13",
    },
}


# ── Woertlich uebernommen ─────────────────────────────────────────────────────
#
# groesse | wert | einheit | quelle | zitat/fundstelle
# Zahlen NUR aus den obigen Dokumenten. Nichts hier ist von uns gerechnet.

MESSPUNKTE = [
    # (1) Speiche gegen Doppel-V -- gleicher Stator (280 mm), gleiche Baulaenge
    #     (170 mm), gleiches Moment (~400 Nm), Ferritmagnete, 48N/8P.
    {"groesse": "Ld_Speiche", "wert": 0.264, "einheit": "mH", "quelle": "sheffield",
     "zitat": "d-axis inductance @ rated torque 0.264 mH (Tab. 6-17)"},
    {"groesse": "Lq_Speiche", "wert": 0.689, "einheit": "mH", "quelle": "sheffield",
     "zitat": "q-axis inductance @ rated torque 0.689 mH (Tab. 6-17)"},
    {"groesse": "Ld_DoppelV", "wert": 0.304, "einheit": "mH", "quelle": "sheffield",
     "zitat": "d-axis inductance @ rated torque 0.304 mH (Tab. 6-20)"},
    {"groesse": "Lq_DoppelV", "wert": 1.002, "einheit": "mH", "quelle": "sheffield",
     "zitat": "q-axis inductance @ rated torque 1.002 mH (Tab. 6-20)"},
    {"groesse": "Strom_Speiche_400Nm", "wert": 393.9, "einheit": "A(eff)",
     "quelle": "sheffield", "zitat": "Torque 400.3 Nm / Current (RMS) 393.9 A (Tab. 6-17)"},
    {"groesse": "Strom_DoppelV_400Nm", "wert": 291.8, "einheit": "A(eff)",
     "quelle": "sheffield", "zitat": "Torque 401.7 Nm / Current (RMS) 291.8 A (Tab. 6-20)"},
    {"groesse": "Reluktanzanteil_Speiche_Nenn", "wert": 68.2, "einheit": "%",
     "quelle": "sheffield", "zitat": "Reluctance torque contribution 68.2 % @ rated torque"},
    {"groesse": "Reluktanzanteil_DoppelV_Nenn", "wert": 63.0, "einheit": "%",
     "quelle": "sheffield", "zitat": "Reluctance torque contribution 63.0 % @ rated torque"},
    {"groesse": "Reluktanzanteil_Speiche_Spitze", "wert": 72.9, "einheit": "%",
     "quelle": "sheffield", "zitat": "Reluctance torque contribution 72.9 % @ peak torque"},
    {"groesse": "Reluktanzanteil_DoppelV_Spitze", "wert": 68.7, "einheit": "%",
     "quelle": "sheffield", "zitat": "Reluctance torque contribution 68.7 % @ peak torque"},
    {"groesse": "Magnetmasse_Speiche", "wert": 7.43, "einheit": "kg", "quelle": "sheffield",
     "zitat": "PM mass 7.43 kg (Tab. 6-17)"},
    {"groesse": "Magnetmasse_DoppelV", "wert": 6.96, "einheit": "kg", "quelle": "sheffield",
     "zitat": "PM mass 6.96 kg (Tab. 6-20)"},
    {"groesse": "Leistungsfaktor_Speiche_Nenn", "wert": 0.59, "einheit": "-",
     "quelle": "sheffield", "zitat": "Power factor 0.59 @ rated torque (Tab. 6-17)"},
    {"groesse": "Leistungsfaktor_DoppelV_Nenn", "wert": 0.82, "einheit": "-",
     "quelle": "sheffield", "zitat": "Power factor 0.82 @ rated torque (Tab. 6-20)"},
    {"groesse": "Momentenwelligkeit_Speiche_Nenn", "wert": 12.2, "einheit": "%",
     "quelle": "sheffield", "zitat": "Torque ripple 12.2 % @ rated torque (Tab. 6-17)"},
    {"groesse": "Momentenwelligkeit_DoppelV_Nenn", "wert": 23.1, "einheit": "%",
     "quelle": "sheffield", "zitat": "Torque ripple 23.1 % @ rated torque (Tab. 6-20)"},
    {"groesse": "Spaltverhaeltnis_Speiche_opt", "wert": 0.6625, "einheit": "-",
     "quelle": "sheffield", "zitat": "Ks split ratio 0.6625, optimiert (Tab. 6-15)"},

    # (2) Salienz allgemein
    {"groesse": "Salienz_SynRM_Mindestmass", "wert": 6.0, "einheit": "-",
     "quelle": "sheffield",
     "zitat": "torque density of SynRM with a saliency ratio no less than 6 can be "
              "higher than that of IM at the same loss condition (Kap. 1.3)"},
    {"groesse": "Salienz_SynRM_optimiert", "wert": 10.6, "einheit": "-",
     "quelle": "sheffield",
     "zitat": "power factor of 0.8 can be reached for the optimised rotor design "
              "with a 10.6 saliency ratio (Kap. 1.3)"},
    {"groesse": "Salienz_SPM", "wert": 1.0, "einheit": "-", "quelle": "sheffield",
     "zitat": "the rotor saliency can be neglected and thereby practically no "
              "reluctance torque is generated in an SPM (Kap. 1.3.6.1.1)"},
    {"groesse": "Salienz_gemessen_niedrig", "wert": 2.93, "einheit": "-",
     "quelle": "saujs2021", "zitat": "two IPM machines with a saliency ratio of 2.93 and 5.86"},
    {"groesse": "Salienz_gemessen_hoch", "wert": 5.86, "einheit": "-",
     "quelle": "saujs2021", "zitat": "two IPM machines with a saliency ratio of 2.93 and 5.86"},
    {"groesse": "Momentgewinn_bei_doppeltem_xi", "wert": 33.6, "einheit": "%",
     "quelle": "saujs2021",
     "zitat": "torque production capability of the machine would increase 33.6 % while "
              "the machine operates at 30 A stator current magnitude"},

    # (3) V-Oeffnungswinkel -- die beiden Ziele ziehen GEGENEINANDER
    {"groesse": "V_Oeffnungswinkel_Kompromiss", "wert": 115.0, "einheit": "Grad",
     "quelle": "scirep2025",
     "zitat": "When a1 is set to 115 deg, both torque density and reluctance torque "
              "can be simultaneously considered"},
    {"groesse": "V_Polbogenwinkel_Kompromiss", "wert": 130.0, "einheit": "Grad",
     "quelle": "scirep2025",
     "zitat": "When the pole arc angle is set to 130 deg, both the torque density and "
              "reluctance torque output can be simultaneously considered"},

    # (4) Bauverhaeltnisse ausgefuehrter Traktionsmaschinen (Tab. 2.7, in cm)
    #     Reihenfolge: 2010 Prius | LS 600h | Camry | 2004 Prius
    {"groesse": "StatorAD_Bauteile", "wert": None, "einheit": "cm", "quelle": "ornl2011",
     "zitat": "Stator OD 26.4 / 20.0 / 26.4 / 26.9 cm"},
    {"groesse": "RotorAD_Bauteile", "wert": None, "einheit": "cm", "quelle": "ornl2011",
     "zitat": "Rotor OD 16.04 / 12.91 / 16.05 / 16.05 cm"},
    {"groesse": "RotorBohrung_Bauteile", "wert": None, "einheit": "cm", "quelle": "ornl2011",
     "zitat": "Rotor lamination ID 5.1 / 5.3 / 10.5 / 11.1 cm"},
    {"groesse": "Blechpaket_Bauteile", "wert": None, "einheit": "cm", "quelle": "ornl2011",
     "zitat": "Stator stack length 5.08 / 13.54 / 6.07 / 8.4 cm"},
    {"groesse": "Luftspalt_Bauteile", "wert": None, "einheit": "mm", "quelle": "ornl2011",
     "zitat": "Air gap 0.73 / 0.89 / 0.73025 / 0.73025 mm"},
    {"groesse": "Rotorbohrung_klein_2010Prius", "wert": None, "einheit": "-",
     "quelle": "ornl2011",
     "zitat": "feature of interest is the small inner diameter (ID) of the rotor "
              "lamination, and thus the outer diameter (OD) of the rotor shaft. "
              "Previous designs consist of a rotor shaft with a much larger O"},
    {"groesse": "Rotor_ID_AD_5kW", "wert": None, "einheit": "mm", "quelle": "pierm2018",
     "zitat": "Rotor lamination OD 115 mm, Rotor lamination ID 64 mm, "
              "Stator lamination OD 192 mm, stack length 65 mm (Tab. 1)"},
]

# Die vier ausgefuehrten Maschinen als Zahlen -- damit die abgeleiteten Baender
# unten nachrechenbar sind und nicht behauptet werden muessen.
# (Name, StatorAD mm, RotorAD mm, Rotorbohrung mm, Blechpaket mm, Luftspalt mm, Quelle)
BAUMUSTER = [
    ("2010 Prius", 264.0, 160.4,  51.0,  50.8, 0.73,  "ornl2011"),
    ("LS 600h",    200.0, 129.1,  53.0, 135.4, 0.89,  "ornl2011"),
    ("Camry",      264.0, 160.5, 105.0,  60.7, 0.73,  "ornl2011"),
    ("2004 Prius", 269.0, 160.5, 111.0,  84.0, 0.73,  "ornl2011"),
    ("PIER-M 5 kW", 192.0, 115.0,  64.0,  65.0, 0.5,  "pierm2018"),
    ("Sheffield Speiche", 280.0, 184.5, None, 170.0, 0.5, "sheffield"),
    ("Sheffield Doppel-V", 280.0, 203.5, None, 170.0, 0.5, "sheffield"),
]


# ── Abgeleitet: unsere Einordnung, keine zitierbare Zahl ──────────────────────
#
# code -> (xi_min, xi_max, stuetzen, bemerkung)
#
# Das Band ist WEIT, wo die Belege duenn sind. Ein schmales Band ohne Beleg waere
# eine erfundene Genauigkeit -- und die faellt spaeter niemandem mehr auf, weil
# sie plausibel aussieht.

SALIENZ_BAND = {
    "spm": (1.00, 1.05, ("Salienz_SPM",),
            "Oberflaechenmagnete: praktisch kein Reluktanzmoment, das Moment ist "
            "reines Magnetmoment."),
    "halbach": (1.00, 1.05, ("Salienz_SPM",),
                "Ebenfalls Oberflaeche; die Halbach-Segmentierung aendert die "
                "Feldform, nicht das d/q-Verhaeltnis des Rotors."),
    "bar": (1.6, 2.6, ("Salienz_gemessen_niedrig",),
            "Ein gerader Balken je Pol: eine einzige q-Achsen-Bahn, keine "
            "Flusskonzentration -- das untere Ende der IPM-Familie."),
    "v": (2.0, 3.5, ("Salienz_gemessen_niedrig", "Lq_DoppelV", "Ld_DoppelV"),
          "Die zwei Schenkel machen die q-Achsen-Bahnen gleichmaessiger, heben Lq "
          "und damit xi ueber den Balken."),
    "vasym": (2.0, 3.5, ("Salienz_gemessen_niedrig",),
              "Magnetisch dieselbe Familie wie V. Die Unsymmetrie verschiebt die "
              "Oberwellen (Rastmoment, Welligkeit), nicht das d/q-Verhaeltnis."),
    "u": (2.2, 4.0, ("Salienz_gemessen_niedrig", "Salienz_gemessen_hoch"),
          "Die U-Schale legt zusaetzliche Sperrflaeche in die d-Achse; PMa-SynRM-"
          "Rotoren werden aus genau dieser Form aufgebaut."),
    "delta": (2.5, 4.5, ("Lq_DoppelV", "Ld_DoppelV"),
              "Balken plus V: der Balken hebt den d-Achsen-Magnetfluss, das V "
              "verbreitert die q-Achsen-Bahn -- beide Momentanteile steigen."),
    "vv": (2.3, 4.5, ("Ld_DoppelV", "Lq_DoppelV"),
           "Gemessen 1,002/0,304 = 3,30. Mehr Lagen heben xi in der Regel, aber "
           "nicht zwangslaeufig -- deshalb ein Band und kein Punkt."),
    "spoke": (2.0, 3.2, ("Ld_Speiche", "Lq_Speiche"),
              "Gemessen 0,689/0,264 = 2,61. Die Speiche traegt ihren grossen "
              "Reluktanzanteil ueber wenig psi_pm, nicht ueber ein grosses xi."),
    "pmasynrm": (4.0, 7.0, ("Salienz_SynRM_Mindestmass", "Salienz_SynRM_optimiert",
                            "Salienz_gemessen_hoch"),
                 "Reluktanzgetrieben: muss hoeher ausgelegt werden als ein IPM; "
                 "der reine SynRM braucht mindestens 6 und erreicht optimiert 10,6."),
}

# V-Oeffnungswinkel: der einzige Parameter, bei dem die beiden Ziele nachweislich
# GEGENEINANDER laufen -- Momentdichte steigt mit dem Winkel, Reluktanzmoment
# faellt. Deshalb gibt es hier ein Optimum und keine Richtung.
V_OEFFNUNG_GRAD = {
    "kompromiss": 115.0,
    "band": (95.0, 140.0),
    "stuetzen": ("V_Oeffnungswinkel_Kompromiss", "V_Polbogenwinkel_Kompromiss"),
    "bemerkung": ("Momentdichte steigt mit dem Oeffnungswinkel, das Reluktanzmoment "
                  "faellt. 115 Grad ist der belegte Kompromiss EINER 8-poligen "
                  "Maschine -- als Anhaltspunkt zu lesen, nicht als Sollwert."),
}

# Bauverhaeltnisse -- aus BAUMUSTER gerechnet (unsere Arithmetik auf fremden Zahlen).
BAUBAND = {
    "spaltverhaeltnis": {
        "band": (0.59, 0.73), "label": "Rotor-Außen-Ø / Stator-Außen-Ø",
        "bemerkung": "Vier ausgefuehrte Traktionsmaschinen liegen bei 0,60-0,65; "
                     "zwei optimierte Entwuerfe reichen bis 0,73."},
    "wellenverhaeltnis": {
        "band": (0.32, 0.69), "label": "Wellenbohrung / Rotor-Außen-Ø",
        "bemerkung": "Das weiteste Band von allen -- und eine echte Entscheidung: "
                     "der 2010er Prius ging bewusst auf eine kleine Rotorbohrung "
                     "(0,32) zurueck, wo Camry und der 2004er bei 0,65-0,69 lagen."},
    "laengenverhaeltnis": {
        "band": (0.19, 0.68), "label": "Blechpaketlänge / Stator-Außen-Ø",
        "bemerkung": "Kein enges Band: die Scheibe (0,19) und die lange Walze (0,68) "
                     "sind beide ausgefuehrt. Die Laenge ist eine Bauraumfrage, "
                     "keine elektromagnetische."},
    "luftspalt_mm": {
        "band": (0.73, 0.89), "label": "Luftspalt",
        "bemerkung": "Ueber Stator-Außen-Ø 200 bis 269 mm praktisch unveraendert -- "
                     "der Luftspalt skaliert NICHT mit dem Durchmesser. Genau "
                     "deshalb laesst ihn die Durchmesser-Achse stehen."},
}


# ── Zugriff ───────────────────────────────────────────────────────────────────

def salienz_band(code: str):
    """``(xi_min, xi_max)`` fuer eine Topologie -- oder ``None``, wenn unbelegt."""
    e = SALIENZ_BAND.get(code)
    return (e[0], e[1]) if e else None


def messpunkt(groesse: str):
    for m in MESSPUNKTE:
        if m["groesse"] == groesse:
            return m
    return None


def _verhaeltnisse(geom: dict) -> dict:
    stator = float(geom.get("statorOD") or 0.0)
    rotor = float(geom.get("rotorOD") or 0.0)
    welle = float(geom.get("shaftD") or 0.0)
    laenge = float(geom.get("axialLen") or 0.0)
    aus = {}
    if stator > 0 and rotor > 0:
        aus["spaltverhaeltnis"] = rotor / stator
    if rotor > 0 and welle > 0:
        aus["wellenverhaeltnis"] = welle / rotor
    if stator > 0 and laenge > 0:
        aus["laengenverhaeltnis"] = laenge / stator
    if stator > 0 and rotor > 0:
        aus["luftspalt_mm"] = (float(geom.get("statorID", rotor)) - rotor) / 2.0
    return aus


def bauband_pruefen(geom: dict) -> list:
    """Welche Bauverhaeltnisse liegen ausserhalb des Bandes der Vorbilder?

    Ausdruecklich **kein Tor**. Ausserhalb des Bandes heisst nicht falsch --
    es heisst nur, dass keine der abgerufenen Maschinen dort gebaut wurde. Der
    Paarvergleich zeigt das an der Option an, damit man weiss, wann man den
    Bereich verlaesst, in dem die Vorbilder Auskunft geben.
    """
    aus = []
    for name, wert in _verhaeltnisse(geom).items():
        lo, hi = BAUBAND[name]["band"]
        if wert < lo or wert > hi:
            aus.append(f"{BAUBAND[name]['label']} {wert:.2f} liegt ausserhalb "
                       f"{lo:.2f}–{hi:.2f} der Vorbilder")
    return aus


def als_text() -> str:
    """Die Recherche zum Nachlesen -- fuer Agent, Bericht und Mensch."""
    z = ["RECHERCHIERTE VERGLEICHSWERTE — Fremdtext, nicht gerechnet, nicht nachgerechnet.",
         "Nur mit Quellenangabe verwenden und niemals als Ersatz fuer eine eigene Zahl.",
         ""]
    z.append("Quellen (alle im Volltext abgerufen, 02.09.2026):")
    for k, q in QUELLEN.items():
        z.append(f"  [{k}] {q['titel']}")
        z.append(f"        {q['kennung']} — {q['stelle']}")
        z.append(f"        {q['url']}")
    z.append("")
    z.append("Salienzband je Anordnung (ABGELEITET aus den Messpunkten, kein Zitat):")
    z.append(f"  {'Anordnung':<12} {'xi = Lq/Ld':>12}   Begruendung")
    for code, (lo, hi, _st, bem) in SALIENZ_BAND.items():
        z.append(f"  {code:<12} {lo:>5.2f}–{hi:<5.2f}   {bem}")
    z.append("")
    z.append("V-Oeffnungswinkel:")
    z.append(f"  Kompromiss {V_OEFFNUNG_GRAD['kompromiss']:.0f}°, "
             f"Band {V_OEFFNUNG_GRAD['band'][0]:.0f}–{V_OEFFNUNG_GRAD['band'][1]:.0f}°")
    z.append(f"  {V_OEFFNUNG_GRAD['bemerkung']}")
    z.append("")
    z.append("Bauverhaeltnisse ausgefuehrter Maschinen (unsere Arithmetik auf fremden Massen):")
    z.append(f"  {'Maschine':<20} {'D_r/D_s':>8} {'D_w/D_r':>8} {'L/D_s':>8}")
    for name, ds, dr, dw, lang, _lsp, _q in BAUMUSTER:
        w = f"{dw / dr:>8.2f}" if dw else f"{'—':>8}"
        z.append(f"  {name:<20} {dr / ds:>8.2f} {w} {lang / ds:>8.2f}")
    for name, e in BAUBAND.items():
        lo, hi = e["band"]
        z.append(f"  → {e['label']}: {lo:.2f}–{hi:.2f}. {e['bemerkung']}")
    z.append("")
    z.append("Woertlich uebernommene Zahlen:")
    for m in MESSPUNKTE:
        wert = f"{m['wert']} {m['einheit']}" if m["wert"] is not None else "(siehe Zitat)"
        z.append(f"  {m['groesse']:<34} {wert:<14} [{m['quelle']}]")
        z.append(f"      „{m['zitat']}“")
    return "\n".join(z)


def in_datenbank(conn, projekt_id: str | None = None) -> int:
    """Die Messpunkte in ``referenzwerte`` legen -- NICHT zu den Kennwerten.

    Freiwillig und wiederholbar; der Paarvergleich braucht die Datenbank nicht.
    Sie ist dafuer da, dass ein Bericht die Herkunft mitfuehren kann.
    """
    import ema_db
    n = 0
    for m in MESSPUNKTE:
        q = QUELLEN[m["quelle"]]
        ema_db.referenz_hinzufuegen(conn, m["groesse"], m["wert"], m["einheit"],
                                    m["zitat"], q["url"], q["titel"],
                                    projekt_id=projekt_id, notiz=q["stelle"])
        n += 1
    return n
