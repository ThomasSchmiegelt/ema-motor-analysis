"""Python FDM field solver + analytical EM estimates for IPM motors."""

import math
from collections import OrderedDict

import numpy as np

from ema_topology import magnet_legs

try:                                    # direct sparse solver (exact at any grid size)
    import scipy.sparse as _sp
    import scipy.sparse.linalg as _spla
    _HAVE_SCIPY = True
except Exception:                       # pragma: no cover — fall back to iterative SOR
    _HAVE_SCIPY = False

try:                                    # iterative AMG solver for very high resolution
    import pyamg
    _HAVE_PYAMG = True
except Exception:                       # pragma: no cover — fall back to direct solver
    _HAVE_PYAMG = False

# Above this grid size the direct splu factorisation needs too much memory
# (~15 GB at N=2500, ~70 GB at N=5000); switch to the pyamg AMG branch instead.
_DIRECT_N_MAX = 2500

# LU-factorisation cache for the field operator.  The operator depends only on
# the permeability map mu (geometry + rotor angle), NOT on the stator/magnet
# currents (those live in the RHS J).  So one factorisation is reused for every
# RPM / current-angle / load step at the same rotor position — the rotate sweep
# re-uses the same handful of angles across all RPMs, and the standstill modes
# factor once.  Keyed by (N, hash(mu)); LRU-evicted to bound memory.
_LU_CACHE = OrderedDict()
_LU_CACHE_MAX = 48

# AMG-hierarchy cache (used for N > _DIRECT_N_MAX).  Hierarchies are large, so a
# small LRU (a few rotor angles) is enough.  Keyed like _LU_CACHE: (N, hash(mu)).
_AMG_CACHE = OrderedDict()
_AMG_CACHE_MAX = 6


def clear_lu_cache():
    """Drop all cached factorisations (call between analyses to free memory)."""
    _LU_CACHE.clear()
    _AMG_CACHE.clear()

# Material constants
Br_NdFeB   = 1.15   # T – NdFeB N35 remanence
MU_R_MAG   = 1.05   # NdFeB relative permeability
MU_R_IRON  = 500.0  # electrical steel (linear; see _saturate_mu for the B-H pass)
MU0        = 4e-7 * math.pi
B_SAT_IRON = 2.0    # T – electrical-steel saturation knee (nonlinear μ pass)

# Inverter limits — the ONLY place they are defined. They were previously buried as
# literals in `estimate_dq_currents` (v_dc default 800, the 800 A current clamp);
# `power_envelope` needs exactly the same two numbers, and a torque/speed envelope
# drawn against different limits than the operating point would be a silent lie.
INVERTER_V_DC  = 800.0   # DC-link voltage [V]
INVERTER_I_MAX = 800.0   # phase current amplitude [A_pk], at 1 turn/slot (see Kt)
AIR_DOMAIN_FACTOR = 1.25   # outer air-box radius = statorOD/2 · this (Dirichlet A=0)
# A real air gap (0.5–1 mm) is sub-pixel at usable N (e.g. 0.7 mm vs ~1.2 mm/px at
# N=300), so the rotor/stator iron rings touch and the gap is unresolved.  Sampling
# the field there reads the IRON field (radial suppressed, large spurious tangential
# from the staircased rim) → the plotted B_t wrongly dominates B_r.  We open a clean
# air band just BELOW the stator bore (removing rotor-rim iron only) so Br/Bt can be
# read in genuine air while the stator-iron boundary (which pins B_t→0 at the bore)
# is preserved.  The band is PHYSICAL (mm) so it is a no-op at low/animation N (sub-
# pixel → nothing removed) and only resolves the gap once N is high enough.
AIRGAP_MIN_MM   = 2.5      # target resolved air-gap width [mm] (≈4 px at N=600)
AIRGAP_SMOOTH_DEG = 1.5    # angular boxcar on sampled Br/Bt (< slot pitch) — kills
                           # per-pixel staircase spikes, keeps slot/pole harmonics
AIRGAP_PROFILE_N  = 700    # min FDM resolution for the (static) air-gap Br/Bt chart

# Removed: ID_FW_FLOOR = 350.0  (arbitrary absolute floor — replaced by geometry-based saliency)


# ── geometry rasterisation ────────────────────────────────────────────────────

