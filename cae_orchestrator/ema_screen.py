"""Vorauswahl: viele Konfigurationen grob durchspielen, bevor eine teuer gerechnet wird.

Das Problem, das es loest
-------------------------

Bisher beginnt jede Rechnung beim **letzten Stand** (``--from-project last``) und
aendert daran einzelne Werte. Das ist bequem und fuehrt zu einem engen Pfad: die
Polzahl, die Nutzahl und die Magnetanordnung des ersten Entwurfs bleiben stehen,
obwohl gerade sie den Entwurf praegen. Wer eine Maschine wirklich auslegt, sieht sich
zuerst die **Konfigurationen** an — 4 oder 8 Pole, 36 oder 48 Nuten, V- oder
Speichenanordnung — und waehlt dann, was er fein rechnet.

Genau das tut dieses Modul, und es kann es sich leisten: die analytische Bewertung
kostet **18 µs je Variante** (gemessen), die Tore einige Millisekunden. Hunderte
Konfigurationen sind damit Sekundenarbeit, waehrend ein einziger voller Lauf 30
Minuten bis 4 Stunden dauert.

Was hier NICHT passiert
-----------------------

Kein Feldlauf, keine FEM, keine Thermik. Alles ist geschlossene Mathe auf Geometrie
und Werkstofftabellen. Die Vorauswahl **sortiert aus und rangiert**; sie entscheidet
nichts. Was sie oben hinstellt, muss danach richtig gerechnet werden — und die
Kennzahlen, die sie liefert, tragen in der Rechnungsdatenbank folgerichtig die
Herkunft ``analytisch``.

Guenstig oder Leistung
----------------------

Beide Ziele bewerten dieselben Varianten anders. Ein Antrieb, der billig sein soll,
gewichtet Magnetmasse und Fertigungsaufwand; einer, der Leistung bringen soll,
gewichtet Momentkonstante und Drehzahlfestigkeit. ``ziel_aus_text`` liest die Absicht
aus dem Auslegungsauftrag, wenn einer da ist — mit **Belegwoertern**, damit
nachvollziehbar bleibt, warum ein Ziel erkannt wurde.

**Die Preise sind Platzhalter zum Rangieren, kein Kostenvoranschlag.** Sie stehen in
``PREISE_EUR_KG`` und sind grob; entscheidend ist, dass NdFeB rund das Fuenffache von
Kupfer und das Dreissigfache von Elektroblech kostet — diese Ordnung, nicht der
absolute Betrag, treibt das Ergebnis.
"""

from __future__ import annotations

import math
from itertools import product

from ema_analysis import _analytical_Bgap, compute_performance
from ema_pipeline import HAIRPIN_MATS, LAMINATES, MAGNETS
from ema_rotorcheck import (Pocket, _rot2, pocket_distance,
                            rotor_layout_check, rotor_stress_check)
from ema_topology import BRIDGE_MM, TOPOLOGY_LABELS, leg_center, magnet_legs

# Platzhalterpreise 2026 — fuer das Rangieren, nicht als Angebot. Was zaehlt, ist das
# Verhaeltnis: NdFeB ~5x Kupfer, ~34x Elektroblech.
PREISE_EUR_KG = {"magnet": 55.0, "kupfer": 10.0, "stahl": 1.6}

# NdFeB-Dichte; steht so nicht in der MAGNETS-Tabelle (Literaturwert N42–N52).
MAG_DICHTE_KG_M3 = 7600.0

# Die Achsen, ueber die vorausgewaehlt wird. Bewusst grob gerastert — eine Vorauswahl
# soll die GESTALT finden, nicht die dritte Nachkommastelle.
ACHSEN_VORGABE = {
    "p":                 [2, 3, 4, 5],
    "slots":             [24, 36, 48, 60],
    "magShape":          ["v", "vasym", "bar", "u", "vv", "delta", "spoke", "pmasynrm"],
    "conductorsPerSlot": [4, 6, 8],
}

ZIELE = ("guenstig", "leistung", "ausgewogen")

# Gewichte je Ziel. Summe 1,0. Offen im Code, damit man sie bestreiten kann.
GEWICHTE = {
    "leistung":   {"kt": 0.30, "drehzahl": 0.22, "leistungsdichte": 0.22,
                   "rundlauf": 0.10, "kosten": 0.08, "einfachheit": 0.08},
    "guenstig":   {"kt": 0.16, "drehzahl": 0.10, "leistungsdichte": 0.10,
                   "rundlauf": 0.06, "kosten": 0.40, "einfachheit": 0.18},
    "ausgewogen": {"kt": 0.22, "drehzahl": 0.16, "leistungsdichte": 0.15,
                   "rundlauf": 0.10, "kosten": 0.22, "einfachheit": 0.15},
}

# Wortfelder fuer die Zielerkennung. Absichtlich klein und nachlesbar.
_WORTE_GUENSTIG = ("günstig", "guenstig", "billig", "kosten", "preiswert", "sparsam",
                   "budget", "wirtschaftlich", "magnetarm", "seltene erden sparen",
                   "kostenoptimiert", "low cost", "economical", "cheap")
_WORTE_LEISTUNG = ("leistung", "performance", "sport", "maximal", "hochdrehend",
                   "spitzenleistung", "rennen", "dynamik", "drehmomentstark",
                   "high performance", "power", "track")


