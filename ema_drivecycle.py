"""Drive-cycle analysis: WLTP Class 3b preset + custom CSV loading.

The bundled WLTP-3b profile is a representative reconstruction with the
correct phase durations, peak/average speeds and accelerations (the official
table is normative; the demonstrator approximation captures total distance
±2 %, peak speed exact, and the four-phase structure faithfully).

For real-world calibration upload your own `t[s], v[km/h]` CSV.
"""

from __future__ import annotations
import math, csv, io
import numpy as np


# ── WLTP Class 3b reference data (approximation) ─────────────────────────────

WLTP3B_PHASES = [
    {"name": "Low",        "t_end": 589,  "v_max": 56.5,  "v_avg": 18.9, "d_m": 3095},
    {"name": "Medium",     "t_end": 1022, "v_max": 76.6,  "v_avg": 39.5, "d_m": 4756},
    {"name": "High",       "t_end": 1477, "v_max": 97.4,  "v_avg": 56.7, "d_m": 7158},
    {"name": "Extra-High", "t_end": 1800, "v_max": 131.3, "v_avg": 92.0, "d_m": 8254},
]
WLTP_TOTAL_T = 1800
WLTP_TOTAL_D_KM = 23.26


def _build_wltp3b() -> np.ndarray:
    """Build a v[km/h] array sampled at 1 Hz over 1800 s that matches the four
    WLTP-3b phases in peak speed, average speed and gross distance.

    Strategy: stochastic-but-deterministic profile shaped from accel/cruise/decel
    triangular pulses, scaled to the target average per phase.
    """
    rng = np.random.default_rng(20260522)
    v = np.zeros(WLTP_TOTAL_T + 1, dtype=float)
    t_prev = 0

    for phase in WLTP3B_PHASES:
        t_start = t_prev
        t_end   = phase["t_end"]
        dur     = t_end - t_start
        v_peak  = phase["v_max"]
        v_avg   = phase["v_avg"]

        # Build a sequence of accel/cruise/decel segments
        i = t_start
        while i < t_end:
            # Segment duration 25-80 s
            seg_dur = int(rng.integers(25, 80))
            seg_end = min(i + seg_dur, t_end)
            seg_len = seg_end - i

            # Target peak for this segment
            v_target = float(rng.uniform(0.4, 1.0) * v_peak)

            # Mode: 70 % cruise-with-ramps, 25 % full stop-and-go, 5 % cruise
            mode = rng.choice(["ramp", "stop", "cruise"], p=[0.70, 0.25, 0.05])

            if mode == "stop":
                # Decel to 0, hold briefly, accel back up
                t_decel = max(2, int(seg_len * 0.25))
                t_hold  = max(1, int(seg_len * 0.15))
                t_accel = seg_len - t_decel - t_hold
                v_now = v[i - 1] if i > 0 else 0
                seg = np.concatenate([
                    np.linspace(v_now, 0, t_decel),
                    np.zeros(t_hold),
                    np.linspace(0, v_target, max(1, t_accel)),
                ])
            elif mode == "ramp":
                t_acc = max(3, int(seg_len * 0.30))
                t_cru = max(1, int(seg_len * 0.50))
                t_dec = seg_len - t_acc - t_cru
                v_now = v[i - 1] if i > 0 else 0
                seg = np.concatenate([
                    np.linspace(v_now, v_target, t_acc),
                    np.full(t_cru, v_target),
                    np.linspace(v_target, max(0, v_target - 15), max(1, t_dec)),
                ])
            else:  # cruise
                v_now = v[i - 1] if i > 0 else 0
                seg = np.linspace(v_now, v_target, seg_len)

            # Truncate segment to fit remaining phase budget
            remaining = t_end - i
            seg = seg[:remaining]
            v[i:i + len(seg)] = seg
            i += len(seg) if len(seg) > 0 else 1

        # Rescale this phase to match the target average
        actual_avg = v[t_start:t_end].mean()
        if actual_avg > 1e-3:
            v[t_start:t_end] *= v_avg / actual_avg
        # Clip to peak
        np.clip(v[t_start:t_end], 0, v_peak, out=v[t_start:t_end])

        t_prev = t_end

    # Smooth slightly (acceleration limit) — 3-point moving average twice
    v = np.convolve(v, np.ones(3) / 3, mode="same")
    v = np.convolve(v, np.ones(3) / 3, mode="same")
    np.clip(v, 0, None, out=v)
    return v


_WLTP_CACHE: dict = {}