def _rasterise(geom: dict, N: int, rotor_angle: float = 0.0,
               iq: float = 0.0, id_: float = 0.0, maps: bool = False):
    """Build mu_r and J arrays for the 2-D motor cross-section.

    iq, id_ inject stator currents (Amps) via dq-transform per slot.

    maps=True additionally returns a dict of the intermediate fields that are
    otherwise thrown away — needed by the ML surrogate encoder
    (``physics_surrogate/data/encode2d.py``), which must not re-implement this
    rasterisation (a second implementation would silently drift from this one):

      ``iron`` / ``magnet`` / ``air`` : bool (N,N) material masks, derived from the
          FINAL ``mu`` (so the air-gap carve below is already reflected — exactly the
          same classification the rest of this module uses, cf. ``_saturate_field``).
      ``Mx`` / ``My`` : float32 (N,N) magnetisation vector field. NOTE only its curl
          (``∂My/∂x − ∂Mx/∂y``) survives into ``J``, so the magnet polarity/direction
          is NOT recoverable from the regular return values — that is the main reason
          this switch exists.
      ``j_amp`` : the amplitude scale of Mx/My (``6000/N``, i.e. grid-dependent);
          divide by it for a unit-magnetisation field instead of hardcoding it.

    Known raster quirk (PRE-EXISTING, do not "fix" here — it would change the field):
    ``Mx/My`` can be non-zero on a few pixels that the masks classify as AIR. The
    obround end cap of a magnet drawn later (``mu[cap_air] = 1.0``) overwrites the mu of
    a magnet drawn earlier where multi-layer pockets touch, while the accumulated
    magnetisation of the earlier magnet stays. Measured ~1 % of magnetised pixels for a
    3-layer V-IPM, 0 % for surface/PMa-SynRM topologies. The encoder must therefore not
    assume ``M != 0 ⇒ magnet``.

    The default return signature is unchanged (4-tuple), so every existing caller is
    unaffected; gated by ``smoke_test.py`` + ``test_fdm_golden.py``.
    """
    # Air domain: pad 25 % beyond the stator OD so the outer Dirichlet boundary
    # (A=0) sits well clear of the iron — keeps the external/leakage field lines
    # from being squared off against a too-tight box (boundary artefact). The cost
    # is ~14 % coarser machine features per N; raise N for a sharp air gap.
    maxD   = geom["statorOD"] * AIR_DOMAIN_FACTOR
    sc     = N / maxD          # px / mm
    ctr    = N / 2

    ix = np.arange(N, dtype=np.float32) - ctr
    X, Y = np.meshgrid(ix, ix)
    R = np.hypot(X, Y)

    r_so = (geom["statorOD"] / 2) * sc
    r_si = (geom["statorID"] / 2) * sc
    r_ro = (geom["rotorOD"]  / 2) * sc
    r_sh = (geom["shaftD"]   / 2) * sc

    mu = np.ones((N, N), dtype=np.float32)
    J  = np.zeros((N, N), dtype=np.float32)

    # Iron rings: stator, rotor, and the (steel) shaft. A hollow shaft bore is
    # carved back out as air so the field routes differently around it.
    mu[(R >= r_si) & (R <= r_so)] = MU_R_IRON
    mu[(R >= r_sh) & (R <= r_ro)] = MU_R_IRON
    mu[R <= r_sh] = MU_R_IRON                       # solid (steel) shaft
    r_bore = (geom.get("shaftBoreD", 0) / 2) * sc
    if r_bore > 0:
        mu[R <= r_bore] = 1.0                       # hollow-shaft bore (air)

    # Balance-disc bolt holes (optional): symmetric through-holes in the rotor iron,
    # count = pole number, on a pitch circle (Ø/offset adjustable). They rotate WITH
    # the rotor (rotor_angle), so the FDM field "sees" them just like the structural
    # FEM does — modelled as air flux barriers (the steel bolt + clearance gap carry
    # little flux at this scale). Mirrors the FreeCAD/2D/canvas hole geometry.
    if bool(geom.get("genBalanceBolts", False)):
        _thr_d = {"M4": 4.0, "M5": 5.0, "M6": 6.0, "M8": 8.0, "M10": 10.0,
                  "M12": 12.0, "M16": 16.0, "M20": 20.0}
        _bnom  = _thr_d.get(str(geom.get("balanceBoltThread", "M6")).upper(), 6.0)
        _bhr   = ((_bnom + 0.4) / 2.0) * sc                 # clearance hole radius [px]
        _bcd   = float(geom.get("balanceBoltCircleD", 0) or 0)
        _bpcr  = (_bcd / 2.0 if _bcd > 0
                  else geom["shaftD"] / 2 + (geom["rotorOD"] / 2 - geom["shaftD"] / 2) * 0.5) * sc
        _boff  = math.radians(float(geom.get("balanceBoltOffsetDeg", 0)))
        _nb    = max(2, int(geom["p"]) * 2)
        for _i in range(_nb):
            _a  = _boff + rotor_angle + _i * 2 * math.pi / _nb
            _hx = _bpcr * math.cos(_a)
            _hy = _bpcr * math.sin(_a)
            mu[((X - _hx) ** 2 + (Y - _hy) ** 2) <= _bhr ** 2] = 1.0

    # Flux-barrier radial slots (optional): air slots in the rotor iron, q-axis
    # (between poles) and/or d-axis (pole centre). One per pole each, rotating WITH
    # the rotor so the field "sees" them like the FEM/CAD. Mirrors the FreeCAD slots.
    if bool(geom.get("genFluxBarrierQ", False)) or bool(geom.get("genFluxBarrierD", False)):
        _poles = int(geom["p"]) * 2
        _fbw   = max(0.5, min(40.0, float(geom.get("fluxBarrierWidth", 3.0)))) * sc
        _fbd   = max(1.0, min(120.0, float(geom.get("fluxBarrierDepth", 10.0)))) * sc
        _r_out = r_ro - 2.0 * sc                        # bridge below the OD
        _r_in  = max(r_sh + 1.0 * sc, _r_out - _fbd)
        _angs  = []
        if bool(geom.get("genFluxBarrierD", False)):
            _angs += [rotor_angle + i * 2 * math.pi / _poles for i in range(_poles)]
        if bool(geom.get("genFluxBarrierQ", False)):
            _angs += [rotor_angle + (i + 0.5) * 2 * math.pi / _poles for i in range(_poles)]
        _Th_fb = np.arctan2(Y, X)
        for _a in _angs:
            _dth = np.abs(((_Th_fb - _a + math.pi) % (2 * math.pi)) - math.pi)
            # tangential half-width w/2 → angular half-width (w/2)/r; band in radius
            _slot = (R >= _r_in) & (R <= _r_out) & (R * _dth <= _fbw / 2.0)
            mu[_slot] = 1.0

    # Custom (designer) flux barriers: free-form polylines in the pole-local frame,
    # replicated per pole + rotating with the rotor. Each barrier = a thick polyline
    # (capsule), carved as air. Mirrors the FreeCAD custom-barrier solids.
    _cbars = geom.get("customBarriers") or []
    if _cbars:
        _poles_c = int(geom["p"]) * 2
        for _p in range(_poles_c):
            _pa = _p * 2 * math.pi / _poles_c + rotor_angle
            _ca, _sa = math.cos(_pa), math.sin(_pa)
            for _bar in _cbars:
                _pts = _bar.get("pts") or []
                _w   = max(0.5, float(_bar.get("width", 3.0))) * sc / 2.0   # half-width px
                _gp  = [((px * _ca - py * _sa) * sc, (px * _sa + py * _ca) * sc)
                        for px, py in _pts]
                for _i in range(len(_gp) - 1):
                    _ax, _ay = _gp[_i]; _bx, _by = _gp[_i + 1]
                    _dx, _dy = _bx - _ax, _by - _ay
                    _ll = _dx * _dx + _dy * _dy
                    if _ll < 1e-9:
                        continue
                    _t = np.clip(((X - _ax) * _dx + (Y - _ay) * _dy) / _ll, 0.0, 1.0)
                    _cx = _ax + _t * _dx; _cy = _ay + _t * _dy
                    mu[((X - _cx) ** 2 + (Y - _cy) ** 2) <= _w * _w] = 1.0

    # Stator slots (air) + winding currents (dq-modulated by rotor angle)
    n_slots    = int(geom["slots"])
    p_pairs    = int(geom["p"])
    slot_d_px  = geom["slotDepth"] * sc
    dtheta_s   = 2 * math.pi / n_slots
    sw         = dtheta_s * 0.5 / 2           # half angular width of slot
    Th = np.arctan2(Y, X)

    # IQ_REF=2.0 gives ~50 % stator-to-magnet J ratio at rated 800 A with converged FDM.
    # (Old IQ_REF=7 was calibrated for the diverging float32 solver — now invalid.)
    IQ_REF = 2.0
    J_slot_scale = 5.0 / N
    has_current = (abs(iq) + abs(id_)) > 0.1

    for s in range(n_slots):
        ang  = s * dtheta_s
        diff = np.abs(((Th - ang + math.pi) % (2 * math.pi)) - math.pi)
        mask = diff < sw
        mask &= (R >= r_si) & (R <= r_si + slot_d_px)
        mu[mask] = 1.0

        if has_current:
            elAng = ang * p_pairs
            cur = (id_ * math.cos(elAng - rotor_angle * p_pairs)
                   - iq * math.sin(elAng - rotor_angle * p_pairs)) / IQ_REF
            J[mask] += cur * J_slot_scale

    # Magnets – permanent magnet modelled via numerical curl of M.
    # Standard 2-D FEM approach: J_z_eq = ∂My/∂x − ∂Mx/∂y where M = amp·t̂
    # inside the magnet and 0 outside.  The finite-difference gradient at the
    # boundary pixels automatically produces the correct surface-current term
    # without point-source artefacts.
    poles    = int(geom["p"]) * 2
    legs, _meta = magnet_legs(geom)   # single source of truth (ema_topology)

    J_amp  = 6000.0 / N
    Mx_acc = np.zeros((N, N), dtype=np.float32)
    My_acc = np.zeros((N, N), dtype=np.float32)

    for p_i in range(poles):
        pole_ang = p_i * (2 * math.pi / poles) + rotor_angle
        sign     = 1 if p_i % 2 == 0 else -1
        cp, sp   = math.cos(pole_ang), math.sin(pole_ang)

        for lg in legs:
            long_ang = pole_ang + lg.tilt
            lx = math.cos(long_ang); ly = math.sin(long_ang)

            # Magnetisation direction (global frame) by mode.
            if lg.mag_mode == "tangential":
                mdx, mdy = -sp, cp                       # tangential at pole
            elif lg.mag_mode == "radial":
                base = pole_ang + lg.mag_rot
                mdx, mdy = math.cos(base), math.sin(base)
            else:                                         # "perp": perp. to long axis
                mdx, mdy = -ly, lx
            # Optional 90° re-orientation: rotate the magnetisation vector so the
            # SHORT magnet side carries the poles instead of the long side
            # (UI magOrient="longitudinal"). Mirrored 1:1 in ema.html stepPhysics.
            if geom.get("magOrient") == "longitudinal":
                mdx, mdy = -mdy, mdx

            cap_air = None
            if lg.placement == "surface":
                # Annular shell wedge on the rotor OD; length = arc length [mm],
                # offset = tangential arc-length shift of the segment centre.
                magH_px = lg.thickness * sc
                center_ang = pole_ang + lg.offset / (geom["rotorOD"] / 2)
                half_arc = (lg.length / 2) / (geom["rotorOD"] / 2)
                dth = np.abs(((Th - center_ang + math.pi) % (2 * math.pi)) - math.pi)
                # surface magnets occupy the OUTER rotor band (inside the OD)
                in_mag = (R >= r_ro - magH_px) & (R <= r_ro) & (dth <= half_arc)
            else:
                # Straight rectangular magnet. "interior" adds semicircular AIR end
                # caps (obround pocket flux barriers); "surface_flat" (Halbach flat
                # tile) is the bare rectangle, no caps/pocket.
                sx_g = lg.r_pos * sc * cp - lg.offset * sc * sp
                sy_g = lg.r_pos * sc * sp + lg.offset * sc * cp
                magW_px = lg.length * sc
                magH_px = lg.thickness * sc
                r_cap = magH_px / 2
                dx = X - sx_g;  dy = Y - sy_g
                l_c = dx * lx + dy * ly
                t_c = dx * (-ly) + dy * lx
                in_mag = (l_c >= 0) & (l_c <= magW_px) & (np.abs(t_c) <= magH_px / 2)
                if lg.placement == "interior":
                    cap_air = (((l_c < 0) & (l_c ** 2 + t_c ** 2 <= r_cap ** 2)) |
                               ((l_c > magW_px) & ((l_c - magW_px) ** 2 + t_c ** 2 <= r_cap ** 2)))

            if cap_air is not None:
                mu[cap_air] = 1.0                # air flux barrier (set before magnet)
            mu[in_mag] = MU_R_MAG
            amp = J_amp * sign * lg.mag_sign
            Mx_acc[in_mag] += amp * mdx
            My_acc[in_mag] += amp * mdy

    # J_z = curl(M) = ∂My/∂x − ∂Mx/∂y  (central differences, no wrap-around)
    dMy_dx = np.zeros((N, N), dtype=np.float32)
    dMy_dx[:, 1:-1] = (My_acc[:, 2:] - My_acc[:, :-2]) * 0.5
    dMy_dx[:,  0]   =  My_acc[:,  1] - My_acc[:,  0]
    dMy_dx[:, -1]   =  My_acc[:, -1] - My_acc[:, -2]

    dMx_dy = np.zeros((N, N), dtype=np.float32)
    dMx_dy[1:-1, :] = (Mx_acc[2:, :] - Mx_acc[:-2, :]) * 0.5
    dMx_dy[ 0,  :]  =  Mx_acc[ 1, :] - Mx_acc[ 0, :]
    dMx_dy[-1,  :]  =  Mx_acc[-1, :] - Mx_acc[-2, :]

    J += dMy_dx - dMx_dy

    # Resolve the air gap (see AIRGAP_MIN_MM): open a clean air band of width
    # max(physical gap, AIRGAP_MIN_MM) just BELOW the stator bore by removing the
    # rotor-rim IRON there (magnets / slot air kept — iron-only mask).  The stator
    # iron at r_si is deliberately left intact so its boundary condition keeps the
    # radial component dominant.  Physical width ⇒ sub-pixel (no-op) at animation N,
    # a properly resolved band once N is high enough (chart runs at AIRGAP_PROFILE_N).
    band_px = max(r_si - r_ro, AIRGAP_MIN_MM * sc)
    ring = (R >= r_si - band_px) & (R < r_si) & (mu >= MU_R_IRON - 1e-3)
    mu[ring] = 1.0

    if maps:
        # Material classification from the final mu (1.0 air / MU_R_MAG magnet /
        # MU_R_IRON iron). Tolerance bands rather than == so a future float32 mu value
        # cannot silently fall out of a class.
        m_iron = mu >= MU_R_IRON - 1e-3
        m_mag  = (mu > 1.0 + 1e-3) & ~m_iron
        return mu, J, sc, ctr, {
            "iron":   m_iron,
            "magnet": m_mag,
            "air":    ~(m_iron | m_mag),
            "Mx":     Mx_acc,
            "My":     My_acc,
            "j_amp":  J_amp,
        }

    return mu, J, sc, ctr


