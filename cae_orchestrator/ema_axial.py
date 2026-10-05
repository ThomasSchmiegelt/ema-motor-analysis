"""Axialflussmaschine: Auslegung des Ringraums -- Stufe 1 aus ``AXIALFLUSS.md``.

Was hier gerechnet wird und was ``ema_fluss`` schon tut
-------------------------------------------------------

``ema_fluss`` haelt den Flussweg als Begriff und gibt die zwei Integrale der
Luftspaltflaeche heraus (``a_fluss_m2`` mit r^1, ``a_moment_m3`` mit r^2).
Dieses Modul rechnet daraus die **Auslegung**: welche Masse der Ringraum
braucht, und -- nach der Hausregel -- bei jeder Groesse, **welche Grenze
bindet**.

Jede Funktion hier gibt deshalb nicht eine Zahl heraus, sondern zwei Zahlen und
den Namen der bindenden: ``ruecken`` die magnetisch noetige Dicke UND die aus
der Durchbiegung, ``zahnform`` die Zahnflussdichte am Aussen- UND am Innenrand,
``lambda_grenze`` die Schranke aus der Nut UND die aus dem Zahn.

Drei Dinge, die beim Bauen anders herauskamen als geplant
----------------------------------------------------------

**1. lambda = 1/sqrt(3) ist nicht herleitbar.** ``AXIALFLUSS.md`` nannte es in
seiner ersten Fassung "den klassischen Wert bei endlichem Strombelag". Das ist
falsch, und zwar nachrechenbar::

    T = 2*pi*sigma*Ro^3*(1-lambda^3)/3     ->  dT/dlambda = -2*pi*sigma*Ro^3*lambda^2 < 0

Das Momentintegral ist in lambda **monoton fallend**; es hat gar kein inneres
Maximum. Und die Schubspannung ist ueber r konstant, solange der Zahn keilfoermig
ist: der Leiterquerschnitt je Nut waechst mit der Nutteilung, also mit r, und der
Flaechenstrombelag ``K = J*swr*h_z`` haengt damit **nicht** von r ab.

Der Literaturwert ``lambda = 1/3`` stammt aus der Mitteldurchmesser-Naeherung
``T ~ sigma*(pi*D_m*L_e)*(D_m/2)``, und die liegt bei lambda -> 0 um **25 %** zu
niedrig (gemessen: 1,5708 gegen 2,0944 in Einheiten von sigma*Ro^3). Sie erzeugt
damit ein Maximum, das die Maschine nicht hat. ``1/sqrt(3) = 0,5774`` ist
ueberhaupt keiner von beiden Werten.

Was lambda WIRKLICH bindet, ist die Zeichnung am Innenrand: dort wird die Nut zu
schmal oder der Zahn zu duenn. Das rechnet ``lambda_grenze`` -- aus ``slots`` und
``slotWidthRatio``, also aus Groessen, die im Schema stehen.

**2. Die Durchbiegung ist rund 9x groesser als geplant.** ``AXIALFLUSS.md`` §1.7
rechnete einen Kragstreifen ueber dem AKTIVEN Ring (Ro-Ri = 55 mm) und nannte das
eine *obere* Schranke. Es war eine **untere**: die Scheibe ist nicht am Innenrand
des Ringraums eingespannt, sondern an der **Nabe**, und damit ist der Hebel 100 mm
statt 55 mm -- (100/55)^4 ~ 11, abzueglich der um 1/(1-nu^2) hoeheren
Plattensteifigkeit bleibt Faktor 9. Gemessen am 2p=16-Fall: 105,0 um statt
11,1 um, also **10,5 % des Luftspalts** statt 1,1 %.

Deshalb rechnet ``ruecken`` die **Kreisringplatte** (``_platte``, achssymmetrische
Plattengleichung, innen eingespannt, aussen frei, Druck nur auf dem aktiven Ring)
und keine Schranke. Geprueft gegen den Kragstreifen im Grenzfall des schmalen
Rings (Abweichung 0,26 % bei 1 mm Ringbreite), Randrest ~1e-21, Linearitaet in q
exakt 2,000000 und in t exakt 8,000000 (``test_axial.py``).

**3. Die Nabe bemisst, nicht die Blechdicke.** Von 30 mm auf 75 mm
Einspannradius faellt die Durchbiegung um den **Faktor 9**. Und die
Steifigkeitsforderung ist **polzahlunabhaengig** (sie haengt am Druck und an der
Geometrie, nicht daran, wie sich der Fluss aufteilt), waehrend die magnetische
Forderung mit der Polzahl faellt. Die beiden kreuzen sich, und ``ruecken`` sagt
wo: bei Nabe 30 mm bindet die Durchbiegung ab 2p = 16, bei einer Nabe bis an Ri
erst ab 2p = 40.

Was dieses Modul NICHT tut
---------------------------

Es rechnet **analytisch**. Das Luftspaltfeld kommt herein, es wird hier nicht
geloest -- die Feldstufe ist Stufe 2 (abgewickelter Mehrschnitt, Geruest in
``axialfluss_scheibenprobe.py``). Und es rechnet keine Struktur-FEM: die
Kreisringplatte ist eine geschlossene Loesung fuer eine **ebene Scheibe
konstanter Dicke** unter **gleichmaessigem** Druck. Eine gestufte Scheibe, die
Magnettaschen, die Nabenverschraubung und die Fliehkraft in der Scheibenebene
sind darin nicht. Dafuer braucht es ``ema_deck`` mit einem axialen Lastfall --
den es heute nicht gibt (Stufe 4).
"""