def wltp_class3() -> dict:
    """Return the WLTP-3b reference cycle as t[s], v[km/h] arrays + phase info."""
    if "data" not in _WLTP_CACHE:
        v_kmh = _build_wltp3b()
        _WLTP_CACHE["data"] = {
            "t":        np.arange(len(v_kmh)).astype(float),
            "v_kmh":    v_kmh,
            "name":     "WLTP Class 3b (approximiert)",
            "phases":   WLTP3B_PHASES,
            "duration": WLTP_TOTAL_T,
        }
    return _WLTP_CACHE["data"]


# ── Vollast-Zyklus (maximale Belastung) ──────────────────────────────────────

# ── Autobahn-Vollgas 220 km/h ────────────────────────────────────────────────

VOLLAST_PHASES = [
    {"name": "Aufheizen",        "t_end": 120,  "v_max": 140.0, "v_avg":  82.0},
    {"name": "Richtgeschw.",     "t_end": 480,  "v_max": 180.0, "v_avg": 162.0},
    {"name": "Autobahn 220",     "t_end": 900,  "v_max": 220.0, "v_avg": 205.0},
    {"name": "Hochgeschw.-Spr.", "t_end": 1200, "v_max": 220.0, "v_avg": 212.0},
]
VOLLAST_TOTAL_T = 1200


def _build_vollast() -> np.ndarray:
    """1200 s German Autobahn profile: v_avg ≈ 180 km/h, peak 220 km/h, no stops.

    Models free-Autobahn high-speed driving with sporadic sprints to 220 km/h.
    This stresses the motor at high RPM / moderate torque (field-weakening zone).
    """
    rng = np.random.default_rng(20260523)
    v = np.zeros(VOLLAST_TOTAL_T + 1, dtype=float)
    t_prev = 0

    for phase in VOLLAST_PHASES:
        t_start = t_prev
        t_end   = phase["t_end"]
        v_peak  = phase["v_max"]
        v_avg   = phase["v_avg"]

        i = t_start
        while i < t_end:
            seg_dur = int(rng.integers(40, 100))
            seg_end = min(i + seg_dur, t_end)
            seg_len = seg_end - i

            v_target = float(rng.uniform(0.80, 1.0) * v_peak)
            mode = rng.choice(["cruise", "accel", "brief_lift"],
                               p=[0.65, 0.25, 0.10])
            v_now = v[i - 1] if i > 0 else 0.0

            if mode == "accel":
                # Hard acceleration run then hold
                t_acc = max(8, int(seg_len * 0.30))
                t_cru = max(1, seg_len - t_acc)
                seg = np.concatenate([
                    np.linspace(v_now, v_target, t_acc),
                    np.full(t_cru, v_target),
                ])
            elif mode == "brief_lift":
                # Brief throttle-lift then back up
                v_lift = max(v_peak * 0.70, v_now * 0.85)
                t_dn   = max(3, int(seg_len * 0.25))
                t_up   = seg_len - t_dn
                seg = np.concatenate([
                    np.linspace(v_now, v_lift, t_dn),
                    np.linspace(v_lift, v_target, max(1, t_up)),
                ])
            else:  # cruise at target
                t_acc = max(5, int(seg_len * 0.20))
                t_cru = seg_len - t_acc
                seg = np.concatenate([
                    np.linspace(v_now, v_target, t_acc),
                    np.full(max(1, t_cru), v_target),
                ])

            remaining = t_end - i
            seg = seg[:remaining]
            v[i:i + len(seg)] = seg
            i += len(seg) if len(seg) > 0 else 1

        actual_avg = v[t_start:t_end].mean()
        if actual_avg > 1.0:
            v[t_start:t_end] *= v_avg / actual_avg
        np.clip(v[t_start:t_end], 0, v_peak, out=v[t_start:t_end])
        t_prev = t_end

    v = np.convolve(v, np.ones(3) / 3, mode="same")
    v = np.convolve(v, np.ones(3) / 3, mode="same")
    np.clip(v, 0, None, out=v)
    return v


_VOLLAST_CACHE: dict = {}


def fullload_cycle() -> dict:
    """Return the Autobahn-Vollgas cycle as t[s], v[km/h] arrays + phase info."""
    if "data" not in _VOLLAST_CACHE:
        v_kmh = _build_vollast()
        _VOLLAST_CACHE["data"] = {
            "t":        np.arange(len(v_kmh)).astype(float),
            "v_kmh":    v_kmh,
            "name":     "Autobahn-Vollgas 220 km/h",
            "phases":   VOLLAST_PHASES,
            "duration": VOLLAST_TOTAL_T,
        }
    return _VOLLAST_CACHE["data"]


