"""Fremderregte Synchronmaschine (EESM) -- analytisch, in der Hauskonvention.

Was die EESM von den anderen drei unterscheidet
------------------------------------------------

Sie ist die einzige Bauart, bei der der Luftspaltfluss **eingestellt** wird.
PSM: der Magnet gibt ihn vor, immer. ASM: der Stator baut ihn auf, mit
Blindstrom, den er dauernd mittraegt. SynRM: es gibt gar keinen eingepraegten
Fluss. EESM: eine Gleichstromwicklung im Laeufer macht ihn, und wieviel davon,
ist eine Stellgroesse.

Das entscheidet drei Dinge, und alle drei gehoeren in den Paarvergleich:

* **Im Feldschwaechbereich** kostet der Fluss nichts, den man abschaltet.
  Eine PSM muss ihren Magnetfluss mit d-Strom niederhalten -- dauernd, und
  ohne Moment dafuer. Die EESM dreht den Erregerstrom herunter.
* **Kein Kurzschlussmoment.** Faellt der Umrichter aus, wird die Erregung
  abgeschaltet und die Maschine ist feldfrei. Bei einer PSM dreht der Magnet
  weiter und erzeugt Bremsmoment und Spannung.
* **Der Preis** sind Schleifringe (oder ein Drehuebertrager) und ein Laeufer,
  der Verluste macht -- an der thermisch schlechtesten Stelle, wie bei der ASM.

Wo der Magnetisierungsstrom sitzt -- der eigentliche Unterschied zur ASM
-------------------------------------------------------------------------

Beide haben keine Magnete, und beide brauchen einen Strom, um das Feld zu
machen. Aber:

    ASM:  der Magnetisierungsstrom liegt im STATOR, als Blindstrom, dauernd,
          und er addiert sich geometrisch zum Momentstrom (I_s = hypot(i_mag, i_q)).
    EESM: er liegt im LAEUFER, als Gleichstrom. Der Stator fuehrt nur i_q.

Deshalb braucht die EESM bei gleichem Moment **weniger Statorstrom** als die
ASM -- und dafuer eine eigene Wicklung mit eigener Kuehlung. Genau diese
Abwaegung soll die Achse „Maschinenart" zeigen koennen, und dafuer muss der
Erregerkreis wirklich gerechnet werden und nicht pauschal angesetzt.

Die Erregerwicklung, und warum ihre Verluste NICHT von der Windungszahl abhaengen
----------------------------------------------------------------------------------

Gebraucht wird eine Durchflutung je Pol, ``F_pol = B * g_eff / mu0``. Ob sie aus
vielen Windungen mit wenig Strom oder wenigen mit viel Strom kommt, ist eine
Wickelentscheidung -- die Verlustleistung ist dieselbe:

    P_f = I_f^2 * R_f  mit  R_f = rho * N_f^2 * l_w / (k_fuell * A_fenster)
        = (N_f * I_f)^2 * rho * l_w / (k_fuell * A_fenster)
        = F_pol^2 * rho * l_w / (k_fuell * A_fenster)          -- ohne N_f

Das ist keine Vereinfachung, sondern eine Kuerzung. Was sehr wohl von der
Wahl abhaengt, ist der **Schleifringverlust** (``2 * U_buerste * I_f``), denn
der geht linear mit dem Strom. Deshalb steht ``fieldCurrentA`` als Groesse da,
und der Bericht sagt, welcher Teil von ihr abhaengt und welcher nicht.

Was diese Stufe NICHT kann
---------------------------

Keine Saettigung im Polschuh, keine Daempferwicklung, keinen Feldlauf, keinen
Drehuebertrager als Alternative zum Schleifring. Der Laeufer ist als
Schenkelpollaeufer angesetzt; ein Vollpollaeufer haette ein anderes
Wickelfenster.
"""

from __future__ import annotations

import math

import ema_analysis
import ema_thermal
from ema_analysis import MU0, compute_performance

# Wicklungskonvention -- identisch zu ``ema_asm`` und ``_analytical_Barm``.
K_W = 0.95
K_CARTER = 1.15