from __future__ import annotations

import math

import numpy as np

MU0 = 4.0e-7 * math.pi

#: Randabfall der Luftspaltwelle, **gemessen** in ``axialfluss_scheibenprobe.py``:
#: bei vollpoliger Bedeckung ist <B_n^2> = 0,948 * B_spitze^2. Der Rest ist
#: Streuung an den Polkanten. Eine 1,0 hier waere die Annahme einer
#: rechteckigen Welle ohne Kanten, und die gibt es nicht.
RANDFAKTOR_B2 = 0.948

#: Zulaessige Durchbiegung als Anteil des Luftspalts. Keine Materialgrenze,
#: sondern eine **Auslegungsentscheidung**, und darum hier mit Begruendung:
#: bei 10 % Versatz bleiben nach ``anzug()`` 41 % einer Spaltkraft als
#: destabilisierender Restschub stehen. Wer mehr zulaesst, laesst die Scheibe
#: gegen eine Kraft arbeiten, die mit dem Versatz waechst.
W_ZUL_ANTEIL = 0.10

#: Jochflussdichte, auf die das Rueckenblech bemessen wird, wenn keine
#: Blechsorte hereingereicht wird. Ebenfalls eine Auslegungsgroesse und keine
#: Materialgrenze -- ``LAMINATES[...]["B_sat_T"]`` liegt bei 1,65..1,80 T.
B_FE_ZUL_VORGABE = 1.50

#: Fertigungsboden fuer Nut- und Zahnbreite am Innenrand. Derselbe Wert und
#: dieselbe Rolle wie der 2,0-mm-Boden in ``ema_asm`` (Kaefignut): eine
#: Fertigungsgrenze, KEIN Ersatz fuer eine fehlende Auslegung.
B_MIN_MM = 2.0


def _geom(geom: dict) -> dict:
    return geom or {}


