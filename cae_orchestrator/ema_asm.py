"""Asynchronmaschine (Kaefiglaeufer) -- analytisch, in der Hauskonvention.

Warum die ASM KEIN zweites Momentgesetz bekommt
-----------------------------------------------

Der Paarvergleich stellt Optionen bei **demselben Betriebspunkt** gegeneinander.
Das funktioniert nur, wenn ``Kt``, ``I_s``, ``P_verlust`` und ``T_dauer`` fuer alle
Optionen dieselbe Bedeutung haben. Deshalb rechnet die ASM hier nicht mit einem
eigenen Momentgesetz, sondern speist **dieselbe** ``compute_performance`` mit dem
Luftspaltfeld, das ihr Magnetisierungsstrom erzeugt:

    B_m  = Ziel-Luftspaltfeld (Grundwelle), gedeckelt durch die Zahnsaettigung
    psi  = compute_performance(geom, B_m)["psi_pm_Wb"]     # gleiche Formel wie PSM
    Kt   = 1.5 * p * psi                                    # gleiche Definition
    i_q  = T_soll / Kt

Der Unterschied zur PSM steht dann genau dort, wo er physikalisch hingehoert:

    I_s  = hypot(i_mag, i_q)      # die ASM traegt i_mag DAUERND mit
    P_r  = s * T * omega_syn      # Schlupfverlust IM LAEUFER

Die Normierungsbruecke ``k_norm`` -- und warum sie sein muss
-------------------------------------------------------------

``compute_performance`` gibt eine **normierte** Flussverkettung heraus
(``psi_pm = p*(2/pi)*B*R_gap*L``, Docstring dort: „normalised, 1 turn per slot"),
waehrend ``_analytical_Barm`` und die ``Ld``-Formel in ``estimate_dq_currents``
mit der **physikalischen** Durchflutung rechnen
(``F = 1.5*(4/pi)*(N_ph*k_w/(2p))*i``). Die beiden Skalen unterscheiden sich um

    k_norm = psi_phys / psi_haus = (2*k_w*N_ph*B*R*L/p) / ((2/pi)*p*B*R*L)
           = pi * k_w * N_ph / p**2

Wer den Magnetisierungsstrom physikalisch ausrechnet (aus ``_analytical_Barm``
rueckwaerts) und ihn ungerechnet neben ein ``i_q = T/Kt_haus`` stellt, vergleicht
zwei verschiedene Amperes -- und der Magnetisierungsanteil der ASM kaeme um genau
diesen Faktor zu klein heraus. Das waere derselbe stille Fehler wie ein
Fahrzyklus, der nicht zum Fahrzeug passt: die Zahl steht da und widerspricht nicht.

``k_norm`` rechnet den physikalischen Strom in die Hausskala um. Dass diese
Umrechnung die **einzig** widerspruchsfreie ist, haengt an einer pruefbaren
Erhaltung, und genau die nagelt ``test_asm.py`` fest:

    1.5*p*psi_haus*i_haus  ==  1.5*p*psi_phys*i_phys        (das Moment)

Das Moment ist invariant, weil psi mit 1/k_norm und i mit k_norm geht. Die
Bruecke aendert also **keine Physik**; sie sorgt nur dafuer, dass i_mag und i_q
in derselben Einheit stehen.

Was diese Stufe NICHT kann
--------------------------

Kein Feldlauf. Die 2-D-FDM (``_rasterise``/``_solve_fdm``) ist reell, linear und
**magnetostatisch** -- kein sigma, kein dA/dt, keine komplexe Arithmetik. Ein
Kaefiglaeufer ist dort nicht abbildbar; die ASM-Feldstufe laeuft ueber Elmers
``MagnetoDynamics2DHarmonic`` und ist eine eigene Stufe. Bis dahin meldet
``ema_maschinenart.pruefe_stufe("asm", "feld")`` das ausdruecklich als Fehler,
statt ersatzweise PSM-Physik zu rechnen.

Ebenfalls nicht enthalten: Stromverdraengung im Stab (Anlaufverhalten,
Doppelkaefig/Hochstab), Saettigung des Streupfads, Oberwellenmomente.
Der Betriebspunkt hier ist der **stationaere** Nennpunkt bei kleinem Schlupf.
"""

from __future__ import annotations

import math

import ema_analysis
import ema_thermal
from ema_analysis import MU0, compute_performance
from ema_pipeline import HAIRPIN_MATS, LAMINATES

