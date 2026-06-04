"""Lumped-Parameter Thermal Network (LPTN) for IPM motors.

6 thermal nodes:
  0  W   Winding (Hairpin Cu in slots)
  1  Si  Stator iron (yoke + teeth)
  2  Ri  Rotor iron
  3  M   Magnets
  4  Sh  Shaft
  5  H   Housing
  +  Amb Ambient (boundary, not in state vector)

Connections (conductances G [W/K]):
  W  ↔ Si   slot insulation + tooth body
  Si ↔ H    shrink-fit / contact
  Si ↔ M    airgap convection + radiation
  M  ↔ Ri   bonded magnet in pocket
  Ri ↔ Sh   shaft press-fit
  Sh ↔ H    via bearings
  H  → Amb  cooling-type-dependent
"""

from __future__ import annotations
import math
import numpy as np


# ── Material thermal properties ──────────────────────────────────────────────

CP_CU       = 385.0      # J/(kg·K)
CP_FE       = 460.0
CP_NDFEB    = 420.0
CP_AL       = 900.0      # housing aluminium
RHO_AL      = 2700.0
K_FE        = 30.0       # W/(m·K)  electrical steel
K_CU        = 380.0
K_NDFEB     = 9.0
K_AL        = 200.0
K_INS       = 0.2        # slot liner (mica paper / NMN)
T_INS_M     = 0.5e-3     # insulation thickness

# ── Cooling presets: housing → ambient conductance [W/K] per m² housing area ─
# These are h_eff values (W/m²·K) that get multiplied by housing outer area.

COOLING_PRESETS = {
    "natural":  {"label": "Natürliche Konvektion",     "h_eff": 8,    "delta_T_coolant": 0},
    "forced":   {"label": "Zwangsluft (Lüfter)",       "h_eff": 35,   "delta_T_coolant": 5},
    "water":    {"label": "Wassermantel um Stator",    "h_eff": 800,  "delta_T_coolant": 15},
    "oil":      {"label": "Ölkühlung (Spray/Direkt)",  "h_eff": 2500, "delta_T_coolant": 20},
}

# ── Continuous (S1) rating by cooling ────────────────────────────────────────
# Airgap tangential shear stress σ [kPa] sets the continuous torque the cooling
# can sustain; J_rms [A/mm²] is the matching continuous current density. Together
# they let us anchor copper loss on the *cycle's own* load instead of a free
# input torque: at T = T_rated the winding runs at J_rms.

COOLING_RATING = {
    "natural":  {"sigma_kPa": 10, "J_rms_Apmm2":  4.0},
    "forced":   {"sigma_kPa": 18, "J_rms_Apmm2":  6.0},
    "water":    {"sigma_kPa": 40, "J_rms_Apmm2": 12.0},
    "oil":      {"sigma_kPa": 65, "J_rms_Apmm2": 20.0},
}

# Field-weakening d-axis current density as a fraction of J_rated at deep FW
# (fw = 1.5, i.e. 2.5×base speed). Mirrors the 0.6 factor in
# ema_analysis.estimate_dq_currents so the cycle losses and the field animation
# use the same field-weakening strength.
FW_ID_FRAC = 0.6


def rated_torque(geom: dict, axial: float, cooling: str) -> float:
    """Continuous (S1) rated torque [Nm] from rotor volume × airgap shear stress.

    T = 2·σ·V_rotor is the standard electromagnetic sizing relation. σ depends on
    how hard the machine can be cooled. This replaces the free ``load_nm`` as the
    reference the cycle loads are measured against."""
    R_rot = geom["rotorOD"] / 2 / 1000
    L     = axial / 1000
    V_rot = math.pi * R_rot ** 2 * L
    sigma = COOLING_RATING.get(cooling, COOLING_RATING["natural"])["sigma_kPa"] * 1000.0
    return max(1.0, 2.0 * sigma * V_rot)


def copper_volume(geom: dict, axial: float) -> float:
    """Total conductor volume [m³] in the slots (incl. end-turn overhang)."""
    n_slots  = int(geom["slots"])
    R_si     = geom["statorID"] / 2 / 1000
    slot_dep = float(geom["slotDepth"]) / 1000
    sw_ratio = float(geom.get("slotWidthRatio", 0.5))
    L_cond   = axial / 1000 + 2 * 0.018
    dtheta   = 2 * math.pi / n_slots
    slot_w   = max(3e-3, R_si * dtheta * sw_ratio)
    ins      = 0.8e-3
    n_layers = 2
    cond_w   = max(1.5e-3, slot_w - 2 * ins)
    layer_h  = max(2e-3, (slot_dep - 2e-3 - (n_layers + 1) * ins) / n_layers)
    return n_slots * n_layers * (cond_w * layer_h) * L_cond