# Ziel-Luftspaltfeld wie bei der ASM. Es ist hier eine STELLGROESSE, kein
# Datenblattwert -- ``betriebspunkt`` gibt darum auch aus, was ein anderer Wert
# kostete.
B_ZIEL_T = 0.85
B_ZIEL_SPANNE = (0.55, 1.05)
B_ZAHN_MAX_T = 1.8

# Schenkelpollaeufer: Anteil der Polteilung, den der Polschuh einnimmt. Der Rest
# ist Wickelfenster. 0,65-0,72 ist der uebliche Bereich; darunter wird der
# Polschuh zu schmal fuer den Fluss, darueber bleibt kein Platz zum Wickeln.
POLBEDECKUNG = 0.68

# Nutfuellfaktor der Erregerwicklung: gewickelter Runddraht, wie in
# ``ema_wicklung.FUELL_RUNDDRAHT``. Dieselbe Bauart, derselbe Wert -- eine
# zweite Zahl waere eine zweite Wahrheit.
def _fuellfaktor() -> float:
    import ema_wicklung
    return ema_wicklung.FUELL_RUNDDRAHT


# Buerstenspannungsabfall je Kontakt [V]. Zwei Kontakte je Stromkreis.
U_BUERSTE_V = 1.0

# Vorgabe fuer den Erregerstrom [A]. Sie bestimmt NUR den Schleifringverlust
# (s. Modulkopf), nicht den Kupferverlust der Erregerwicklung.
I_F_VORGABE_A = 15.0

# Stromdichte der Erregerwicklung [A/mm^2]. **Sie** bemisst die Wicklung, nicht
# das Wickelfenster.
#
# Der Unterschied ist gemessen und gross: eine Wicklung, die das ganze Fenster
# fuellt, kam an einem 190-mm-Laeufer auf 15,7 kg Erregerkupfer bei 0,7 A/mm^2
# und 16 W Verlust -- eine Maschine, die niemand baut. Bemessen ueber die
# Stromdichte sind es 2,3 kg und 110 W. Beide Rechnungen sind in sich
# widerspruchsfrei; nur eine beschreibt eine Auslegung.
#
# 4-6 A/mm^2 ist der uebliche Bereich fuer eine fluessigkeitsgekuehlte
# Erregerwicklung, 2-3 fuer eine luftgekuehlte. Das Fenster bleibt die
# Schranke: passt der Querschnitt nicht hinein, wird das gesagt.
J_F_VORGABE_APMM2 = 5.0

ERREGER_MAT = "cu_etp"


def k_norm(geom: dict) -> float:
    """Bruecke Hausskala <-> physikalische Skala (s. ``ema_asm.k_norm``)."""
    import ema_asm
    return ema_asm.k_norm(geom)


def ziel_feld(geom: dict) -> float:
    """Ziel-Luftspaltfeld [T] -- gesetzt oder Vorgabe, gedeckelt durch den Zahn."""
    b = float(geom.get("bZielT") or B_ZIEL_T)
    b = min(max(b, B_ZIEL_SPANNE[0]), B_ZIEL_SPANNE[1])
    return min(b, B_ZAHN_MAX_T / 2.0)


def polgeometrie(geom: dict, axial_mm: float) -> dict:
    """Polschuh und Wickelfenster des Schenkelpollaeufers. Alles in mm/mm^2."""
    import ema_radien
    r = ema_radien.radien(geom)
    p = max(int(geom["p"]), 1)
    poles = 2 * p
    r_rot = r["r_rotor_gap_mm"]
    r_wel = max(r["r_welle_mm"], 1.0)
    b_m = ziel_feld(geom)
    L = float(axial_mm)

    tau_pol = 2.0 * math.pi * r_rot / poles                  # Polteilung [mm]
    b_pol = POLBEDECKUNG * tau_pol                           # Polschuhbreite
    fenster_b = max(tau_pol - b_pol, 1.0)                    # Breite zwischen den Polen

    # Laeuferjoch aus dem Fluss je Pol, wie bei der ASM (``ema_asm.kaefig``):
    #   Phi_pol = (2/pi)*B*tau*L , h_joch = Phi/(2*B_joch*L)
    phi_pol = (2.0 / math.pi) * b_m * tau_pol * L * 1e-6      # Wb
    h_joch = max(phi_pol / (2.0 * 1.5 * (L * 1e-3)) * 1e3, 3.0)

    h_fenster = max(r_rot - r_wel - h_joch - 2.0, 2.0)        # radiale Fensterhoehe
    a_fenster = fenster_b * h_fenster                          # mm^2, je Pol
    # Mittlere Windungslaenge: einmal um den Polkoerper (Laenge + Breite).
    l_windung = 2.0 * (L + b_pol) + 2.0 * fenster_b

    return {"poles": poles, "tau_pol_mm": round(tau_pol, 2),
            "b_pol_mm": round(b_pol, 2), "fenster_b_mm": round(fenster_b, 2),
            "fenster_h_mm": round(h_fenster, 2), "A_fenster_mm2": round(a_fenster, 1),
            "h_joch_mm": round(h_joch, 2), "l_windung_mm": round(l_windung, 1),
            "eng": a_fenster < 50.0}