# ── Auslegungsgroessen (Vorgaben, alle ueberschreibbar ueber geom) ────────────

# Ziel-Grundwelle im Luftspalt. 0,75-0,90 T ist der uebliche Bereich fuer
# Kaefiglaeufer; darueber saettigen Zahn und Joch, darunter wird der Laeuferstrom
# und mit ihm der Schlupfverlust unnoetig gross.
B_ZIEL_T = 0.80
B_ZIEL_SPANNE = (0.55, 0.95)

# Zahn- und Jochflussdichte, gegen die die Zielflussdichte gedeckelt wird.
B_ZAHN_MAX_T = 1.8
B_JOCH_MAX_T = 1.5

# Nutfuellung des Laeuferstabs im Nutraum und Nut/Zahn-Aufteilung am Umfang.
KAEFIG_NUT_ANTEIL = 0.50     # Anteil der Laeufernutteilung, der Nut ist
KAEFIG_FUELLUNG   = 0.95     # Druckguss fuellt die Nut nahezu vollstaendig
KURZSCHLUSSRING_ZUSCHLAG = 0.20   # Ringverlust als Anteil des Stabverlusts

# Groesstes zugelassenes Tiefe/Breite-Verhaeltnis der Laeufernut. Darueber wird
# der Stab zum Hochstab: die Stromverdraengung bestimmt dann den Widerstand, und
# genau die ist auf dieser Stufe NICHT gerechnet. Der Deckel haelt das Modell in
# dem Bereich, in dem es gilt -- ohne ihn frisst die Nut den ganzen Ringraum
# zwischen Steg und Joch (gemessen 45 mm bei einem 178-mm-Laeufer, was kein
# Kaefiglaeufer je hatte).
KAEFIG_TIEFE_ZU_BREITE = 3.0

# Steg zwischen Kaefignut und Luftspalt [mm]. **Ausdruecklich NICHT**
# ``ema_topology.BRIDGE_MM``: das ist die Wand zur MAGNETTASCHE, und die ist auf
# 1,3 mm gesetzt, weil dort ein 1,3 mm dicker Steg einen ruhenden Magneten haelt.
# Hier haelt der Steg einen Aludruckguss-Stab von rund 250 mm^2 Querschnitt ueber
# die volle Paketlaenge -- gemessen faellt der Sicherheitsfaktor bei 12.000 1/min
# von 2,9 (2,0 mm) auf 1,23 (1,3 mm). Die beiden Zahlen zusammenzulegen hiesse,
# eine Entscheidung ueber die Magnettasche stillschweigend auf den Kaefiglaeufer
# zu uebertragen. ``steg_check`` misst diesen Wert, er ist also nicht gesetzt und
# vergessen, sondern gesetzt und geprueft.
KAEFIG_STEG_MM = 2.0

KAEFIG_VORGABE = "al_1350"   # Aludruckguss; "cu_etp" = Kupferkaefig

# Wicklungskonvention -- identisch zu ``_analytical_Barm`` und
# ``estimate_dq_currents``: 1 Windung je Nut, k_w = 0,95, Carter 1,15.
K_W = 0.95
K_CARTER = 1.15


# ── Normierungsbruecke ────────────────────────────────────────────────────────

def k_norm(geom: dict) -> float:
    """Faktor physikalischer Strom -> Strom in der Hauskonvention (s. Kopf)."""
    p = max(int(geom["p"]), 1)
    n_ph = max(int(geom["slots"]) / 3.0, 1.0)
    return math.pi * K_W * n_ph / (p ** 2)


# ── Kaefiggeometrie ───────────────────────────────────────────────────────────

def stabzahl(geom: dict) -> int:
    """Zahl der Laeufernuten.

    Ausdruecklich gesetzt (``rotorBars``) oder nach der ueblichen Auswahlregel:
    rund 0,85 x Statornutzahl, aber **nicht** gleich der Statornutzahl und nicht
    um 0, +-p oder +-2p daneben -- diese Differenzen erzeugen synchrone
    Oberwellenmomente (Kleben beim Anlauf) bzw. Rastmomente.
    """
    gesetzt = geom.get("rotorBars")
    if gesetzt:
        return max(6, int(gesetzt))
    n_s = int(geom["slots"])
    p = max(int(geom["p"]), 1)
    verboten = {0, p, 2 * p, 3 * p}
    ziel = max(6, int(round(0.85 * n_s)))
    for d in range(0, n_s):                      # von ziel aus nach aussen suchen
        for kand in (ziel - d, ziel + d):
            if kand < 6 or kand == n_s:
                continue
            if abs(kand - n_s) in verboten:
                continue
            if kand % (2 * p) == 0:              # Vielfaches der Polzahl meiden
                continue
            return kand
    return max(6, n_s - 1)