def cycle_loss_series(drv: dict, geom: dict, axial: float, perf: dict,
                      mat: dict, st_mat: dict, hp_mat: dict, mag: dict,
                      cooling: str = "water", rpm_base: float = 0.0) -> dict:
    """Per-timestep LPTN heat sources [W] for a drive cycle, anchored on physics
    (no free load torque):

      copper  : J(t) = √(J_q² + J_d²),  J_q = J_rated·|T|/T_rated (load),
                J_d = J_rated·fw·FW_ID_FRAC (speed-driven field weakening);
                P_Cu = ρ_el · V_cu · J(t)²
      iron    : Bertotti, ∝ rpm · flux_fac²   (anchored via compute_losses at rpm_rms)
      magnet  : eddy,     ∝ rpm²
      bearing : windage,  ∝ rpm

    The copper anchor is turn-count- and Kt-independent (current density × copper
    volume), so it stays valid even when the demonstrator's Kt is unreliable.

    Field weakening (``rpm_base`` > 0): above the base speed the inverter voltage
    limit forces a demagnetising d-axis current. fw ramps 0→1.5 from rpm_base to
    2.5×rpm_base. This adds load-independent copper loss at high speed (e.g. the
    Autobahn cruise) and reduces the B²-dependent iron loss via the reduced
    fundamental flux (flux_fac = 1/(1+fw)). Pass the same ``rpm_base`` used for the
    field animation so both stay consistent.
    """
    rpm = np.abs(np.asarray(drv["rpm_motor"], dtype=float))
    T   = np.abs(np.asarray(drv["T_motor"],   dtype=float))

    T_rated = rated_torque(geom, axial, cooling)
    J_rated = COOLING_RATING.get(cooling, COOLING_RATING["natural"])["J_rms_Apmm2"]
    V_cu    = copper_volume(geom, axial)
    rho     = hp_mat["rho_el"]

    if rpm_base and rpm_base > 0:
        fw = np.clip((rpm - rpm_base) / rpm_base, 0.0, 1.5)
    else:
        fw = np.zeros_like(rpm)

    J_q     = J_rated * (T / T_rated)                      # A/mm², load-driven
    J_d     = J_rated * fw * FW_ID_FRAC                    # A/mm², speed-driven
    J       = np.sqrt(J_q ** 2 + J_d ** 2) * 1e6           # A/m²
    P_Cu    = rho * V_cu * J ** 2

    rpm_ref = max(1.0, float(np.sqrt(np.mean(rpm ** 2))))  # rpm_rms anchor
    ref     = compute_losses(geom, axial, rpm_ref, 0.0, 0.0,
                             perf, mat, st_mat, hp_mat, mag)
    r_ratio = rpm / rpm_ref
    flux_fac = 1.0 / (1.0 + fw)                            # reduced flux in FW
    P_Fe_s  = ref["P_Fe_stator"] * r_ratio * flux_fac ** 2
    P_Fe_r  = ref["P_Fe_rotor"]  * r_ratio * flux_fac ** 2
    P_Mag   = ref["P_Mag_eddy"]  * r_ratio ** 2
    P_Bear  = ref["P_Bearing"]   * r_ratio
    P_total = P_Cu + P_Fe_s + P_Fe_r + P_Mag + P_Bear

    return {
        "P_Cu":        P_Cu,
        "P_Fe_stator": P_Fe_s,
        "P_Fe_rotor":  P_Fe_r,
        "P_Mag_eddy":  P_Mag,
        "P_Bearing":   P_Bear,
        "P_total":     P_total,
        "T_rated":     round(T_rated, 1),
        "J_rated":     J_rated,
        "V_cu_cm3":    round(V_cu * 1e6, 1),
    }


# ── Loss computation ─────────────────────────────────────────────────────────

