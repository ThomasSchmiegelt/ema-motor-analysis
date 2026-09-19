"""Was den Schenkelpol HAELT und was ihn DAEMPFT.

Zwei Dinge, die bisher als Luecke benannt waren und sonst nichts
-----------------------------------------------------------------

``ema_eesm_cad.koerper`` gibt seit jeher ein Feld ``ungeprueft`` heraus:
„Polbefestigung (Schwalbenschwanz/Bolzen) und die Fliehkraft am Polfuss sind
NICHT gerechnet". Das war ehrlich und trotzdem unbefriedigend — ein
Schenkelpol ist das einzige Bauteil dieses Werkzeugs, das **nicht aus dem
Vollen** kommt: er sitzt auf dem Joch und wird dort gehalten. Bei 12.000 1/min
zieht ein 3-kg-Pol mit mehreren Tonnen an seiner Wurzel, und ob das haelt,
entscheidet ein Querschnitt von wenigen Quadratzentimetern.

Ebenso die **Daempferwicklung**: sie stand im Modulkopf von ``ema_eesm`` unter
„was dieses Modell NICHT kennt" und kam sonst nirgends vor. Eine Synchron-
maschine ohne Daempferkaefig laeuft am Netz nicht von selbst an und pendelt
bei jedem Lastsprung; die Staebe im Polschuh sind kein Zubehoer.

Was hier gerechnet wird — und was ausdruecklich nicht
------------------------------------------------------

**Befestigung.** Die Fliehkraft des ganzen Pols (Schuh + Kern + Spule, aus
``ema_eesm_cad.koerper``, also aus derselben Funktion, aus der gezeichnet
wird) gegen den tragenden Querschnitt an der Wurzel. Zwei Bauarten:

    ``schwalbenschwanz``  Der Polfuss ist in eine Nut des Jochs eingeschoben;
        der engste Schnitt ist der **Hals** und traegt auf ZUG. Geprueft wird
        ``sigma = F / (b_hals * L) * KT_HALS`` gegen ``yield_mpa / SF``.
    ``bolzen``  ``n`` Schrauben je Pol, Spannungsquerschnitt nach ISO 898-1,
        Festigkeitsklasse 8.8 (``RP02_BOLZEN_MPA``).

``KT_HALS`` ist ein Kerbfaktor nach dem Muster von ``ema_rotorcheck.KT_POCKET``
— eine benannte Konstante und keine gerechnete Kerbzahl. Was **nicht** geprueft
wird, steht in ``ungeprueft``: die Flankenpressung der Schwalbenschwanzfuehrung
(dafuer fehlt der Flankenwinkel), die Dauerfestigkeit, der Presssitz und die
Biegung des Pols aus dem einseitigen Magnetzug.

**Daempferkaefig.** Die Bemessung ist eine **Auslegungsregel**, keine Messung,
und sie steht deshalb als solche da:

    Querschnitt je Pol   ``A_d = K_QUERSCHNITT * A_staender_je_Pol``
    Stabteilung          ``tau_d = TEILUNG_ZU_NUT * tau_nut_staender``

Beide sind die ueblichen Werte der Literatur (Say, *Alternating Current
Machines*; IEEE Std 115): der Daempferquerschnitt liegt bei 15–35 % des
Staenderkupfers je Pol, und die Stabteilung wird bewusst VERSCHIEDEN von der
Staendernutteilung gewaehlt, damit der Laeufer nicht in einer Oberwelle
haengenbleibt. Gerechnet werden daraus Stabzahl, Stabdurchmesser, Widerstand
(ueber ``ema_pipeline.rho_bei`` bei der Leitertemperatur, wie jede andere
Wicklung hier) und Masse.

**Der Daempfer geht in KEINE Kennzahl dieses Werkzeugs ein.** Er daempft
Pendelungen und ermoeglicht den asynchronen Anlauf — beides braucht einen
zeitabhaengigen Lauf, und den gibt es hier nicht. Was er kostet (Masse, Kupfer,
Platz im Polschuh) wird gerechnet, was er nuetzt, wird benannt. Eine Zahl dafuer
zu erfinden waere schlimmer als die Luecke.
"""

from __future__ import annotations

import math

# ── Befestigung ──────────────────────────────────────────────────────────────

