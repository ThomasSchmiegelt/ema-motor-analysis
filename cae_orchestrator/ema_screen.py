"""Stufe-A-Screener: Konzept-Vergleich mit rein analytischen Grenzwertprüfungen.

Zweck: EHE vor teuren Simulationen (Feld/Thermik/3D/Öl) aussortieren, die einen
harten physikalischen Punkt nicht erreichen können. Alles hier ist geschlossene
Mathe auf Geometrie + Materialdaten (LAMINATES/MAGNETS/HAIRPIN_MATS aus
ema_pipeline) — läuft in Millisekunden, auch ohne Server.

Prüfungen (harte Gates, pass/fail, kein Rangieren):

  1. TASCHEN-LAYOUT  — ema_rotorcheck (Kollisionen, Einbettung, Mindeststege).
  2. KRITISCHE DREHZAHL — Jeffcott-Modell (rotierender Scheibenstack als Masse
     auf Welle, 1. + 2. Biegeeigenfrequenz), Tabelle über plausible Lagerabstände.
     Das Lagermaß ist in der Geometrie NICHT enthalten → explizite Annahme, nicht
     stillschweigend "gerechnet".
  3. FLIEHKRAFT-FESTIGKEIT bei n_max:
     • Magneten: Vollscheiben-Formel Obergrenze gegen Querzug/Scherfestigkeit.
     • Rotorscheibe: exakte Lamé-Lösung rotierende Scheibe mit Bohrung an der
       Bohrung gegen Zugfestigkeit (Sicherheit ≥ 3).
  4. MASSE & KOSTEN (GROBE Schätzung, ±25–30 %): Magnetmasse ist exakt aus den
     Leg-Records; Stator/Kupfer/Vorgehensweise mit Annahmen.

Nicht hier (ehrliche Grenze): TEMPERATUR. Ohne Verluste ist jede Temperatur eine
Halbierung — Verluste braucht die Stufe-B-Pipeline (Feld + Thermik, 5–15 min).
Magnet-Density und -Festigkeit sind Materialdaten aus der Literatur (N42–N52
NdFeB), weil sie in der MAGNETS-Tabelle nicht vorkommen — Flag im Report.

Public API:
    from ema_screen import screen_design
    rep = screen_design(payload, targets=None)
"""

from __future__ import annotations

import math

from ema_topology import magnet_legs
from ema_rotorcheck import rotor_layout_check
from ema_pipeline import LAMINATES, MAGNETS, HAIRPIN_MATS

# ── Literature magnet strength data (not in the MAGNETS table) ────────────────
MAG_RHO_KG_M3   = 7600.0   # NdFeB N42–N52 typical compacted density
MAG_SHEAR_MPA   = 80.0     # transverse tensile / shear, high-grade NdFeB, conservative
# 2026 placeholder prices — for ranking, not for quotes:
PRICE_MAG_EUR_KG  = 55.0
PRICE_CU_EUR_KG   = 10.0
PRICE_STEEL_EUR_KG = 1.6

DEFAULT_TARGETS = {"n_rated": 6000.0, "n_max": 20000.0, "web_min_mm": 2.0}
SPAN_TABLE_M = (0.30, 0.40, 0.50, 0.60)   # bearing spans considered


def _rpm_to_w(n):
    return 2.0 * math.pi * n / 60.0


# ── checks ─────────────────────────────────────────────────────────────────────

def check_layout(payload: dict, t: dict) -> dict:
    geom = payload.get("geom", {})
    chk = rotor_layout_check(geom, min_web_mm=t["web_min_mm"])
    return {
        "ok": chk["ok"],
        "min_web_mm": chk["layout"]["min_web_found_mm"],
        "detail": chk["layout"],
        "fatal": chk["fatal"],
    }


