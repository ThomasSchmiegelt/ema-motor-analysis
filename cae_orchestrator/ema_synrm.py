"""Reluktanzmaschine (SynRM) -- analytisch, in der Hauskonvention.

Was die SynRM von den anderen drei unterscheidet
-------------------------------------------------

Sie hat **keinen eingepraegten Fluss**. Keine Magnete, keinen Kaefig, keine
Erregerwicklung -- nichts, was von sich aus ein Luftspaltfeld macht. Ihr Moment
kommt allein daraus, dass der Laeufer in einer Richtung leichter magnetisierbar
ist als in der anderen:

    T = 1,5 * p * (Ld - Lq) * i_d * i_q

Das ist **derselbe Reluktanzterm**, den die IPM auch hat -- nur ohne den
Magnetterm davor. In der Hauskonvention (``estimate_saliency``: d-Achse durch
die Barrieren, also hoher Widerstand; q-Achse durch das Eisen) ist ``Lq > Ld``,
und ``i_d`` ist negativ. Die SynRM ist damit rechnerisch genau die IPM mit
``psi_pm = 0``, und genau so wird sie hier gerechnet: kein zweites Momentgesetz,
sondern dasselbe mit einem Glied weniger. Nur so bleibt der Paarvergleich einer.

Die Folge, die in der Tabelle stehen muss
------------------------------------------

**``Kt`` ist bei der SynRM keine Konstante.** Bei PSM, ASM und EESM ist das
Moment dem Strom proportional (der Fluss kommt von woanders); hier waechst es
mit dem **Quadrat** des Stroms, weil derselbe Strom erst den Fluss aufbauen und
dann das Moment machen muss:

    T(I) = c_rel * I^2 / 2        bei MTPA (i_d = i_q = I/sqrt(2))
    Kt(I) = T/I = c_rel * I / 2

Ein ``Kt``, das ohne Betriebspunkt dasteht, ist bei dieser Bauart also sinnlos.
``betriebspunkt`` gibt es deshalb immer mit dem Strom heraus, an dem es gilt,
und ``Kt_konstant`` sagt ausdruecklich ``False``.

Die Normierungsbruecke
-----------------------

``Ld``/``Lq`` aus ``compute_advanced_em`` sind **physikalische** Induktivitaeten
(N_ph = slots/3, eine Windung je Nut), die Stroeme des Hauses sind normiert
(s. ``ema_asm.k_norm``). Das Moment ist invariant, wenn der
Reluktanzkoeffizient mit ``k_norm^2`` umgerechnet wird -- die Stroeme gehen
quadratisch ein, nicht linear wie bei der ASM. Wer hier ``k_norm`` statt
``k_norm^2`` nimmt, bekommt ein Moment, das um den Faktor 4 danebenliegt und
nicht widerspricht; ``test_synrm`` nagelt die Invarianz fest.

Was diese Stufe NICHT kann
---------------------------

Keine Saettigung (die q-Achse einer SynRM saettigt frueh, und genau das
begrenzt ihr Moment in der Wirklichkeit), keine Rippel-Aussage, keinen
Feldlauf. Die Barrieren sind ueber ``estimate_saliency`` und das recherchierte
Band in ``ema_referenz`` erfasst, nicht ueber ihre Einzelgeometrie.
"""

from __future__ import annotations

import math

import ema_analysis
import ema_thermal
from ema_analysis import MU0, compute_performance

# Wicklungskonvention -- identisch zu ``_analytical_Barm``, ``ema_asm`` und
# ``compute_advanced_em``.
K_W = 0.95
K_CARTER = 1.15

# Kleinstes gerechnetes Salienzverhaeltnis. Darunter ist die Maschine keine
# Reluktanzmaschine mehr, sondern eine Rundlaeufermaschine ohne Erregung -- also
# eine, die gar kein Moment macht. Das wird gesagt, nicht gerechnet.
XI_MIN = 1.15