# Stromdichte des Kaefigstabs [A/mm^2, Effektivwert]. **Sie** bemisst den Stab,
# nicht der verfuegbare Platz. 4-8 A/mm^2 ist der uebliche Bereich fuer einen
# Aludruckguss-Kaefig; der Laeufer kuehlt schlecht, darum nicht hoeher.
J_STAB_APMM2 = 6.0


def kaefig(geom: dict, axial_mm: float, j_stab_Apmm2: float = 0.0) -> dict:
    """Stab- und Ringgeometrie aus dem Laeuferblech. Alles in mm / mm^2.

    Der Nutraum liegt zwischen dem Steg unter dem Luftspalt
    (``KAEFIG_STEG_MM`` -- eine EIGENE Groesse, nicht die der Magnettaschen, s.
    dort) und dem Laeuferjoch, dessen Hoehe aus dem Fluss je Pol folgt -- nicht geraten:

        Phi_pol = (2/pi) * B_m * tau_pol * L        (Grundwelle, sinusfoermig)
        h_joch  = Phi_pol / (2 * B_joch * L)        (das Joch fuehrt Phi/2)
    """
    p      = max(int(geom["p"]), 1)
    r_rot  = float(geom["rotorOD"]) / 2.0
    r_wel  = float(geom["shaftD"]) / 2.0
    L      = float(axial_mm)
    b_m    = ziel_feld(geom)

    tau_pol = math.pi * float(geom["statorID"]) / (2 * p)          # Polteilung [mm]
    phi_pol = (2.0 / math.pi) * b_m * tau_pol * L * 1e-6           # [Wb] (mm->m)
    h_joch  = phi_pol / (2.0 * B_JOCH_MAX_T * (L * 1e-3)) * 1e3    # [mm]
    h_joch  = max(h_joch, 3.0)

    n_stab  = stabzahl(geom)
    nutraum = r_rot - KAEFIG_STEG_MM - h_joch - r_wel        # was das Blech hergibt
    # Breite an der Nutoberkante als obere Schranke -- damit ist die Tiefe ohne
    # Iteration bestimmbar (die Teilung nimmt nach innen ab, die Nut wird also
    # keinesfalls breiter als hier angesetzt).
    breite  = 2.0 * math.pi * (r_rot - KAEFIG_STEG_MM) / n_stab * KAEFIG_NUT_ANTEIL

    # Die Tiefe folgt aus der STROMDICHTE, nicht aus dem verfuegbaren Platz.
    #
    # Bis hierher stand hier ``min(nutraum, 3*breite)`` -- der Stab fuellte also
    # den Laeuferraum bis zum Deckel. Gemessen ergab das 306 mm^2 bei
    # **1,14 A/mm^2**; gebaut werden 4-8. Der Stabwiderstand kam damit um den
    # Faktor 5 zu klein heraus, und mit ihm der Schlupf (0,24 % gerechnet gegen
    # 2-13 % recherchiert). Der Deckel begrenzte nur den Schaden.
    #
    # Der Auslegungsstrom kommt aus ``auslegungsstrom_stab`` und braucht keinen
    # Betriebspunkt: mehr als ``sqrt(I_lim^2 - i_mag^2)`` kann diese Maschine
    # nie fuehren.
    j_soll = float(j_stab_Apmm2 or geom.get("barCurrentDensity") or J_STAB_APMM2)
    j_soll = min(max(j_soll, 1.0), 20.0)
    a_soll = auslegungsstrom_stab(geom)["I_stab_eff_A"] / j_soll        # mm^2
    t_strom = a_soll / max(breite * KAEFIG_FUELLUNG, 1e-9)
    t_deckel = KAEFIG_TIEFE_ZU_BREITE * breite
    nuttiefe = max(min(t_strom, nutraum, t_deckel), 2.0)
    if nuttiefe >= nutraum - 1e-9 and t_strom > nutraum:
        bemessung = "Blechraum"          # der Laeufer ist zu klein fuer den Strom
    elif nuttiefe >= t_deckel - 1e-9 and t_strom > t_deckel:
        bemessung = "Tiefe/Breite"       # Stromverdraengung waere nicht mehr erfasst
    else:
        bemessung = "Stromdichte"
    r_mitte  = r_rot - KAEFIG_STEG_MM - nuttiefe / 2.0
    a_stab  = breite * nuttiefe * KAEFIG_FUELLUNG                  # [mm^2]

    # Ringquerschnitt: uebliche Auslegung ~ Stabquerschnitt x n_stab/(2*pi*p),
    # weil der Ring den Strom von rund n_stab/(2*pi*p) Staeben fuehrt.
    a_ring = a_stab * n_stab / (2.0 * math.pi * p)

    return {
        "n_stab": n_stab,
        "nuttiefe_mm": round(nuttiefe, 2),
        "stabbreite_mm": round(breite, 2),
        "A_stab_mm2": round(a_stab, 2),
        "A_ring_mm2": round(a_ring, 2),
        "h_joch_mm": round(h_joch, 2),
        "l_stab_mm": round(L * 1.05, 1),        # 5 % Ueberstand ueber das Paket
        "r_ring_mm": round(r_mitte, 2),
        "nutraum_mm": round(nutraum, 2),          # was das Blech hergaebe
        "tief_begrenzt": bool(nutraum > KAEFIG_TIEFE_ZU_BREITE * breite),
        "bemessung": bemessung,
        "J_stab_Apmm2": round(auslegungsstrom_stab(geom)["I_stab_eff_A"]
                              / max(a_stab, 1e-9), 2),
        "tiefe_zu_breite": round(nuttiefe / max(breite, 1e-9), 2),
        "eng": nutraum < 2.0,                    # Laeufer hat keinen Platz mehr
    }