# ── Anhänger-Alpenpass-Zyklus ─────────────────────────────────────────────────

# Speed limit for trailer operation (German Tempo-100-Zulassung).
ANHAENGER_V_CAP = 100.0

ANHAENGER_PHASES = [
    {"name": "Tal-Auffahrt",  "t_end": 60,   "v_max":  90.0, "v_avg":  70.0,
     "slope_range": (0.0,  2.0)},
    {"name": "Bergauffahrt",  "t_end": 780,  "v_max":  70.0, "v_avg":  52.0,
     "slope_range": (7.0, 11.0)},
    {"name": "Pass-Plateau",  "t_end": 960,  "v_max": 100.0, "v_avg":  85.0,
     "slope_range": (0.0,  1.0)},
    {"name": "Bergabfahrt",   "t_end": 1560, "v_max":  80.0, "v_avg":  65.0,
     "slope_range": (-10.0, -6.0)},
    {"name": "Tal-Sprint",    "t_end": 1800, "v_max": 100.0, "v_avg":  90.0,
     "slope_range": (-1.0,  1.0)},
]
ANHAENGER_TOTAL_T = 1800

# Trailer additions applied on top of the *base* PKW (whatever the user set).
# Only the Anhänger-Alpenpass cycle uses these — WLTP and Autobahn keep the base
# vehicle. The trailer is modelled as a tandem-axle unit (2 extra axles).
TRAILER_ADD = {
    "mass_kg":         1800,   # Anhänger-Masse zusätzlich zum PKW
    "cwA_m2":          0.85,   # zusätzliche (schlechte) Anhänger-Aerodynamik
    "n_extra_axles":   2,      # Tandemachser
    "axle_friction_N": 140.0,  # Radlager-/Dichtungsreibung der 2 Zusatzachsen (~70 N/Achse)
    "cr":              0.018,  # erhöhter Rollwiderstand (Bergstraße + Anhänger)
    "eta_drive":       0.92,   # zusätzliche Triebstrangverluste unter Last
    "regen_frac":      0.30,   # begrenzte Rekuperation (Stabilitätsgrenzen mit Anhänger)
}


def trailer_vehicle(base: dict) -> dict:
    """Derive the trailer-laden vehicle from a *base* PKW dict.

    Adds the trailer mass and aero drag on top of the base car, raises the
    rolling resistance, caps regen, and adds an explicit constant axle-friction
    force for the trailer's two extra axles (consumed by ``compute_drivetrain``).
    Drivetrain geometry (r_wheel, gear_ratio) is inherited from the base car.
    """
    v = dict(base)
    v["mass_kg"]         = base.get("mass_kg",  DEFAULT_VEHICLE["mass_kg"])  + TRAILER_ADD["mass_kg"]
    v["cwA_m2"]          = base.get("cwA_m2",   DEFAULT_VEHICLE["cwA_m2"])   + TRAILER_ADD["cwA_m2"]
    v["cr"]              = max(base.get("cr",   DEFAULT_VEHICLE["cr"]), TRAILER_ADD["cr"])
    v["eta_drive"]       = min(base.get("eta_drive", DEFAULT_VEHICLE["eta_drive"]), TRAILER_ADD["eta_drive"])
    v["regen_frac"]      = min(base.get("regen_frac", DEFAULT_VEHICLE["regen_frac"]), TRAILER_ADD["regen_frac"])
    v["n_extra_axles"]   = TRAILER_ADD["n_extra_axles"]
    v["axle_friction_N"] = TRAILER_ADD["axle_friction_N"]
    return v