def erregung(geom: dict, axial_mm: float, i_f_A: float = 0.0,
             j_f_Apmm2: float = 0.0) -> dict:
    """Erregerdurchflutung, Erregerverlust und Schleifringverlust.

    ``F_pol`` folgt aus demselben Magnetkreis wie ``ema_asm.magnetisierungsstrom``:
    dieselbe Carter-Korrektur, dasselbe Ziel-Luftspaltfeld. Nur sitzt die
    Durchflutung hier im Laeufer und wird mit Gleichstrom gemacht.
    """
    from ema_pipeline import HAIRPIN_MATS

    pg = polgeometrie(geom, axial_mm)
    b_m = ziel_feld(geom)
    g = ema_analysis.luftspalt_mm(geom) / 1000.0
    g_eff = K_CARTER * g

    # Durchflutung je Pol fuer die Grundwelle. Der Faktor 2/pi bringt die
    # rechteckige Polfeldform auf ihre Grundwelle -- ohne ihn kaeme die
    # Erregung um 27 % zu klein heraus.
    f_pol = (b_m * g_eff / MU0) * (math.pi / 2.0) / 2.0        # A je Pol (Amplitude)

    mat = HAIRPIN_MATS.get(geom.get("fieldMat") or ERREGER_MAT,
                           HAIRPIN_MATS[ERREGER_MAT])
    rho = float(mat["rho_el"])
    a_fenster = pg["A_fenster_mm2"] * 1e-6                      # m^2, geometrisch
    l_w = pg["l_windung_mm"] * 1e-3                             # m
    kf = _fuellfaktor()

    # Die Wicklung wird ueber die STROMDICHTE bemessen, das Fenster ist die
    # Schranke (s. J_F_VORGABE_APMM2). Der noetige Kupferquerschnitt je Pol:
    #   A_cu = F_pol / J          [A / (A/mm^2)]
    j_f = float(j_f_Apmm2) if j_f_Apmm2 and j_f_Apmm2 > 0 else J_F_VORGABE_APMM2
    j_f = min(max(j_f, 0.5), 20.0)
    a_cu = f_pol / (j_f * 1e6)                                  # m^2 je Pol
    a_cu_max = kf * a_fenster
    passt = a_cu <= a_cu_max
    if not passt:
        # Nicht still deckeln: es wird gerechnet, was hineinpasst, und die
        # dann noetige (hoehere) Stromdichte steht im Ergebnis.
        a_cu = a_cu_max
        j_f = f_pol / max(a_cu * 1e6, 1e-12)

    # P_f = F_pol^2 * rho * l_w / A_cu -- ohne Windungszahl, s. Modulkopf.
    # Gleichwertig: P_f = F_pol * J * rho * l_w.
    p_f_pol = f_pol ** 2 * rho * l_w / max(a_cu, 1e-12)
    p_f = p_f_pol * pg["poles"]

    i_f = float(i_f_A) if i_f_A and i_f_A > 0 else I_F_VORGABE_A
    n_f = f_pol / max(i_f, 1e-6)                                # Windungen je Pol
    p_ring = 2.0 * U_BUERSTE_V * i_f

    return {
        "B_m_T": b_m, "F_pol_A": round(f_pol, 1),
        "P_erreger_W": round(p_f, 1), "P_schleifring_W": round(p_ring, 1),
        "P_laeufer_W": round(p_f + p_ring, 1),
        "I_f_A": round(i_f, 2), "N_f_windungen": round(n_f, 1),
        "J_f_Apmm2": round(j_f, 2),
        "A_cu_mm2": round(a_cu * 1e6, 1),
        "A_cu_max_mm2": round(a_cu_max * 1e6, 1),
        "fenster_ausl": round(a_cu / max(a_cu_max, 1e-12), 3),
        "fenster_reicht": bool(passt),
        "erregermaterial": mat["label"],
        "hinweis_stellgroesse": (
            "P_erreger haengt NICHT von der Windungszahl ab (F_pol ist die "
            "Groesse, N_f kuerzt sich heraus); P_schleifring haengt linear von "
            "I_f ab und damit sehr wohl von der Wickelentscheidung."),
        "pol": pg,
    }