def k_norm(geom: dict) -> float:
    """Bruecke Hausskala <-> physikalische Skala (s. ``ema_asm.k_norm``)."""
    import ema_asm
    return ema_asm.k_norm(geom)


def induktivitaeten(geom: dict, axial_mm: float) -> dict:
    """``Ld``, ``Lq`` und ``xi`` -- aus DERSELBEN Formel wie ``compute_advanced_em``.

    Die Barrieren sind Luft: im d-Pfad steht ``magThick`` (die Barrierenbreite)
    ohne den Magnet-``mu_r``. Bei ``mu_r = 1,05`` ist das fast dasselbe, aber
    „fast dasselbe" ist keine Begruendung -- eine Barriere ist Luft, und so
    steht sie hier.
    """
    p = max(int(geom["p"]), 1)
    n_slots = int(geom["slots"])
    l_ax = float(axial_mm) / 1000.0
    r_gap = ema_analysis.r_gap_m(geom)
    g = ema_analysis.luftspalt_mm(geom) / 1000.0
    h_barriere = float(geom.get("magThick", 8.0)) / 1000.0
    n_ph = max(n_slots / 3.0, 1.0)

    g_eff_d = K_CARTER * g + h_barriere            # Barriere = Luft, mu_r = 1
    ld = (1.5 * (4 / math.pi) * MU0 * (n_ph * K_W) ** 2
          * (r_gap * l_ax) / (p ** 2 * max(g_eff_d, 1e-9)))
    xi = max(float(ema_analysis.estimate_saliency(geom)), 1.0)
    return {"Ld_H": ld, "Lq_H": xi * ld, "xi": xi,
            "g_eff_d_mm": round(1000.0 * g_eff_d, 3)}


def reluktanzkoeffizient(geom: dict, axial_mm: float) -> float:
    """``c_rel`` [Nm/A^2] in der **Hausskala**: ``T = c_rel * i_d * i_q``.

    ``k_norm`` geht QUADRATISCH ein, weil beide Stroeme umgerechnet werden.
    """
    ind = induktivitaeten(geom, axial_mm)
    p = max(int(geom["p"]), 1)
    kn = k_norm(geom)
    return 1.5 * p * (ind["Lq_H"] - ind["Ld_H"]) / max(kn * kn, 1e-18)


def betriebspunkt(geom: dict, axial_mm: float, rpm: float, last_nm: float) -> dict:
    """Stationaerer Punkt bei MTPA: ``i_d = i_q = I/sqrt(2)``.

    Ohne Magnetfluss ist MTPA genau die Winkelhalbierende -- das ist keine
    Naeherung, sondern das Maximum von ``i_d*i_q`` bei festem ``i_d^2+i_q^2``.
    """
    p = max(int(geom["p"]), 1)
    ind = induktivitaeten(geom, axial_mm)
    c_rel = reluktanzkoeffizient(geom, axial_mm)
    t_soll = float(last_nm) + ema_analysis.DQ_TORQUE_MARGIN_NM

    if ind["xi"] < XI_MIN or c_rel <= 0:
        return {"ok": False,
                "grund": (f"Salienz {ind['xi']:.2f} unter {XI_MIN}: ohne "
                          f"Reluktanzunterschied gibt es kein Moment, und ein "
                          f"gerechnetes waere keines")}

    i_roh = math.sqrt(2.0 * t_soll / c_rel)
    i_s = min(i_roh, ema_analysis.INVERTER_I_MAX)
    am_limit = i_roh > i_s
    i_d = i_q = i_s / math.sqrt(2.0)
    t_ist = c_rel * i_d * i_q

    # Das Luftspaltfeld ist hier ein ERGEBNIS des Stroms, nicht seine Ursache.
    # Es wird ueber die q-Achse (Eisenpfad) gebildet, weil dort der Fluss
    # tatsaechlich hindurchgeht.
    kn = k_norm(geom)
    psi_q = ind["Lq_H"] * (i_q / kn)                       # Wb, physikalisch
    b_gap = psi_q * p / (2.0 * K_W * max(int(geom["slots"]) / 3.0, 1.0)
                         * ema_analysis.r_gap_m(geom)
                         * max(float(axial_mm) / 1000.0, 1e-6))
    perf = compute_performance(geom, max(b_gap, 1e-6), rpm=rpm, axial_mm=axial_mm)

    return {
        "ok": True,
        "Ld_mH": round(1000.0 * ind["Ld_H"], 4),
        "Lq_mH": round(1000.0 * ind["Lq_H"], 4),
        "xi": round(ind["xi"], 3),
        "c_rel_Nm_per_A2": c_rel,
        "i_d_A": round(i_d, 1), "i_q_A": round(i_q, 1),
        # Der d-Strom ist hier, was bei der ASM der Magnetisierungsstrom ist:
        # er baut den Fluss auf und macht kein Moment. Unter diesem Namen kann
        # ``dauermoment`` denselben thermischen Weg gehen wie ASM und PSM --
        # ein zweiter waere ein zweites Ergebnis fuer dieselbe Frage.
        "i_mag_A": round(i_d, 1),
        "I_s_A": round(i_s, 1),
        "strom_limit": bool(am_limit),
        "T_ist_Nm": round(t_ist, 1),
        # Kt am Betriebspunkt -- und der Hinweis, dass es keine Konstante ist.
        "Kt_Nm_per_A": round(t_ist / max(i_s, 1e-9), 5),
        "Kt_konstant": False,
        "B_gap_T": round(b_gap, 4),
        "rel_anteil_pct": 100.0,      # das GANZE Moment ist Reluktanzmoment
        "perf": perf,
    }