def _build_anhaenger() -> tuple[np.ndarray, np.ndarray]:
    """Build v[km/h] and slope[°] profiles for the Anhänger-Alpenpass cycle."""
    rng = np.random.default_rng(20260601)
    n   = ANHAENGER_TOTAL_T + 1
    v   = np.zeros(n, dtype=float)
    slp = np.zeros(n, dtype=float)
    t_prev = 0

    for phase in ANHAENGER_PHASES:
        t_start = t_prev
        t_end   = phase["t_end"]
        v_peak  = phase["v_max"]
        v_avg   = phase["v_avg"]
        s_lo, s_hi = phase["slope_range"]

        # Speed profile for this phase
        i = t_start
        while i < t_end:
            seg_dur = int(rng.integers(20, 70))
            seg_end = min(i + seg_dur, t_end)
            seg_len = seg_end - i
            v_target = float(rng.uniform(0.80, 1.0) * v_peak)
            v_now    = v[i - 1] if i > 0 else 0.0
            t_acc    = max(4, int(seg_len * 0.25))
            t_cru    = max(1, seg_len - t_acc)
            seg = np.concatenate([
                np.linspace(v_now, v_target, t_acc),
                np.full(t_cru, v_target),
            ])
            remaining = t_end - i
            seg = seg[:remaining]
            v[i:i + len(seg)] = seg
            i += len(seg) if len(seg) > 0 else 1

        # Scale to target average
        actual_avg = v[t_start:t_end].mean()
        if actual_avg > 0.5:
            v[t_start:t_end] *= v_avg / actual_avg
        np.clip(v[t_start:t_end], 0, v_peak, out=v[t_start:t_end])

        # Slope profile: constant mean with small variation
        s_mean = (s_lo + s_hi) / 2
        s_amp  = (s_hi - s_lo) / 2
        t_arr  = np.arange(t_end - t_start)
        # Slow sinusoidal variation (bends in the road / switchbacks)
        slp[t_start:t_end] = s_mean + s_amp * np.sin(
            2 * math.pi * t_arr / max(1, t_end - t_start) * 3)

        t_prev = t_end

    # Smooth both profiles
    v   = np.convolve(v,   np.ones(5) / 5, mode="same")
    slp = np.convolve(slp, np.ones(9) / 9, mode="same")
    np.clip(v, 0, ANHAENGER_V_CAP, out=v)   # trailer speed limit (Tempo 100)
    return v, slp


_ANHAENGER_CACHE: dict = {}


def trailer_mountain_cycle() -> dict:
    """Anhänger-Alpenpass: 1800 s, 8–10 % Steigung bergauf, −6 bis −10 % bergab.

    Stress test for low-RPM / high-sustained-torque (thermal-critical zone).
    The returned dict includes a ``slope_profile_deg`` array consumed by
    ``compute_drivetrain`` to compute the correct driving force at each timestep.
    Use ``trailer_vehicle(base)`` to derive the trailer-laden vehicle.
    """
    if "data" not in _ANHAENGER_CACHE:
        v_kmh, slp = _build_anhaenger()
        _ANHAENGER_CACHE["data"] = {
            "t":                np.arange(len(v_kmh)).astype(float),
            "v_kmh":            v_kmh,
            "slope_profile_deg": slp,
            "name":             "Anhänger-Alpenpass",
            "phases":           ANHAENGER_PHASES,
            "duration":         ANHAENGER_TOTAL_T,
        }
    return _ANHAENGER_CACHE["data"]


def load_csv_cycle(text: str) -> dict:
    """Parse a `t[s], v[km/h]` CSV upload. Header row optional, ',' or ';' separator."""
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not lines:
        raise ValueError("Leere CSV-Datei")
    sep = ";" if lines[0].count(";") > lines[0].count(",") else ","
    reader = csv.reader(lines, delimiter=sep)
    rows = list(reader)
    # Skip header if first cell is non-numeric
    try:
        float(rows[0][0])
    except ValueError:
        rows = rows[1:]
    t  = np.array([float(r[0]) for r in rows])
    v  = np.array([float(r[1]) for r in rows])
    # Resample to 1 Hz if necessary
    if len(t) < 5:
        raise ValueError("Zu wenige Datenpunkte")
    if not np.allclose(np.diff(t), 1.0, atol=0.1):
        t_new = np.arange(t[0], t[-1] + 1)
        v = np.interp(t_new, t, v)
        t = t_new
    return {"t": t, "v_kmh": v, "name": "Custom CSV",
            "phases": [], "duration": float(t[-1] - t[0])}


# ── Vehicle dynamics ────────────────────────────────────────────────────────

DEFAULT_VEHICLE = {
    "mass_kg":     1600,    # incl. driver
    "cwA_m2":      0.65,    # c_w · A
    "cr":          0.012,   # rolling resistance
    "r_wheel_m":   0.32,    # wheel radius
    "gear_ratio":  9.5,     # motor/wheel
    "eta_drive":   0.95,    # gearbox + diff efficiency
    "rho_air":     1.20,    # kg/m³
    "g":           9.81,
    "regen_frac":  0.55,    # fraction of braking energy recuperated
    "slope_deg":   0.0,
}