def auslegung(geom: dict, axial_mm: float | None = None) -> dict:
    """Der Ringraum in Metern, plus die Groessen, die ueber r laufen.

    Polteilung und Nutteilung wachsen mit dem Radius; ihr Verhaeltnis zum
    Luftspalt aendert sich damit um 1/lambda. Das ist der Grund, warum kein
    einzelner Querschnitt diese Maschine darstellt (``AXIALFLUSS.md`` §1.4), und
    es steht deshalb hier als Zahl und nicht als Satz.
    """
    import ema_fluss

    g = _geom(geom)
    f = ema_fluss.flaechen(g, axial_mm)
    if f["flussweg"] != "axial":
        raise ValueError("ema_axial rechnet den Axialfluss; dieser Payload ist "
                         f"'{f['flussweg']}' (s. ema_fluss.flussweg)")
    ro, ri, n = f["r_aussen_m"], f["r_innen_m"], f["n_spalte"]
    poles = 2 * max(1, int(g.get("p", 3) or 3))
    q = max(3, int(g.get("slots", 48) or 48))
    spalt = float(g.get("axialSpaltMm", 0) or 1.0) / 1000.0
    alpha = min(1.0, max(0.1, float(g.get("axialPolbedeckung", 0) or 1.0)))
    aus = {
        "r_aussen_m": ro, "r_innen_m": ri, "lambda": f["lambda"],
        "n_spalte": n, "bauform": f["bauform"], "poles": poles, "slots": q,
        "luftspalt_m": spalt, "polbedeckung": alpha,
        "a_fluss_m2": f["a_fluss_m2"], "a_moment_m3": f["a_moment_m3"],
        # Ringflaeche EINES Luftspalts -- die Flaeche, auf der der Anzug wirkt.
        "ringflaeche_je_spalt_m2": math.pi * (ro ** 2 - ri ** 2),
        "magnet_dicke_m": float(g.get("axialMagnetDicke", 0) or 6.0) / 1000.0,
        "zahnform": str(g.get("axialZahnform", "") or "keil").strip().lower(),
    }
    for name, r in (("innen", ri), ("mitte", 0.5 * (ri + ro)), ("aussen", ro)):
        aus[f"polteilung_{name}_m"] = 2 * math.pi * r / poles
        aus[f"nutteilung_{name}_m"] = 2 * math.pi * r / q
        aus[f"spalt_je_polteilung_{name}"] = spalt / (2 * math.pi * r / poles)
    aus["spaltverhaeltnis_spanne"] = (aus["spalt_je_polteilung_innen"]
                                      / aus["spalt_je_polteilung_aussen"])
    return aus


def lambda_grenze(geom: dict) -> dict:
    """Die untere Schranke fuer lambda -- aus der ZEICHNUNG, nicht aus Literatur.

    Das Moment ist in lambda monoton fallend (s. Modulkopf), also gibt es kein
    inneres Optimum: das beste lambda ist das kleinste **zeichenbare**. Zwei
    Dinge werden am Innenrand zu klein, und beide stehen im Schema:

        Nut:   swr * 2*pi*Ri/Q        >= b_min
        Zahn:  (1-swr) * 2*pi*Ri/Q    >= b_min

    Zurueckgegeben wird, welche von beiden bindet. Wer ein kleineres lambda
    will, muss die Nutzahl senken oder den Boden ``b_min`` begruenden -- nicht
    eine Konstante waehlen.
    """
    g = _geom(geom)
    q = max(3, int(g.get("slots", 48) or 48))
    swr = min(0.8, max(0.2, float(g.get("slotWidthRatio", 0) or 0.5)))
    b_min = float(g.get("axialBminMm", 0) or B_MIN_MM) / 1000.0
    ri_nut = q * b_min / (2 * math.pi * swr)
    ri_zahn = q * b_min / (2 * math.pi * (1.0 - swr))
    ri_min = max(ri_nut, ri_zahn)
    bindet = "Nut" if ri_nut >= ri_zahn else "Zahn"
    d_a = float(g.get("axialAktivOD", 0) or 0.0)
    ro = d_a / 2.0 / 1000.0 if d_a > 0 else 0.0
    lam_min = (ri_min / ro) if ro > 0 else float("nan")
    lam_ist = float(g.get("axialLambda", 0) or 0.5774)
    return {
        "ri_aus_nut_m": ri_nut, "ri_aus_zahn_m": ri_zahn,
        "ri_min_m": ri_min, "bindet": bindet,
        "lambda_min": lam_min, "lambda_ist": lam_ist,
        "lambda_haelt": bool(ro > 0 and lam_ist >= lam_min),
        "b_min_m": b_min, "slots": q, "slotWidthRatio": swr,
        "monoton": True,
        "aussage": (
            f"Das Moment faellt monoton mit lambda (dT/dlambda = "
            f"-2*pi*sigma*Ro^3*lambda^2), es gibt also kein inneres Optimum. "
            f"Bindend ist die Zeichnung am Innenrand: {bindet.lower()}seitig "
            f"wird es bei Ri = {ri_min * 1000:.2f} mm zu schmal "
            f"(Boden {b_min * 1000:.1f} mm, Q = {q}, swr = {swr:.2f}). "
            f"lambda_min = {lam_min:.4f}."
            + ("" if (ro > 0 and lam_ist >= lam_min) else
               f" Das gewaehlte lambda = {lam_ist:.4f} liegt DARUNTER und ist "
               f"nicht zeichenbar.")),
    }