def ziel_feld(geom: dict) -> float:
    """Ziel-Luftspaltfeld [T] -- gesetzt oder Vorgabe, gedeckelt durch den Zahn.

    Der Deckel ist keine Zierde: wer ``B_m`` frei hochdreht, bekommt Moment
    geschenkt, das im Blech gar nicht durchpasst. Der Zahn traegt den Fluss einer
    Nutteilung; bei einem Zahnanteil von 50 % der Nutteilung heisst das
    ``B_zahn = 2 * B_m``.
    """
    b = float(geom.get("bZielT") or B_ZIEL_T)
    b = min(max(b, B_ZIEL_SPANNE[0]), B_ZIEL_SPANNE[1])
    return min(b, B_ZAHN_MAX_T / 2.0)


# ── Magnetkreis: Magnetisierungsstrom ─────────────────────────────────────────

def magnetisierungsstrom(geom: dict) -> dict:
    """Strom, der ``B_m`` im Luftspalt aufbaut -- physikalisch UND in Hausskala.

    Rueckwaerts aus ``_analytical_Barm``: dieselbe Durchflutungswelle, derselbe
    Carter-Luftspalt, dieselbe Wicklungskonvention. Damit kommt der
    Magnetisierungsstrom aus **genau der Funktion**, an der auch das
    FDM-Statorfeld geeicht ist -- und nicht aus einer zweiten, eigenen Formel.
    """
    p    = max(int(geom["p"]), 1)
    n_ph = max(int(geom["slots"]) / 3.0, 1.0)
    g    = ema_analysis.luftspalt_mm(geom)      # beide Bauformen, s. ema_radien
    g_m  = K_CARTER * g / 1000.0
    b_m  = ziel_feld(geom)

    # B = MU0 * F / g_eff  mit  F = 1.5*(4/pi)*(N_ph*k_w/(2p)) * i
    nenner = MU0 * 1.5 * (4.0 / math.pi) * (n_ph * K_W / (2.0 * p))
    i_phys = b_m * g_m / max(nenner, 1e-18)
    kn = k_norm(geom)
    return {"B_m_T": b_m, "i_mag_phys_A": i_phys, "i_mag_A": i_phys * kn,
            "k_norm": kn, "g_eff_mm": round(K_CARTER * g, 3)}


# ── Betriebspunkt ─────────────────────────────────────────────────────────────