# ── FDM solver ────────────────────────────────────────────────────────────────

def _build_fv_matrix(mu: np.ndarray):
    """Assemble the variable-ν Poisson operator −∇·(ν∇A) on a uniform grid.

    Finite-volume 5-point stencil with harmonic-mean face conductivities
    (ν = 1/µ), Dirichlet A = 0 on the outer boundary (the rasteriser leaves a
    10 % air margin, so A→0 there is physical).  Returns the symmetric positive-
    definite matrix over the interior unknowns plus the interior mask.  A global
    scale factor (the omitted h²) is irrelevant — the caller calibrates the
    air-gap peak to the analytical value, so only the field *pattern* matters.
    """
    N  = mu.shape[0]
    nu = 1.0 / mu.astype(np.float64)
    interior = np.zeros((N, N), bool)
    interior[1:-1, 1:-1] = True
    nint = int(interior.sum())
    cid = -np.ones((N, N), dtype=np.int64)
    cid[interior] = np.arange(nint)

    diag = np.zeros((N, N))
    rows, cols, vals = [], [], []
    for di, dj in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nb     = np.roll(nu,       (-di, -dj), (0, 1))
        f      = 2.0 * nu * nb / (nu + nb)            # harmonic-mean face ν
        nb_int = np.roll(interior, (-di, -dj), (0, 1))
        nb_id  = np.roll(cid,      (-di, -dj), (0, 1))
        diag  += np.where(interior, f, 0.0)           # every face adds to its diag
        m = interior & nb_int                         # off-diagonals: interior↔interior
        rows.append(cid[m]); cols.append(nb_id[m]); vals.append(-f[m])
    rows.append(cid[interior]); cols.append(cid[interior]); vals.append(diag[interior])
    M = _sp.csc_matrix((np.concatenate(vals),
                        (np.concatenate(rows), np.concatenate(cols))),
                       shape=(nint, nint))
    return M, interior


def _solve_fdm(mu: np.ndarray, J: np.ndarray, iters: int | None = None) -> np.ndarray:
    """Solve ∇·(ν∇A) = −J exactly via a cached direct sparse factorisation.

    SuperLU factorises −∇·(ν∇A) once per permeability map and back-substitutes
    for the RHS J.  This converges in one shot at any grid size (no iteration-
    count tuning), so the air gap and stator teeth resolve cleanly at high N —
    e.g. N=600 factors in ~3 s, each subsequent same-geometry solve in <0.1 s.
    Falls back to the iterative defect-correction SOR if SciPy is unavailable.
    The `iters` argument is accepted for backwards compatibility and ignored
    by the direct path.
    """
    if not _HAVE_SCIPY:
        return _solve_fdm_sor(mu, J, iters if iters is not None else 180)

    N   = mu.shape[0]
    if N > _DIRECT_N_MAX:
        if _HAVE_PYAMG:
            return _solve_fdm_amg(mu, J)
        raise MemoryError(
            f"Gitter N={N} überschreitet das Limit des direkten Solvers "
            f"({_DIRECT_N_MAX}); für höhere Auflösung wird pyamg benötigt "
            f"(pip install pyamg).")

    key = (N, hash(mu.tobytes()))
    cached = _LU_CACHE.get(key)
    if cached is None:
        M, interior = _build_fv_matrix(mu)
        lu = _spla.splu(M)
        _LU_CACHE[key] = (lu, interior)
        if len(_LU_CACHE) > _LU_CACHE_MAX:
            _LU_CACHE.popitem(last=False)
    else:
        lu, interior = cached
        _LU_CACHE.move_to_end(key)

    A = np.zeros((N, N), dtype=np.float64)
    A[interior] = lu.solve(J.astype(np.float64)[interior])
    return A


def _solve_fdm_amg(mu: np.ndarray, J: np.ndarray) -> np.ndarray:
    """Solve ∇·(ν∇A) = −J via CG-accelerated algebraic multigrid (pyamg).

    For very high resolution (N > _DIRECT_N_MAX) the direct splu factorisation
    needs tens of GB.  AMG solves the same SPD interior operator from
    `_build_fv_matrix` in ~O(M) memory.  The multigrid hierarchy depends only on
    µ (geometry + rotor angle), so it is cached by (N, hash(mu)) — like the LU
    cache — and reused across all current/load steps at the same rotor position;
    a cache hit costs just the cheap CG solve.  Pure CG stalls on the µ=500 iron
    jump, so smoothed-aggregation AMG (with a Ruge-Stüben fallback) is used.
    """
    N   = mu.shape[0]
    key = (N, hash(mu.tobytes()))
    cached = _AMG_CACHE.get(key)
    if cached is None:
        M, interior = _build_fv_matrix(mu)
        ml = pyamg.smoothed_aggregation_solver(M, max_coarse=2000)
        _AMG_CACHE[key] = (ml, interior, M)
        if len(_AMG_CACHE) > _AMG_CACHE_MAX:
            _AMG_CACHE.popitem(last=False)
    else:
        ml, interior, M = cached
        _AMG_CACHE.move_to_end(key)

    b   = J.astype(np.float64)[interior]
    res = []
    x   = ml.solve(b, tol=1e-8, accel="cg", maxiter=300, residuals=res)

    # Fall back to Ruge-Stüben (more robust on hard coefficient jumps) if the
    # smoothed-aggregation cycle failed to reduce the residual enough.
    if len(res) >= 2 and res[0] > 0 and res[-1] / res[0] > 1e-4:
        ml2 = pyamg.ruge_stuben_solver(M, max_coarse=2000)
        res2 = []
        x2 = ml2.solve(b, tol=1e-8, accel="cg", maxiter=300, residuals=res2)
        if len(res2) >= 2 and res2[0] > 0 and res2[-1] / res2[0] < res[-1] / res[0]:
            ml, x, res = ml2, x2, res2
            _AMG_CACHE[key] = (ml, interior, M)
        if len(res) >= 2 and res[0] > 0 and res[-1] / res[0] > 1e-4:
            print(f"WARN: AMG-Solver konvergierte nur auf "
                  f"{res[-1] / res[0]:.1e} relativ (N={N})")

    A = np.zeros((N, N), dtype=np.float64)
    A[interior] = x
    return A