def compute_losses(geom: dict, axial: float, rpm: float, iq: float, id_: float,
                   perf: dict, mat: dict, st_mat: dict, hp_mat: dict, mag: dict) -> dict:
    """Decompose total motor losses into the four LPTN heat sources.

    Returns {P_Cu, P_Fe_stator, P_Fe_rotor, P_Mag_eddy, P_Bearing, P_total} [W]."""
    n_slots  = int(geom["slots"])
    R_si     = geom["statorID"] / 2 / 1000      # m
    R_so     = geom["statorOD"] / 2 / 1000
    R_rot    = geom["rotorOD"]  / 2 / 1000
    R_shaft  = geom["shaftD"]   / 2 / 1000
    slot_dep = float(geom["slotDepth"]) / 1000
    sw_ratio = float(geom.get("slotWidthRatio", 0.5))
    L_st     = axial / 1000
    end_turn = 0.018                            # m, ~18 mm overhang
    L_cond   = L_st + 2 * end_turn

    # Hairpin conductor cross-section
    dtheta   = 2 * math.pi / n_slots
    slot_w   = max(3e-3, R_si * dtheta * sw_ratio)
    ins      = 0.8e-3
    n_layers = 2
    cond_w   = max(1.5e-3, slot_w - 2 * ins)
    layer_h  = max(2e-3, (slot_dep - 2e-3 - (n_layers + 1) * ins) / n_layers)
    A_cond   = cond_w * layer_h                  # m² per layer
    # Per-phase: n_slots/3 slots, n_layers per slot, in series
    R_phase  = hp_mat["rho_el"] * L_cond * n_slots * n_layers / (3 * A_cond)

    # i_q, i_d are peak phase currents → RMS conversion (i_rms = i_pk/√2)
    i_rms_sq = 0.5 * (iq**2 + id_**2)
    P_Cu     = 3 * i_rms_sq * R_phase            # W

    # Iron losses (already estimated in pipeline) — split 70/30 stator/rotor
    f_el     = rpm * int(geom["p"]) / 60
    V_st     = math.pi * (R_so**2 - R_si**2) * L_st
    V_rot    = math.pi * (R_rot**2 - R_shaft**2) * L_st
    m_st     = max(0.01, V_st * st_mat["density"])
    m_ri     = max(0.01, V_rot * mat["density"])
    P_Fe_total = st_mat["specific_loss_Wkg"] * (f_el / 50) * (perf["B_gap_T"] ** 2) * m_st
    P_Fe_s   = 0.75 * P_Fe_total
    P_Fe_r   = 0.25 * P_Fe_total

    # Magnet eddy losses — empirical 0.5 % of stator copper at base speed,
    # scaling quadratically with electrical frequency (eddy ∝ f²)
    f_base_ratio = (f_el / max(50, f_el))        # cap at 1 — eddy already non-trivial above f_base
    P_Mag    = 0.005 * P_Cu + 0.02 * P_Fe_total * (f_el / 200)**2

    # Bearing / windage — proportional to mechanical power
    omega    = rpm * 2 * math.pi / 60
    T_mech   = perf.get("T_maxwell_Nm", 0.0)
    P_mech   = abs(T_mech * omega)
    P_Bearing = 0.005 * P_mech + 5.0             # +5 W base drag

    P_total  = P_Cu + P_Fe_s + P_Fe_r + P_Mag + P_Bearing
    return {
        "P_Cu":         round(P_Cu, 1),
        "P_Fe_stator":  round(P_Fe_s, 1),
        "P_Fe_rotor":   round(P_Fe_r, 1),
        "P_Mag_eddy":   round(P_Mag, 1),
        "P_Bearing":    round(P_Bearing, 1),
        "P_total":      round(P_total, 1),
        "R_phase_mOhm": round(R_phase * 1000, 2),
    }


# ── Thermal capacities ───────────────────────────────────────────────────────