def stabstrom(geom: dict, i_q_haus: float, n_stab: int) -> float:
    """Stabstrom [A, Amplitude] aus dem Durchflutungsgleichgewicht.

    Die Laeuferdurchflutung hebt die momentbildende Statordurchflutung auf:

        F_stator = 1.5*(4/pi)*(N_ph*k_w/(2p)) * i_q_phys      [A je Pol]
        F_kaefig = n_stab * I_stab / (2*pi*p)                 (Strombelag)

    Steht hier und nicht zweimal: der Betriebspunkt braucht sie, und die
    Kaefigauslegung braucht sie auch -- und zwar dieselbe. Zwei Fassungen davon
    waeren zwei verschiedene Staebe fuer dieselbe Maschine.
    """
    p = max(int(geom["p"]), 1)
    n_ph = max(int(geom["slots"]) / 3.0, 1.0)
    i_q_phys = i_q_haus / max(k_norm(geom), 1e-12)
    f_stator = 1.5 * (4.0 / math.pi) * (n_ph * K_W / (2.0 * p)) * i_q_phys
    return 2.0 * math.pi * p * f_stator / max(int(n_stab), 1)


def auslegungsstrom_stab(geom: dict) -> dict:
    """Der Strom, fuer den der Kaefig zu bemessen ist -- aus der Geometrie allein.

    Warum das ohne Betriebspunkt geht: der Umrichter begrenzt den Strangstrom
    auf ``INVERTER_I_MAX``, und der Magnetisierungsstrom liegt durch das
    Ziel-Luftspaltfeld fest. Mehr momentbildenden Strom als
    ``sqrt(I_lim^2 - i_mag^2)`` kann diese Maschine nie fuehren -- also ist der
    zugehoerige Stabstrom ihr groesster ueberhaupt moeglicher. Genau dafuer wird
    ein Kaefig ausgelegt.

    Das ersetzt die bisherige Bemessung nach PLATZ. Sie fuellte den Laeuferraum
    bis zum Deckel ``KAEFIG_TIEFE_ZU_BREITE`` und ergab gemessen einen Stab von
    306 mm^2 bei **1,14 A/mm^2** -- ein Viertel bis ein Fuenftel dessen, was
    gebaut wird. Die Folge war ein viel zu kleiner Stabwiderstand und damit ein
    Schlupf von 0,24 %, wo die Recherche 2-13 % ausweist.
    """
    mg = magnetisierungsstrom(geom)
    i_mag = mg["i_mag_A"]
    i_lim = float(ema_analysis.INVERTER_I_MAX)
    i_q = math.sqrt(max(i_lim ** 2 - i_mag ** 2, 0.0))
    n_stab = stabzahl(geom)
    i_stab = stabstrom(geom, i_q, n_stab)
    return {"i_mag_A": i_mag, "i_q_max_A": i_q, "n_stab": n_stab,
            "I_stab_A": i_stab, "I_stab_eff_A": i_stab / math.sqrt(2.0),
            "am_limit": bool(i_q <= 1e-6)}