def check_critical_speed(geom: dict, mat_shaft: dict, m_rotor_kg: float,
                         t: dict) -> dict:
    """Jeffcott: rotor mass as disc on simply-supported shaft, disc at mid-span."""
    D = float(geom.get("shaftD", 50.0)) / 1000.0          # m
    d = float(geom.get("shaftBoreD", 0.0)) / 1000.0       # m (hollow shaft)
    E = float(mat_shaft["E"]) * 1e6                        # Pa
    I = math.pi / 32.0 * (D**4 - (d**4 if d > 0 else 0.0)) # m⁴
    rows = []
    for Ls in SPAN_TABLE_M:
        k = 48.0 * E * I / Ls**3                            # N/m
        w1 = math.sqrt(k / m_rotor_kg)
        rows.append({"span_m": Ls,
                     "n_crit1_rpm": round(w1 * 60.0 / (2 * math.pi), 0),
                     "n_crit2_rpm": round(w1 * 2.757 * 60.0 / (2 * math.pi), 0)})
    worst = rows[-1]   # longest span → lowest criticals
    nmax = t["n_max"]
    if worst["n_crit1_rpm"] < 1.0 * nmax:
        level = "FAIL"
        why = (f"1. Kritische ({worst['n_crit1_rpm']:.0f} U/min bei "
               f"L={worst['span_m']} m) liegt IN bzw. unter dem max. "
               f"Betriebsbereich ({nmax:.0f}) — Resonanz im Laufband unvermeidbar.")
    elif worst["n_crit1_rpm"] < 1.3 * nmax:
        level = "WARN"
        why = (f"1. Kritische nur {worst['n_crit1_rpm']/nmax:.2f}× n_max — "
               f"Reservemarge < 30 % bei L={worst['span_m']} m.")
    else:
        level = "PASS"
        why = (f"1. Kritische ≥ {worst['n_crit1_rpm']/nmax:.2f}× n_max "
               f"selbst bei L={worst['span_m']} m.")
    return {"ok": level != "FAIL", "level": level, "why": why, "table": rows,
            "assumption": ("Lager maß NICHT in Geometrie enthalten — Tabelle über "
                           "Lagerabstände 0.30–0.60 m; Welle aus shaftD/shaftBOreD, "
                           "Rotor-Scheibenmasse + 5 % Anschlussmasse."),
            "m_rotor_kg": m_rotor_kg, "shaft_I_m4": I, "shaft_E_Pa": E}


def check_centrifugal(geom: dict, mat_rotor: dict, m_mag_kg: float,
                      t: dict) -> dict:
    """Fliehkraft bei n_max. Magneten: Vollscheibe (Obergrenze). Fe: exakte
    Lamé-Lösung rotierende Scheibe mit Bohrung (beide Ebenenzustände, konservativ
    = Ebenenverformung) – delegiert an ema_rotorcheck.rotor_stress_check."""
    b = float(geom["rotorOD"]) / 2.0                    # mm
    w = _rpm_to_w(t["n_max"])

    # --- Rotor disc: exakte 2D-Lame-Lösung (Single Source of Truth) ---
    from ema_rotorcheck import rotor_stress_check
    _st = rotor_stress_check(geom, mat_rotor, t)
    disc = {
        "sigma_T_bore_MPa": _st["sigma_bore_conservative_MPa"],
        "sigma_T_bore_plane_stress_MPa": _st["sigma_bore_plane_stress_MPa"],
        "sigma_T_bore_plane_strain_MPa": _st["sigma_bore_plane_strain_MPa"],
        "yield_MPa": _st["yield_mpa"],
        "safety_factor": _st["safety_factor"],
        "sf_plane_stress": _st["sf_plane_stress"],
        "ok": _st["ok"],
        "level": _st["level"],
        "note": _st["note"],
    }

    # --- Magnet: solid-disk upper bound at its outer radius ---
    from ema_topology import leg_center
    legs, _ = magnet_legs(geom)
    r_out = (max(math.hypot(*leg_center(l)) + 0.5 * (l.length + l.thickness)
                 for l in legs) or b)
    sig_nu = 0.30
    sigma_mag = 0.375 * (3.0 + sig_nu) / (1.0 + sig_nu) \
                * MAG_RHO_KG_M3 * w * w * (r_out * 1e-3) ** 2 / 1e6   # MPa
    ratio = sigma_mag / MAG_SHEAR_MPA
    mag = {
        "sigma_c_MPa": round(sigma_mag, 1),
        "allow_MPa": MAG_SHEAR_MPA,
        "utilization": round(ratio, 3),
        "ok": ratio <= 1.0,
        "level": "PASS" if ratio <= 0.5 else ("WARN" if ratio <= 1.0 else "FAIL"),
        "note": ("Vollscheiben-Obergrenze bei max. Magnetenaußenradius "
                 f"r_out={r_out:.1f} mm; Zulässige {MAG_SHEAR_MPA:.0f} MPa = "
                 "Literaturwert NdFeB (nicht in MAGNETS-Tabelle)"),
    }
    overall = "PASS" if (disc["ok"] and mag["ok"]) else \
              ("WARN" if (disc["level"] == "WARN" or mag["level"] == "WARN")
               else "FAIL")
    return {"ok": disc["ok"] and mag["ok"], "level": overall,
            "n_evaluated_rpm": t["n_max"], "magnet": mag, "disc": disc}