def _solve_fdm_sor(mu: np.ndarray, J: np.ndarray, iters: int = 180) -> np.ndarray:
    """Solve ∇(ν∇A) = −J via defect-correction: fast uniform SOR + outer ∇ν·∇A fix.

    WHY THE PREVIOUS APPROACH WAS WRONG:
    The old code solved ∇²A = −µJ (uniform Laplacian, coefficient 0.25 everywhere).
    That is only correct for constant µ.  With variable µ, field lines spread equally
    through iron and air — the permeability has no guiding effect on the topology.

    THE CORRECT EQUATION:  ∇(ν∇A) = −J  where  ν = 1/µ
    Expanding:  ν·∇²A + (∇ν)·(∇A) = −J
    →           ∇²A = −µJ − µ·(∇ν)·(∇A)          [defect-correction form]
                     = −µJ + (∇ log µ)·(∇A)

    SOLVER STRATEGY (defect-correction outer loop):
    Each outer step:
      1. Compute correction f = (∇ log µ)·(∇A) from current A.
      2. Run `inner` steps of fast uniform Red-Black SOR on ∇²A = −µJ + f.
    The inner SOR uses the uniform stencil (ω~1.65, fast convergence), while the
    outer loop drives the solution towards the correct variable-µ result.
    With µ-contrast ~500, 6 outer iterations of 30 inner steps (=180 total inner)
    converge to N/S pole asymmetry < 8 % — far better than a pure variable-ν SOR
    which needs thousands of iterations for the same accuracy.

    HOW THIS CHANNELS FLUX:
    (∇ log µ)·(∇A) is large only at iron–air interfaces (sharp µ jump).  The
    correction bends A contours so they follow iron paths, recreating the physical
    effect that high-µ iron is a preferential path for magnetic flux.  Field lines
    will be dense in the air gap and sparse outside the stator, as expected.
    """
    N     = mu.shape[0]
    mu64  = mu.astype(np.float64)
    J64   = J.astype(np.float64)
    sor   = 1.65                 # can stay high — inner problem is uniform Laplacian
    outer = 3                    # 3 outer corrections is optimal (more degrades quality)
    inner = max(40, iters // outer)  # spread iters evenly, at least 40 inner per step

    # log µ for gradient computation (clamped to avoid log(0))
    log_mu = np.log(np.clip(mu64, 1e-6, None))

    # Red-Black masks
    ii, jj = np.meshgrid(np.arange(N), np.arange(N), indexing='ij')
    red = ((ii + jj) % 2 == 0)
    blk = ~red

    src_base = mu64 * J64   # −∇²A without correction term
    A = np.zeros((N, N), dtype=np.float64)

    for _outer in range(outer):
        # ── Step 1: compute defect correction from current A ──────────────────
        # (∇ log µ)·(∇A)  — central differences, zero-padded at borders
        dlogmu_dx = np.gradient(log_mu, axis=1)
        dlogmu_dy = np.gradient(log_mu, axis=0)
        dA_dx     = np.gradient(A, axis=1)
        dA_dy     = np.gradient(A, axis=0)
        correction = dlogmu_dx * dA_dx + dlogmu_dy * dA_dy
        src = src_base - correction    # effective RHS for uniform Laplacian

        # ── Step 2: inner uniform Red-Black SOR ───────────────────────────────
        for _ in range(inner):
            nb  = (np.roll(A,  1, 0) + np.roll(A, -1, 0) +
                   np.roll(A,  1, 1) + np.roll(A, -1, 1))
            tgt = (nb + src) * 0.25
            A[red] += sor * (tgt[red] - A[red])
            A[0, :] = A[-1, :] = A[:, 0] = A[:, -1] = 0.0

            nb  = (np.roll(A,  1, 0) + np.roll(A, -1, 0) +
                   np.roll(A,  1, 1) + np.roll(A, -1, 1))
            tgt = (nb + src) * 0.25
            A[blk] += sor * (tgt[blk] - A[blk])
            A[0, :] = A[-1, :] = A[:, 0] = A[:, -1] = 0.0

    return A


# ── air-gap sampling ──────────────────────────────────────────────────────────

def _circ_smooth(sig, win):
    """Periodic (wrap-around) boxcar average — used to de-spike air-gap profiles."""
    if win <= 1:
        return sig
    k   = np.ones(win) / win
    pad = np.concatenate([sig[-win:], sig, sig[:win]])
    return np.convolve(pad, k, mode="same")[win:-win]


def _interp2(arr, xf, yf):
    N  = arr.shape[0]
    x0 = np.floor(xf).astype(int).clip(0, N - 2)
    y0 = np.floor(yf).astype(int).clip(0, N - 2)
    fx = xf - x0;  fy = yf - y0
    return (arr[y0, x0]   * (1-fy)*(1-fx) + arr[y0+1, x0]   * fy*(1-fx) +
            arr[y0, x0+1] * (1-fy)*fx     + arr[y0+1, x0+1] * fy*fx)


def _material_labels(mu):
    """Coarse material class per cell from the LINEAR mu (0 air, 1 magnet, 2 iron).

    Must be fed the base mu from ``_rasterise`` — after the nonlinear pass the iron
    mu is a continuum and the classes would smear.
    """
    lbl = np.zeros(np.shape(mu), dtype=np.int8)
    mu  = np.asarray(mu)
    lbl[mu > 1.0 + 1e-6]        = 1
    lbl[mu >= MU_R_IRON - 1e-3] = 2
    return lbl


def _curl_a(A, lbl=None):
    """B = curl A = (∂A/∂y, −∂A/∂x) on the pixel grid, in A/pixel.

    With ``lbl`` given the difference stencil is **material aware**: it never spans
    a material change.  That is not cosmetic.  Only the NORMAL component of B is
    continuous across an iron/air or magnet/iron interface — the tangential one
    jumps by the mu ratio (up to 500), and the equivalent magnet surface current
    ``J = ∇×M`` sits exactly in those boundary cells.  A central difference there
    averages two physically different fields across a genuine discontinuity and
    returns a value belonging to neither.  Measured on the delta IPM at N=512
    (saturated pass): boundary cells read 2.14 T median / 14.0 T max against
    0.86 T median / 2.91 T max three cells in — the inflation was the stencil, not
    the field.  One-sided differencing from INSIDE the material gives the field of
    that material, which is what a per-cell |B| map is supposed to show.

    Cells whose neighbours on both sides are foreign (isolated 1-px slivers) keep
    the plain central difference — there is no in-material stencil to use, and they
    are rare (<0.2 % of iron at N=512).
    """
    if lbl is None:
        return np.gradient(A, axis=0), -np.gradient(A, axis=1)

    def _d(axis):
        df   = np.diff(A, axis=axis)                  # F[i+1] − F[i]
        same = np.diff(lbl, axis=axis) == 0
        lo   = [slice(None)] * A.ndim; lo[axis] = slice(0, -1)
        hi   = [slice(None)] * A.ndim; hi[axis] = slice(1, None)
        lo, hi = tuple(lo), tuple(hi)
        fwd = np.zeros_like(A); vf = np.zeros(A.shape, bool)
        bwd = np.zeros_like(A); vb = np.zeros(A.shape, bool)
        fwd[lo] = df; vf[lo] = same                   # forward diff lives at i
        bwd[hi] = df; vb[hi] = same                   # backward diff lives at i+1
        ctr = 0.5 * (fwd + bwd)                       # == np.gradient in the interior
        return np.where(vf & vb, ctr, np.where(vf, fwd, np.where(vb, bwd, ctr)))

    return _d(0), -_d(1)


def _sample_airgap(A, geom, sc, ctr, N, mu=None):
    """Air-gap radial/tangential flux profile + the full-grid Cartesian B arrays.

    The 1-D gap profile is taken DIRECTLY from the vector potential on the gap
    circle, not from the Cartesian gradient projected onto (r̂, t̂).  Projecting
    np.gradient(A) at the gap centre is corrupted by the staircase approximation
    of the round iron rim on the square grid: the local surface normal alternates
    between x̂ and ŷ, so a near-radial field leaks a large SPURIOUS tangential
    component (this made the plotted B_t dominate B_r — physically impossible).

    Instead:
      • Br = (1/r)·∂A/∂θ  — a derivative ALONG the smooth gap circle, so it never
        crosses the staircased rim → immune to that artefact.
      • Bt = −∂A/∂r       — sampled with a stencil kept inside the *resolved* air
        band (the rasteriser guarantees ≥ AIRGAP_MIN_PX cells of air at the gap).
    Both get a sub-slot-pitch angular boxcar to remove residual per-pixel spikes.
    Units are A/pixel as before, so the downstream analytical calibration (peak →
    B_gap) is unchanged.
    """
    r_ro_px = (geom["rotorOD"]  / 2) * sc
    r_si_px = (geom["statorID"] / 2) * sc

    # Full-grid B = curl A for the field-magnitude heatmap + iso-A field lines.
    # Material-aware stencil when mu is known (see _curl_a); the air-gap profile
    # below does NOT use these arrays, so torque/EMF are untouched either way.
    Bx_arr, By_arr = _curl_a(A, _material_labels(mu) if mu is not None else None)

    n_th  = 720
    theta = np.linspace(0, 2 * math.pi, n_th, endpoint=False)
    def _A_on(r):
        return _interp2(A, ctr + r * np.cos(theta), ctr + r * np.sin(theta))

    # Evaluate the profile just INSIDE the stator bore (r_si − 1 px): there the
    # stator-iron boundary pins the tangential field small and the radial component
    # is the working flux.  Br = (1/r)·∂A/∂θ is a derivative ALONG the circle, so it
    # never crosses the staircased iron rim → robust at any resolution.
    r_ev   = r_si_px - 1.0
    A_ev   = _A_on(r_ev)
    Br     = np.gradient(A_ev, 2 * math.pi / n_th) / r_ev

    # Bt = −∂A/∂r.  A finite difference across the sub-pixel gap is meaningless, so
    # fit the air-gap field to angular harmonics on TWO circles inside the resolved
    # air band (the rasteriser guarantees ≥ AIRGAP_MIN_MM of air below the bore) and
    # evaluate the analytic derivative at r_ev — spike-free by construction.  In the
    # current-free gap A is harmonic: A_n(r) = a_n (r/r_ev)^n + b_n (r/r_ev)^{-n}, so
    # Bt_n = −(n/r_ev)(a_n − b_n).  Limit to physical orders (≤ ~2.5·slots); higher
    # orders are grid noise.  If the band is too thin to resolve (low/animation N),
    # the 2×2 system is singular and Bt falls back to ~0 (physically correct: the
    # iron pins it) rather than the old staircase garbage.
    band = max(r_si_px - r_ro_px, AIRGAP_MIN_MM * sc)
    r_in  = r_si_px - band + 0.5
    r_out = r_si_px - 0.5
    Bt    = np.zeros(n_th)
    if r_out - r_in > 1.5:                                  # enough air to fit
        c_in  = np.fft.rfft(_A_on(r_in))
        c_out = np.fft.rfft(_A_on(r_out))
        n_max = min(len(c_in), int(2.5 * int(geom["slots"])) + 1)
        Bt_n  = np.zeros(len(c_in), dtype=complex)
        u_in, u_out = r_in / r_ev, r_out / r_ev
        for k in range(1, n_max):
            uip, uim = u_in ** k,  u_in ** -k
            uop, uom = u_out ** k, u_out ** -k
            det = uip * uom - uim * uop
            if abs(det) < 1e-9:
                continue
            a = (c_in[k] * uom - c_out[k] * uim) / det
            b = (c_out[k] * uip - c_in[k] * uop) / det
            Bt_n[k] = -(k / r_ev) * (a - b)
        Bt = np.fft.irfft(Bt_n, n_th)

    win = max(1, int(round(n_th * AIRGAP_SMOOTH_DEG / 360.0)))
    Br  = _circ_smooth(Br, win)
    Bt  = _circ_smooth(Bt, win)

    return Br, Bt, theta, Bx_arr, By_arr


# ── analytical estimates ──────────────────────────────────────────────────────

def _orient_factor(geom: dict) -> float:
    """Air-gap flux scaling for the magnet orientation toggle (``magOrient``).

    The useful radial air-gap flux scales with the radial component of the magnet
    magnetisation, |M·r̂|.  Rotating the magnetisation by 90°
    (``magOrient="longitudinal"``) changes that projection — e.g. for a perp-mode
    magnet from ∝|sin(tilt)| (long side N/S) to ∝|cos(tilt)| (short side N/S).
    This returns the ratio mean|M·r̂|_chosen / mean|M·r̂|_transverse, using the
    SAME per-mode magnetisation directions as ``_rasterise`` so the calibrated FDM
    field (which is otherwise pinned to the orientation-blind analytical B_gap)
    actually reflects the rotation.  ==1.0 for the default transverse orientation.
    """
    if geom.get("magOrient") != "longitudinal":
        return 1.0
    legs, _meta = magnet_legs(geom)
    cp, sp = 1.0, 0.0                       # representative pole at angle 0 (|·| only)
    num = den = 0.0
    for lg in legs:
        lx, ly = math.cos(lg.tilt), math.sin(lg.tilt)
        if lg.mag_mode == "tangential":
            mdx, mdy = -sp, cp
        elif lg.mag_mode == "radial":
            mdx, mdy = math.cos(lg.mag_rot), math.sin(lg.mag_rot)
        else:                                # "perp"
            mdx, mdy = -ly, lx
        den += abs(mdx * cp + mdy * sp)                 # transverse radial projection
        num += abs((-mdy) * cp + mdx * sp)              # rotated 90° (longitudinal)
    if den < 1e-6:                            # e.g. pure tangential (spoke) — leave as is
        return 1.0
    return num / den


def _analytical_Bgap(geom: dict) -> float:
    """Open-circuit air-gap flux density [T] from a magnetic-circuit estimate.

    IPM/V-magnets concentrate flux: the magnet source width per pole is the sum
    of the leg widths (2 for a V), referenced to the pole-arc width. The previous
    single-leg ``cos(magAngle/2)`` projection under-counted this badly and gave
    unrealistically low B_gap (~0.2 T for a 280 mm motor). ``eta_mag`` is a rough
    V-opening efficiency so the magAngle slider still moves the result.
    """
    hm = float(geom["magThick"])                          # thickness in flux path [mm]
    g  = max((geom["statorID"] - geom["rotorOD"]) / 2, 0.3)
    kc = 1.15                                              # Carter coefficient

    poles      = int(geom["p"]) * 2
    pole_pitch = math.pi * geom["statorID"] / poles        # [mm]
    _legs, meta = magnet_legs(geom)
    f_orient   = _orient_factor(geom)                       # 90°-rotation flux scaling

    if meta.is_surface:
        # Surface magnets occupy the outer rotor band (inside the OD) and face the
        # air gap directly; gap = statorID/2 - rotorOD/2 (normal mechanical gap).
        g_s   = max((geom["statorID"] - geom["rotorOD"]) / 2, 0.3)
        perm  = hm / (hm + MU_R_MAG * kc * g_s)
        alpha_i = min(meta.eta_hint, 0.98)                  # pole-arc coverage
        B_gap = Br_NdFeB * perm * alpha_i * f_orient
        return float(np.clip(B_gap, 0.05, 1.5))

    if meta.flux_focusing:
        # Spoke: tangential magnets concentrate flux into the iron pole. The
        # concentration factor = magnet radial face length / pole-arc width, so
        # B_gap can exceed Br when the pole pitch is small (high pole count).
        h_rad = max(geom["rotorOD"] / 2 - geom["shaftD"] / 2 - 2 * 1.0, 1.0)
        k_fc  = h_rad / pole_pitch
        perm  = hm / (hm + MU_R_MAG * kc * g)
        B_gap = Br_NdFeB * perm * k_fc * f_orient
        return float(np.clip(B_gap, 0.05, 2.2))

    n_legs     = meta.n_legs_per_pole                       # topology leg count
    eta_mag    = meta.eta_hint                              # opening efficiency
    k_leak     = 0.85                                       # bridge + end leakage
    # Flux concentration / pole coverage: magnet source width vs pole arc
    alpha_i    = min(n_legs * float(geom["magWidth"]) / pole_pitch * k_leak * eta_mag, 0.92)

    perm  = hm / (hm + MU_R_MAG * kc * g)                   # magnet load-line permeance
    B_gap = Br_NdFeB * perm * alpha_i * f_orient
    return float(np.clip(B_gap, 0.05, 1.5))


def _analytical_Barm(geom: dict, i_pk: float) -> float:
    """Peak fundamental armature-reaction air-gap flux density [T] at peak
    stator current ``i_pk`` [A].

    Standard distributed-winding estimate: the three phases set up a rotating
    MMF wave of peak amplitude F = (3/2)·(4/π)·(N_ph·k_w/(2p))·i_pk per pole,
    driven across the Carter-corrected q-axis air gap.  1 turn/slot is assumed,
    matching ``estimate_dq_currents`` (N_ph = slots/3, k_w = 0.95).  This is the
    calibration target for the FDM *stator* field, exactly as ``_analytical_Bgap``
    is for the *magnet* field — the two equivalent-current systems (dipolar
    curl-of-M vs. net slot current) have very different field-transfer gains and
    must be scaled independently.
    """
    if i_pk <= 1e-6:
        return 0.0
    p       = max(int(geom["p"]), 1)
    n_slots = int(geom["slots"])
    g       = max((geom["statorID"] - geom["rotorOD"]) / 2.0, 0.3)   # air gap [mm]
    kc      = 1.15                                                     # Carter factor
    k_w     = 0.95                                                     # winding factor
    N_ph    = max(n_slots / 3.0, 1.0)                                 # turns/phase (1/slot)
    g_eff_m = max((kc * g) / 1000.0, 1e-6)                            # q-axis path [m]
    F_pk    = 1.5 * (4.0 / math.pi) * (N_ph * k_w / (2.0 * p)) * i_pk
    B_arm   = MU0 * F_pk / g_eff_m
    return float(np.clip(B_arm, 0.0, 5.0))


def compute_performance(geom: dict, B_gap: float, rpm: float = 1000.0,
                        axial_mm: float | None = None) -> dict:
    """Key EM performance metrics from air gap flux density.

    axial_mm: actual stack length [mm]; defaults to 80 mm if not given.
    Passing the real axial length makes Kt, psi_pm and EMK geometry-accurate.
    """
    p       = int(geom["p"])
    poles   = p * 2
    n_slots = int(geom["slots"])
    L_ax    = (axial_mm / 1000.0) if axial_mm is not None else 0.080
    R_gap   = ((geom["statorID"] / 2) + (geom["rotorOD"] / 2)) / 2 / 1000  # m

    # Flux linkage (normalised, 1 turn per slot assumed)
    psi_pm  = p * (2 / math.pi) * B_gap * R_gap * L_ax
    omega_e = rpm * 2 * math.pi / 60 * p
    emf_pk  = psi_pm * omega_e
    emf_rms = emf_pk / math.sqrt(2)
    Kt      = 1.5 * p * psi_pm  # Nm / A_pk

    from math import gcd
    lcm = poles * n_slots // gcd(poles, n_slots)
    T_cogging_est = Br_NdFeB * R_gap * L_ax * 0.05 / lcm * 1000  # rough [Nm]

    return {
        "B_gap_T":          round(B_gap, 3),
        "psi_pm_Wb":        round(psi_pm, 4),
        "emf_peak_V":       round(emf_pk, 1),
        "emf_rms_V":        round(emf_rms, 1),
        "Kt_Nm_per_A":      round(Kt, 3),
        "T_cogging_Nm":     round(abs(T_cogging_est), 3),
        "air_gap_mm":       round((geom["statorID"] - geom["rotorOD"]) / 2, 2),
        "pole_pairs":       p,
        "n_slots":          n_slots,
        "rpm":              rpm,
        "lcm_slots_poles":  lcm,
    }


# ── Saliency estimate ─────────────────────────────────────────────────────────

def estimate_saliency(geom: dict) -> float:
    """Estimate Lq/Ld saliency ratio from magnetic circuit reluctance.

    d-axis path: air gap (Carter-corrected) + magnet thickness / µ_r  → high reluctance → low Ld.
    q-axis path: air gap only                                           → low  reluctance → high Lq.

    Slot leakage and fringing reduce apparent saliency vs the pure gap ratio;
    k_leak = 0.35 is an empirical correction consistent with published IPM data.
    Result is clipped to the realistic IPM range [1.5, 5.0].
    """
    _legs, meta = magnet_legs(geom)
    if meta.is_surface:
        return 1.02                  # SPM/Halbach: Ld ≈ Lq, negligible saliency
    if meta.flux_focusing:           # Spoke: moderate saliency
        return float(np.clip(meta.salient_xi_hint or 1.6, 1.2, 2.5))

    g   = max((geom["statorID"] - geom["rotorOD"]) / 2.0, 0.3)   # air gap [mm]
    hm  = float(geom.get("magThick", 8.0))                         # magnet thickness [mm]
    kc  = 1.15                                                      # Carter factor
    g_d = g * kc + hm / MU_R_MAG     # effective d-axis reluctance path [mm]
    g_q = g * kc                      # effective q-axis reluctance path [mm]
    xi  = 1.0 + 0.35 * (g_d / g_q - 1.0)
    if meta.salient_xi_hint > 0:      # reluctance-dominated topologies (PMa-SynRM)
        xi = max(xi, meta.salient_xi_hint)
    hi = 7.0 if meta.reluctance_dominated else 5.0
    return float(np.clip(xi, 1.5, hi))


# ── main entry point ──────────────────────────────────────────────────────────

def estimate_dq_currents(geom: dict, rpm: float, load_nm: float,
                          v_dc: float = INVERTER_V_DC, b_gap_t: float = 1.0,
                          rpm_base: float | None = None) -> tuple[float, float]:
    """Physics-based i_q (load) + i_d (field-weakening) for a given RPM/load.

    Below base speed the operating point follows **MTPA** (max torque per amp): a
    salient IPM (ξ = Lq/Ld > 1) injects a negative d-axis current to add reluctance
    torque T_rel = 1.5·p·(Ld−Lq)·i_d·i_q on top of the magnet torque, so for a given
    torque it uses less current than pure i_q (i_d=0). Non-salient rotors (SPM,
    ξ≈1) keep i_d=0. Above base speed, field-weakening adds a further demagnetising
    d-current on top of the MTPA point (geometry-derived ξ; continuous at rpm_base).
    """
    perf   = compute_performance(geom, b_gap_t, rpm)
    Kt     = max(perf["Kt_Nm_per_A"], 1e-3)
    psi_pm = max(float(perf.get("psi_pm_Wb", 0.0)), 1e-6)
    p      = int(geom["p"])
    T_req  = float(load_nm) + 5.0
    iq_pure = max(min(T_req / Kt, 800.0), 5.0)          # pure-q current for this torque

    if rpm_base is None or rpm_base <= 0:
        v_max = v_dc / math.sqrt(3)
        emf_1 = compute_performance(geom, b_gap_t, 1000.0)["emf_peak_V"]
        rpm_base = 1000.0 * 0.4 * v_max / emf_1 if emf_1 > 0 else 5000.0

    # ── MTPA operating point (reluctance torque for salient rotors) ──────────────
    xi = estimate_saliency(geom)
    R_gap   = ((geom["statorID"] / 2) + (geom["rotorOD"] / 2)) / 2 / 1000.0
    g       = max((geom["statorID"] - geom["rotorOD"]) / 2.0, 0.3) / 1000.0
    hm      = float(geom["magThick"]) / 1000.0
    kc = 1.15; k_w = 0.95; N_ph = max(int(geom["slots"]) / 3.0, 1.0)
    g_eff_d = kc * g + hm / MU_R_MAG
    Ld = (1.5 * (4 / math.pi) * MU0 * (N_ph * k_w) ** 2 *
          (R_gap * 0.080) / (p ** 2 * max(g_eff_d, 1e-6)))     # 80 mm ref (as compute_performance)
    Lq = xi * Ld
    dL = Lq - Ld
    if xi <= 1.05 or dL <= 1e-12:
        iq0, id0 = iq_pure, 0.0                          # non-salient → pure q-axis
    else:
        def _torque(iqv):
            idv = (psi_pm - math.sqrt(psi_pm ** 2 + 8.0 * dL ** 2 * iqv ** 2)) / (4.0 * dL)
            return 1.5 * p * (psi_pm * iqv + (Ld - Lq) * idv * iqv), idv
        lo, hi = 0.0, 800.0                              # T monotonic ↑ in iq → bisection
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            Tm, _ = _torque(mid)
            if Tm < T_req: lo = mid
            else:          hi = mid
        iq0 = 0.5 * (lo + hi)
        _, id0 = _torque(iq0)
        Is = math.hypot(iq0, id0)                        # respect inverter current limit
        if Is > 800.0:
            iq0 *= 800.0 / Is; id0 *= 800.0 / Is
        iq0 = max(iq0, 5.0)

    if rpm <= rpm_base:
        return float(iq0), float(id0)

    # ── field weakening above base: add demagnetising d-current on top of MTPA ──
    fw     = min((rpm - rpm_base) / max(rpm_base, 1.0), 1.5)
    id_fw  = iq_pure * fw / xi                          # ∝ load, ∝ 1/ξ
    id_    = -min(abs(id0) + id_fw, 0.9 * 800.0)        # cap at 90 % of inverter limit
    iq     = max(iq0 * (1.0 - 0.25 * fw), 5.0)          # MTPV: slight iq reduction in FW
    return float(iq), float(id_)


def compute_advanced_em(geom: dict, perf: dict, axial_mm: float,
                        rpm_base: float, rpm_max: float, load_nm: float,
                        mag: dict | None = None,
                        magnet_temp_C: float = 20.0) -> dict:
    """Advanced EM metrics: d/q inductances, MTPA, short-circuit current, demag.

    Minimum-viable model on top of the existing linear FDM/analytical estimates:

    • Ld, Lq from a magnetic-circuit magnetising inductance with the same
      "1 turn per slot" normalisation as ``compute_performance`` (so Isc is
      consistent with psi_pm).  Saliency ξ = Lq/Ld is taken from
      ``estimate_saliency`` to stay consistent with field-weakening.
    • MTPA: torque T = 1.5·p·(ψm·iq + (Ld−Lq)·id·iq) maximised over current
      angle β for a set of current magnitudes (motoring-positive convention:
      ξ = Lq/Ld > 1, id < 0 ⇒ positive reluctance torque).
    • Isc = ψm / Ld  (characteristic short-circuit current).
    • Demagnetisation: temperature-corrected Br(T) and the d-axis armature-
      reaction field opposing the magnet; risk flagged near the 0.9·Br knee.

    NOTE: the FDM is linear (constant μ), so Ld/Lq here are unsaturated. A
    saturation-dependent map would require the optional nonlinear μ pass.
    """
    p        = int(geom["p"])
    n_slots  = int(geom["slots"])
    L_ax     = (axial_mm / 1000.0) if axial_mm else 0.080
    R_gap    = ((geom["statorID"] / 2) + (geom["rotorOD"] / 2)) / 2 / 1000.0
    g        = max((geom["statorID"] - geom["rotorOD"]) / 2.0, 0.3) / 1000.0   # m
    hm       = float(geom["magThick"]) / 1000.0
    kc       = 1.15
    k_w      = 0.95
    N_ph     = max(n_slots / 3.0, 1.0)                     # 1 turn/slot → turns/phase

    g_eff_d  = kc * g + hm / MU_R_MAG
    # d-axis magnetising inductance (round-rotor magnetising form)
    Ld = (1.5 * (4 / math.pi) * MU0 * (N_ph * k_w) ** 2 *
          (R_gap * L_ax) / (p ** 2 * max(g_eff_d, 1e-6)))
    xi = estimate_saliency(geom)
    Lq = xi * Ld

    psi_pm = float(perf.get("psi_pm_Wb", 0.0))
    Isc    = psi_pm / Ld if Ld > 1e-9 else 0.0

    # ── MTPA sweep ────────────────────────────────────────────────────────────
    mtpa = []
    betas = np.radians(np.arange(0, 90.5, 1.0))
    for Is in (200.0, 400.0, 600.0, 800.0):
        idv = -Is * np.sin(betas)
        iqv =  Is * np.cos(betas)
        T   = 1.5 * p * (psi_pm * iqv + (Ld - Lq) * idv * iqv)
        k   = int(np.argmax(T))
        mtpa.append({
            "Is_A":     round(Is, 0),
            "beta_deg": round(float(np.degrees(betas[k])), 1),
            "T_Nm":     round(float(T[k]), 1),
            "id_A":     round(float(idv[k]), 0),
            "iq_A":     round(float(iqv[k]), 0),
        })

    # ── Demagnetisation check at worst case (max speed FW + magnet temp) ──────
    Br0   = float(mag.get("Br", Br_NdFeB)) if mag else Br_NdFeB
    a_Br  = float(mag.get("alpha_Br", -0.0012)) if mag else -0.0012
    Br_T  = Br0 * (1.0 + a_Br * (magnet_temp_C - 20.0))
    perm  = hm / (hm + MU_R_MAG * kc * g)
    B_op  = Br_T * perm                                    # magnet load-line B [T]
    _iq, id_fw = estimate_dq_currents(geom, rpm_max, load_nm,
                                      b_gap_t=perf.get("B_gap_T", 1.0),
                                      rpm_base=rpm_base)
    id_pk  = abs(id_fw)
    # d-axis armature-reaction field opposing the magnet (per pole, simplified)
    H_arm  = (N_ph * k_w * id_pk) / (p * max(g_eff_d, 1e-6))
    B_arm  = MU0 * MU_R_MAG * H_arm
    margin = B_op - B_arm
    demag_risk = margin < 0.1 * Br_T

    return {
        "Ld_mH":  round(Ld * 1e3, 4),
        "Lq_mH":  round(Lq * 1e3, 4),
        "xi":     round(xi, 2),
        "psi_pm_Wb": round(psi_pm, 4),
        "Isc_A":  round(Isc, 1),
        "mtpa":   mtpa,
        "demag": {
            "magnet_temp_C": round(magnet_temp_C, 1),
            "Br_T":          round(Br_T, 3),
            "B_operating_T": round(B_op, 3),
            "B_armature_T":  round(B_arm, 3),
            "margin_T":      round(margin, 3),
            "id_worstcase_A": round(id_pk, 0),
            "risk":          bool(demag_risk),
        },
    }


def power_envelope(geom: dict, adv: dict, rpm_max: float,
                   T_rated_Nm: float = 0.0,
                   v_dc: float = INVERTER_V_DC, i_max: float = INVERTER_I_MAX,
                   n_pts: int = 80) -> dict:
    """Torque/power over speed — the machine's CAPABILITY, not the demanded load.

    Answers "was kann die Maschine maximal?" from quantities that already exist:
    ψ_pm, Ld, Lq (``compute_advanced_em``) plus the two inverter limits. For every
    speed the best feasible operating point is searched on an (I_s, β) grid under

        |i| ≤ i_max                                        (current limit)
        ω_el·√((ψ + Ld·i_d)² + (Lq·i_q)²) ≤ v_dc/√3        (voltage limit)

    which reproduces the three classical regions on its own — constant torque below
    base speed, constant power in field weakening, MTPV roll-off at the top — with
    no case distinction in the code.

    Two envelopes are returned:
    * **peak** — everything the inverter allows (short-time, S2).
    * **continuous** — additionally capped at ``T_rated_Nm``, the cooling-limited
      S1 torque from ``ema_thermal.rated_torque``. Without it the "continuous"
      curve would just be the peak one.

    Scope, stated because the numbers look more precise than they are: the
    inductances are **unsaturated** (the FDM is linear), so the real peak torque at
    full current is lower; the currents share the **1 turn per slot** normalisation
    of ``Kt``/``psi_pm``; losses are not deducted (this is shaft-side
    electromagnetic power, not inverter input). ``rpm_max`` should be the
    structurally safe speed, so a rotor that cannot spin does not book power.
    """
    p      = int(geom["p"])
    psi    = float(adv.get("psi_pm_Wb") or 0.0)
    Ld     = float(adv.get("Ld_mH") or 0.0) / 1e3
    Lq     = float(adv.get("Lq_mH") or 0.0) / 1e3
    rpm_hi = float(rpm_max)
    if psi <= 0 or Ld <= 0 or Lq <= 0 or rpm_hi <= 0:
        return {"error": "Ld/Lq/psi_pm oder Drehzahlgrenze fehlen"}

    v_ph  = float(v_dc) / math.sqrt(3.0)                  # phase voltage limit [V_pk]
    # Grid fine enough that the field-weakening branch comes out smooth — a coarse
    # one shows a visible staircase in the chart (each step = one grid cell).
    betas = np.radians(np.linspace(0.0, 90.0, 181))
    amps  = np.linspace(0.0, float(i_max), 161)[1:]       # skip Is=0
    IS, BE = np.meshgrid(amps, betas, indexing="ij")
    id_g, iq_g = -IS * np.sin(BE), IS * np.cos(BE)
    T_g   = 1.5 * p * (psi * iq_g + (Ld - Lq) * id_g * iq_g)
    # flux-linkage magnitude is speed-independent → compute once, scale by ω_el
    flux  = np.hypot(psi + Ld * id_g, Lq * iq_g)

    rpms  = np.linspace(max(1.0, rpm_hi / n_pts), rpm_hi, n_pts)
    T_pk, T_co = [], []
    for rpm in rpms:
        w_el = 2 * math.pi * rpm / 60.0 * p
        ok   = (w_el * flux <= v_ph) & (T_g > 0)
        T_pk.append(float(T_g[ok].max()) if ok.any() else 0.0)
        ok_c = ok & (T_g <= T_rated_Nm) if T_rated_Nm > 0 else ok
        T_co.append(float(T_g[ok_c].max()) if ok_c.any() else 0.0)

    w_mech = 2 * math.pi * rpms / 60.0
    P_pk   = np.asarray(T_pk) * w_mech
    P_co   = np.asarray(T_co) * w_mech
    k_pk   = int(np.argmax(P_pk))
    k_co   = int(np.argmax(P_co))
    T0     = float(np.max(T_pk))
    # base speed = last point still holding (essentially) the full stall torque
    i_base = int(np.max(np.where(np.asarray(T_pk) >= 0.98 * T0)[0])) if T0 > 0 else 0

    return {
        "rpm":            [round(float(r)) for r in rpms],
        "T_peak_Nm":      [round(t, 1) for t in T_pk],
        "T_cont_Nm":      [round(t, 1) for t in T_co],
        "P_peak_kW":      [round(float(x) / 1e3, 2) for x in P_pk],
        "P_cont_kW":      [round(float(x) / 1e3, 2) for x in P_co],
        "P_max_kW":       round(float(P_pk[k_pk]) / 1e3, 1),
        "P_max_rpm":      round(float(rpms[k_pk])),
        "P_cont_max_kW":  round(float(P_co[k_co]) / 1e3, 1),
        "P_cont_max_rpm": round(float(rpms[k_co])),
        "T_peak_max_Nm":  round(T0, 1),
        "T_rated_Nm":     round(float(T_rated_Nm), 1),
        "rpm_base":       round(float(rpms[i_base])),
        "rpm_max":        round(rpm_hi),
        "v_dc_V":         round(float(v_dc)),
        "i_max_A":        round(float(i_max)),
        # Which limit actually binds the continuous curve: with generous cooling the
        # inverter current runs out first, and then "Dauer" == "Spitze" — worth
        # saying out loud, otherwise two identical curves look like a bug.
        "cont_limited_by": ("kuehlung" if 0 < T_rated_Nm < T0 else "strom"),
        # true when the speed window itself is the binding limit: power still rising
        # at the last point, i.e. the structural cap cuts the constant-power region
        "limited_by_rpm": bool(P_pk[-1] >= 0.995 * P_pk.max()),
    }


def _saturate_field(mu_base, J, geom, sc, ctr, N, target_peak_T,
                    iters: int = 4, P: float = 8.0, relax: float = 0.5):
    """Nonlinear B-H saturation pass for the DISPLAY field.

    The base FDM is linear (constant µr=500), so iron shows unphysical >2 T at
    tooth/corner cells. This fixed-point pass lowers µ where the physically-scaled
    |B| exceeds the steel knee ``B_SAT_IRON`` (Fröhlich-type law), so flux
    redistributes as real iron would and |B| caps near saturation. Returns
    ``(A_raw, phys_scale)`` — the caller multiplies the field by ``phys_scale`` for
    Tesla. Operates only on iron cells (µ_base>1.5; magnets/air untouched). Returns
    ``(None, None)`` on any failure so the caller keeps the linear field.
    """
    try:
        iron = mu_base > 1.5
        lbl  = _material_labels(mu_base)   # from the LINEAR mu — mu itself changes below
        mu   = mu_base.copy()
        A    = _solve_fdm(mu, J)
        scale = 1.0
        for _ in range(max(1, iters)):
            # Material-aware curl: with the plain central difference the boundary
            # cells read several times the true |B|, the Fröhlich law then knocks mu
            # down there, and the pass "saturates" cells that were never saturated.
            Bx, By = _curl_a(A, lbl)
            Bmag = np.hypot(Bx, By)
            Br, _bt, _th, _bx, _by = _sample_airgap(A, geom, sc, ctr, N, mu=mu_base)
            pk = float(np.max(np.abs(Br)))
            scale = (target_peak_T / pk) if pk > 1e-9 else scale
            ratio  = np.clip(Bmag * scale / max(B_SAT_IRON, 1e-3), 0.0, 50.0)
            mu_new = 1.0 + (MU_R_IRON - 1.0) / (1.0 + ratio ** P)        # μ drops past the knee
            mu_upd = np.where(iron, relax * mu_new + (1.0 - relax) * mu, mu_base)
            if not np.all(np.isfinite(mu_upd)):
                break
            mu = mu_upd.astype(np.float32)
            A  = _solve_fdm(mu, J)
        return A, scale
    except Exception:
        return None, None


def run_em_analysis(geom: dict, N: int = 150, rotor_angle: float = 0.0,
                    iq: float = 0.0, id_: float = 0.0,
                    axial_mm: float | None = None,
                    fdm_iters: int | None = None,
                    sf_ref: float | None = None,
                    saturate: bool = False) -> dict:
    """Full EM analysis: FDM solve + calibrated physical quantities.

    axial_mm  : actual stack length [mm] for geometry-accurate Kt/EMK (default 80 mm).
    fdm_iters : SOR iterations; None → default (180 for static, pass 120 for animation).
    sf_ref    : pre-computed calibration factor [T/rel.unit] from an OC run.
                Pass this for physically correct amplitude when stator currents are present:
                sf_ref = run_em_analysis(geom, N, iq=0, id_=0, ...)["sf_ref"]
                Without sf_ref the loaded case re-calibrates from its own peak, which
                removes the amplitude effect of armature reaction (ok for pattern vis only).

    Returns a dict with:
      - A, Bx, By  : 2-D numpy arrays (relative units, for plotting)
      - Br_gap, Bt_gap, theta : 1-D arrays along air gap [T physical]
      - performance : dict of key EM numbers
      - sf_ref     : calibration factor for use in subsequent loaded runs
      - scale, center, N : grid metadata
    """
    has_cur = (abs(iq) + abs(id_)) > 0.1
    mu, J_full, sc, ctr = _rasterise(geom, N, rotor_angle=rotor_angle, iq=iq, id_=id_)

    # The FV operator depends only on mu (geometry + rotor angle); the source J is
    # the RHS, so the field is LINEAR in J: A = A_magnet + A_stator.  The magnet
    # equivalent currents (dipolar curl-of-M) and the stator slot currents (net
    # current per slot) have very different field-transfer gains, so a single
    # shared calibration factor — tuned to the magnet — lets the stator field blow
    # up to >100 T and bury the magnets (or, when self-calibrated from the combined
    # peak, scales the magnets down to ~0).  We therefore solve the magnet and
    # stator parts separately (the 2nd solve re-uses the SAME cached factorisation,
    # so it is just a back-substitution) and scale each to its own analytical
    # air-gap target: magnets → _analytical_Bgap, armature → _analytical_Barm.
    if has_cur:
        _mu0, J_mag, _, _ = _rasterise(geom, N, rotor_angle=rotor_angle, iq=0.0, id_=0.0)
        J_stat = J_full - J_mag
        A_mag  = _solve_fdm(mu, J_mag) if fdm_iters is None else _solve_fdm(mu, J_mag, fdm_iters)
        A_stat = _solve_fdm(mu, J_stat) if fdm_iters is None else _solve_fdm(mu, J_stat, fdm_iters)
    else:
        A_mag  = _solve_fdm(mu, J_full) if fdm_iters is None else _solve_fdm(mu, J_full, fdm_iters)
        A_stat = None

    Br_m, Bt_m, th, Bx_m, By_m = _sample_airgap(A_mag, geom, sc, ctr, N, mu=mu)

    B_analytical = _analytical_Bgap(geom)
    pk_mag = float(np.max(np.abs(Br_m)))
    # sf_ref (when given) is the open-circuit MAGNET calibration from the static
    # run — keeps the magnet amplitude constant across animation frames.
    sf_mag = sf_ref if sf_ref is not None else (B_analytical / pk_mag if pk_mag > 1e-6 else 1.0)

    if A_stat is not None:
        Br_s, Bt_s, _th, Bx_s, By_s = _sample_airgap(A_stat, geom, sc, ctr, N, mu=mu)
        pk_stat = float(np.max(np.abs(Br_s)))
        B_arm   = _analytical_Barm(geom, math.hypot(iq, id_))
        sf_arm  = (B_arm / pk_stat) if pk_stat > 1e-6 else 0.0
    else:
        Br_s = Bt_s = Bx_s = By_s = 0.0
        sf_arm = 0.0

    Br_T = Br_m * sf_mag + Br_s * sf_arm
    Bt_T = Bt_m * sf_mag + Bt_s * sf_arm
    Bx_T = Bx_m * sf_mag + Bx_s * sf_arm
    By_T = By_m * sf_mag + By_s * sf_arm
    B_T  = np.hypot(Bx_T, By_T)
    # Combined calibrated vector potential for the field-line (iso-A) plot, so the
    # contours reflect the true magnet-vs-armature flux balance.
    A    = (A_mag * sf_mag + A_stat * sf_arm) if A_stat is not None else A_mag * sf_mag
    sf   = sf_mag

    # Optional nonlinear B-H pass for the DISPLAYED field: replaces the unphysical
    # linear >2 T iron spikes with a saturated, flux-redistributed map. The
    # quantitative air-gap arrays (Br_gap/Bt_gap → torque) keep the rigorous linear
    # split; only the display field (Bx_T/By_T/B_mag/A) is replaced, anchored to the
    # same air-gap radial peak so the amplitude stays consistent.
    if saturate:
        target = float(np.max(np.abs(Br_T)))
        A_nl, sc_nl = _saturate_field(mu, J_full, geom, sc, ctr, N, target)
        if A_nl is not None and sc_nl is not None:
            Bx_nl, By_nl = _curl_a(A_nl, _material_labels(mu))
            Bx_T = Bx_nl * sc_nl
            By_T = By_nl * sc_nl
            B_T  = np.hypot(Bx_T, By_T)
            A    = A_nl * sc_nl

    L_ax = (axial_mm / 1000.0) if axial_mm is not None else 0.080
    perf = compute_performance(geom, B_analytical, axial_mm=axial_mm)

    # Maxwell-stress torque estimate from FDM (in physical units)
    R_gap_m  = ((geom["statorID"] / 2) + (geom["rotorOD"] / 2)) / 2 / 1000
    T_maxwell = (2 * math.pi * R_gap_m * L_ax / MU0 *
                 float(np.mean(Br_T * Bt_T)))
    perf["T_maxwell_Nm"] = round(abs(T_maxwell), 1)

    return {
        "A":         A,
        "Bx":        Bx_T,
        "By":        By_T,
        "B_mag":     B_T,
        "mu":        mu,
        "Br_gap":    Br_T,
        "Bt_gap":    Bt_T,
        "theta":     th,
        "performance": perf,
        "sf_ref":    sf,          # calibration factor for re-use in loaded runs
        "scale":     sc,
        "center":    ctr,
        "N":         N,
    }