def zahnform(geom: dict, b_gap_t: float, b_sat_t: float | None = None) -> dict:
    """Zahnflussdichte am Aussen- UND am Innenrand -- die Zahnform entscheidet.

    ``ema_saettigung`` kuerzt die Nutteilung heraus::

        B_zahn = B_gap * tau_nut / (b_zahn * k_fe) = B_gap / ((1-swr) * k_fe)

    Das gilt nur, weil radial alle Zaehne auf EINEM Radius sitzen. Axial:

    * **keilfoermig** (b ~ r): die Kuerzung gilt weiter, B_zahn ist konstant;
    * **parallel** (konstante Breite, auf den Aussenrand bemessen):
      B_zahn ~ 1/r, der Innenrand traegt 1/lambda mal so viel.

    Gemessen bei B_gap = 0,63 T und swr = 0,5: 1,299 T aussen gegen 2,250 T
    innen bei lambda = 0,577. Das ist kein Randeffekt, sondern ein Faktor 1,73
    auf die bindende Saettigungsstelle.
    """
    from ema_saettigung import STAPELFAKTOR

    g = _geom(geom)
    a = auslegung(g)
    swr = min(0.8, max(0.2, float(g.get("slotWidthRatio", 0) or 0.5)))
    b_sat = float(b_sat_t or 0.0) or 1.70
    b_aussen = b_gap_t / ((1.0 - swr) * STAPELFAKTOR)
    keil = a["zahnform"] != "parallel"
    b_innen = b_aussen if keil else b_aussen / a["lambda"]
    return {
        "zahnform": "keil" if keil else "parallel",
        "b_zahn_aussen_t": b_aussen, "b_zahn_innen_t": b_innen,
        "ueberhoehung": b_innen / b_aussen,
        "b_sat_t": b_sat,
        "haelt": bool(b_innen <= b_sat),
        "bindende_stelle": "Innenrand" if not keil else "ueber r konstant",
        "aussage": (
            f"Keilzahn (b ~ r): die Nutteilung kuerzt sich wie radial, "
            f"B_zahn = {b_aussen:.3f} T ueber dem ganzen Radius. Gegen B_sat "
            f"{b_sat:.2f} T "
            f"{'haelt es' if b_aussen <= b_sat else 'haelt es NICHT -- die '
             'Zahnform ist hier nicht die Ursache, der Zahn ist zu schmal '
             '(slotWidthRatio) oder B_gap zu hoch'}."
            if keil else
            f"Paralleler Zahn: B_zahn ~ 1/r. Aussen {b_aussen:.3f} T, innen "
            f"{b_innen:.3f} T -- das {1 / a['lambda']:.2f}-fache, weil die "
            f"Nutteilung am Innenrand um genau diesen Faktor kleiner ist. "
            f"Gegen B_sat {b_sat:.2f} T "
            f"{'haelt es' if b_innen <= b_sat else 'haelt es NICHT'}."),
    }