def compute_capacities(geom: dict, axial: float,
                       mat: dict, st_mat: dict, hp_mat: dict, mag: dict) -> dict:
    """Mass × specific heat for each thermal node. Returns C [J/K]."""
    n_slots   = int(geom["slots"])
    n_poles   = int(geom["p"]) * 2
    R_si      = geom["statorID"] / 2 / 1000
    R_so      = geom["statorOD"] / 2 / 1000
    R_rot     = geom["rotorOD"]  / 2 / 1000
    R_shaft   = geom["shaftD"]   / 2 / 1000
    slot_dep  = float(geom["slotDepth"]) / 1000
    sw_ratio  = float(geom.get("slotWidthRatio", 0.5))
    magH      = float(geom["magThick"]) / 1000
    magW      = float(geom.get("magWidth", 35)) / 1000
    L_st      = axial / 1000
    end_turn  = 0.018

    # Winding mass
    dtheta   = 2 * math.pi / n_slots
    slot_w   = max(3e-3, R_si * dtheta * sw_ratio)
    ins      = 0.8e-3
    cond_w   = max(1.5e-3, slot_w - 2 * ins)
    layer_h  = max(2e-3, (slot_dep - 2e-3 - 3*ins) / 2)
    V_w      = n_slots * 2 * cond_w * layer_h * (L_st + 2 * end_turn)
    m_w      = V_w * hp_mat["density"]

    # Stator iron (with slot cut-outs)
    V_st_ring = math.pi * (R_so**2 - R_si**2) * L_st
    V_slots   = n_slots * slot_dep * slot_w * L_st
    m_st      = max(0.01, (V_st_ring - V_slots) * st_mat["density"])

    # Rotor iron (with magnet pockets)
    n_mags = n_poles * (2 if geom.get("magShape", "v") == "v" else 1)
    V_rot_ring = math.pi * (R_rot**2 - R_shaft**2) * L_st
    V_mag_total = n_mags * magW * magH * L_st
    m_ri = max(0.01, (V_rot_ring - V_mag_total) * mat["density"])

    # Magnets (NdFeB density ~7500 kg/m³)
    m_mag = V_mag_total * 7500

    # Shaft (steel)
    V_sh = math.pi * R_shaft**2 * (L_st + 0.06)
    m_sh = V_sh * 7850

    # Housing (Al, 6 mm wall, length L_st + 0.05 m)
    R_h_out = R_so + 0.006
    V_h = math.pi * (R_h_out**2 - R_so**2) * (L_st + 0.05)
    # End plates (2 × disc, 8 mm thick)
    V_h += 2 * math.pi * R_h_out**2 * 0.008
    m_h = V_h * RHO_AL

    return {
        "C_winding":  round(m_w  * CP_CU, 1),
        "C_stator":   round(m_st * CP_FE, 1),
        "C_rotor":    round(m_ri * CP_FE, 1),
        "C_magnet":   round(m_mag * CP_NDFEB, 1),
        "C_shaft":    round(m_sh * CP_FE, 1),
        "C_housing":  round(m_h  * CP_AL, 1),
        "_masses_g": {
            "winding": round(m_w  * 1000, 1),
            "stator":  round(m_st * 1000, 1),
            "rotor":   round(m_ri * 1000, 1),
            "magnet":  round(m_mag * 1000, 1),
            "shaft":   round(m_sh * 1000, 1),
            "housing": round(m_h  * 1000, 1),
        },
    }


# ── Conductance matrix ───────────────────────────────────────────────────────

def conductances(geom: dict, axial: float, cooling: str, rpm: float) -> dict:
    """Pairwise conductances G [W/K] between nodes."""
    R_si    = geom["statorID"] / 2 / 1000
    R_so    = geom["statorOD"] / 2 / 1000
    R_rot   = geom["rotorOD"]  / 2 / 1000
    R_shaft = geom["shaftD"]   / 2 / 1000
    n_slots = int(geom["slots"])
    L       = axial / 1000

    # Winding ↔ Stator iron: through slot liner; total slot-wall area
    slot_wall_per_slot = 2 * (float(geom["slotDepth"])/1000) * L  # two sides
    A_slot = n_slots * slot_wall_per_slot
    G_w_si = K_INS * A_slot / T_INS_M           # very high (cond layer is thin)
    # Cap to realistic value — slot-fill imperfections dominate in reality
    G_w_si = min(G_w_si, 100.0)

    # Stator ↔ Housing: shrink-fit contact, large interface area
    A_si_h = 2 * math.pi * R_so * L
    G_si_h = 1500 * A_si_h                       # h_contact ~ 1500 W/m²K typical

    # Stator ↔ Magnet (across airgap, convection + rotation effect)
    A_gap = 2 * math.pi * R_si * L
    h_gap = 6 + 0.02 * rpm                       # increases with rotor speed
    G_si_m = h_gap * A_gap

    # Magnet ↔ Rotor iron (sintered + glued)
    G_m_ri = 80.0                                # K/W — pretty high contact

    # Rotor ↔ Shaft (press fit)
    A_ri_sh = 2 * math.pi * R_shaft * L
    G_ri_sh = 800 * A_ri_sh

    # Shaft ↔ Housing (via bearings, two ends)
    G_sh_h = 5.0                                 # poor heat path

    # Housing ↔ Ambient
    cp = COOLING_PRESETS.get(cooling, COOLING_PRESETS["natural"])
    R_h_out = R_so + 0.006
    A_h_ext = 2 * math.pi * R_h_out * (L + 0.05)
    A_h_ext += 2 * math.pi * R_h_out**2           # end plates
    G_h_amb = cp["h_eff"] * A_h_ext

    return {
        "G_w_si":   G_w_si,
        "G_si_h":   G_si_h,
        "G_si_m":   G_si_m,
        "G_m_ri":   G_m_ri,
        "G_ri_sh":  G_ri_sh,
        "G_sh_h":   G_sh_h,
        "G_h_amb":  G_h_amb,
        "_label":   cp["label"],
        "_delta_T_coolant": cp.get("delta_T_coolant", 0),
    }