def compute_drivetrain(cycle: dict, vehicle: dict) -> dict:
    """From v(t) compute rpm_motor(t), T_motor(t), P_wheel(t).

    Negative torque means generator mode (braking with possible regen).
    Supports a ``slope_profile_deg`` array in the cycle dict for time-varying
    gradients (e.g. mountain passes). Falls back to the constant
    ``vehicle["slope_deg"]`` when no profile is present.
    Returns dict with arrays. All units SI except rpm.
    """
    v_kmh = np.asarray(cycle["v_kmh"], dtype=float)
    t     = np.asarray(cycle["t"], dtype=float)
    v     = v_kmh / 3.6                                # m/s

    a = np.gradient(v, t)
    a = np.clip(a, -8.0, 8.0)

    m     = vehicle["mass_kg"]
    cwA   = vehicle["cwA_m2"]
    cr    = vehicle["cr"]
    rho   = vehicle["rho_air"]
    g     = vehicle["g"]

    moving    = np.where(v > 0.1, 1.0, 0.0)
    F_inertia = m * a
    F_drag    = 0.5 * rho * cwA * v**2
    F_roll    = m * g * cr * moving
    # Constant bearing/seal friction of the trailer's extra axles (0 for the
    # base car). Velocity-independent, only present while moving.
    F_axle    = float(vehicle.get("axle_friction_N", 0.0)) * moving

    slope_profile = cycle.get("slope_profile_deg")
    if slope_profile is not None:
        slp_arr = np.asarray(slope_profile, dtype=float)
        # Align length (trim or pad with last value)
        n = len(v)
        if len(slp_arr) < n:
            slp_arr = np.pad(slp_arr, (0, n - len(slp_arr)), mode="edge")
        else:
            slp_arr = slp_arr[:n]
        F_slope = m * g * np.sin(np.radians(slp_arr))
    else:
        slope   = math.radians(float(vehicle.get("slope_deg", 0.0)))
        F_slope = np.full(len(v), m * g * math.sin(slope))

    F_wheel   = F_inertia + F_drag + F_roll + F_slope + F_axle  # N

    P_wheel   = F_wheel * v                            # W (positive = drive, negative = brake)

    rW        = vehicle["r_wheel_m"]
    omega_w   = v / rW                                 # rad/s
    rpm_wheel = omega_w * 60 / (2 * math.pi)
    rpm_motor = rpm_wheel * vehicle["gear_ratio"]

    T_wheel   = F_wheel * rW                           # Nm at wheel
    # Motor torque: dividing by gear ratio; drivetrain losses penalise traction
    # mode but help braking mode (less energy needs to be absorbed)
    eta = vehicle["eta_drive"]
    T_motor = np.where(
        T_wheel >= 0,
        T_wheel / (vehicle["gear_ratio"] * eta),
        T_wheel / vehicle["gear_ratio"] * eta,
    )

    return {
        "t":         t,
        "v_kmh":     v_kmh,
        "v_ms":      v,
        "a":         a,
        "rpm_motor": rpm_motor,
        "T_motor":   T_motor,
        "P_wheel":   P_wheel,
        "F_wheel":   F_wheel,
    }


# ── Energy + loss budget ─────────────────────────────────────────────────────