def betriebspunkt(geom: dict, axial_mm: float, rpm: float, last_nm: float,
                  i_f_A: float = 0.0, j_f_Apmm2: float = 0.0) -> dict:
    """Stationaerer Nennpunkt. Der Stator fuehrt NUR den Momentstrom.

    Das ist der Unterschied zur ASM in einer Zeile: dort steht
    ``I_s = hypot(i_mag, i_q)``, hier ``I_s = i_q``.
    """
    p = max(int(geom["p"]), 1)
    L = float(axial_mm)
    err = erregung(geom, L, i_f_A, j_f_Apmm2)
    perf = compute_performance(geom, err["B_m_T"], rpm=rpm, axial_mm=L)
    kt = max(float(perf["Kt_Nm_per_A"]), 1e-9)
    t_soll = float(last_nm) + ema_analysis.DQ_TORQUE_MARGIN_NM

    i_q_roh = t_soll / kt
    i_q = min(i_q_roh, ema_analysis.INVERTER_I_MAX)
    i_s = i_q                                   # kein Magnetisierungsstrom im Stator
    am_limit = i_s >= 0.999 * ema_analysis.INVERTER_I_MAX or i_q_roh > i_q
    t_ist = min(t_soll, kt * i_q)

    return {
        "ok": not err["pol"]["eng"] and err["fenster_reicht"],
        "grund": (
            f"Kein Platz fuer die Erregerwicklung: Wickelfenster "
            f"{err['pol']['A_fenster_mm2']:.0f} mm^2" if err["pol"]["eng"] else
            (f"Erregerwicklung passt nicht: {err['A_cu_mm2']:.0f} mm^2 noetig, "
             f"{err['A_cu_max_mm2']:.0f} mm^2 nutzbar -- die Stromdichte "
             f"stiege auf {err['J_f_Apmm2']:.1f} A/mm^2"
             if not err["fenster_reicht"] else "")),
        "B_m_T": round(err["B_m_T"], 4),
        "i_q_A": round(i_q, 1), "I_s_A": round(i_s, 1),
        "i_mag_A": 0.0,          # ausgerechnet, nicht fehlend: er sitzt im Laeufer
        "mag_anteil": 0.0,
        "strom_limit": bool(am_limit),
        "Kt_Nm_per_A": round(kt, 5),
        "Kt_konstant": True,     # solange die Erregung steht
        "psi_Wb": float(perf["psi_pm_Wb"]),
        "T_ist_Nm": round(t_ist, 1),
        "F_pol_A": err["F_pol_A"],
        "I_f_A": err["I_f_A"], "N_f_windungen": err["N_f_windungen"],
        "J_f_Apmm2": err["J_f_Apmm2"],
        "A_cu_mm2": err["A_cu_mm2"], "fenster_ausl": err["fenster_ausl"],
        "P_erreger_W": err["P_erreger_W"],
        "P_schleifring_W": err["P_schleifring_W"],
        "P_laeufer_W": err["P_laeufer_W"],
        "erregung": err, "perf": perf,
    }