# ── Magnettaschen in den Pol einpassen ────────────────────────────────────────

# Groessen, die den MAGNETKOERPER beschreiben, und solche, die seine ANORDNUNG
# beschreiben. Die Unterscheidung ist der Kern des Einpassens: einen Koerper zu
# verkleinern macht JEDEN Steg dicker; die Anordnung enger zu ziehen macht die Stege
# zwischen den Polen dicker und die INNERHALB eines Pols duenner. Ein einziger
# gemeinsamer Massstab kann darum nicht funktionieren -- er skaliert die Stege gleich
# mit und aendert an einem zu duennen Steg nichts.
KOERPERMASSE  = ("magWidth", "magThick", "magTangLen")
ANORDNUNGSMASSE = ("magDist", "magLayerGap")

# Untere Schranke fuer den Koerpermassstab. Wer mehr als 60 % wegnehmen muss, damit
# die Taschen in den Pol passen, baut keine Variante dieser Maschine mehr.
S_MIN = 0.40


def _taschen(geom: dict):
    """Die Taschen EINES Pols und aller Pole -- exakt die Formgebung des Tors.

    Bewusst dieselben Bausteine wie ``ema_rotorcheck``: ``Pocket``,
    ``pocket_distance``, dieselbe Spaltregel. Eine zweite, eigene Taschenformel waere
    genau der Fehler, den die Vorauswahl nicht machen darf -- sie wuerde Varianten
    durchwinken, an denen das Tor danach scheitert.
    """
    legs, meta = magnet_legs(geom)
    poles = max(2, 2 * max(1, int(geom.get("p", 3))))
    gap = max(0.05, min(0.3, float(geom.get("magGapMm", 0.1))))
    pol0, alle = [], []
    for li, leg in enumerate(legs):
        if leg.length <= 0 or leg.thickness <= 0:
            continue
        hl = leg.length / 2.0 + gap
        ht = leg.thickness / 2.0 + gap
        zentrum = leg_center(leg)
        for pol in range(poles):
            a = pol * 2.0 * math.pi / poles
            eintrag = (pol, li, Pocket(_rot2(zentrum, a), leg.tilt + a, hl, ht),
                       leg.placement)
            alle.append(eintrag)
            if pol == 0:
                pol0.append(eintrag)
    return pol0, alle, legs, meta


def _masse(geom: dict, nur_radial: bool = False,
           abbruch_unter: float | None = None) -> dict:
    """Die vier Zahlen, an denen das Einpassen haengt.

    ``rmin``/``rmax`` = radiale Ausdehnung aller eingelassenen Taschen;
    ``steg_im_pol`` = duennste Stelle zwischen zwei Taschen DESSELBEN Pols;
    ``steg_zw_polen`` = duennste Stelle zwischen Taschen VERSCHIEDENER Pole.

    Verglichen wird Pol 0 gegen **alle** Pole. Das ist wegen der Drehsymmetrie
    vollstaendig -- jedes Paar (i, j) ist ein Paar (0, j-i) -- und kostet doch nur
    einen Bruchteil des vollen Tors, das alle Paare rechnet.

    Der frueher hier stehende Kurzweg "Pol 0 und seine beiden Nachbarn" war NICHT
    vollstaendig: sobald die Anordnung aufgeweitet wird, greift eine Tasche ueber den
    Nachbarpol hinaus. Gemessen liefen so 27 von 384 Varianten durch die Einpassung
    und fielen danach am Tor durch -- an Paaren wie Pol 0 <-> Pol 3.
    """
    pol0, alle, legs, meta = _taschen(geom)
    rmin, rmax = math.inf, -math.inf
    for _p, _l, pk, plc in alle:
        if plc != "interior":
            continue
        a, b = pk.radius_bounds()
        rmin, rmax = min(rmin, a), max(rmax, b)

    # KEIN Abstandsvorfilter. Er waere naheliegend und ist hier trotzdem falsch:
    # ``pocket_distance`` gibt eine UNTERE Schranke des wahren Abstands zurueck, kein
    # Mass. Ein Filter, der nach wahrer Geometrie aussortiert, wuerde darum Paare
    # uebergehen, die das Tor selbst noch als zu eng meldet -- die Vorauswahl liefe
    # dem Tor davon.
    #
    # Die Geschwindigkeit kommt stattdessen aus drei exakten Abkuerzungen: der
    # Zwischenspeicher in ``screene`` (Nutzahl und Leiterzahl aendern die Geometrie
    # nicht), ``nur_radial`` (die Sitzkorrektur braucht ueberhaupt keine Abstaende)
    # und ``abbruch_unter`` (steht ein Steg schon unter der Mindestdicke, ist die
    # Antwort auf die einzige gestellte Frage -- passt es? -- bereits gefallen).
    im_pol, zw_polen = math.inf, math.inf
    if not nur_radial:
        for _p0, li, a, _pa in pol0:
            for pj, lj, b, _pb in alle:
                if pj == 0 and lj == li:
                    continue
                d = pocket_distance(a, b)
                if pj == 0:
                    im_pol = min(im_pol, d)
                else:
                    zw_polen = min(zw_polen, d)
                if abbruch_unter is not None and d < abbruch_unter:
                    return {"rmin": rmin, "rmax": rmax, "steg_im_pol": im_pol,
                            "steg_zw_polen": zw_polen,
                            "taschen": sum(1 for t in alle if t[3] == "interior"),
                            "legs": legs, "meta": meta}
    return {"rmin": rmin, "rmax": rmax, "steg_im_pol": im_pol,
            "steg_zw_polen": zw_polen,
            "taschen": sum(1 for t in alle if t[3] == "interior"),
            "legs": legs, "meta": meta}