def betriebspunkt(geom: dict, axial_mm: float, rpm: float, last_nm: float,
                  stabmaterial: str | None = None) -> dict:
    """Stationaerer Nennpunkt: Stroeme, Schlupf, Laeuferverlust, Moment.

    Der Momentaufschlag ``DQ_TORQUE_MARGIN_NM`` wird uebernommen, damit der
    Betriebspunkt derselbe ist wie bei ``estimate_dq_currents`` -- sonst
    verglichen PSM und ASM zwei verschiedene Lastfaelle.
    """
    p     = max(int(geom["p"]), 1)
    L     = float(axial_mm)
    mg    = magnetisierungsstrom(geom)
    perf  = compute_performance(geom, mg["B_m_T"], rpm=rpm, axial_mm=L)
    kt    = max(float(perf["Kt_Nm_per_A"]), 1e-9)
    t_soll = float(last_nm) + ema_analysis.DQ_TORQUE_MARGIN_NM

    # Der Umrichter begrenzt den STRANGSTROM, nicht seinen momentbildenden
    # Anteil. Hier stand ``min(i_q, INVERTER_I_MAX)`` -- und weil der
    # Magnetisierungsstrom danach geometrisch dazukam, meldete die ASM gemessen
    # 977 A bei einer Grenze von 800 A. Die Zahl stand da, war ueber der Grenze,
    # und nur ein Warnhinweis daneben sagte es.
    #
    # Richtig ist: was nach dem Magnetisierungsstrom uebrig bleibt, ist der
    # groesste momentbildende Strom. Genau das ist der Preis dieser Bauart.
    i_mag = mg["i_mag_A"]
    i_lim = float(ema_analysis.INVERTER_I_MAX)
    i_q_max = math.sqrt(max(i_lim ** 2 - i_mag ** 2, 0.0))
    i_q_roh = t_soll / kt
    i_q = min(i_q_roh, i_q_max)
    i_s = math.hypot(i_mag, i_q)
    am_limit = i_q_roh > i_q

    # ── Laeuferkaefig: Stabstrom aus dem Durchflutungsgleichgewicht ───────────
    # Die Laeuferdurchflutung hebt die momentbildende Statordurchflutung auf.
    #   F_stator = 1.5*(4/pi)*(N_ph*k_w/(2p)) * i_q_phys          [A je Pol]
    #   F_kaefig = n_stab * I_stab / (2*pi*p)                     (Strombelag)
    kf   = kaefig(geom, L)
    mat  = HAIRPIN_MATS.get(stabmaterial or geom.get("barMat") or KAEFIG_VORGABE,
                            HAIRPIN_MATS[KAEFIG_VORGABE])
    i_stab = stabstrom(geom, i_q, kf["n_stab"])

    r_stab = float(mat["rho_el"]) * (kf["l_stab_mm"] * 1e-3) / max(kf["A_stab_mm2"] * 1e-6, 1e-12)
    p_stab = kf["n_stab"] * 0.5 * i_stab ** 2 * r_stab           # Amplitude -> eff^2
    p_kaefig = p_stab * (1.0 + KURZSCHLUSSRING_ZUSCHLAG)

    omega_syn = 2.0 * math.pi * float(rpm) / 60.0
    t_ist = min(t_soll, kt * i_q)
    p_luft = max(t_ist * omega_syn, 1e-6)                        # Luftspaltleistung
    schlupf = min(p_kaefig / p_luft, 0.5) if p_luft > 0 else 0.0

    return {
        "B_m_T":        round(mg["B_m_T"], 4),
        "i_mag_A":      round(i_mag, 1),
        "i_q_A":        round(i_q, 1),
        "I_s_A":        round(i_s, 1),
        "mag_anteil":   round(i_mag / max(i_s, 1e-9), 3),
        "strom_limit":  bool(am_limit),
        "Kt_Nm_per_A":  round(kt, 5),
        "psi_Wb":       float(perf["psi_pm_Wb"]),
        "T_ist_Nm":     round(t_ist, 1),
        "I_stab_A":     round(i_stab, 1),
        "R_stab_uOhm":  round(r_stab * 1e6, 2),
        "P_kaefig_W":   round(p_kaefig, 1),
        "schlupf":      round(schlupf, 5),
        "schlupf_pct":  round(100.0 * schlupf, 3),
        "n_syn_1pmin":  round(float(rpm), 1),
        "n_laeufer_1pmin": round(float(rpm) * (1.0 - schlupf), 1),
        "kaefig":       kf,
        "stabmaterial": mat["label"],
        "perf":         perf,
    }


# ── Verluste und Dauermoment ──────────────────────────────────────────────────

def verluste(geom: dict, axial_mm: float, rpm: float, last_nm: float,
             bp: dict, rot_lam: dict, st_lam: dict, hp_mat: dict,
             kuehlung: str) -> dict:
    """Verluste am Betriebspunkt -- auf ``design_point_losses`` aufgesetzt.

    Zwei Aenderungen gegenueber der PSM, beide zwingend:

    * **Statorkupfer** steigt mit ``(I_s/i_q)^2``. ``design_point_losses``
      verankert das Kupfer an der Stromdichte, die das **Moment** braucht; die
      ASM schickt zusaetzlich den Magnetisierungsstrom durch dieselbe Wicklung.
    * **Magnetwirbelstrom faellt weg** (kein Magnet) und wird durch den
      **Kaefigverlust** ersetzt -- der sitzt im Laeufer, also dort, wo die
      Waerme am schlechtesten wegkommt.
    """
    mag_platzhalter = {"rho_el": 1.4e-6, "density": 7600.0, "label": "—"}
    basis = ema_thermal.design_point_losses(geom, axial_mm, rpm, last_nm,
                                            bp["perf"], rot_lam, st_lam, hp_mat,
                                            mag_platzhalter, kuehlung)
    faktor = (bp["I_s_A"] / max(bp["i_q_A"], 1e-9)) ** 2
    p_cu = float(basis["P_Cu"]) * faktor
    p_kaefig = float(bp["P_kaefig_W"])
    p_total = (p_cu + float(basis["P_Fe_stator"]) + float(basis["P_Fe_rotor"])
               + p_kaefig + float(basis["P_Bearing"]))
    aus = dict(basis)
    aus.update({
        "P_Cu":        round(p_cu, 1),
        "P_Cu_mag_anteil": round(p_cu - float(basis["P_Cu"]), 1),
        "P_Mag_eddy":  0.0,          # kein Magnet vorhanden
        "P_Kaefig":    round(p_kaefig, 1),
        "P_total":     round(p_total, 1),
    })
    return aus