# ── LPTN matrix assembly ─────────────────────────────────────────────────────

# Node indices
W, SI, RI, M, SH, H = 0, 1, 2, 3, 4, 5
N_NODES = 6


def build_GA(G: dict) -> tuple[np.ndarray, np.ndarray]:
    """Return (A, b) so that A·T = P + b for steady state at ambient.
    Here b incorporates -G_amb·T_amb on the housing node; caller adds T_amb·G_h_amb to RHS."""
    A = np.zeros((N_NODES, N_NODES))
    def add(i, j, g):
        A[i, i] -= g; A[j, j] -= g
        A[i, j] += g; A[j, i] += g
    add(W,  SI, G["G_w_si"])
    add(SI, H,  G["G_si_h"])
    add(SI, M,  G["G_si_m"])
    add(M,  RI, G["G_m_ri"])
    add(RI, SH, G["G_ri_sh"])
    add(SH, H,  G["G_sh_h"])
    A[H, H] -= G["G_h_amb"]                     # ambient sink
    return A


def solve_steady(G: dict, P_dict: dict, T_amb: float = 25.0) -> dict:
    """T_node = inv(-A) · (P + G_amb·T_amb·e_H).  Returns temperatures [°C]."""
    A = build_GA(G)
    P = np.zeros(N_NODES)
    P[W]  = P_dict["P_Cu"]
    P[SI] = P_dict["P_Fe_stator"]
    P[RI] = P_dict["P_Fe_rotor"]
    P[M]  = P_dict["P_Mag_eddy"]
    P[SH] = P_dict["P_Bearing"]
    rhs = P.copy()
    rhs[H] += G["G_h_amb"] * (T_amb + G.get("_delta_T_coolant", 0))
    T = np.linalg.solve(-A, rhs)
    return {
        "T_winding":  round(float(T[W]),  1),
        "T_stator":   round(float(T[SI]), 1),
        "T_rotor":    round(float(T[RI]), 1),
        "T_magnet":   round(float(T[M]),  1),
        "T_shaft":    round(float(T[SH]), 1),
        "T_housing":  round(float(T[H]),  1),
        "T_ambient":  T_amb,
        "cooling":    G["_label"],
    }


def solve_transient(G: dict, C_dict: dict, P_dict: dict,
                     T_amb: float = 25.0, t_max: float = 1800.0,
                     dt: float = 5.0) -> dict:
    """Implicit Euler over [0, t_max]. Returns time series."""
    A = build_GA(G)
    C = np.array([C_dict["C_winding"], C_dict["C_stator"], C_dict["C_rotor"],
                  C_dict["C_magnet"],  C_dict["C_shaft"],  C_dict["C_housing"]])
    P = np.zeros(N_NODES)
    P[W]  = P_dict["P_Cu"]
    P[SI] = P_dict["P_Fe_stator"]
    P[RI] = P_dict["P_Fe_rotor"]
    P[M]  = P_dict["P_Mag_eddy"]
    P[SH] = P_dict["P_Bearing"]
    rhs_const = P.copy()
    rhs_const[H] += G["G_h_amb"] * (T_amb + G.get("_delta_T_coolant", 0))

    # Implicit Euler: (C/dt - A) T^{n+1} = C/dt · T^n + rhs_const
    M_lhs = np.diag(C / dt) - A
    n_steps = max(2, int(t_max / dt))
    T_series = np.zeros((n_steps + 1, N_NODES))
    T_series[0] = T_amb
    for k in range(n_steps):
        rhs = C / dt * T_series[k] + rhs_const
        T_series[k + 1] = np.linalg.solve(M_lhs, rhs)

    t = np.arange(n_steps + 1) * dt
    return {
        "t":          t.tolist(),
        "T_winding":  T_series[:, W].tolist(),
        "T_stator":   T_series[:, SI].tolist(),
        "T_rotor":    T_series[:, RI].tolist(),
        "T_magnet":   T_series[:, M].tolist(),
        "T_shaft":    T_series[:, SH].tolist(),
        "T_housing":  T_series[:, H].tolist(),
        "T_steady":   T_series[-1].tolist(),
    }


