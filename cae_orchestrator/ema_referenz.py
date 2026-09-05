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
    # ── Die drei neuen Maschinenarten (abgerufen und im Volltext gelesen
    #    am 05.09.2026). Jede der drei haelt EINE Vergleichsgroesse fest, die
    #    unsere analytischen Module bisher nur angenommen hatten.
    "gundogdu2023": {
        "titel": ("Torque Capability Comparison of Induction and Interior "
                  "Permanent Magnet Machines for Traction Applications"),
        "kennung": ("Tayfun Gundogdu, Gazi University Journal of Science 36(2): "
                    "675-691 (2023), DOI 10.35378/gujs.1067707"),
        "url": "https://dergipark.org.tr/en/download/article-file/2230751",
        "stelle": ("Tab. 2 (Auslegung IM und Prius-2010-IPM am GLEICHEN Stator: "
                   "264 mm Aussen-Ø, 0,73 mm Luftspalt, 48 Nuten, 8 Pole, M270-35), "
                   "Tab. 3 (Wirkungsgraddifferenz), Fig. 8/11 (Moment, Schlupf)"),
    },
    "gercekcioglu2021": {
        "titel": ("Efficiency and Performance Comparison Between Synchronous "
                  "Reluctance and Induction Motor in Axial Flux Concept"),
        "kennung": ("H. S. Gercekcioglu, M. Akar, GU J Sci Part C 9(2): 297-316 "
                    "(2021), DOI 10.29109/gujsc.910521"),
        "url": "https://dergipark.org.tr/en/download/article-file/1687918",
        "stelle": ("Tab. 6 (SynRM gegen ASM am GLEICHEN Stator, 2,2 kW, ueber "
                   "25-125 % Last), Sekil 12-17. ACHTUNG: AXIALFLUSSMASCHINEN"),
    },
    "carlsson2026": {
        "titel": ("Investigation of Soft Magnetic Composites in Radial-Flux Wound "
                  "Field Synchronous Machines for Automotive Propulsion"),
        "kennung": ("A. Carlsson, C. Sandstroem, V. Josefsson, L. Kjellen, "
                    "T. El Hajji, M. Lenberg (Polestar / Hoeganaes / Alvier), "
                    "arXiv:2605.05853v1, 07.05.2026"),
        "url": "https://arxiv.org/pdf/2605.05853",
        "stelle": ("Tab. 1 (EESM gegen PSM am GLEICHEN Stator-Aussendurchmesser "
                   "237 mm), Tab. 4 (Kennwerte der Varianten), Tab. 5 (WLTP)"),
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
# ── Die drei neuen Maschinenarten, woertlich uebernommen ─────────────────────
#
# Was diese Zahlen wert sind: sie stammen aus drei Untersuchungen, die jeweils
# ZWEI Bauarten am **gleichen Stator** gegeneinanderstellen. Genau das macht sie
# fuer den Paarvergleich brauchbar -- er tut dasselbe.

MESSPUNKTE += [
    # (5) ASM gegen IPM am gleichen Stator: 264 mm Aussen-Ø, 0,73 mm Luftspalt,
    #     48 Nuten, 8 Pole, M270-35. Der IPM ist der Prius 2010.
    {"groesse": "ASM_Statorbohrung", "wert": 195.0, "einheit": "mm",
     "quelle": "gundogdu2023",
     "zitat": "Stator inner diameter (mm): IM 195, Prius IPM 161.9 (Tab. 2)"},
    {"groesse": "ASM_Laeuferstaebe", "wert": 44, "einheit": "-",
     "quelle": "gundogdu2023",
     "zitat": "PM/Rotor slot number: IM 44, bei 48 Statornuten und 8 Polen (Tab. 2)"},
    {"groesse": "ASM_Stabnut_Breite", "wert": 9.29, "einheit": "mm",
     "quelle": "gundogdu2023", "zitat": "Rotor slot width (mm) 9.29 (Tab. 2)"},
    {"groesse": "ASM_Stabnut_Hoehe", "wert": 15.2, "einheit": "mm",
     "quelle": "gundogdu2023", "zitat": "Rotor slot height (mm) 15.2 (Tab. 2)"},
    {"groesse": "ASM_Stabnut_Schlitz", "wert": 1.0, "einheit": "mm",
     "quelle": "gundogdu2023",
     "zitat": "Rotor slot opening width (mm) 1 — die Kaefignut ist HALBGESCHLOSSEN "
              "(Tab. 2)"},
    {"groesse": "Nutfuellfaktor", "wert": 0.465, "einheit": "-",
     "quelle": "gundogdu2023",
     "zitat": "Slot filling factor 0.465, fuer IM und IPM gleich (Tab. 2)"},
    {"groesse": "ASM_Kaefigwerkstoff", "wert": None, "einheit": "-",
     "quelle": "gundogdu2023", "zitat": "PM/Cage material: IM Copper (Tab. 2)"},
    {"groesse": "Luftspalt_ASM_IPM", "wert": 0.73, "einheit": "mm",
     "quelle": "gundogdu2023",
     "zitat": "Air-gap length (mm) 0.73 — fuer BEIDE Bauarten gleich (Tab. 2)"},
    {"groesse": "ASM_Schlupf_bei_Nennstrom", "wert": 5.5, "einheit": "%",
     "quelle": "gundogdu2023",
     "zitat": "Slip versus excitation current curve: rund 5,5 % beim Nennstrom "
              "250 A, rund 2 % bei 125 A und 13,3 % bei 1500 A (Fig. 11)"},
    {"groesse": "ASM_keine_Salienz", "wert": None, "einheit": "-",
     "quelle": "gundogdu2023",
     "zitat": "„these flux components are identical for IM, indicating that there "
              "is no saliency in the IM“ (S. 680)"},
    {"groesse": "Wirkungsgrad_IPM_minus_ASM", "wert": None, "einheit": "%-Punkte",
     "quelle": "gundogdu2023",
     "zitat": "eta-Differenz IPM gegen IM: +2,06 (125 A), +1,04 (250 A), 0 "
              "(500 A), -9,41 (1000 A) (Tab. 3)"},

    # (6) SynRM gegen ASM am gleichen Stator, 2,2 kW. ACHTUNG: Axialfluss --
    #     die Betriebsgroessen sind uebertragbar, die Geometrie nicht.
    {"groesse": "SynRM_Leistungsfaktor_Vollast", "wert": 0.67, "einheit": "-",
     "quelle": "gercekcioglu2021",
     "zitat": "Guec Faktoeru (cos phi) bei 100 % Last: EA-SRM 0.67, EA-IM 0.63 "
              "(Tab. 6)"},
    {"groesse": "SynRM_Leistungsfaktor_Teillast", "wert": 0.60, "einheit": "-",
     "quelle": "gercekcioglu2021",
     "zitat": "Bei 25 % Last: EA-SRM 0.6 gegen EA-IM 0.3 (Tab. 6)"},
    {"groesse": "SynRM_Wirkungsgrad_Vollast", "wert": 89.3, "einheit": "%",
     "quelle": "gercekcioglu2021",
     "zitat": "Verim (%) bei 100 % Last: EA-SRM 89.3, EA-IM 82.28 (Tab. 6)"},
    {"groesse": "SynRM_Verluste_Vollast", "wert": 0.26, "einheit": "kW",
     "quelle": "gercekcioglu2021",
     "zitat": "Toplam Kayiplar (kW) bei 100 % Last: EA-SRM 0.26, EA-IM 0.63 — "
              "der ASM-Verlust ist das 2,42-fache (Tab. 6, Sekil 17)"},
    {"groesse": "SynRM_Moment_je_Ampere", "wert": 2.4, "einheit": "Nm/A",
     "quelle": "gercekcioglu2021",
     "zitat": "Akim basina Tork (Nm/A) bei 100 % Last: EA-SRM 2.4, EA-IM 2.2 "
              "(Tab. 6)"},
    {"groesse": "SynRM_Strom_Vollast", "wert": 5.8, "einheit": "A",
     "quelle": "gercekcioglu2021",
     "zitat": "Vollast: EA-SRM 5,8 A fuer 13,93 Nm, EA-IM 6,36 A fuer 13,96 Nm "
              "(Sekil 12)"},

    # (7) EESM gegen PSM am gleichen Stator-Aussendurchmesser (237 mm),
    #     Traktionsantrieb, radialer Fluss.
    {"groesse": "EESM_Spitzenmoment", "wert": 610.0, "einheit": "Nm",
     "quelle": "carlsson2026",
     "zitat": "Peak Torque: WFSM (M0) 610 N.m, PMSM 450 N.m (Tab. 1)"},
    {"groesse": "EESM_Hoechststrom", "wert": 400.0, "einheit": "A(eff)",
     "quelle": "carlsson2026",
     "zitat": "Maximum Current: WFSM 400 Arms, PMSM 550 Arms (Tab. 1)"},
    {"groesse": "EESM_Erregerstrom", "wert": 32.0, "einheit": "A",
     "quelle": "carlsson2026", "zitat": "Field Current: WFSM 32 A (Tab. 1)"},
    {"groesse": "EESM_Erregerleistung", "wert": 8.2, "einheit": "kW",
     "quelle": "carlsson2026",
     "zitat": "„a contactless rotating transformer capable of transferring up to "
              "8.2 kW to the rotor field winding“ bei 210 kW Spitzenleistung "
              "(Abschn. 3)"},
    {"groesse": "EESM_Statoraussendurchmesser", "wert": 237.0, "einheit": "mm",
     "quelle": "carlsson2026",
     "zitat": "Stator Outer Diameter 237 mm fuer BEIDE; aktive Laenge WFSM 133 mm, "
              "PMSM 128 mm (Tab. 1)"},
    {"groesse": "EESM_WLTP_Wirkungsgrad", "wert": 89.7, "einheit": "%",
     "quelle": "carlsson2026",
     "zitat": "WLTP Efficiency: WFSM M6 89.7 %, PMSM 88.3 % (Tab. 5)"},
    {"groesse": "EESM_Wirkungsgrad_Konstantfahrt", "wert": None, "einheit": "%",
     "quelle": "carlsson2026",
     "zitat": "70 km/h: WFSM 91.7 gegen PMSM 88.5; 130 km/h: 92.5 gegen 89.9 "
              "(Tab. 5)"},
]


# ── Bänder je Maschinenart (ABGELEITET) ──────────────────────────────────────
#
# Unsere Einordnung der obigen Messpunkte, kein Zitat. Sie sind **kein Tor**:
# ausserhalb heisst nicht falsch, sondern „keine der abgerufenen Maschinen wurde
# dort gebaut". Der Paarvergleich zeigt es an der Option an.
#
# Warum diese Groessen und keine anderen: es sind genau die, die unsere
# analytischen Module bisher **gesetzt** hatten. Ein Band um eine gerechnete
# Zahl ist nutzlos; ein Band um eine angenommene Zahl sagt, ob die Annahme
# traegt.

ART_BAND = {
    # Kein Band, sondern ein Hinweistext: die Umrichtergrenzen sind in
    # ``ema_analysis`` fest verdrahtet und ausdruecklich nicht Teil dieses
    # Vorhabens (s. CLAUDE.md). Wo sie greifen, ist ein Stromverhaeltnis eine
    # Aussage ueber den Deckel und nicht ueber die Bauart.
    "_limit_hinweis": "800 A bei 1 Wdg/Nut, ema_analysis.INVERTER_I_MAX",
    "asm": {
        "schlupf_pct": {
            "band": (2.0, 13.3), "nenn": 5.5, "label": "Schlupf",
            "stuetzen": ("ASM_Schlupf_bei_Nennstrom",),
            "bemerkung": ("Am Nennstrom rund 5,5 %, ueber den Strom von 2 % bis "
                          "13,3 %. Unsere analytische Leistungsbilanz kam auf "
                          "0,24 % — zwanzigmal kleiner. Die Feldstufe (feld2d) "
                          "bestaetigt, dass der Schlupf groesser sein muss.")},
        "staebe_je_nut": {
            "band": (0.85, 1.00), "nenn": 0.917, "label": "Läuferstäbe / Statornuten",
            "stuetzen": ("ASM_Laeuferstaebe",),
            "bemerkung": ("44 Staebe zu 48 Nuten. Gleiche Zahl waere wegen der "
                          "Nutungskraefte falsch, sehr viel weniger kostet "
                          "Laeuferquerschnitt.")},
        "stab_tiefe_zu_breite": {
            "band": (1.4, 2.2), "nenn": 1.64, "label": "Stabtiefe / Stabbreite",
            "stuetzen": ("ASM_Stabnut_Hoehe", "ASM_Stabnut_Breite"),
            "bemerkung": ("15,2 zu 9,29 mm. ema_asm.KAEFIG_TIEFE_ZU_BREITE deckelt "
                          "erst bei 3,0 — der Deckel greift also spaeter als das "
                          "Vorbild und laesst tiefere Staebe zu, als hier gebaut "
                          "wurden.")},
        "leistungsfaktor": {
            "band": (0.30, 0.67), "nenn": 0.63, "label": "Leistungsfaktor",
            "stuetzen": ("SynRM_Leistungsfaktor_Vollast",
                         "SynRM_Leistungsfaktor_Teillast"),
            "bemerkung": ("Vollast 0,63, Teillast bis herab zu 0,30 — der "
                          "Magnetisierungsstrom liegt dauernd im Stator und faellt "
                          "bei kleiner Last nicht mit. Genau das rechnet ema_asm "
                          "als hypot(i_mag, i_q).")},
        "xi_LqLd": {
            "band": (1.00, 1.00), "nenn": 1.0, "label": "Salienz",
            "stuetzen": ("ASM_keine_Salienz",),
            "bemerkung": "Der Kaefiglaeufer ist magnetisch glatt — gemessen, nicht angenommen."},
    },
    "synrm": {
        "leistungsfaktor": {
            "band": (0.60, 0.72), "nenn": 0.67, "label": "Leistungsfaktor",
            "stuetzen": ("SynRM_Leistungsfaktor_Vollast",
                         "SynRM_Leistungsfaktor_Teillast"),
            "bemerkung": ("Der schlechte Leistungsfaktor ist der bekannte Einwand "
                          "gegen die SynRM. Gemessen liegt er bei Vollast mit 0,67 "
                          "UEBER dem der ASM (0,63) und bei Teillast doppelt so "
                          "hoch — der Einwand traegt in dieser Gegenueberstellung "
                          "nicht.")},
        "verlust_anteil_asm": {
            "band": (0.30, 0.45), "nenn": 0.41,
            "label": "Verluste, bezogen auf die ASM",
            "stuetzen": ("SynRM_Verluste_Vollast",),
            "bemerkung": ("0,26 gegen 0,63 kW bei Vollast. Der Laeufer hat weder "
                          "Kaefig noch Magnet und damit fast keine eigenen "
                          "Verluste — das ist ihr Hauptvorteil und steht in "
                          "ema_synrm als P_Laeufer = 0.")},
        "moment_je_ampere_anteil_asm": {
            "band": (1.00, 2.20), "nenn": 1.09,
            "label": "Moment je Ampere, bezogen auf die ASM",
            "stuetzen": ("SynRM_Moment_je_Ampere", "SynRM_Strom_Vollast"),
            "bemerkung": ("Bei Vollast 2,4 gegen 2,2 Nm/A, bei Teillast 1,62 gegen "
                          "0,75. Eine OPTIMIERTE SynRM erreicht also die ASM und "
                          "uebertrifft sie in Teillast. Unser analytisches Modell "
                          "kommt deutlich darunter heraus — die Barrieren sind dort "
                          "ueber ein Salienzband erfasst, nicht ueber ihre "
                          "Einzelgeometrie, und genau hier ist der Unterschied.")},
    },
    "eesm": {
        "I_f_A": {
            "band": (20.0, 45.0), "nenn": 32.0, "label": "Erregerstrom",
            "stuetzen": ("EESM_Erregerstrom",),
            "bemerkung": ("32 A an einer 210-kW-Maschine. ema_eesm.I_F_VORGABE_A "
                          "steht auf 15 A — dieselbe Groessenordnung, aber am "
                          "unteren Rand; die Wahl bestimmt nur den "
                          "Schleifringverlust, nicht den Erregerverlust.")},
        "erreger_anteil_pct": {
            "band": (2.0, 4.0), "nenn": 3.9,
            "label": "Erregerleistung / Spitzenleistung",
            "stuetzen": ("EESM_Erregerleistung",),
            "bemerkung": ("8,2 kW Uebertragungsvermoegen zu 210 kW Spitzenleistung "
                          "= 3,9 %. Das ist die OBERE Schranke des Uebertragungs"
                          "weges, nicht der Dauerwert — als solche zu lesen.")},
        "strom_anteil_psm": {
            "band": (0.65, 0.80), "nenn": 0.727,
            "label": "Statorstrom, bezogen auf die PSM",
            "stuetzen": ("EESM_Hoechststrom", "EESM_Spitzenmoment"),
            "bemerkung": ("400 gegen 550 Arms — und dabei 610 statt 450 Nm, am "
                          "GLEICHEN Stator-Aussendurchmesser. Die EESM macht also "
                          "36 % mehr Moment mit 27 % weniger Strom. Das ist genau "
                          "die Aussage von ema_eesm (I_s = i_q, der "
                          "Magnetisierungsstrom sitzt im Laeufer) — hier gemessen.")},
        "wirkungsgrad_vorteil_psm_pkt": {
            "band": (1.4, 3.2), "nenn": 1.4,
            "label": "Wirkungsgradvorsprung gegenüber der PSM",
            "stuetzen": ("EESM_WLTP_Wirkungsgrad", "EESM_Wirkungsgrad_Konstantfahrt"),
            "bemerkung": ("Ueber den WLTP 1,4 Prozentpunkte, bei 70 km/h 3,2 und "
                          "bei 130 km/h 2,6. Der Vorsprung waechst mit der "
                          "Drehzahl — die PSM muss ihren Magnetfluss dauernd "
                          "niederhalten, die EESM schaltet ihn ab.")},
    },
}


# Das Band ist WEIT, wo die Belege duenn sind.# Das Band ist WEIT, wo die Belege duenn sind. Ein schmales Band ohne Beleg waere
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


def art_band(code: str, groesse: str):
    """``(lo, hi)`` fuer eine Maschinenart und eine Groesse -- oder ``None``."""
    e = ART_BAND.get(str(code or "").lower())
    e = e.get(groesse) if isinstance(e, dict) else None
    return tuple(e["band"]) if e else None


def art_pruefen(code: str, werte: dict) -> list:
    """Welche gerechneten Kennwerte liegen ausserhalb des recherchierten Bandes?

    Ausdruecklich **kein Tor** -- wie ``bauband_pruefen``. Ausserhalb heisst
    nicht falsch; es heisst, dass keine der abgerufenen Maschinen dort lag.

    Der Sinn ist ein anderer als beim Bauband: dort geht es um Masse, hier um
    **Annahmen**. Jede Groesse in ``ART_BAND`` ist eine, die unsere analytischen
    Module gesetzt und nicht gemessen haben. Faellt die gerechnete Zahl aus dem
    Band, ist das der erste Hinweis, dass die Annahme nicht traegt -- und beim
    ASM-Schlupf war es genau so (0,24 % gerechnet gegen 5,5 % gemessen).
    """
    band = ART_BAND.get(str(code or "").lower())
    if not isinstance(band, dict) or not band:
        return []
    aus = []
    for name, e in band.items():
        wert = werte.get(name)
        if wert is None:
            continue
        lo, hi = e["band"]
        if wert < lo or wert > hi:
            aus.append(f"{e['label']} {wert:.3g} liegt ausserhalb {lo:.3g}–{hi:.3g} "
                       f"der Vorbilder (Nennwert {e['nenn']:.3g})")
    return aus


def arten_gegenueberstellung(zeilen: dict) -> list:
    """Die Vergleiche, die erst ZWISCHEN den Bauarten eine Aussage sind.

    Drei der recherchierten Groessen sind Verhaeltnisse und lassen sich an einer
    einzelnen Option gar nicht pruefen: der Statorstrom der EESM bezogen auf die
    PSM, die Verluste der SynRM bezogen auf die ASM, ihr Moment je Ampere
    ebenso. Genau diese Verhaeltnisse sind aber das, was die drei abgerufenen
    Untersuchungen festhalten -- alle drei stellen zwei Bauarten am **gleichen
    Stator** gegeneinander, und das tut die Achse „Maschinenart" auch.

    ``zeilen`` ist ``{code: ergebnis}`` aus dem Paarvergleich. Fehlt eine Seite,
    entfaellt der Vergleich -- er wird nicht ersatzweise gegen etwas anderes
    gerechnet.
    """
    def wert(code, schluessel):
        z = zeilen.get(code) or {}
        return z.get(schluessel) if z.get("ok") else None

    def gedeckelt(*codes):
        """Steht eine der beiden Seiten am Umrichter-Limit?

        Dann ist ein Stromverhaeltnis KEINE Aussage ueber die Bauart, sondern
        ueber den Deckel: beide Zahlen laufen gegen dieselbe Schranke und muessen
        sich zwangslaeufig annaehern. Das gehoert dazugesagt, sonst liest sich
        eine Abweichung wie ein Modellfehler, den es an dieser Stelle nicht gibt.
        """
        return [c for c in codes if (zeilen.get(c) or {}).get("strom_limit")]

    aus = []
    # EESM gegen PSM: Statorstrom.
    i_e, i_p = wert("eesm", "I_s_A"), wert("pmsm", "I_s_A")
    if i_e and i_p:
        v = i_e / i_p
        lo, hi = ART_BAND["eesm"]["strom_anteil_psm"]["band"]
        drin = lo <= v <= hi
        limit = gedeckelt("eesm", "pmsm")
        aus.append({
            "groesse": "EESM-Statorstrom / PSM-Statorstrom",
            "gerechnet": round(v, 3), "band": (lo, hi), "im_band": drin,
            "vergleichbar": not limit, "beleg": "carlsson2026",
            "text": (f"EESM braucht {v:.2f} mal den Statorstrom der PSM "
                     f"({i_e:.0f} gegen {i_p:.0f} A). Gemessen an einer "
                     f"Traktionsmaschine gleichen Aussendurchmessers: 0,73 "
                     f"(400 gegen 550 Arms) — und dabei 36 % mehr Moment."
                     + ("" if drin else
                        (f"  NICHT VERGLEICHBAR: {', '.join(limit)} steht am "
                         f"Umrichter-Limit ({ART_BAND['_limit_hinweis']}), beide "
                         f"Stroeme laufen gegen dieselbe Schranke und muessen sich "
                         f"annaehern. Das Verhaeltnis sagt hier nichts ueber die "
                         f"Bauart." if limit else "  ABWEICHEND vom Band.")))})
    # SynRM gegen ASM: Verluste und Moment je Ampere.
    p_s, p_a = wert("synrm", "P_verlust_W"), wert("asm", "P_verlust_W")
    if p_s and p_a:
        v = p_s / p_a
        lo, hi = ART_BAND["synrm"]["verlust_anteil_asm"]["band"]
        drin = lo <= v <= hi
        # Verluste haengen nicht am Umrichterdeckel -- dieser Vergleich ist
        # immer zulaessig. ``vergleichbar`` steht trotzdem dabei: ein fehlendes
        # Feld liest sich wie „unbekannt", und das waere es nicht.
        aus.append({
            "groesse": "SynRM-Verluste / ASM-Verluste",
            "gerechnet": round(v, 3), "band": (lo, hi), "im_band": drin,
            "vergleichbar": True, "beleg": "gercekcioglu2021",
            "text": (f"SynRM verliert {v:.2f} mal soviel wie die ASM "
                     f"({p_s:.0f} gegen {p_a:.0f} W). Gemessen am gleichen "
                     f"Stator: 0,41 (0,26 gegen 0,63 kW) — der SynRM-Laeufer "
                     f"hat weder Kaefig noch Magnet."
                     + ("" if drin else "  ABWEICHEND vom Band."))})
    kt_s, kt_a = wert("synrm", "Kt_Nm_per_A"), wert("asm", "Kt_Nm_per_A")
    if kt_s and kt_a:
        v = kt_s / kt_a
        lo, hi = ART_BAND["synrm"]["moment_je_ampere_anteil_asm"]["band"]
        drin = lo <= v <= hi
        # Kt ist Moment JE AMPERE und damit auch am Stromdeckel noch eine
        # Aussage ueber die Bauart -- anders als das Stromverhaeltnis oben.
        aus.append({
            "groesse": "SynRM-Moment je Ampere / ASM",
            "gerechnet": round(v, 3), "band": (lo, hi), "im_band": drin,
            "vergleichbar": True, "beleg": "gercekcioglu2021",
            "text": (f"SynRM erreicht {v:.2f} mal das Moment je Ampere der ASM. "
                     f"Gemessen an einer OPTIMIERTEN SynRM am gleichen Stator: "
                     f"1,09 bei Vollast, 2,16 bei Teillast."
                     + ("" if drin else
                        "  ABWEICHEND: unser Barrierenmodell erfasst die "
                        "Sperrschichten ueber ein Salienzband, nicht ueber ihre "
                        "Einzelgeometrie — genau hier liegt der Unterschied."))})
    return aus


def art_text(code: str) -> str:
    """Die Recherche zu EINER Maschinenart -- fuer Agent und Bericht."""
    band = ART_BAND.get(str(code or "").lower())
    if not isinstance(band, dict) or not band:
        return f"Zu '{code}' liegt keine eigene Recherche vor."
    z = [f"Recherchierte Vergleichswerte fuer '{code}' — FREMDTEXT, abgeleitet, kein Tor:"]
    for name, e in band.items():
        lo, hi = e["band"]
        z.append(f"  {e['label']:<38} {lo:>7.3g} – {hi:<7.3g} (Nennwert {e['nenn']:.3g})")
        z.append(f"      {e['bemerkung']}")
        for st in e["stuetzen"]:
            m = messpunkt(st)
            if m:
                z.append(f"      Beleg [{m['quelle']}]: „{m['zitat']}“")
    return "\n".join(z)


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
    z.append("Baender je Maschinenart (ABGELEITET — die Groessen, die unsere Module")
    z.append("bisher gesetzt und nicht gemessen hatten):")
    for code in ART_BAND:
        if code.startswith("_"):
            continue
        z.append("")
        z.append(art_text(code))
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