def verluste(geom: dict, axial_mm: float, rpm: float, last_nm: float,
             bp: dict, rot_lam: dict, st_lam: dict, hp_mat: dict,
             kuehlung: str) -> dict:
    """Verluste am Betriebspunkt -- auf ``design_point_losses`` aufgesetzt.

    * **Statorkupfer bleibt** wie bei der PSM: der Stator fuehrt nur ``i_q``.
      Das ist der Vorteil gegenueber der ASM und er soll unverfaelscht dastehen.
    * **Magnetwirbelstrom faellt weg** (kein Magnet).
    * **Erregung und Schleifring kommen dazu** -- im Laeufer, also an der
      thermisch schlechtesten Stelle, wie der Kaefigverlust der ASM.
    """
    mag_platzhalter = {"rho_el": 1.4e-6, "density": 7600.0, "label": "—"}
    basis = ema_thermal.design_point_losses(geom, axial_mm, rpm, last_nm,
                                            bp["perf"], rot_lam, st_lam, hp_mat,
                                            mag_platzhalter, kuehlung)
    p_laeufer = float(bp["P_laeufer_W"])
    p_total = (float(basis["P_Cu"]) + float(basis["P_Fe_stator"])
               + float(basis["P_Fe_rotor"]) + p_laeufer + float(basis["P_Bearing"]))
    aus = dict(basis)
    aus.update({
        "P_Mag_eddy": 0.0,
        "P_Erreger": float(bp["P_erreger_W"]),
        "P_Schleifring": float(bp["P_schleifring_W"]),
        "P_Laeufer": round(p_laeufer, 1),
        "P_total": round(p_total, 1),
    })
    return aus


def dauermoment(geom: dict, axial_mm: float, kuehlung: str, bp: dict) -> float:
    """Dauermoment ueber DENSELBEN thermischen Weg wie PSM, ASM und SynRM."""
    import ema_asm
    return ema_asm.dauermoment(geom, axial_mm, kuehlung, bp)


def massen_und_kosten(payload: dict) -> dict:
    """Massen und Kosten -- ohne Magnete, mit Erregerwicklung und Schleifringen."""
    import ema_screen
    from ema_pipeline import HAIRPIN_MATS, LAMINATES

    basis = ema_screen.massen_und_kosten(payload)
    geom = payload.get("geom", {})
    L = float(geom.get("axialLen") or payload.get("axial_len") or 80.0)
    pg = polgeometrie(geom, L)
    mat = HAIRPIN_MATS.get(payload.get("fieldMat") or geom.get("fieldMat")
                           or ERREGER_MAT, HAIRPIN_MATS[ERREGER_MAT])
    lam = LAMINATES.get(payload.get("rotor_lam", "m270_35a"), LAMINATES["m270_35a"])

    err = erregung(geom, L, float(payload.get("fieldCurrentA", 0) or 0),
                   float(payload.get("fieldCurrentDensity", 0) or 0))
    v_cu_mm3 = pg["poles"] * err["A_cu_mm2"] * pg["l_windung_mm"]
    m_erreger = v_cu_mm3 * 1e-9 * float(mat["density"])
    # Das Wickelfenster ist Luft im Laeuferblech -- unabhaengig davon, wieviel
    # Kupfer wirklich darin sitzt: der Platz ist aus dem Blech genommen.
    v_fenster_mm3 = pg["poles"] * pg["A_fenster_mm2"] * L
    m_rot_fe = max(0.0, float(basis["rotoreisen_kg"])
                   - v_fenster_mm3 * 1e-9 * float(lam["density"]))

    preis_cu = ema_screen.PREISE_EUR_KG["kupfer"]
    kosten = dict(basis["kosten"])
    kosten["magnet_EUR"] = 0.0
    kosten["erreger_EUR"] = round(m_erreger * preis_cu, 0)
    kosten["stahl_EUR"] = round(
        (m_rot_fe + float(basis["statoreisen_kg"]) + float(basis["welle_kg"]))
        * ema_screen.PREISE_EUR_KG["stahl"], 0)
    kosten["gesamt_EUR"] = round(sum(v for k, v in kosten.items()
                                     if k != "gesamt_EUR"), 0)

    gesamt = (m_erreger + m_rot_fe + float(basis["welle_kg"])
              + float(basis["statoreisen_kg"]) + float(basis["kupfer_kg"]))
    aus = dict(basis)
    aus.update({
        "magnet_kg": 0.0,
        "erreger_kg": round(m_erreger, 3),
        "rotoreisen_kg": round(m_rot_fe, 2),
        "gesamt_kg": round(gesamt, 2),
        "kosten": kosten,
        "hinweis": basis["hinweis"] + " Kein Magnet, dafuer eine Erregerwicklung "
                                      "im Laeufer und Schleifringe.",
    })
    return aus