def anzug(geom: dict, b_gap_t: float) -> dict:
    """Der axiale Anzug -- die Last, die es beim Radialfluss nicht gibt.

    ``sigma_n = alpha * B_gap^2 / (2*mu0)`` mit ``alpha`` aus Polbedeckung und
    dem **gemessenen** Randfaktor 0,948 (s. ``RANDFAKTOR_B2``). Bei
    B_gap = 0,9573 T kommen damit die 345,8 kPa der Scheibenprobe heraus.

    Zwei Luftspalte heben sich auf -- **nur bei mittigem Staender**. Der
    Restschub bei Versatz d wirkt IN Richtung des Versatzes, ist also
    destabilisierend, und seine Steigung bei d = 0 hat eine geschlossene Form::

        F(d) = sigma_n*A*[(g/(g-d))^2 - (g/(g+d))^2]
        dF/dd|_0 = 4*sigma_n*A/g                      (negative Steifigkeit)

    Das ist die Groesse, die der Staender aufbringen muss. Sie steht hier, weil
    "traegt die Kraft" und "haelt die Lage" zwei verschiedene Forderungen sind.
    """
    a = auslegung(geom)
    alpha = a["polbedeckung"] * RANDFAKTOR_B2
    sig = alpha * b_gap_t ** 2 / (2.0 * MU0)
    area = a["ringflaeche_je_spalt_m2"]
    g_m = a["luftspalt_m"]
    f_je_spalt = sig * area
    k_neg = 4.0 * sig * area / g_m
    rest = {}
    for d_mm in (0.02, 0.05, 0.10, 0.20):
        d = d_mm / 1000.0
        if d >= g_m:
            continue
        df = sig * ((g_m / (g_m - d)) ** 2 - (g_m / (g_m + d)) ** 2)
        rest[d_mm] = {"kraft_N": df * area, "anteil": df / sig}
    return {
        "sigma_n_pa": sig, "alpha_wirksam": alpha,
        "ringflaeche_je_spalt_m2": area,
        "kraft_je_spalt_N": f_je_spalt,
        "n_spalte": a["n_spalte"],
        "hebt_sich_auf": a["n_spalte"] > 1,
        "negative_steifigkeit_N_per_m": k_neg,
        "restschub": rest,
        "aussage": (
            f"Anzug {f_je_spalt / 1e3:.2f} kN je Luftspalt bei "
            f"{sig / 1e3:.1f} kPa Normalspannung. "
            + (f"Zwei Spalte heben sich auf, aber nur bei mittigem Staender: "
               f"die negative Steifigkeit um die Mittellage ist "
               f"{k_neg / 1e6:.1f} MN/m, und der Restschub wirkt IN Richtung "
               f"des Versatzes."
               if a["n_spalte"] > 1 else
               f"Einseitiger Aufbau: die ganze Kraft liegt dauerhaft am Lager.")),
    }


def _platte(a_m: float, b_m: float, t_m: float, q_pa: float, ri_last_m: float,
            e_pa: float = 200e9, nu: float = 0.30, n: int = 2001) -> dict:
    """Achssymmetrische Kreisringplatte: innen eingespannt, aussen frei.

    Geloest wird die Plattengleichung in der Form::

        Q_r(r) = (1/r) * int_r^b q*rho drho               (Gleichgewicht, Q_r(b) = 0)
        S(r)   = dphi/dr + phi/r = S(a) - (1/D)*int_a^r Q_r
        phi(r) = (1/r) * int_a^r rho*S drho               (phi(a) = 0, eingespannt)
        w(r)   = int_a^r phi                              (w(a) = 0)
        M_r    = -D*(S - (1-nu)*phi/r),  freier Rand: S(b) = (1-nu)*phi(b)/b

    ``S(a)`` ist die einzige Unbekannte und geht linear ein -- zwei Probelaeufe
    geben sie exakt, es wird nicht iteriert.

    ``q_pa`` wirkt nur auf ``r >= ri_last_m``: der Anzug greift am aktiven Ring
    an, nicht auf der Nabenscheibe. Das ist kein Detail -- mit Druck auf der
    ganzen Scheibe kaeme eine andere Zahl heraus.
    """
    if not (b_m > a_m > 0.0) or t_m <= 0.0:
        raise ValueError(f"Plattenmasse unbrauchbar: a={a_m}, b={b_m}, t={t_m}")
    d_st = e_pa * t_m ** 3 / (12.0 * (1.0 - nu ** 2))
    r = np.linspace(a_m, b_m, n)
    q = np.where(r >= ri_last_m, q_pa, 0.0)

    def _int(y):
        return np.concatenate(([0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(r))))

    i_q = _int(q * r)
    q_r = (i_q[-1] - i_q) / r

    def _lauf(s_a):
        s = s_a - _int(q_r) / d_st
        phi = _int(r * s) / r
        w = _int(phi)
        return s, phi, w, s[-1] - (1.0 - nu) * phi[-1] / r[-1]

    _, _, _, r0 = _lauf(0.0)
    _, _, _, r1 = _lauf(1.0)
    s, phi, w, rest = _lauf(-r0 / (r1 - r0))
    return {"r": r, "w": w, "w_max_m": float(abs(w).max()),
            "biegesteifigkeit_Nm": d_st, "randrest": float(rest)}