# ── Per-cycle thermal analysis ───────────────────────────────────────────────

def _temps_dict(Tvec: np.ndarray, T_amb: float, cooling_label: str) -> dict:
    return {
        "T_winding": round(float(Tvec[W]),  1),
        "T_stator":  round(float(Tvec[SI]), 1),
        "T_rotor":   round(float(Tvec[RI]), 1),
        "T_magnet":  round(float(Tvec[M]),  1),
        "T_shaft":   round(float(Tvec[SH]), 1),
        "T_housing": round(float(Tvec[H]),  1),
        "T_ambient": T_amb,
        "cooling":   cooling_label,
    }


def thermal_warnings(cont: dict, peak: dict | None, mag: dict) -> list[str]:
    """Unified winding-class + magnet-grade warnings for continuous and (optional)
    transient-peak temperatures. ``mag`` carries T_op_max / T_curie per grade."""
    w: list[str] = []
    T_op  = float(mag.get("T_op_max", 120))
    T_cur = float(mag.get("T_curie",  310))
    label = mag.get("label", "NdFeB")

    if cont["T_winding"] > 180:
        w.append(f"⚠ Dauerbetrieb: T_Wicklung={cont['T_winding']:.0f}°C > Isolierklasse H (180°C)")
    elif cont["T_winding"] > 155:
        w.append(f"⚠ Dauerbetrieb: T_Wicklung={cont['T_winding']:.0f}°C nahe Klasse F (155°C)")
    if cont["T_magnet"] > T_op:
        w.append(f"⚠ Dauerbetrieb: T_Magnet={cont['T_magnet']:.0f}°C > Dauergrenze "
                 f"{T_op:.0f}°C ({label}) — irreversible Entmagnetisierung")

    if peak is not None:
        if peak["T_magnet"] >= T_cur:
            w.append(f"🛑 Peak: T_Magnet={peak['T_magnet']:.0f}°C ≥ Curie-Temp "
                     f"{T_cur:.0f}°C — Magnet wird zerstört")
        elif peak["T_magnet"] > T_op:
            w.append(f"⚠ Peak: T_Magnet={peak['T_magnet']:.0f}°C > Dauergrenze "
                     f"{T_op:.0f}°C — teilweise irreversible Entmagnetisierung möglich")
        if peak["T_winding"] > 200:
            w.append(f"⚠ Peak: T_Wicklung={peak['T_winding']:.0f}°C > 200°C — kurzzeitig grenzwertig")
    return w