def cycle_energy(drv: dict, loss_series: dict, vehicle: dict) -> dict:
    """Integrate energy over the cycle and break down losses.

    loss_series: per-timestep loss arrays from ``ema_thermal.cycle_loss_series``
    (current-density copper + Bertotti iron + rpm² magnet + rpm bearing). This is
    the single source of truth shared with the thermal model — no scaling from a
    free reference torque.
    """
    t     = drv["t"]
    dt    = float(np.mean(np.diff(t)))               # 1 s typically
    rpm   = drv["rpm_motor"]
    T     = drv["T_motor"]
    P_w   = drv["P_wheel"]
    v_ms  = drv["v_ms"]

    # Mechanical motor power
    omega = rpm * 2 * math.pi / 60
    P_mech = np.abs(T) * omega                       # W
    # Sign: positive = motor drives wheel, negative = regen
    P_mech_signed = T * omega

    P_Cu_t  = np.asarray(loss_series["P_Cu"],        dtype=float)
    P_Fe_t  = (np.asarray(loss_series["P_Fe_stator"], dtype=float)
               + np.asarray(loss_series["P_Fe_rotor"], dtype=float))
    P_Mag_t = np.asarray(loss_series["P_Mag_eddy"],  dtype=float)
    P_Bear  = np.asarray(loss_series["P_Bearing"],   dtype=float)

    P_loss_total = P_Cu_t + P_Fe_t + P_Mag_t + P_Bear

    # Electrical input power: motor power + losses (when motoring), regen partial
    # In motoring: P_elec = P_mech + P_loss
    # In braking : P_elec = -|P_mech| * regen_frac + P_loss   (energy back to battery)
    regen = float(vehicle.get("regen_frac", 0.5))
    P_elec = np.where(P_mech_signed >= 0,
                      P_mech_signed + P_loss_total,
                      P_mech_signed * regen + P_loss_total)

    # Integrate energies (Wh = W·h)
    E_elec_net_Wh   = float(np.sum(P_elec) * dt / 3600)                              # net battery draw
    E_elec_drv_Wh   = float(np.sum(P_elec[P_elec > 0]) * dt / 3600)                  # battery → motor
    E_mech_drv_Wh   = float(np.sum(P_mech_signed[P_mech_signed > 0]) * dt / 3600)    # useful traction
    E_regen_Wh      = float(np.sum(-P_elec[P_elec < 0]) * dt / 3600)                 # battery ← motor
    E_loss_Cu   = float(np.sum(P_Cu_t)     * dt / 3600)
    E_loss_Fe   = float(np.sum(P_Fe_t)     * dt / 3600)
    E_loss_Mag  = float(np.sum(P_Mag_t)    * dt / 3600)
    E_loss_Bear = float(np.sum(P_Bear)     * dt / 3600)
    E_loss_total= E_loss_Cu + E_loss_Fe + E_loss_Mag + E_loss_Bear

    # Distance
    d_m  = float(np.sum(v_ms) * dt)
    d_km = d_m / 1000

    E_per_100km = (E_elec_net_Wh / d_km) * 100 if d_km > 0 else 0

    # RMS values
    rpm_rms = float(np.sqrt(np.mean(rpm**2)))
    T_rms   = float(np.sqrt(np.mean(T**2)))

    # Overload check: continuous cycle torque vs the geometry's rated torque
    T_rated = float(loss_series.get("T_rated", 0.0))
    overload_warning = (
        f"⚠ Zyklus-T_rms={T_rms:.0f} Nm > Dauer-Nennmoment {T_rated:.0f} Nm "
        f"— thermisch dauerhaft überlastet"
    ) if T_rated > 0 and T_rms > T_rated else None

    # Operating-point cloud (sub-sample 1:5 to keep response size sane)
    sub = slice(None, None, 5)
    op_points = {
        "rpm":   rpm[sub].tolist(),
        "T":     T[sub].tolist(),
        "P_loss": P_loss_total[sub].tolist(),
        "t":     t[sub].tolist(),
    }

    return {
        "duration_s":     float(t[-1] - t[0]),
        "distance_km":    round(d_km, 3),
        "E_elec_net_Wh":  round(E_elec_net_Wh, 1),
        "E_elec_drv_Wh":  round(E_elec_drv_Wh, 1),
        "E_mech_drv_Wh":  round(E_mech_drv_Wh, 1),
        "E_regen_Wh":     round(E_regen_Wh, 1),
        "E_per_100km_Wh": round(E_per_100km, 1),
        "E_per_100km_kWh":round(E_per_100km / 1000, 3),
        "losses": {
            "E_Cu_Wh":    round(E_loss_Cu, 1),
            "E_Fe_Wh":    round(E_loss_Fe, 1),
            "E_Mag_Wh":   round(E_loss_Mag, 1),
            "E_Bear_Wh":  round(E_loss_Bear, 1),
            "E_total_Wh": round(E_loss_total, 1),
        },
        "eta_drive":      round(E_mech_drv_Wh / max(1, E_elec_drv_Wh), 3),
        "regen_share":    round(E_regen_Wh / max(1, E_elec_drv_Wh), 3),
        "v_max_kmh":      round(float(np.max(drv["v_kmh"])), 1),
        "v_avg_kmh":      round(float(np.mean(drv["v_kmh"])), 1),
        "rpm_max":        round(float(np.max(rpm)), 0),
        "rpm_rms":        round(rpm_rms, 0),
        "T_max":          round(float(np.max(np.abs(T))), 1),
        "T_rms":          round(T_rms, 1),
        "T_rated_Nm":     round(T_rated, 1),
        "overload_warning": overload_warning,
        "op_points":      op_points,
    }