def dauermoment(geom: dict, axial_mm: float, kuehlung: str, bp: dict) -> dict:
    """S1-Dauermoment der ASM -- beide Grenzen, und welche bindet.

    ``ema_thermal.rated_torque`` ist eine **geometrische** Schubspannungsformel;
    sie kennt weder Magnetisierungsstrom noch Kaefigverlust. Der Abschlag folgt
    aus derselben Stromdichtegrenze, an der auch ``design_point_losses`` haengt:
    thermisch zulaessig ist ein Strangstrom ``I_s,max``; momentbildend ist davon
    nur ``sqrt(I_s,max^2 - i_mag^2)``.
    """
    t_geo = ema_thermal.rated_torque(geom, axial_mm, kuehlung)
    kt    = max(float(bp["Kt_Nm_per_A"]), 1e-9)
    i_max = t_geo / kt                                  # Strangstrom bei T_geo
    i_mag = float(bp["i_mag_A"])
    if i_mag >= i_max:
        t_th = 0.0                                       # Magnetisierung frisst alles
    else:
        t_th = t_geo * math.sqrt(max(i_max ** 2 - i_mag ** 2, 0.0)) / i_max
    # Und die zweite Grenze: was der Umrichter hergibt. Ohne sie stand hier ein
    # Moment, fuer das viermal der zulaessige Strom noetig gewesen waere.
    return ema_thermal.mit_umrichtergrenze(
        t_th, lambda i: kt * math.sqrt(max(i ** 2 - i_mag ** 2, 0.0)))


# ── Massen und Kosten ─────────────────────────────────────────────────────────

def massen_und_kosten(payload: dict) -> dict:
    """Wie ``ema_screen.massen_und_kosten``, aber ohne Magnete und mit Kaefig.

    Der Kaefig verdraengt Laeufereisen (die Nut ist gefraest, nicht zusaetzlich)
    und bringt sein eigenes Material ein. Magnetmasse und Magnetkosten entfallen
    **ersatzlos** -- das ist der eine grosse Vorteil dieser Bauart und er muss in
    der Bilanz sichtbar sein.
    """
    import ema_screen

    basis = ema_screen.massen_und_kosten(payload)
    geom  = payload.get("geom", {})
    L     = float(geom.get("axialLen") or payload.get("axial_len") or 80.0)
    kf    = kaefig(geom, L)
    mat   = HAIRPIN_MATS.get(payload.get("barMat") or geom.get("barMat")
                             or KAEFIG_VORGABE, HAIRPIN_MATS[KAEFIG_VORGABE])
    lam   = LAMINATES.get(payload.get("rotor_lam", "m270_35a"), LAMINATES["m270_35a"])

    v_nut_mm3 = kf["n_stab"] * kf["A_stab_mm2"] * kf["l_stab_mm"]
    v_ring_mm3 = 2.0 * kf["A_ring_mm2"] * 2.0 * math.pi * kf["r_ring_mm"]
    v_kaefig = (v_nut_mm3 + v_ring_mm3) * 1e-9                    # m^3
    m_kaefig = v_kaefig * float(mat["density"])
    m_rot_fe = max(0.0, float(basis["rotoreisen_kg"])
                   - v_nut_mm3 * 1e-9 * float(lam["density"]))

    preis = ema_screen.PREISE_EUR_KG.get(
        "alu" if float(mat["density"]) < 5000 else "kupfer", 10.0)
    kosten = dict(basis["kosten"])
    kosten["magnet_EUR"] = 0.0
    kosten["kaefig_EUR"] = round(m_kaefig * preis, 0)
    kosten["stahl_EUR"] = round(
        (m_rot_fe + float(basis["statoreisen_kg"]) + float(basis["welle_kg"]))
        * ema_screen.PREISE_EUR_KG["stahl"], 0)
    kosten["gesamt_EUR"] = round(sum(v for k, v in kosten.items()
                                     if k != "gesamt_EUR"), 0)

    gesamt = (m_kaefig + m_rot_fe + float(basis["welle_kg"])
              + float(basis["statoreisen_kg"]) + float(basis["kupfer_kg"]))
    aus = dict(basis)
    aus.update({
        "magnet_kg":     0.0,
        "kaefig_kg":     round(m_kaefig, 3),
        "rotoreisen_kg": round(m_rot_fe, 2),
        "gesamt_kg":     round(gesamt, 2),
        "kosten":        kosten,
        "hinweis": basis["hinweis"] + " Kein Magnet: Magnetmasse und -kosten entfallen.",
    })
    return aus