def verluste(geom: dict, axial_mm: float, rpm: float, last_nm: float,
             bp: dict, rot_lam: dict, st_lam: dict, hp_mat: dict,
             kuehlung: str) -> dict:
    """Verluste am Betriebspunkt -- auf ``design_point_losses`` aufgesetzt.

    Zwei Aenderungen gegenueber der PSM, beide zwingend:

    * **Statorkupfer** steigt mit ``(I_s/i_q)^2 = 2``: die SynRM braucht
      denselben Betrag an d-Strom wie an q-Strom, und der d-Strom macht kein
      Moment, sondern nur den Fluss. Das ist ihr Preis, und er ist genau ein
      Faktor 2 im Kupfer -- nicht geschaetzt, sondern die Folge von MTPA.
    * **Kein Magnetwirbelstrom** (kein Magnet) und **kein Laeuferverlust**
      (keine Laeuferwicklung). Der Laeufer der SynRM ist der verlustaermste von
      allen vier Bauarten; das ist ihr eigentlicher Vorteil.
    """
    mag_platzhalter = {"rho_el": 1.4e-6, "density": 7600.0, "label": "—"}
    basis = ema_thermal.design_point_losses(geom, axial_mm, rpm, last_nm,
                                            bp["perf"], rot_lam, st_lam, hp_mat,
                                            mag_platzhalter, kuehlung)
    faktor = (bp["I_s_A"] / max(bp["i_q_A"], 1e-9)) ** 2       # = 2 bei MTPA
    p_cu = float(basis["P_Cu"]) * faktor
    p_total = (p_cu + float(basis["P_Fe_stator"]) + float(basis["P_Fe_rotor"])
               + float(basis["P_Bearing"]))
    aus = dict(basis)
    aus.update({
        "P_Cu": round(p_cu, 1),
        "P_Cu_d_anteil": round(p_cu - float(basis["P_Cu"]), 1),
        "P_Mag_eddy": 0.0,          # kein Magnet
        "P_Laeufer": 0.0,           # keine Laeuferwicklung
        "P_total": round(p_total, 1),
    })
    return aus