BEFESTIGUNGEN = ("schwalbenschwanz", "bolzen")

# Kerbfaktor am Polfuss. Muster ``ema_rotorcheck.KT_POCKET`` = 1.5: eine
# benannte Annahme, keine gerechnete Kerbzahl. Der Schwalbenschwanz hat einen
# schaerferen Uebergang als eine Magnettasche, deshalb etwas hoeher.
KT_HALS = 1.8

# Sicherheit gegen die Fliessgrenze -- dieselbe wie ``ema_pipeline.SF_TARGET``
# und ``ema_topopt``s ``sigma_ref``. Eine zweite Zahl hier waere die Stelle, an
# der zwei Tore verschieden streng werden, ohne dass es jemand merkt.
SF_ZIEL = 1.3

# Festigkeitsklasse 8.8: Rp0,2 = 640 MPa (ISO 898-1).
RP02_BOLZEN_MPA = 640.0

# Spannungsquerschnitte A_s [mm^2] nach ISO 898-1, Regelgewinde.
BOLZEN_AS_MM2 = {"M4": 8.78, "M5": 14.2, "M6": 20.1, "M8": 36.6,
                 "M10": 58.0, "M12": 84.3, "M16": 157.0, "M20": 245.0}

# Wie breit der Hals hoechstens sein darf, bezogen auf die Kernbreite am Joch.
# Er ist der EINGESCHOBENE Teil und damit schmaler als der Kern -- sonst gaebe
# es keine Schulter, an der die Schwalbenschwanznut greift.
HALS_ZU_KERN = 0.70


# ── Daempferkaefig ───────────────────────────────────────────────────────────

# Daempferquerschnitt je Pol, bezogen auf das STAENDERkupfer je Pol.
# Literaturband 0,15...0,35; genommen wird die Mitte.
K_QUERSCHNITT = 0.25

# Stabteilung, bezogen auf die Staendernutteilung. Bewusst NICHT 1,0: gleiche
# Teilungen lassen den Laeufer in einer Oberwelle haengen ("Goerges"-Sattel).
TEILUNG_ZU_NUT = 0.80

# Steg zwischen Stabbohrung und Polschuhoberflaeche [mm]. Er haelt den Stab
# gegen die Fliehkraft, genau wie ``ema_asm.KAEFIG_STEG_MM`` beim Kaefig.
DAEMPFER_STEG_MM = 2.0

DAEMPFER_STAEBE_SPANNE = (3, 9)
DAEMPFER_VORGABE_MAT = "cu_etp"


def _mat_blech(geom: dict) -> dict:
    import ema_pipeline
    name = str(geom.get("rotor_lam") or geom.get("rotorLam") or "m270_35a")
    return ema_pipeline.LAMINATES.get(name, ema_pipeline.LAMINATES["m270_35a"])