def ruecken(geom: dict, b_gap_t: float, b_fe_zul_t: float | None = None,
            lam: dict | None = None) -> dict:
    """Rueckenblech: magnetisch noetige Dicke UND die aus der Durchbiegung.

    Magnetisch fuehrt das Rueckenblech **die Haelfte** des Polflusses umfangs
    weiter, durch den Querschnitt ``(Ro-Ri)*t``::

        Phi_pol = B_gap * alpha * pi*(Ro^2-Ri^2)/(2p)
        t_mag   = Phi_pol / (2*(Ro-Ri)*B_fe_zul)

    Mechanisch traegt dieselbe Scheibe den Anzug. Gerechnet wird die
    Kreisringplatte (``_platte``) und nicht eine Schranke -- der Kragstreifen
    ueber dem aktiven Ring, der in der ersten Fassung von ``AXIALFLUSS.md``
    stand, liegt um den Faktor 9 zu NIEDRIG (s. Modulkopf).

    Die Einspannung sitzt an der **Nabe** (``axialNabeD``, sonst ``shaftD``),
    und das ist der Haupthebel: von 30 mm auf 75 mm Radius faellt die
    Durchbiegung um Faktor 9. Die Steifigkeitsforderung ist dabei
    **polzahlunabhaengig**, die magnetische faellt mit der Polzahl -- deshalb
    kreuzen sie sich, und deshalb steht hier, welche bindet.
    """
    g = _geom(geom)
    a = auslegung(g)
    az = anzug(g, b_gap_t)
    b_zul = float(b_fe_zul_t or 0.0) or B_FE_ZUL_VORGABE
    quelle = "hereingereicht (Blechsorte)" if b_fe_zul_t else \
             f"Modulvorgabe {B_FE_ZUL_VORGABE} T (Auslegungswert, nicht B_sat)"

    ro, ri = a["r_aussen_m"], a["r_innen_m"]
    phi_pol = (b_gap_t * a["polbedeckung"]
               * math.pi * (ro ** 2 - ri ** 2) / a["poles"])
    t_mag = phi_pol / (2.0 * (ro - ri) * b_zul)

    d_nabe = float(g.get("axialNabeD", 0) or g.get("shaftD", 0) or 60.0)
    a_nabe = d_nabe / 2.0 / 1000.0
    if a_nabe >= ro:
        raise ValueError(f"Nabenradius {a_nabe * 1000:.1f} mm liegt nicht innerhalb "
                         f"von Ro = {ro * 1000:.1f} mm")
    w_zul = W_ZUL_ANTEIL * a["luftspalt_m"]
    sig = az["sigma_n_pa"]

    def _w(t):
        return _platte(a_nabe, ro, t, sig, ri)["w_max_m"]

    # t_steif monoton fallend in w -> Bisektion. Die Spanne ist bewusst weit:
    # bei kleiner Nabe braucht es mehr als die magnetische Dicke.
    lo, hi = 0.2e-3, 0.200
    if _w(hi) > w_zul:
        t_steif, erreichbar = hi, False
    else:
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if _w(mid) > w_zul:
                lo = mid
            else:
                hi = mid
        t_steif, erreichbar = hi, True

    t_soll = max(t_mag, t_steif)
    bindet = "Durchbiegung" if t_steif > t_mag else "Fluss"
    artikel = "die" if bindet == "Durchbiegung" else "der"
    pl = _platte(a_nabe, ro, t_soll, sig, ri)
    return {
        "t_magnetisch_m": t_mag, "t_steifigkeit_m": t_steif,
        "t_soll_m": t_soll, "bindet": bindet,
        "steifigkeit_erreichbar": erreichbar,
        "phi_pol_wb": phi_pol, "b_fe_zul_t": b_zul, "b_fe_quelle": quelle,
        "nabe_r_m": a_nabe, "w_zul_m": w_zul,
        "w_bei_t_soll_m": pl["w_max_m"],
        "w_anteil_spalt": pl["w_max_m"] / a["luftspalt_m"],
        "randrest": pl["randrest"],
        "aussage": (
            f"Magnetisch {t_mag * 1000:.2f} mm, aus der Durchbiegung "
            f"{t_steif * 1000:.2f} mm -> bindend ist {artikel} {bindet}. "
            f"Bei {t_soll * 1000:.2f} mm biegt sich die Scheibe um "
            f"{pl['w_max_m'] * 1e6:.1f} um = "
            f"{pl['w_max_m'] / a['luftspalt_m'] * 100:.1f} % des Luftspalts. "
            f"Eingespannt an r = {a_nabe * 1000:.1f} mm -- das ist der "
            f"Haupthebel, nicht die Blechdicke."
            + ("" if erreichbar else
               " ACHTUNG: auch 200 mm Blech halten die Grenze nicht; die Nabe "
               "muss nach aussen wandern.")),
    }