def dauermoment(geom: dict, axial_mm: float, kuehlung: str, bp: dict) -> float:
    """S1-Dauermoment [Nm] der SynRM.

    ``ema_thermal.rated_torque`` gibt das **kuehlbare** Moment aus der
    Luftspalt-Schubspannung: ``T = 2*sigma*V_Laeufer``. Es unterstellt, dass der
    ganze zulaessige Strom Moment macht. Bei MTPA macht das nur ``i_q``, und
    ``i_d = i_q`` baut den Fluss auf:

        T_dauer = T_kuehlbar * i_q / I_s = T_kuehlbar / sqrt(2)

    Das Verhaeltnis ist **unabhaengig vom Betriebspunkt** -- bei MTPA ist es
    immer 1/sqrt(2), auch an der thermischen Grenze. Genau deshalb steht hier
    eine eigene Funktion und nicht die der ASM: deren Abschlag rechnet mit
    ``i_max = T_kuehlbar / Kt``, und ``Kt`` ist bei der SynRM keine Konstante.
    Ueber diesen Weg kam das Dauermoment gemessen bei 178,7 Nm heraus -- so
    hoch wie bei der PSM, was fuer eine Maschine ohne eingepraegten Fluss
    offensichtlich nicht stimmt, aber nirgends widersprach.
    """
    t_geo = ema_thermal.rated_torque(geom, axial_mm, kuehlung)
    i_q = float(bp.get("i_q_A", 0.0))
    i_s = max(float(bp.get("I_s_A", 0.0)), 1e-9)
    return t_geo * min(i_q / i_s, 1.0)


def massen_und_kosten(payload: dict) -> dict:
    """Massen und Kosten -- ohne Magnete UND ohne Laeuferwicklung.

    Nicht ueber ``ema_asm``: der wuerde einen Kaefig einrechnen, den die SynRM
    nicht hat. Ihr Laeufer ist blankes Blech mit Barrieren -- die billigste und
    leichteste Laeuferbauart der vier, und genau das muss in der Bilanz stehen.

    Die Barrieren nehmen Eisen weg. Ihr Volumen kommt aus ``ema_topology``,
    derselben Quelle, aus der auch die Zeichnung und die 2-D-Rasterung ihre
    Barrieren holen -- eine eigene Abschaetzung waere eine achte Kopie.
    """
    import ema_screen
    from ema_pipeline import LAMINATES
    from ema_topology import magnet_legs

    basis = ema_screen.massen_und_kosten(payload)
    geom = payload.get("geom", {})
    L = float(geom.get("axialLen") or payload.get("axial_len") or 80.0)
    lam = LAMINATES.get(payload.get("rotor_lam", "m270_35a"), LAMINATES["m270_35a"])

    legs, _meta = magnet_legs(geom)
    poles = 2 * max(int(geom.get("p", 1)), 1)
    v_barr_mm3 = poles * sum(lg.length * lg.thickness for lg in legs) * L
    m_rot_fe = max(0.0, float(basis["rotoreisen_kg"])
                   - v_barr_mm3 * 1e-9 * float(lam["density"]))

    kosten = dict(basis["kosten"])
    kosten["magnet_EUR"] = 0.0
    kosten["stahl_EUR"] = round(
        (m_rot_fe + float(basis["statoreisen_kg"]) + float(basis["welle_kg"]))
        * ema_screen.PREISE_EUR_KG["stahl"], 0)
    kosten["gesamt_EUR"] = round(sum(v for k, v in kosten.items()
                                     if k != "gesamt_EUR"), 0)

    gesamt = (m_rot_fe + float(basis["welle_kg"]) + float(basis["statoreisen_kg"])
              + float(basis["kupfer_kg"]))
    aus = dict(basis)
    aus.update({
        "magnet_kg": 0.0,
        "rotoreisen_kg": round(m_rot_fe, 2),
        "gesamt_kg": round(gesamt, 2),
        "kosten": kosten,
        "hinweis": basis["hinweis"] + " Kein Magnet und keine Laeuferwicklung: "
                                      "der Laeufer ist blankes Blech mit Barrieren.",
    })
    return aus