def polmasse_kg(k: dict, axial_mm: float, geom: dict) -> dict:
    """Masse und Schwerpunktradius EINES Pols — Schuh, Kern und Spule.

    Alle Masse kommen aus ``ema_eesm_cad.koerper``; hier wird nur gewogen.
    Die Spule zaehlt mit: sie sitzt auf dem Kern und wird vom Schuh gehalten,
    ihre Fliehkraft laeuft also durch denselben Halsquerschnitt.
    """
    import ema_pipeline
    L_m = float(axial_mm) * 1e-3
    rho_fe = float(_mat_blech(geom)["density"])              # kg/m^3
    mat_cu = str(geom.get("fieldMat") or "cu_etp")
    rho_cu = float(ema_pipeline.HAIRPIN_MATS.get(
        mat_cu, ema_pipeline.HAIRPIN_MATS["cu_etp"])["density"])

    r_rot = float(k["r_rotor_mm"])
    r_kern = float(k["r_kern_aussen_mm"])
    r_joch = float(k["r_joch_aussen_mm"])
    r_sp = float(k.get("r_spule_aussen_mm", r_kern))

    # Schuh: Kreisbogensegment, Flaeche ~ Bogenlaenge x Dicke am MITTLEREN
    # Radius (die Bogenlaenge waechst nach aussen, deshalb nicht am Rand).
    halb = (float(k["b_schuh_mm"]) / 2.0) / max(r_rot, 1e-9)   # rad
    a_schuh = halb * (r_rot ** 2 - r_kern ** 2)                # mm^2
    r_s_schuh = (2.0 / 3.0) * (r_rot ** 3 - r_kern ** 3) / \
                max(r_rot ** 2 - r_kern ** 2, 1e-9)

    b_i, b_a = float(k["b_kern_innen_mm"]), float(k["b_kern_aussen_mm"])
    a_kern = 0.5 * (b_i + b_a) * (r_kern - r_joch)
    r_s_kern = 0.5 * (r_kern + r_joch)

    d_s = float(k["d_spule_mm"])
    a_spule = 2.0 * d_s * max(r_sp - r_joch, 0.0)
    r_s_spule = 0.5 * (r_sp + r_joch)

    m_fe = (a_schuh + a_kern) * 1e-6 * L_m * rho_fe          # kg
    m_cu = a_spule * 1e-6 * L_m * rho_cu
    m = m_fe + m_cu
    if m <= 0:
        return {"m_kg": 0.0, "r_s_mm": r_kern, "m_eisen_kg": 0.0,
                "m_kupfer_kg": 0.0}
    r_s = ((a_schuh * r_s_schuh + a_kern * r_s_kern) * 1e-6 * L_m * rho_fe
           + a_spule * r_s_spule * 1e-6 * L_m * rho_cu) / m
    return {"m_kg": round(m, 4), "r_s_mm": round(r_s, 3),
            "m_eisen_kg": round(m_fe, 4), "m_kupfer_kg": round(m_cu, 4)}