def bandage(geom: dict, rpm: float, sigma_zul_mpa: float = 0.0,
            klebe_zul_mpa: float = 0.0) -> dict:
    """Was den Sektormagneten haelt -- und dass es kein Blechsteg ist.

    Radial drueckt die Fliehkraft den Magneten gegen den Steg (Innenlaeufer)
    oder gegen den Ring (Aussenlaeufer) -- beides Blech, das schon da ist.
    **Axial zieht sie ihn in der SCHEIBENEBENE nach aussen**, und dort ist
    nichts: nur Klebung oder eine Bandage am Aussenrand.

    Zwei Wege, beide gerechnet, weil beide gebaut werden:

    * **Klebung**: Scherspannung = Gesamtkraft / Magnetgrundflaeche;
    * **Bandage**: Ringzug. Mit ``p_r = F/(2*pi*Ro*t_mag)`` und
      ``sigma_h = p_r*Ro/t_band`` folgt ``t_band = F/(2*pi*t_mag*sigma_zul)`` --
      **unabhaengig von Ro**.

    Es gibt im Werkzeug **keine Bandagen-Werkstofftabelle** (``LAMINATES``,
    ``MAGNETS``, ``HAIRPIN_MATS`` fuehren keine). Ohne ``sigma_zul_mpa`` wird
    deshalb nur die Kraft genannt und kein Querschnitt erfunden.
    """
    from ema_screen import MAG_DICHTE_KG_M3

    a = auslegung(geom)
    ro, ri = a["r_aussen_m"], a["r_innen_m"]
    om = float(rpm) * 2.0 * math.pi / 60.0
    t_mag = a["magnet_dicke_m"]
    flaeche = math.pi * (ro ** 2 - ri ** 2) * a["polbedeckung"]
    m_ring = flaeche * t_mag * MAG_DICHTE_KG_M3                 # je Laeuferscheibe
    # Massenmittlerer Radius des Ringsektors: int r dA / int dA
    r_mass = (2.0 / 3.0) * (ro ** 3 - ri ** 3) / (ro ** 2 - ri ** 2)
    f_ges = m_ring * om * om * r_mass
    je_pol = f_ges / a["poles"]
    aus = {
        "rpm": float(rpm), "u_aussen_m_s": om * ro,
        "magnetmasse_je_scheibe_kg": m_ring,
        "magnetmasse_je_pol_kg": m_ring / a["poles"],
        "r_mass_m": r_mass,
        "kraft_gesamt_N": f_ges, "kraft_je_pol_N": je_pol,
        "klebeflaeche_m2": flaeche,
        "klebescherspannung_pa": f_ges / flaeche if flaeche > 0 else float("nan"),
        "steg_vorhanden": False,
        "bandage_werkstoff_im_werkzeug": False,
    }
    if sigma_zul_mpa > 0:
        aus["t_bandage_m"] = f_ges / (2.0 * math.pi * t_mag * sigma_zul_mpa * 1e6)
        aus["sigma_zul_mpa"] = sigma_zul_mpa
    if klebe_zul_mpa > 0:
        aus["klebung_haelt"] = bool(aus["klebescherspannung_pa"]
                                    <= klebe_zul_mpa * 1e6)
        aus["klebe_zul_mpa"] = klebe_zul_mpa
    aus["aussage"] = (
        f"{rpm:.0f} 1/min, u = {om * ro:.1f} m/s: die Magnete einer Scheibe "
        f"({m_ring:.3f} kg) ziehen mit {f_ges / 1e3:.1f} kN radial nach aussen, "
        f"{je_pol / 1e3:.2f} kN je Pol. In der Scheibenebene haelt sie KEIN "
        f"Blechsteg -- die Klebung traegt dabei "
        f"{aus['klebescherspannung_pa'] / 1e6:.2f} MPa Scherspannung"
        + (f", eine Bandage brauchte {aus['t_bandage_m'] * 1000:.2f} mm bei "
           f"{sigma_zul_mpa:.0f} MPa zulaessig." if sigma_zul_mpa > 0 else
           ". Ein Bandagenwerkstoff steht in keiner Tabelle des Werkzeugs, "
           "deshalb wird hier kein Querschnitt genannt."))
    return aus