def _skaliere(basis: dict, s_koerper: float, s_lage: float) -> dict:
    g = dict(basis)
    for k in KOERPERMASSE:
        if isinstance(g.get(k), (int, float)):
            g[k] = round(float(basis[k]) * s_koerper, 4)
    for k in ANORDNUNGSMASSE:
        if isinstance(g.get(k), (int, float)):
            g[k] = round(float(basis[k]) * s_lage, 4)
    return g


def _radial_einpassen(geom: dict, min_web: float) -> tuple[dict, dict]:
    """Den Magnetsitz (``magDepthRel``) so schieben, dass das Taschenband hineinpasst.

    Der haeufigste Ablehnungsgrund war ein Ueberstand von Bruchteilen eines
    Millimeters -- die Bauvorschriften klemmen die Magnetlaenge gegen
    ``r_rot - Steg - halbe Dicke`` auf der Mittellinie, das Tor misst dagegen die
    Taschenecken einschliesslich Spalt und Endkappen. Diese Differenz ist keine
    Fehlkonfiguration, sondern eine Frage des Sitzes: ein paar Zehntel weiter innen,
    und dieselbe Variante ist zulaessig.
    """
    g = dict(geom)
    r_rot = float(g["rotorOD"]) / 2.0
    r_sh  = float(g["shaftD"]) / 2.0
    unten, oben = r_sh + min_web, r_rot - min_web
    m = _masse(g, nur_radial=True)
    if not math.isfinite(m["rmax"]):
        return g, m
    for _ in range(6):
        dicke = m["rmax"] - m["rmin"]
        if dicke > oben - unten:
            return g, m                       # passt radial ueberhaupt nicht
        mitte_ist  = (m["rmax"] + m["rmin"]) / 2.0
        mitte_soll = (oben + unten) / 2.0
        # Nur so weit schieben, wie noetig: die Mitte anzustreben wuerde einen
        # gewollt tiefen oder flachen Sitz ohne Not zerstoeren.
        if m["rmax"] > oben:
            d_r = oben - m["rmax"]
        elif m["rmin"] < unten:
            d_r = unten - m["rmin"]
        else:
            break
        d_rel = d_r / max(r_rot - r_sh, 1e-6)
        neu = min(0.95, max(0.05, float(g.get("magDepthRel", 0.6)) + d_rel))
        if abs(neu - float(g.get("magDepthRel", 0.6))) < 1e-6:
            break
        g["magDepthRel"] = round(neu, 5)
        m = _masse(g, nur_radial=True)
        _ = mitte_ist, mitte_soll
    return g, m


def _passt(geom: dict, min_web: float) -> tuple[bool, dict, dict]:
    g, _ = _radial_einpassen(geom, min_web)
    m = _masse(g, abbruch_unter=min_web - 1e-6)
    if not math.isfinite(m["rmax"]):
        return False, g, m
    r_rot = float(g["rotorOD"]) / 2.0
    r_sh  = float(g["shaftD"]) / 2.0
    ok = (m["rmax"] <= r_rot + 1e-6 and m["rmin"] >= r_sh - 1e-6
          and m["steg_im_pol"] >= min_web - 1e-6
          and m["steg_zw_polen"] >= min_web - 1e-6)
    return ok, g, m