def solve_transient_series(geom: dict, axial: float, caps: dict, series: dict,
                           rpm_series, t_series, cooling: str,
                           T_amb: float = 25.0, T_init=None) -> dict:
    """Implicit-Euler transient driven by the per-timestep loss arrays and
    rpm-dependent conductances. Captures the *real* peak the thermal mass allows
    (short load spikes are buffered) and handles non-coincident T_max / rpm_max
    naturally. ``T_init`` seeds the initial node temps (default: ambient) — pass
    the continuous steady state to capture peaks on a warmed-up machine.
    Returns peak + final node temps and thinned winding/magnet traces."""
    rpm = np.abs(np.asarray(rpm_series, dtype=float))
    t   = np.asarray(t_series, dtype=float)
    n   = len(t)
    dt  = float(np.mean(np.diff(t))) if n > 1 else 1.0
    C   = np.array([caps["C_winding"], caps["C_stator"], caps["C_rotor"],
                    caps["C_magnet"],  caps["C_shaft"],  caps["C_housing"]])
    P   = np.vstack([series["P_Cu"], series["P_Fe_stator"], series["P_Fe_rotor"],
                     series["P_Mag_eddy"], series["P_Bearing"], np.zeros(n)])

    cp_label = COOLING_PRESETS.get(cooling, COOLING_PRESETS["natural"])["label"]
    Tn   = np.full(N_NODES, T_amb) if T_init is None else np.asarray(T_init, dtype=float).copy()
    Tmax = Tn.copy()
    win  = np.empty(n)
    magt = np.empty(n)
    for k in range(n):
        G = conductances(geom, axial, cooling, rpm[k])
        A = build_GA(G)
        M_lhs = np.diag(C / dt) - A
        rhs = C / dt * Tn + P[:, k]
        rhs[H] += G["G_h_amb"] * (T_amb + G.get("_delta_T_coolant", 0))
        Tn = np.linalg.solve(M_lhs, rhs)
        Tmax = np.maximum(Tmax, Tn)
        win[k] = Tn[W]; magt[k] = Tn[M]

    step = max(1, n // 120)
    return {
        "peak":  _temps_dict(Tmax, T_amb, cp_label),
        "final": _temps_dict(Tn,   T_amb, cp_label),
        "trace": {
            "t":         t[::step].tolist(),
            "T_winding": [round(x, 1) for x in win[::step]],
            "T_magnet":  [round(x, 1) for x in magt[::step]],
        },
    }


def thermal_for_cycle(drv: dict, cycle_result: dict, series: dict,
                      geom: dict, axial: float,
                      mat: dict, st_mat: dict, hp_mat: dict, mag: dict,
                      cooling: str = "water", T_amb: float = 25.0) -> dict:
    """Temperatures for a drive cycle, decoupled from any free load torque.

      • Dauerbetrieb (``avg``): steady state at the cycle's *mean* losses — the
        temperature the motor trends toward if the cycle repeats.
      • Peak (``peak``): the real maximum reached by a transient run of the actual
        load profile (thermal inertia buffers short spikes; non-coincident
        T_max/rpm_max handled correctly).

    Losses come from ``cycle_loss_series`` (current density × copper volume, no
    Kt), so the result no longer depends on an arbitrary reference torque.
    """
    cp_label = COOLING_PRESETS.get(cooling, COOLING_PRESETS["natural"])["label"]
    rpm_rms  = float(cycle_result.get("rpm_rms", 0.0))
    T_rms    = float(cycle_result.get("T_rms",   0.0))
    rpm_max  = float(cycle_result.get("rpm_max",  rpm_rms))
    T_max    = float(cycle_result.get("T_max",    T_rms))

    keys = ["P_Cu", "P_Fe_stator", "P_Fe_rotor", "P_Mag_eddy", "P_Bearing"]
    P_cont = {k: float(np.mean(series[k])) for k in keys}
    P_cont["P_total"] = round(sum(P_cont.values()), 1)
    for k in keys:
        P_cont[k] = round(P_cont[k], 1)

    G_cont   = conductances(geom, axial, cooling, rpm_rms)
    cont     = solve_steady(G_cont, P_cont, T_amb)

    # Seed the transient at the continuous steady state so peaks ride on top of a
    # warmed-up machine (true worst case for a repeating cycle).
    T_init   = [cont["T_winding"], cont["T_stator"], cont["T_rotor"],
                cont["T_magnet"],  cont["T_shaft"],  cont["T_housing"]]
    caps     = compute_capacities(geom, axial, mat, st_mat, hp_mat, mag)
    trans    = solve_transient_series(geom, axial, caps, series,
                                      drv["rpm_motor"], drv["t"], cooling, T_amb,
                                      T_init=T_init)
    peak     = trans["peak"]

    # Loss snapshot at the worst instant (max total dissipation)
    i_pk = int(np.argmax(np.asarray(series["P_total"])))
    P_peak = {k: round(float(series[k][i_pk]), 1) for k in keys}
    P_peak["P_total"] = round(float(series["P_total"][i_pk]), 1)

    warns = thermal_warnings(cont, peak, mag)

    return {
        "avg_rpm":     round(rpm_rms, 0),
        "avg_T_Nm":    round(T_rms, 1),
        "avg":         cont,
        "avg_losses":  P_cont,
        "peak_rpm":    round(rpm_max, 0),
        "peak_T_Nm":   round(T_max, 1),
        "peak":        peak,
        "peak_losses": P_peak,
        "trace":       trans["trace"],
        "T_rated_Nm":  series.get("T_rated"),
        "J_rated_Apmm2": series.get("J_rated"),
        "warnings":    warns,
        "cooling":     cooling,
        "cooling_label": cp_label,
    }


# ── Top-level analysis ──────────────────────────────────────────────────────

def design_point_losses(geom: dict, axial: float, rpm: float, load_nm: float,
                        perf: dict, mat: dict, st_mat: dict, hp_mat: dict,
                        mag: dict, cooling: str) -> dict:
    """Losses at a standalone S1 duty point (load_nm @ rpm), copper anchored on
    current density relative to the geometry's rated torque — Kt-independent."""
    T_rated = rated_torque(geom, axial, cooling)
    J_rated = COOLING_RATING.get(cooling, COOLING_RATING["natural"])["J_rms_Apmm2"]
    V_cu    = copper_volume(geom, axial)
    J       = J_rated * (abs(load_nm) / T_rated) * 1e6     # A/m²
    P_Cu    = hp_mat["rho_el"] * V_cu * J ** 2
    base    = compute_losses(geom, axial, rpm, 0.0, 0.0, perf, mat, st_mat, hp_mat, mag)
    P_total = P_Cu + base["P_Fe_stator"] + base["P_Fe_rotor"] + base["P_Mag_eddy"] + base["P_Bearing"]
    return {
        "P_Cu":         round(P_Cu, 1),
        "P_Fe_stator":  base["P_Fe_stator"],
        "P_Fe_rotor":   base["P_Fe_rotor"],
        "P_Mag_eddy":   base["P_Mag_eddy"],
        "P_Bearing":    base["P_Bearing"],
        "P_total":      round(P_total, 1),
        "R_phase_mOhm": base["R_phase_mOhm"],
        "T_rated_Nm":   round(T_rated, 1),
        "J_Apmm2":      round(J / 1e6, 2),
    }


def run_thermal_analysis(geom: dict, axial: float, rpm: float, load_nm: float,
                          perf: dict,
                          mat: dict, st_mat: dict, hp_mat: dict, mag: dict,
                          cooling: str = "water", T_amb: float = 25.0,
                          t_max: float = 1800.0) -> dict:
    """Standalone S1 duty-point thermal analysis (continuous load_nm @ rpm)."""
    losses = design_point_losses(geom, axial, rpm, load_nm,
                                 perf, mat, st_mat, hp_mat, mag, cooling)
    caps   = compute_capacities(geom, axial, mat, st_mat, hp_mat, mag)
    G      = conductances(geom, axial, cooling, rpm)
    steady = solve_steady(G, losses, T_amb)
    trans  = solve_transient(G, caps, losses, T_amb, t_max=t_max)

    # Thermal time constants per node (τ = C_eff / G_eff to ambient pathway)
    tau = {
        "winding":  round(caps["C_winding"] / max(1e-3, G["G_w_si"]), 1),
        "stator":   round(caps["C_stator"]  / max(1e-3, G["G_si_h"]), 1),
        "magnet":   round(caps["C_magnet"]  / max(1e-3, G["G_si_m"]), 1),
        "housing":  round(caps["C_housing"] / max(1e-3, G["G_h_amb"]), 1),
    }

    warnings = thermal_warnings(steady, None, mag)
    if steady["T_housing"] > 80:
        warnings.append(f"⚠ Gehäusetemperatur {steady['T_housing']:.0f}°C — Berührungsschutz nötig")
    if abs(load_nm) > losses["T_rated_Nm"]:
        warnings.append(f"ℹ Lastpunkt {load_nm:.0f} Nm > Dauer-Nennmoment "
                        f"{losses['T_rated_Nm']:.0f} Nm ({G['_label']}) — nur kurzzeitig zulässig")

    return {
        "losses":       losses,
        "capacities":   caps,
        "conductances": {k: round(v, 2) for k, v in G.items() if not k.startswith("_")},
        "steady":       steady,
        "transient":    trans,
        "tau_s":        tau,
        "warnings":     warnings,
        "cooling":      cooling,
        "cooling_label": G["_label"],
        "T_ambient":    T_amb,
        "rpm":          rpm,
        "load_nm":      load_nm,
        "T_rated_Nm":   losses["T_rated_Nm"],
        "J_Apmm2":      losses["J_Apmm2"],
    }