def moment(geom: dict, sigma_kpa: float, axial_mm: float | None = None) -> float:
    """Dauermoment [Nm] aus der Schubspannung -- dieselbe Formel wie radial.

    ``T = 2*pi*sigma*a_moment_m3``; den Unterschied zwischen den Bauformen
    traegt allein ``ema_fluss.flaechen``.
    """
    import ema_fluss
    f = ema_fluss.flaechen(geom, axial_mm)
    return 2.0 * math.pi * float(sigma_kpa) * 1e3 * f["a_moment_m3"]


def uebersicht(geom: dict, b_gap_t: float, rpm: float = 0.0,
               axial_mm: float | None = None) -> str:
    a = auslegung(geom, axial_mm)
    lg = lambda_grenze(geom)
    zf = zahnform(geom, b_gap_t)
    az = anzug(geom, b_gap_t)
    rk = ruecken(geom, b_gap_t)
    z = [f"Axialfluss, Bauform {a['bauform']} ({a['n_spalte']} Luftspalt"
         f"{'e' if a['n_spalte'] != 1 else ''}), 2p = {a['poles']}, Q = {a['slots']}",
         f"  Ringraum   Ri = {a['r_innen_m'] * 1000:.2f} .. "
         f"Ro = {a['r_aussen_m'] * 1000:.2f} mm   lambda = {a['lambda']:.4f}",
         f"  Polteilung {a['polteilung_innen_m'] * 1000:.2f} mm innen .. "
         f"{a['polteilung_aussen_m'] * 1000:.2f} mm aussen  "
         f"-> Spalt/Polteilung aendert sich um {a['spaltverhaeltnis_spanne']:.2f}x",
         f"  lambda     {lg['aussage']}",
         f"  Zahn       {zf['aussage']}",
         f"  Anzug      {az['aussage']}",
         f"  Ruecken    {rk['aussage']}"]
    if rpm > 0:
        z.append(f"  Bandage    {bandage(geom, rpm)['aussage']}")
    z.append(f"  T_dauer    {moment(geom, 40.0, axial_mm):.1f} Nm bei 40 kPa (water)")
    return "\n".join(z)