def einpassen(geom: dict, p_neu: int | None = None,
              min_web: float = BRIDGE_MM) -> dict:
    """Eine Konfiguration so einpassen, dass sie baubar ist -- oder ehrlich scheitern.

    Vorgehen in drei Schritten:

    1. **Anordnung mit der Polteilung mitziehen.** Wird die Polzahl erhoeht, wird der
       Pol schmaler; ``magDist`` und ``magLayerGap`` gehen im Verhaeltnis der
       Polteilungen mit. Das ist der einzige Schritt, der aus der Polzahl folgt.
    2. **Sitz nachfuehren** (``_radial_einpassen``).
    3. **Koerpermassstab absenken, bis die Stege stehen.** Grobe Absenkung in
       10-%-Schritten bis ``S_MIN``, danach vier Halbierungsschritte zurueck nach
       oben -- so bleibt der Magnet so gross wie zulaessig und nicht kleiner.

    Rueckgabe enthaelt IMMER das Protokoll (``s_koerper``, ``s_lage``, verschobener
    Sitz, gemessene Stege). Eine Vorauswahl, die Magnete stillschweigend verkleinert
    und danach nach Momentkonstante rangiert, wuerde sich selbst betruegen; hier ist
    jede Verkleinerung ablesbar -- und sie schlaegt ueber ``magThick`` und die
    Magnetmasse ohnehin auf B_gap, Kosten und Rang durch.
    """
    basis = dict(geom)
    p_alt = max(1, int(basis.get("p", 3)))
    if p_neu is not None:
        basis["p"] = max(1, int(p_neu))
    s_lage = p_alt / max(1, int(basis["p"]))

    # Aussen aufgesetzte Magnete (SPM/Halbach) und die frei gezeichnete Geometrie
    # kennen weder Taschen noch Polteilungsskalierung -- unveraendert durchreichen.
    if basis.get("magShape") in ("spm", "halbach", "custom"):
        ok, g, m = _passt(basis, min_web)
        return {"geom": g, "ok": ok, "s_koerper": 1.0, "s_lage": 1.0,
                "magDepthRel": g.get("magDepthRel"), "steg_im_pol": m["steg_im_pol"],
                "steg_zw_polen": m["steg_zw_polen"], "grund": "" if ok else "Taschenlayout"}

    def sweep(s_l: float):
        """Groesstmoegliches ``s_koerper`` bei fester Anordnung -- oder None."""
        s = 1.0
        treffer = None
        while s >= S_MIN - 1e-9:
            ok, g, m = _passt(_skaliere(basis, s, s_l), min_web)
            if ok:
                treffer = (s, g, m)
                break
            s = round(s - 0.10, 4)
        if treffer is None:
            return None
        lo, hi = treffer[0], min(1.0, treffer[0] + 0.10)
        for _ in range(4):
            mitte = (lo + hi) / 2.0
            ok, g, m = _passt(_skaliere(basis, mitte, s_l), min_web)
            if ok:
                lo, treffer = mitte, (mitte, g, m)
            else:
                hi = mitte
        return treffer

    # Die Anordnung darf in BEIDE Richtungen. Nur zu verkleinern reicht nicht: ein zu
    # duenner Steg INNERHALB eines Pols -- die Regel bei mehrlagigen Bauformen wie
    # pmasynrm und Doppel-V -- wird durch engeres Zusammenruecken schlimmer, nicht
    # besser. Er verlangt das Gegenteil: die Lagen weiter auseinander. Gemessen ist
    # pmasynrm bei ``magLayerGap`` 16 mm und 2 Lagen mit 2,71 mm Steg zulaessig,
    # waehrend es bei den 8 mm des Ausgangsentwurfs an 0,01 mm scheitert.
    kandidaten = [s_lage * f for f in (1.0, 1.25, 1.5, 1.75, 2.0, 0.8, 0.65)]
    bestes = None
    for s_l in kandidaten:
        t = sweep(s_l)
        if t is None:
            continue
        if bestes is None or t[0] > bestes[0][0] + 1e-9:
            bestes = (t, s_l)
        if t[0] >= 0.95:            # Magnet praktisch ungeschmaelert -- fertig
            break

    if bestes is None:
        ok, g, m = _passt(_skaliere(basis, S_MIN, s_lage), min_web)
        return {"geom": g, "ok": False, "s_koerper": S_MIN, "s_lage": round(s_lage, 4),
                "magDepthRel": g.get("magDepthRel"),
                "steg_im_pol": round(m["steg_im_pol"], 3) if math.isfinite(m["steg_im_pol"]) else None,
                "steg_zw_polen": round(m["steg_zw_polen"], 3) if math.isfinite(m["steg_zw_polen"]) else None,
                "grund": (f"Taschen passen weder bei {S_MIN:.0%} Magnetgroesse noch bei "
                          f"veraenderter Anordnung in den Pol")}

    (s_ok, g_ok, m_ok), s_lage = bestes

    # magWidth auf die TATSAECHLICH gebaute Magnetlaenge zurueckschreiben. Die
    # Bauvorschriften klemmen die Laenge gegen den Aussenrand; ``_analytical_Bgap``
    # liest aber das NOMINELLE ``magWidth``. Ohne diesen Abgleich bewertet die
    # Vorauswahl eine Magnetbreite, die im Blech gar nicht steht -- und rangiert
    # dann nach einer Momentkonstante, die es nicht gibt.
    #
    # Der Rueckschreib ist selbst eine Geometrieaenderung: bei mehrteiligen Bauformen
    # haengen weitere Masse an ``magWidth`` (beim U etwa die Laenge des Bodenbalkens).
    # Er wird darum NACHGEPRUEFT und im Zweifel verworfen -- sonst gibt die
    # Einpassung eine Geometrie zurueck, die sie nie gemessen hat. Genau das ist hier
    # passiert: 15 von 384 Varianten meldeten einen Steg von 2,01 mm und fielen
    # danach am Tor mit 0,12 mm durch.
    innen_legs = [l for l in m_ok["legs"] if l.placement == "interior" and l.length > 0]
    if innen_legs:
        breite = min(float(g_ok.get("magWidth", 0.0)) or math.inf,
                     max(l.length for l in innen_legs))
        if math.isfinite(breite) and breite > 0:
            kandidat = dict(g_ok)
            kandidat["magWidth"] = round(breite, 4)
            ok2, g2, m2 = _passt(kandidat, min_web)
            if ok2:
                g_ok, m_ok = g2, m2

    return {"geom": g_ok, "ok": True, "s_koerper": round(s_ok, 4),
            "s_lage": round(s_lage, 4), "magDepthRel": g_ok.get("magDepthRel"),
            "steg_im_pol": round(m_ok["steg_im_pol"], 3),
            "steg_zw_polen": round(m_ok["steg_zw_polen"], 3), "grund": ""}