def befestigung(geom: dict, axial_mm: float, rpm_max: float) -> dict:
    """Haelt der Polfuss die Fliehkraft? Geschlossene Formel, Millisekunden.

    Gerechnet wird beides — Schwalbenschwanz UND Bolzen —, gewaehlt wird ueber
    ``geom.polBefestigung``; die jeweils andere Bauart steht als Vergleich
    daneben. Das ist derselbe Gedanke wie in ``ema_getriebe``: welcher Weg
    bindet, ist die Auskunft, nicht die Zahl allein.
    """
    import ema_eesm_cad

    k = ema_eesm_cad.koerper(geom, axial_mm)
    L = float(axial_mm)
    art = str(geom.get("polBefestigung") or "schwalbenschwanz")
    if art not in BEFESTIGUNGEN:
        art = "schwalbenschwanz"

    pm = polmasse_kg(k, L, geom)
    omega = 2.0 * math.pi * max(float(rpm_max), 0.0) / 60.0
    f_n = pm["m_kg"] * omega ** 2 * pm["r_s_mm"] * 1e-3       # N

    blech = _mat_blech(geom)
    sig_zul_fe = float(blech["yield_mpa"]) / SF_ZIEL

    # ── Schwalbenschwanz: der Hals traegt auf ZUG ─────────────────────────
    b_hals = HALS_ZU_KERN * float(k["b_kern_innen_mm"])
    a_hals = b_hals * L                                       # mm^2
    sig_hals = f_n / max(a_hals, 1e-9) * KT_HALS              # MPa (N/mm^2)
    sf_hals = float(blech["yield_mpa"]) / max(sig_hals, 1e-9)
    b_hals_noetig = f_n * KT_HALS / max(sig_zul_fe * L, 1e-9)

    # ── Bolzen ───────────────────────────────────────────────────────────
    gew = str(geom.get("polBolzenGewinde") or "M10")
    if gew not in BOLZEN_AS_MM2:
        gew = "M10"
    n_bolzen = max(int(geom.get("polBolzen") or 2), 1)
    a_bolzen = n_bolzen * BOLZEN_AS_MM2[gew]
    sig_bolzen = f_n / max(a_bolzen, 1e-9)
    sf_bolzen = RP02_BOLZEN_MPA / max(sig_bolzen, 1e-9)
    a_noetig = f_n * SF_ZIEL / RP02_BOLZEN_MPA
    n_noetig = int(math.ceil(a_noetig / BOLZEN_AS_MM2[gew])) if a_noetig > 0 else 1

    sf = sf_hals if art == "schwalbenschwanz" else sf_bolzen
    haelt = sf >= SF_ZIEL

    if haelt:
        grund = ""
    elif art == "schwalbenschwanz":
        grund = (f"Der Polfuss haelt die Fliehkraft nicht: {f_n / 1000.0:.1f} kN "
                 f"je Pol bei {rpm_max:.0f} 1/min auf {a_hals:.0f} mm² Hals "
                 f"ergeben {sig_hals:.0f} MPa gegen eine Fliessgrenze von "
                 f"{blech['yield_mpa']:.0f} MPa (Sicherheit {sf_hals:.2f} "
                 f"statt {SF_ZIEL:.1f}). Noetig waeren {b_hals_noetig:.1f} mm "
                 f"Halsbreite statt {b_hals:.1f}; sonst weniger Drehzahl, ein "
                 f"festeres Blech oder Bolzen ({n_noetig} x {gew})")
    else:
        grund = (f"Die Verschraubung haelt die Fliehkraft nicht: "
                 f"{f_n / 1000.0:.1f} kN je Pol bei {rpm_max:.0f} 1/min auf "
                 f"{n_bolzen} x {gew} ({a_bolzen:.0f} mm²) ergeben "
                 f"{sig_bolzen:.0f} MPa gegen {RP02_BOLZEN_MPA:.0f} MPa (8.8), "
                 f"Sicherheit {sf_bolzen:.2f} statt {SF_ZIEL:.1f}. Noetig waeren "
                 f"{n_noetig} x {gew}")

    # Die Drehzahl, bei der es gerade noch haelt: sigma ~ omega^2, also
    # n_zul = n * sqrt(SF/SF_ziel). Exakt, kein Suchlauf.
    n_zul = (float(rpm_max) * math.sqrt(max(sf, 0.0) / SF_ZIEL)
             if rpm_max > 0 and sf > 0 else 0.0)

    return {
        "art": art,
        "poles": int(k["poles"]),
        "rpm": round(float(rpm_max), 1),
        "m_pol_kg": pm["m_kg"],
        "m_pol_eisen_kg": pm["m_eisen_kg"],
        "m_pol_kupfer_kg": pm["m_kupfer_kg"],
        "r_schwerpunkt_mm": pm["r_s_mm"],
        "F_flieh_kN": round(f_n / 1000.0, 3),
        "b_hals_mm": round(b_hals, 2),
        "b_hals_noetig_mm": round(b_hals_noetig, 2),
        "sigma_hals_MPa": round(sig_hals, 1),
        "SF_schwalbenschwanz": round(sf_hals, 3),
        "bolzen": f"{n_bolzen} x {gew}",
        "A_bolzen_mm2": round(a_bolzen, 1),
        "sigma_bolzen_MPa": round(sig_bolzen, 1),
        "SF_bolzen": round(sf_bolzen, 3),
        "bolzen_noetig": f"{n_noetig} x {gew}",
        "SF": round(sf, 3),
        "SF_ziel": SF_ZIEL,
        "haelt": bool(haelt),
        "n_zulaessig_1pmin": round(n_zul, 0),
        "grund": grund,
        "ungeprueft": ("Flankenpressung der Schwalbenschwanzfuehrung (der "
                       "Flankenwinkel ist kein Parameter dieses Werkzeugs), "
                       "Dauerfestigkeit, Presssitz und die Biegung des Pols "
                       "aus einseitigem Magnetzug"),
    }