# ── Laeuferfestigkeit: der Steg ueber der Kaefignut ───────────────────────────

def steg_check(geom: dict, axial_mm: float, mat: dict, n_max: float,
               stabmaterial: str | None = None) -> dict:
    """Fliehkraft am Steg ueber der Kaefignut.

    ``ema_rotorcheck.rotor_layout_check`` prueft **Magnettaschen** und gilt fuer
    einen Kaefiglaeufer nicht -- es gibt dort keine. Die Ringspannung an der
    Wellenbohrung dagegen gilt unveraendert weiter (``rotor_stress_check``, reine
    Ringformel ueber ``shaftD``/``rotorOD``); der Kerbfaktor ``KT_POCKET`` steht
    dort fuer die scharfe Taschenecke und passt der Groesse nach auch zur
    Nutecke.

    Die eine Stelle, die dem Kaefiglaeufer **eigen** ist, ist der geschlossene
    Steg ueber der Nut: er haelt den Stab. Der Zahn selbst haengt nicht daran --
    er sitzt mit seinem Fuss am Joch. Gerechnet wird der Steg deshalb als
    **beidseitig eingespannter Balken** ueber der Nutbreite, belastet von der
    Fliehkraft des Stabes (plus der eigenen):

        q = F / b ,  M_max = q*b^2/12 ,  W = L*t^2/6
        sigma = M/W = F*b / (2*L*t^2)
    """
    kf     = kaefig(geom, axial_mm)
    stab   = HAIRPIN_MATS.get(stabmaterial or geom.get("barMat") or KAEFIG_VORGABE,
                              HAIRPIN_MATS[KAEFIG_VORGABE])
    rho_fe = float(mat.get("density", 7650.0))
    sig_y  = float(mat.get("yield_mpa", 340.0))
    L_m    = float(axial_mm) * 1e-3
    w      = 2.0 * math.pi * float(n_max) / 60.0
    r_rot  = float(geom["rotorOD"]) / 2.0
    t_m    = KAEFIG_STEG_MM * 1e-3
    b_m    = kf["stabbreite_mm"] * 1e-3

    r_stab = (r_rot - KAEFIG_STEG_MM - kf["nuttiefe_mm"] / 2.0) * 1e-3
    m_stab = float(stab["density"]) * (kf["A_stab_mm2"] * 1e-6) * L_m
    m_steg = rho_fe * b_m * t_m * L_m
    f_z    = (m_stab * r_stab + m_steg * (r_rot - KAEFIG_STEG_MM / 2.0) * 1e-3) * w ** 2

    sigma = f_z * b_m / max(2.0 * L_m * t_m ** 2, 1e-15) / 1e6      # [MPa]
    sf    = sig_y / max(sigma, 1e-9)
    return {
        "ok": sf >= 1.3,
        "steg_mm": KAEFIG_STEG_MM,
        "nutbreite_mm": kf["stabbreite_mm"],
        "F_stab_N": round(f_z, 1),
        "sigma_steg_MPa": round(sigma, 1),
        "safety_factor": round(sf, 2),
        "level": "PASS" if sf >= 1.3 else ("WARN" if sf >= 1.0 else "FAIL"),
        "hinweis": ("Steg ueber der Kaefignut als beidseitig eingespannter Balken; "
                    "der Zahn haengt nicht daran (Fuss am Joch). Magnettaschen "
                    "gibt es hier nicht -- die Bohrungs-Ringspannung prueft "
                    "weiterhin rotor_stress_check."),
    }