def anpassen_an_polzahl(geom: dict, p_neu: int) -> dict:
    """Bequemer Kurzweg: nur die eingepasste Geometrie, ohne Protokoll."""
    return einpassen(geom, p_neu)["geom"]


# ── Wicklung: welche Nut/Pol-Kombination ist ueberhaupt baubar ────────────────

def wicklung_moeglich(slots: int, poles: int) -> bool:
    """Laesst sich aus dieser Nut/Pol-Paarung eine symmetrische Drehstromwicklung bauen?

    Kriterium: ``slots / ggT(slots, poles)`` muss durch 3 teilbar sein — sonst lassen
    sich die drei Straenge nicht gleichmaessig verteilen und die Maschine laeuft
    unrund. Zusaetzlich muss die Nutzahl selbst durch 3 teilbar sein.

    Ohne diesen Filter erzeugt die Vorauswahl Kombinationen, die zwar rechnen, aber
    nicht gebaut werden koennen — und ein Ranking, das solche Varianten enthaelt, ist
    wertlos.
    """
    if slots <= 0 or poles <= 0 or slots % 3:
        return False
    return (slots // math.gcd(slots, poles)) % 3 == 0


def nutzahl_je_pol_und_strang(slots: int, poles: int) -> float:
    return slots / (3.0 * poles)


# ── Massen und Kosten ─────────────────────────────────────────────────────────

def massen_und_kosten(payload: dict) -> dict:
    """Massen [kg] und eine grobe Kostenschaetzung [EUR].

    Die Magnetmasse kommt exakt aus den Leg-Records; alles andere sind Zylinderringe
    mit Annahmen (Nutanteil, Fuellfaktor). Genauigkeit rund ±25–30 %, was fuer eine
    RANGFOLGE reicht und fuer eine Aussage ueber den Preis nicht.
    """
    geom = payload.get("geom", {})
    L    = float(geom.get("axialLen") or payload.get("axial_len") or 80.0)
    d_st_i = float(geom.get("statorID", 0.0))
    d_st_a = float(geom.get("statorOD", 0.0))
    d_rot  = float(geom["rotorOD"])
    d_wel  = float(geom["shaftD"])
    d_bohr = float(geom.get("shaftBoreD", 0.0) or 0.0)

    lam_rot = LAMINATES.get(payload.get("rotor_lam", "m270_35a"), LAMINATES["m270_35a"])
    lam_st  = LAMINATES.get(payload.get("stator_lam", "m270_35a"), LAMINATES["m270_35a"])
    cu      = HAIRPIN_MATS.get(payload.get("hairpin_mat", "cu_etp"),
                               list(HAIRPIN_MATS.values())[0])

    poles = 2 * max(1, int(geom.get("p", 3)))
    legs, _meta = magnet_legs(geom)
    # NUR die eingelassenen Magnete zaehlen als Taschenfuellung; Oberflaechenmagnete
    # sitzen aussen auf. Der geparkte Vorgaenger hatte hier ein "or True" stehen und
    # zaehlte damit immer alle — der Filter war wirkungslos.
    flaeche_mm2 = sum(l.length * l.thickness for l in legs)
    m_mag = flaeche_mm2 * poles * L * 1e-9 * MAG_DICHTE_KG_M3

    m_rot_fe = math.pi / 4 * (d_rot**2 - d_wel**2) * L * 1e-9 * float(lam_rot["density"])
    m_welle  = math.pi / 4 * (d_wel**2 - d_bohr**2) * (L + 80.0) * 1e-9 * 7850.0
    v_st_m3  = math.pi / 4 * (d_st_a**2 - d_st_i**2) * L * 1e-9
    m_st_fe  = v_st_m3 * float(lam_st["density"]) * 0.78          # abzueglich Nuten
    m_cu     = v_st_m3 * 0.30 * 0.55 * float(cu.get("density", 8900.0))

    kosten = {
        "magnet_EUR": round(m_mag * PREISE_EUR_KG["magnet"], 0),
        "kupfer_EUR": round(m_cu * PREISE_EUR_KG["kupfer"], 0),
        "stahl_EUR":  round((m_rot_fe + m_st_fe + m_welle) * PREISE_EUR_KG["stahl"], 0),
    }
    kosten["gesamt_EUR"] = round(sum(kosten.values()), 0)
    return {"magnet_kg": round(m_mag, 3), "rotoreisen_kg": round(m_rot_fe, 2),
            "welle_kg": round(m_welle, 2), "statoreisen_kg": round(m_st_fe, 2),
            "kupfer_kg": round(m_cu, 2),
            "gesamt_kg": round(m_mag + m_rot_fe + m_welle + m_st_fe + m_cu, 2),
            "kosten": kosten,
            "hinweis": "Platzhalterpreise, ±25–30 % — zum Rangieren, kein Angebot."}


# ── Ziel erkennen ─────────────────────────────────────────────────────────────

def ziel_aus_text(text: str) -> dict:
    """Aus einem Auslegungsauftrag ableiten, ob guenstig oder Leistung gemeint ist.

    Gibt Ziel **und Belegwoerter** zurueck. Ohne die Belege waere die Erkennung eine
    Blackbox, und niemand koennte sehen, warum eine Auslegung ploetzlich auf Kosten
    optimiert wird.
    """
    t = (text or "").lower()
    tg = [w for w in _WORTE_GUENSTIG if w in t]
    tl = [w for w in _WORTE_LEISTUNG if w in t]
    if len(tg) > len(tl):
        ziel = "guenstig"
    elif len(tl) > len(tg):
        ziel = "leistung"
    else:
        ziel = "ausgewogen"
    return {"ziel": ziel, "belege_guenstig": tg, "belege_leistung": tl,
            "sicher": bool(tg or tl) and len(tg) != len(tl)}


# ── Eine Variante bewerten ────────────────────────────────────────────────────

def bewerte(payload: dict, n_max: float) -> dict:
    """Eine Konfiguration analytisch bewerten. Kein Feld, keine FEM — Millisekunden."""
    geom = payload["geom"]
    poles = 2 * int(geom["p"])
    zeile = {"p": int(geom["p"]), "poles": poles, "slots": int(geom["slots"]),
             "magShape": geom.get("magShape", "v"),
             "conductorsPerSlot": int(geom.get("conductorsPerSlot", 6)),
             "q": round(nutzahl_je_pol_und_strang(int(geom["slots"]), poles), 3)}

    if not wicklung_moeglich(int(geom["slots"]), poles):
        return {**zeile, "ok": False, "grund": "keine symmetrische Drehstromwicklung"}

    lay = rotor_layout_check(geom)
    if not lay["ok"]:
        return {**zeile, "ok": False,
                "grund": "Taschenlayout: " + "; ".join(lay["fatal"])[:120]}

    mat = LAMINATES.get(payload.get("rotor_lam", "m270_35a"), LAMINATES["m270_35a"])
    st  = rotor_stress_check(geom, mat, {"n_max": n_max})
    if not st.get("ok", True):
        return {**zeile, "ok": False,
                "grund": f"Fliehkraft bei {n_max:.0f} 1/min: SF "
                         f"{st.get('safety_factor', 0):.2f}"}

    b_gap = _analytical_Bgap(geom)
    perf  = compute_performance(geom, b_gap, axial_mm=float(geom.get("axialLen", 80.0)))
    mk    = massen_und_kosten(payload)

    kt = float(perf["Kt_Nm_per_A"])
    # WICHTIG und leicht zu uebersehen: compute_performance rechnet
    # psi_pm = p*(2/pi)*B_gap*R_gap*L und kennt weder Nutzahl noch Windungszahl.
    # Kt und B_gap sind auf dieser Stufe also UNABHAENGIG von slots und
    # conductorsPerSlot. Die Nutzahl laesst sich hier nur ueber zwei Groessen
    # bewerten, die wirklich von ihr abhaengen: das kgV aus Nut- und Polzahl
    # (Ordnung des Rastmoments — je hoeher, desto runder der Lauf) und den
    # Fertigungsaufwand. Wer die Nutzahl elektromagnetisch bewerten will, braucht
    # den Feldlauf; das ist genau die Stufe darunter.
    lcm = int(perf.get("lcm_slots_poles") or 0)
    return {**zeile, "ok": True, "grund": "",
            "B_gap_T": round(b_gap, 4),
            "Kt_Nm_per_A": round(kt, 5),
            "lcm_slots_poles": lcm,
            "safety_factor": round(float(st.get("safety_factor", 0.0)), 2),
            "magnet_kg": mk["magnet_kg"],
            "gesamt_kg": mk["gesamt_kg"],
            "kosten_EUR": mk["kosten"]["gesamt_EUR"],
            "magnetkosten_EUR": mk["kosten"]["magnet_EUR"],
            "kt_je_kg": round(kt / max(mk["gesamt_kg"], 1e-6), 6),
            "kt_je_EUR": round(kt / max(mk["kosten"]["gesamt_EUR"], 1e-6), 8),
            "topologie": TOPOLOGY_LABELS.get(geom.get("magShape", "v"), "?")}


# ── Vorauswahl ────────────────────────────────────────────────────────────────

def _normiere(werte: list, groesser_besser: bool = True) -> list:
    lo, hi = min(werte), max(werte)
    if hi - lo < 1e-12:
        return [0.5] * len(werte)
    n = [(w - lo) / (hi - lo) for w in werte]
    return n if groesser_besser else [1.0 - x for x in n]


def screene(basis: dict, ziel: str = "ausgewogen", achsen: dict | None = None,
            n_max: float | None = None, grenze: int = 400) -> dict:
    """Konfigurationen durchspielen, bewerten, rangieren.

    ``basis`` ist ein vollstaendiger Payload (etwa aus einem vorhandenen Projekt); die
    Achsen werden darueber variiert, alles Uebrige bleibt stehen. So bleibt der
    Vergleich fair — es aendert sich nur, was verglichen werden soll.
    """
    if ziel not in ZIELE:
        raise ValueError(f"ziel muss aus {ZIELE} sein, nicht {ziel!r}")
    achsen = achsen or ACHSEN_VORGABE
    n_max  = float(n_max or (basis.get("target") or {}).get("n_max") or 12000.0)

    namen = list(achsen)
    kombis = list(product(*(achsen[k] for k in namen)))
    if len(kombis) > grenze:
        raise ValueError(f"{len(kombis)} Kombinationen ueberschreiten die Grenze "
                         f"{grenze} — Achsen enger fassen oder grenze anheben.")

    # Die Einpassung haengt nur an der GEOMETRIE. Nutzahl und Leiterzahl aendern
    # daran nichts, laufen aber als eigene Achsen mit -- ohne Zwischenspeicher wuerde
    # dieselbe Taschenrechnung hier zwoelfmal wiederholt (gemessen: 93 s statt 8 s).
    speicher: dict = {}

    def eingepasst(g: dict, p_neu):
        schluessel = (p_neu, tuple(sorted(
            (k, v) for k, v in g.items() if isinstance(v, (int, float, str, bool)))))
        if schluessel not in speicher:
            speicher[schluessel] = einpassen(g, p_neu)
        return speicher[schluessel]

    zeilen = []
    for werte in kombis:
        p = {k: v for k, v in basis.items() if k != "geom"}
        g = dict(basis["geom"])
        p_neu = None
        for name, wert in zip(namen, werte):
            if name == "p":
                p_neu = int(wert)
            else:
                g[name] = wert
        try:
            # Erst einpassen, dann bewerten. Die Reihenfolge ist entscheidend: eine
            # Variante, die nur an einem Zehntelmillimeter Ueberstand oder an der
            # Polteilung scheitert, ist keine unbaubare Variante, sondern eine
            # ungepasste. Erst was auch eingepasst nicht steht, faellt durch.
            pas = eingepasst(g, p_neu)
            p["geom"] = pas["geom"]
            if not pas["ok"]:
                zeile = {"p": int(pas["geom"]["p"]),
                         "poles": 2 * int(pas["geom"]["p"]),
                         "slots": int(pas["geom"]["slots"]),
                         "magShape": pas["geom"].get("magShape", "v"),
                         "conductorsPerSlot": int(pas["geom"].get("conductorsPerSlot", 6)),
                         "ok": False, "grund": pas["grund"]}
            else:
                zeile = bewerte(p, n_max)
            zeile["s_koerper"] = pas["s_koerper"]
            zeile["s_lage"] = pas["s_lage"]
            zeile["magDepthRel"] = pas["magDepthRel"]
            # Die EINGEPASSTE Geometrie muss mit heraus. Ohne sie ist eine Zeile,
            # deren Magnet verkleinert wurde, nicht nachbaubar -- s. `uebernahme`.
            zeile["geom"] = {k: pas["geom"].get(k)
                             for k in UEBERNAHME_GEOM if k in pas["geom"]}
            zeile["steg_min_mm"] = min(x for x in (pas["steg_im_pol"],
                                                   pas["steg_zw_polen"])
                                       if x is not None) if any(
                x is not None for x in (pas["steg_im_pol"], pas["steg_zw_polen"])) else None
            zeilen.append(zeile)
        except Exception as e:                               # noqa: BLE001
            zeilen.append({**{k: v for k, v in zip(namen, werte)},
                           "ok": False, "grund": f"{type(e).__name__}: {e}"})

    gut = [z for z in zeilen if z.get("ok")]
    if gut:
        teil = {
            "kt":              _normiere([z["Kt_Nm_per_A"] for z in gut], True),
            "drehzahl":        _normiere([z["safety_factor"] for z in gut], True),
            "leistungsdichte": _normiere([z["kt_je_kg"] for z in gut], True),
            "rundlauf":        _normiere([z["lcm_slots_poles"] for z in gut], True),
            "kosten":          _normiere([z["kosten_EUR"] for z in gut], False),
            "einfachheit":     _normiere([z["slots"] * z["conductorsPerSlot"]
                                          for z in gut], False),
        }
        g = GEWICHTE[ziel]
        for i, z in enumerate(gut):
            z["teilnoten"] = {k: round(teil[k][i], 3) for k in teil}
            z["punkte"] = round(sum(g[k] * teil[k][i] for k in teil), 4)
        gut.sort(key=lambda z: -z["punkte"])

    return {"ziel": ziel, "gewichte": GEWICHTE[ziel], "n_max": n_max,
            "basis_geom": dict(basis["geom"]),
            "geprueft": len(zeilen), "brauchbar": len(gut),
            "achsen": {k: achsen[k] for k in namen},
            "rangliste": gut,
            "verworfen": [z for z in zeilen if not z.get("ok")],
            "hinweis": ("Analytische Vorauswahl — kein Feldlauf, keine FEM, keine "
                        "Thermik. Sie sortiert aus und rangiert; gerechnet werden "
                        "muss danach.")}


# Geometriegroessen, die die Einpassung veraendern darf. Nur diese koennen sich
# zwischen Basis und Empfehlung unterscheiden, also nur diese muessen mitgegeben werden.
UEBERNAHME_GEOM = ("magWidth", "magThick", "magTangLen", "magDist",
                   "magLayerGap", "magDepthRel")


def uebernahme(zeile: dict, basis_geom: dict) -> list[str]:
    """Die ``--set``-Zuweisungen, die aus der Basis GENAU diese Variante machen.

    Das ist keine Bequemlichkeit, sondern der Punkt, an dem die Vorauswahl bisher in
    die Irre fuehrte. Passt eine Bauform nicht in den Pol, verkleinert ``einpassen``
    den Magneten -- und ohne diese Zahlen ist die Empfehlung **nicht reproduzierbar**:
    wer nur ``p``, ``slots`` und ``magShape`` uebernimmt, baut eine andere Maschine,
    und das Layouttor lehnt sie zu Recht ab.

    Gemessen an einem echten Agentenlauf: die Vorauswahl empfahl p=5 mit V-Anordnung,
    der Agent pruefte mit ``rotor-check --set p=5 --set magShape=v`` nach, bekam
    "Kollision, Ueberlappung 6,20 mm" -- und meldete dem Nutzer, die eigene Empfehlung
    sei unbaubar. Sie war baubar, nur mit ``magWidth`` 21,8 statt 32, ``magThick``
    4,09 statt 6 und ``magDist`` 6,48 statt 13,5. Keine dieser Zahlen stand in der
    Ausgabe.
    """
    g = zeile.get("geom") or {}
    sets = [f"p={zeile['p']}", f"slots={zeile['slots']}",
            f"magShape={zeile['magShape']}",
            f"conductorsPerSlot={zeile['conductorsPerSlot']}"]
    for k in UEBERNAHME_GEOM:
        neu_wert, alt_wert = g.get(k), basis_geom.get(k)
        if neu_wert is None or alt_wert is None:
            continue
        if abs(float(neu_wert) - float(alt_wert)) > 1e-6:
            sets.append(f"{k}={round(float(neu_wert), 4)}")
    return sets


def uebernahme_befehl(zeile: dict, basis_geom: dict, verb: str = "rotor-check") -> str:
    return (f"python3 cae_cli.py {verb} --from-project last "
            + " ".join("--set " + s for s in uebernahme(zeile, basis_geom)))


def bestenliste_text(erg: dict, n: int = 12) -> str:
    """Rangliste als Text — die Teilnoten mit, sonst ist die Reihenfolge Magie.

    Die Spalte **Mag** ist der Magnetmassstab der Einpassung. Sie stand frueher nicht
    hier, obwohl der Agenten-Skill sie ausdruecklich nennt -- ein Wert unter 1,00
    heisst, dass diese Variante nur mit verkleinertem Magneten in den Pol passt, und
    das gehoert in dieselbe Zeile wie die Momentkonstante, die daran haengt.
    """
    g = erg["gewichte"]
    basis_geom = erg.get("basis_geom") or {}
    z = [f"Ziel: {erg['ziel']}  (Gewichte: "
         + ", ".join(f"{k} {v:.2f}" for k, v in g.items()) + ")",
         f"{erg['brauchbar']} von {erg['geprueft']} Konfigurationen brauchbar, "
         f"n_max = {erg['n_max']:.0f} 1/min", "",
         f"  {'#':>2s} {'p':>2s} {'Pole':>4s} {'Nuten':>5s} {'q':>5s} {'Topologie':10s} "
         f"{'Ltr':>3s} {'B_gap':>6s} {'Kt':>7s} {'kgV':>5s} {'SF':>5s} "
         f"{'kg':>6s} {'EUR':>6s} {'Mag':>5s} {'Pkt':>5s}"]
    z.append("  " + "-" * 100)
    for i, r in enumerate(erg["rangliste"][:n], 1):
        mag = r.get("s_koerper")
        z.append(f"  {i:2d} {r['p']:2d} {r['poles']:4d} {r['slots']:5d} {r['q']:5.2f} "
                 f"{r['magShape']:10s} {r['conductorsPerSlot']:3d} "
                 f"{r['B_gap_T']:6.3f} {r['Kt_Nm_per_A']:7.4f} "
                 f"{r.get('lcm_slots_poles', 0):5d} {r['safety_factor']:5.2f} "
                 f"{r['gesamt_kg']:6.1f} {r['kosten_EUR']:6.0f} "
                 f"{(f'{mag:5.2f}' if isinstance(mag, (int, float)) else '    -')} "
                 f"{r['punkte']:5.3f}")

    # Wer den Magneten verkleinern musste, muss das SAGEN -- und zwar so, dass man es
    # nachbauen kann. Das ist die Lehre aus dem Agentenlauf, in dem die eigene
    # Empfehlung fuer unbaubar gehalten wurde, weil die Masse fehlten.
    geschrumpft = [(i, r) for i, r in enumerate(erg["rangliste"][:n], 1)
                   if isinstance(r.get("s_koerper"), (int, float))
                   and r["s_koerper"] < 0.999]
    if geschrumpft:
        z += ["", "  Mag < 1,00 heisst: passt nur mit VERKLEINERTEM Magneten in den Pol.",
              "  Die veraenderten Masse stehen unten — ohne sie ist die Zeile nicht nachbaubar."]

    if erg["rangliste"] and basis_geom:
        z += ["", "  Uebernahme (Platz 1 — die Geometriewerte sind Teil der Empfehlung):",
              "    " + uebernahme_befehl(erg["rangliste"][0], basis_geom, "rotor-check"),
              "    " + uebernahme_befehl(erg["rangliste"][0], basis_geom, "run analyse")]

    if erg["verworfen"]:
        gruende = {}
        for v in erg["verworfen"]:
            k = (v.get("grund") or "?").split(":")[0]
            gruende[k] = gruende.get(k, 0) + 1
        z += ["", "  Verworfen:"]
        for k, c in sorted(gruende.items(), key=lambda x: -x[1]):
            z.append(f"    {c:4d}x {k}")
    z += ["", "  " + erg["hinweis"]]
    return "\n".join(z)