def check_mass_cost(payload: dict) -> dict:
    """Massen + grobe Kosten. Magnetmasse exakt (Leg-Records), Rest ±25–30 %."""
    geom = payload.get("geom", {})
    Lmm  = float(geom["axialLen"])
    boreID   = float(geom.get("statorID", geom.get("boreD", 0.0)))
    shaftD   = float(geom["shaftD"])
    rotorOD  = float(geom["rotorOD"])
    statorOD = float(geom.get("statorOD", rotorOD + 2 * 30.0))

    mat_rotor = LAMINATES.get(payload.get("rotor_lam", "m270_35a"),
                              LAMINATES["m270_35a"])
    mat_st    = LAMINATES.get(payload.get("stator_lam", "m270_35a"),
                              LAMINATES["m270_35a"])
    mat_cu    = HAIRPIN_MATS.get(payload.get("conductor", "cu_etp"),
                                 HAIRPIN_MATS["cu_etp"])

    poles = 2 * max(1, int(geom.get("p", 3)))
    legs, _ = magnet_legs(geom)
    area_leg_mm2 = sum(l.length * l.thickness for l in legs if l.placement != "surface"
                       or True)
    V_mag_mm3 = area_leg_mm2 * poles * Lmm
    V_mag_m3  = V_mag_mm3 * 1e-9
    m_mag = V_mag_m3 * MAG_RHO_KG_M3
    n_mag = poles * len(legs)

    V_rot_fe = math.pi / 4.0 * (rotorOD**2 - shaftD**2) * Lmm * 1e-9   # m³
    m_rot_fe = V_rot_fe * float(mat_rotor["density"])
    V_shaft  = math.pi / 4.0 * (shaftD**2 - float(geom.get("shaftBoreD", 0.0)) ** 2) \
               * (Lmm + 2 * 40.0) * 1e-9          # +2×Lagerstülpe (Annahme)
    m_shaft  = V_shaft * 7850.0

    V_st = math.pi / 4.0 * (statorOD**2 - boreID**2) * Lmm * 1e-9
    m_st_steel = V_st * float(mat_st["density"]) * 0.78      # − Spaltenanteil
    V_cu   = V_st * 0.30 * 0.55                              # Spalten×Füllfaktor
    m_cu   = V_cu * float(mat_cu["density"])

    m_total = m_rot_fe + m_mag + m_shaft + m_st_steel + m_cu

    def eur(m, p):
        return round(m * p, 0)

    costs = {
        "magnet_EUR": eur(m_mag, PRICE_MAG_EUR_KG),
        "kupfer_EUR": eur(m_cu, PRICE_CU_EUR_KG),
        "stahl_EUR":  eur(m_rot_fe + m_st_steel + m_shaft, PRICE_STEEL_EUR_KG),
        "total_EUR":  round((m_mag * PRICE_MAG_EUR_KG + m_cu * PRICE_CU_EUR_KG
                             + (m_rot_fe + m_st_steel + m_shaft) * PRICE_STEEL_EUR_KG), 0),
        "note": ("Placeholder-Preise 2026 (NdFeB 55 €/kg, Cu 10 €/kg, Stahl 1.6 "
                 "€/kg) — für das Rangieren, nicht als Kostenvoranschlag."),
    }
    m_rotor_dyn = round(m_rot_fe + m_mag + 0.05 * (m_rot_fe + m_mag), 2)
    return {
        "magnet_count": n_mag,
        "magnet_kg": round(m_mag, 2),
        "rotor_iron_kg": round(m_rot_fe, 1),
        "shaft_kg": round(m_shaft, 1),
        "stator_steel_kg": round(m_st_steel, 1),
        "copper_kg": round(m_cu, 1),
        "total_kg": round(m_total, 1),
        "costs_rough_EUR": costs,
        "m_rotor_dyn_kg": m_rotor_dyn,
    }


# ── aggregate ─────────────────────────────────────────────────────────────────