def daempferkaefig(geom: dict, axial_mm: float) -> dict:
    """Staebe im Polschuh — Zahl, Durchmesser, Widerstand, Masse.

    Die Bemessung ist eine AUSLEGUNGSREGEL (s. Modulkopf) und wird als solche
    ausgewiesen (``regel``). Gerechnet wird daraus alles Weitere; was der
    Daempfer NUETZT, steht in ``wirkung`` als Text, weil es hier keine Zahl
    dafuer gibt.
    """
    import ema_eesm_cad
    import ema_pipeline
    import ema_wicklung

    k = ema_eesm_cad.koerper(geom, axial_mm)
    L = float(axial_mm)
    poles = int(k["poles"])
    r_rot = float(k["r_rotor_mm"])
    b_pol = float(k["b_schuh_mm"])
    h_schuh = float(k["h_schuh_mm"])

    an = str(geom.get("daempferkaefig") or "nein")
    ein = an in ("ja", "true", "1", True)

    # Staenderkupfer je Pol -- der Bezug der Querschnittsregel.
    slots = max(int(geom.get("slots") or 36), 1)
    nut = ema_wicklung.nutgeometrie(geom)
    # Kupfer JE NUT = Leiterquerschnitt x Leiter je Nut. `nutgeometrie` fuehrt
    # beides einzeln (`A_leiter_m2`, `n_lagen`) und keine Summe -- sie ein
    # zweites Mal zu bilden waere die Stelle, an der zwei Module verschiedene
    # Kupferquerschnitte fuehren.
    a_cu_nut = (float(nut.get("A_leiter_m2") or 0.0)
                * float(nut.get("n_lagen") or 0) * 1e6)      # mm^2
    a_staender_pol = a_cu_nut * slots / max(poles, 1)

    # Stabteilung aus der STAENDERnutteilung, bewusst verschieden davon.
    tau_nut = 2.0 * math.pi * r_rot / slots
    tau_d = TEILUNG_ZU_NUT * tau_nut
    n_vorgabe = int(geom.get("daempferStaebeJePol") or 0)
    n_d = (n_vorgabe if n_vorgabe > 0
           else int(round(b_pol / max(tau_d, 1e-9))))
    n_d = max(DAEMPFER_STAEBE_SPANNE[0], min(DAEMPFER_STAEBE_SPANNE[1], n_d))
    tau_ist = b_pol / max(n_d, 1)

    a_soll = K_QUERSCHNITT * a_staender_pol                   # mm^2 je Pol
    d_stab = math.sqrt(4.0 * a_soll / max(math.pi * n_d, 1e-9))
    d_stab = max(d_stab, 2.0)
    a_stab = math.pi * (d_stab / 2.0) ** 2
    a_ist = a_stab * n_d

    # Passt er in den Schuh? Bohrung plus Steg nach aussen und nach innen.
    noetig = d_stab + 2.0 * DAEMPFER_STEG_MM
    passt = noetig <= h_schuh and tau_ist > d_stab + 1.0
    if not ein:
        grund = ""
    elif noetig > h_schuh:
        grund = (f"Der Polschuh ist zu duenn fuer den Daempfer: {d_stab:.1f} mm "
                 f"Stab plus 2 x {DAEMPFER_STEG_MM:.1f} mm Steg brauchen "
                 f"{noetig:.1f} mm, der Schuh ist {h_schuh:.1f} mm hoch. "
                 f"Weniger Polbedeckung (duennere Staebe), ein dickerer "
                 f"Polschuh oder weniger Daempferquerschnitt")
    elif tau_ist <= d_stab + 1.0:
        grund = (f"Die Staebe stossen aneinander: {n_d} Staebe zu "
                 f"{d_stab:.1f} mm auf {b_pol:.1f} mm Polschuh ergeben "
                 f"{tau_ist:.1f} mm Teilung. Weniger Staebe je Pol")
    else:
        grund = ""

    # Die Stabteilung DARF der Staendernutteilung nicht gleichen.
    #
    # Das ist der Grund fuer `TEILUNG_ZU_NUT` und keine Feinheit: bei gleicher
    # Teilung koppelt der Daempfer an eine Oberwelle und die Maschine bleibt
    # beim asynchronen Anlauf auf einer Unterdrehzahl haengen (Goerges-Sattel).
    # Gedeckelt wird die Stabzahl aber (DAEMPFER_STAEBE_SPANNE), und dann kann
    # das Verhaeltnis in die Naehe von 1 laufen, ohne dass es jemand sieht.
    verh = tau_ist / max(tau_nut, 1e-9)
    teilung_ok = not (0.93 <= verh <= 1.07)
    hinweis = ""
    if not teilung_ok:
        hinweis = (f"Die Stabteilung liegt mit {verh:.2f} x der "
                   f"Staendernutteilung zu nah an 1 — dort koppelt der "
                   f"Daempfer an eine Oberwelle und der asynchrone Anlauf "
                   f"bleibt auf einer Unterdrehzahl haengen (Goerges-Sattel). "
                   f"Andere Stabzahl je Pol oder eine andere Staendernutzahl.")

    # Widerstand EINES Stabes bei der Leitertemperatur -- wie jede andere
    # Wicklung hier ueber `rho_bei`, nicht bei 20 Grad.
    mat = str(geom.get("daempferMat") or DAEMPFER_VORGABE_MAT)
    if mat not in ema_pipeline.HAIRPIN_MATS:
        mat = DAEMPFER_VORGABE_MAT
    t_c = ema_pipeline.leitertemperatur(geom)
    rho = ema_pipeline.rho_bei(ema_pipeline.HAIRPIN_MATS[mat], t_c)   # Ohm*m
    l_stab = L * 1.05 * 1e-3                                  # m, 5 % Ueberstand
    r_stab = rho * l_stab / max(a_stab * 1e-6, 1e-12)         # Ohm
    rho_m = float(ema_pipeline.HAIRPIN_MATS[mat]["density"])
    m_staebe = n_d * poles * a_stab * 1e-6 * l_stab * rho_m   # kg

    # Kurzschlussring wie beim Kaefig: Querschnitt ~ Stabquerschnitt x
    # n/(2*pi*p) -- dieselbe Regel wie ``ema_asm.kaefig``.
    p = max(poles // 2, 1)
    a_ring = a_stab * (n_d * poles) / (2.0 * math.pi * p)
    r_ring_mm = r_rot - DAEMPFER_STEG_MM - d_stab / 2.0
    m_ringe = 2.0 * a_ring * 1e-6 * (2.0 * math.pi * r_ring_mm * 1e-3) * rho_m

    return {
        "aktiv": bool(ein),
        "poles": poles,
        "n_stab_je_pol": n_d,
        "n_stab": n_d * poles,
        "d_stab_mm": round(d_stab, 2),
        "A_stab_mm2": round(a_stab, 2),
        "A_je_pol_mm2": round(a_ist, 1),
        "A_soll_je_pol_mm2": round(a_soll, 1),
        "A_staender_je_pol_mm2": round(a_staender_pol, 1),
        "teilung_mm": round(tau_ist, 2),
        "teilung_staendernut_mm": round(tau_nut, 2),
        "teilungsverhaeltnis": round(verh, 3),
        "teilung_ok": bool(teilung_ok),
        "hinweis": hinweis,
        "r_ring_mm": round(r_ring_mm, 2),
        "A_ring_mm2": round(a_ring, 1),
        "R_stab_mOhm": round(r_stab * 1e3, 4),
        "werkstoff": mat,
        "werkstoff_label": ema_pipeline.HAIRPIN_MATS[mat]["label"],
        "T_leiter_C": round(t_c, 1),
        "masse_kg": round(m_staebe + m_ringe, 3),
        "h_schuh_mm": round(h_schuh, 2),
        "noetige_schuhhoehe_mm": round(noetig, 2),
        "passt": bool(passt),
        "grund": grund,
        "regel": (f"Querschnitt je Pol = {K_QUERSCHNITT:.2f} x Staenderkupfer "
                  f"je Pol, Stabteilung = {TEILUNG_ZU_NUT:.2f} x "
                  f"Staendernutteilung (Say, Alternating Current Machines; "
                  f"IEEE Std 115) — eine Auslegungsregel, keine Messung"),
        "wirkung": ("Der Daempfer ermoeglicht den asynchronen Anlauf und "
                    "daempft Lastpendelungen. BEIDES braucht einen "
                    "zeitabhaengigen Lauf und geht in keine Kennzahl dieses "
                    "Werkzeugs ein — gerechnet wird, was er KOSTET (Masse, "
                    "Platz im Polschuh), nicht was er nuetzt."),
    }


def zeichenmasse(d: dict) -> dict:
    """Nur die Zahlen fuer den Zeichner — Urteile bleiben draussen.

    Ein ``true``/``null`` aus JSON waere im erzeugten **Python**-Skript ein
    NameError; derselbe Grund wie in ``ema_eesm_cad.zeichenmasse``.
    """
    return {"n_stab_je_pol": int(d["n_stab_je_pol"]),
            "d_stab_mm": float(d["d_stab_mm"]),
            "teilung_mm": float(d["teilung_mm"]),
            "r_ring_mm": float(d["r_ring_mm"]),
            "steg_mm": DAEMPFER_STEG_MM}