def screen_design(payload: dict, targets: dict | None = None) -> dict:
    t = {**DEFAULT_TARGETS, **(targets or {})}
    geom = payload.get("geom", {})
    mat_rotor = LAMINATES.get(payload.get("rotor_lam", "m270_35a"),
                              LAMINATES["m270_35a"])
    mat_shaft = LAMINATES.get("steel_42crmo4", {"E": 210000, "nu": 0.3,
                                                 "density": 7850})
    mc = check_mass_cost(payload)
    crit = check_critical_speed(geom, mat_shaft, mc["m_rotor_dyn_kg"], t)
    cent = check_centrifugal(geom, mat_rotor, mc["magnet_kg"], t)
    lay = check_layout(payload, t)

    levels = {"PASS": [], "WARN": [], "FAIL": []}
    for name, r in (("layout", lay), ("kritische_drehzahl", crit),
                    ("fliehkraft", cent)):
        lv = "FAIL" if not r["ok"] else r.get("level", "PASS")
        levels[lv].append(name)

    if levels["FAIL"]:
        verdict = "ABGELEHNT"
    elif levels["WARN"]:
        verdict = "BEDINGT"
    else:
        verdict = "BESTANDEN"

    return {
        "verdict": verdict,
        "targets": t,
        "layout": lay,
        "kritische_drehzahl": crit,
        "fliehkraft": cent,
        "masse_kosten": mc,
        "summary": {
            "min_web_mm": lay["min_web_mm"],
            "n_crit1_rpm_worst_span": crit["table"][-1]["n_crit1_rpm"],
            "sigma_bore_MPa": cent["disc"]["sigma_T_bore_MPa"],
            "sigma_mag_MPa": cent["magnet"]["sigma_c_MPa"],
            "total_kg": mc["total_kg"],
            "costs_EUR": mc["costs_rough_EUR"],
        },
    }


# ── reporting ──────────────────────────────────────────────────────────────────

def fmt_screen(rep: dict) -> str:
    s = rep["summary"]
    L = rep["layout"]
    C = rep["kritische_drehzahl"]
    F = rep["fliehkraft"]
    M = rep["masse_kosten"]
    out = [
        f"┌─ STUFEN-A-SCREEN  →  {rep['verdict']}",
        f"│ Layout  : {'OK ' if L['ok'] else 'ABGELEHNT'}  "
        f"(min_web {L['min_web_mm']} mm, Ziel ≥ {rep['targets']['web_min_mm']}.0 mm)",
    ]
    if not L["ok"]:
        out += [f"│   ✗ {f}" for f in L["fatal"][:3]]
    out.append("│ Kritisch:")
    for row in C["table"]:
        out.append(f"│   Lager 0{row['span_m']*100:.0f} mm : "
                   f"n1 = {row['n_crit1_rpm']:7.0f} U/min    "
                   f"n2 = {row['n_crit2_rpm']:7.0f} U/min")
    out.append(f"│   → {C['level']}: {C['why']}")
    out.append("│ Fliehkraft bei "
               f"{rep['targets']['n_max']:.0f} U/min :")
    out.append(f"│   Magnet σ = {F['magnet']['sigma_c_MPa']} MPa "
               f"(Zul {F['magnet']['allow_MPa']}, {F['magnet']['utilization']*100:.0f} %)  "
               f"→ {F['magnet']['level']}")
    out.append(f"│   Fe     σ = {F['disc']['sigma_T_bore_MPa']} MPa "
               f"(Fließ {F['disc']['yield_MPa']}, S.F. {F['disc']['safety_factor']})  "
               f"→ {F['disc']['level']}")
    out.append(f"│ Masse   : Σ {M['total_kg']} kg "
               f"(Magnet {M['magnet_kg']} kg × {M['magnet_count']}, "
               f"Rotor-Fe {M['rotor_iron_kg']}, Shaft {M['shaft_kg']}, "
               f"Stator-Fe {M['stator_steel_kg']}, Cu {M['copper_kg']})")
    c = M["costs_rough_EUR"]
    out.append(f"│ Kosten  : ~{c['total_EUR']:,.0f} € "
               f"(Magnet {c['magnet_EUR']}, Cu {c['kupfer_EUR']}, "
               f"Stahl {c['stahl_EUR']}) — Platzhalter-Preise")
    out.append("└─")
    return "\n".join(out)


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) > 1:
        doc = json.loads(open(sys.argv[1]).read())
        payload = doc.get("payload", doc) if isinstance(doc, dict) else doc
        rep = screen_design(payload)
        print(fmt_screen(rep))
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        sys.exit(0 if rep["kritische_drehzahl"]["ok"]
                 and rep["fliehkraft"]["ok"] and rep["layout"]["ok"] else 1)
    print(__doc__)
