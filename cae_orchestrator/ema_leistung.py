"""Leistungsermittlung -- was diese Geometrie hergibt, und WAS sie begrenzt.

Die Frage ist die umgekehrte zu der, die dieses Werkzeug bisher beantwortet hat.
``run_pipeline`` bekommt eine Last und rechnet aus, was dabei herauskommt;
``ema_sicherheit`` sagt hinterher, ob das zulaessig war. Beides zusammen
beantwortet **nicht**, was jemand vor dem Auslegen wissen will: *wieviel geht
ueberhaupt, und was haelt mich auf?*

Gebaut wird dafuer nichts Neues gerechnet -- die Bausteine liegen alle da:

* ``ema_analysis.power_envelope``  -- die **elektrische** Huellkurve (Strom- und
  Spannungsgrenze auf einem (I_s, beta)-Raster). Sie bleibt die eine Quelle
  dafuer; dieses Modul rechnet sie nicht nach, es ruft sie.
* ``ema_optimize._eval_geom``      -- der schnelle Bewerter (Feld, Kt, stationaere
  Thermik, analytischer Festigkeits-Sweep), gemessen **0,01--0,09 s** je Aufruf,
  weil der LU-Cache die Faktorisierung ueber alle Lasten haelt: das ``mu`` haengt
  an der Geometrie, nicht am Strom. Eine Bisektion kostet damit Bruchteile einer
  Sekunde statt eines Pipelinelaufs.
* ``ema_sicherheit``               -- die Grenzwerte. Sie werden hier **nicht neu
  aufgeschrieben**, sondern von dort gelesen; zwei Listen mit Grenztemperaturen
  waeren die Stelle, an der eine Auslegung nach der einen zulaessig und nach der
  anderen unzulaessig ist.

**Der Ausnutzungsgrad ist der eigentliche Ertrag.** Jedes Kriterium in
``ema_sicherheit`` fuehrt seit jeher ``wert`` UND ``grenze`` mit; geteilt hat sie
nie jemand. Eine Grenze bei 40 % ist verschenktes Material, und das ist die
Angabe, aus der eine Auslegungsentscheidung folgt -- nicht das bestandene Ja.

Was dieses Modul NICHT sieht, steht in ``UNGEPRUEFT`` und wird bei **jeder**
Ausgabe mitgedruckt. Der wichtigste Posten darin ist die **Saettigung**: der FDM
ist linear (``MU_R_IRON = 500``), ``_analytical_Bgap`` hat keinen Eisenterm, und
``B_SAT_IRON`` wirkt ausschliesslich im Anzeigepfad (``_saturate_field``). Das
Moment waechst hier also linear mit dem Strom weiter, als gaebe es kein Eisen.
Wer darauf einen Optimierer setzt, der "alle Punkte ausreizt", laeuft genau in
diese Luecke -- derselbe Fehler wie das fehlende Layouttor im Bewerter
(``BEFUNDE.md``, 13.09.2026): die Zielgroesse belohnte das Unbaubare, und nichts
widersprach. Deshalb steht die Luecke hier im Ergebnis und nicht in einer
Fussnote.
"""

from __future__ import annotations

import math

import ema_sicherheit


# ── was der schnelle Pfad nicht sieht ────────────────────────────────────────
#
# Jeder Posten nennt die Groesse, den Grund und was ihn schliessen wuerde. Eine
# Liste "ungeprueft" ohne den Weg dorthin ist eine Ausrede.
UNGEPRUEFT = (
    {"groesse": "Saettigung im ROTOR und die oertliche Ueberhoehung",
     "grund":   "gerechnet wird Zahn und Joch ueber die Flusserhaltung; die "
                "duennen Rotorstege ueber den Magnettaschen und die Spitze am "
                "Zahnfuss kennt sie nicht, und |B| aus dem Feldbild ist dort "
                "nicht konvergent (56...73 % Streuung ueber N = 300...800)",
     "weg":     "ema_em2d_harm saettigt den Rotorsteg messend; fuer den Zahnfuss "
                "braeuchte es ein koerperangepasstes Netz"},
    {"groesse": "Nut- und Zahnkopfstreuung",
     "grund":   "die Flusserhaltung schickt den ganzen Polfluss durch Zahn und "
                "Joch; in Wirklichkeit geht ein Teil als Streufluss daran vorbei "
                "-- die Rechnung ist damit konservativ",
     "weg":     "ein Feldlauf mit aufgeloester Nutoeffnung"},
    {"groesse": "Festigkeit (FEM)",
     "grund":   "max_safe_rpm kommt hier aus dem analytischen Lame-Sweep; die "
                "Spannungsspitzen an den Stegen ueber den Magnettaschen kennt "
                "erst die Struktur-FEM",
     "weg":     "ein Pipelinelauf, danach summary.safety_factor_fem"},
    {"groesse": "Welle und Nabenverbindung",
     "grund":   "connection_assessment laeuft im schnellen Bewerter nicht mit",
     "weg":     "cae_cli.py welle / struktur"},
    {"groesse": "Rastmoment",
     "grund":   "analytisch nach Zhu/Howe; Ordnung und Schraegungsfaktor sind "
                "exakt, die AMPLITUDE ist auf Faktor ~2 geschaetzt",
     "weg":     "koerperangepasstes Netz -- im Raster-FDM nicht konvergent"},
)


# ── die Grenzen, die mit der LAST wachsen ────────────────────────────────────
#
# Nur diese taugen als Abbruchbedingung einer Bisektion ueber das Moment.
# ``max_safe_rpm`` und ``baubar`` haengen an der Geometrie und nicht an der Last;
# sie sind Tore ueber der Drehzahl und werden getrennt behandelt -- eine Groesse,
# die sich waehrend der Suche nicht bewegt, in die Suche zu stecken, hiesse
# entweder alles oder nichts zu verwerfen.
LASTGRENZEN = (
    {"name": "magnet_dauer",   "metrik": "T_magnet",  "einheit": "°C",
     "quelle": "thermal.steady (LPTN)"},
    {"name": "wicklung_dauer", "metrik": "T_winding", "einheit": "°C",
     "quelle": "thermal.steady (LPTN)"},
    # Seit 13.09.2026 die vierte Grenze -- und die einzige, die vorher GAR NICHT
    # gerechnet wurde. Gemessen wird sie ueber die Flusserhaltung
    # (``ema_saettigung``) und nicht aus dem Feldbild: |B| im Statoreisen ist bei
    # den hier benutzten Aufloesungen nicht konvergent (56...73 % Streuung ueber
    # N = 300...800), waehrend ``B_gap`` ausdruecklich aufloesungsunabhaengig ist.
    {"name": "saettigung",     "metrik": "B_eisen",   "einheit": "T",
     "quelle": "Flusserhaltung aus B_gap (ema_saettigung)"},
)

# Bisektion: so fein, dass die Ausnutzung auf ein Promille steht -- feiner ist
# bei einem stationaeren LPTN-Modell Zahlenkosmetik.
TOLERANZ_NM = 0.05
MAX_SCHRITTE = 40


def grenzwerte(payload: dict) -> dict:
    """Die Grenzen dieser Auslegung -- gelesen aus ``ema_sicherheit``.

    Der Magnetwert haengt am Werkstoff (N35: 80 °C, Ferrit: 250 °C) und kommt
    deshalb aus der Werkstofftabelle, nicht aus einer Konstanten hier.
    """
    payload = payload or {}
    t_mag, mag_label = ema_sicherheit._magnetgrenze(payload.get("magnet") or "")
    import ema_saettigung
    b_sat, blech = ema_saettigung._blech_bsat(payload.get("stator_lam")
                                              or "m270_35a")
    return {
        "magnet_dauer":   {"grenze": float(t_mag), "label": mag_label},
        "wicklung_dauer": {"grenze": float(ema_sicherheit.ISOLIERKLASSE_C),
                           "label": "Isolierklasse H"},
        "saettigung":     {"grenze": float(b_sat), "label": blech},
        "festigkeit":     {"grenze": float(ema_sicherheit.SF_ZIEL),
                           "label": "geforderter Sicherheitsfaktor"},
    }


def ausnutzung(metriken: dict, grenzen: dict) -> list:
    """Wert/Grenze je Lastkriterium -- >1 heisst verletzt.

    Die Richtung ist hier fuer alle Posten dieselbe (kleiner ist besser); wo das
    nicht gilt -- Festigkeit, Drehzahlreserve -- wird der Kehrwert gebildet, und
    zwar dort, wo die Groesse herkommt, nicht hier.
    """
    aus = []
    for g in LASTGRENZEN:
        wert = metriken.get(g["metrik"])
        lim = (grenzen.get(g["name"]) or {}).get("grenze")
        if wert is None or not lim:
            aus.append({**g, "wert": None, "grenze": lim, "quotient": None})
            continue
        aus.append({**g, "wert": float(wert), "grenze": float(lim),
                    "quotient": float(wert) / float(lim)})
    return aus


def _schlimmster(aus: list) -> tuple:
    """(groesster Quotient, Name) -- ``(None, "")`` wenn nichts bewertbar ist."""
    kand = [(a["quotient"], a["name"]) for a in aus if a["quotient"] is not None]
    return max(kand) if kand else (None, "")


def hoechstlast(bewerte, grenzen: dict, t_obergrenze: float) -> dict:
    """Groesstes Moment, bei dem keine Lastgrenze ueber 100 % geht.

    ``bewerte(T) -> metriken`` ist die einzige Verbindung nach draussen; damit
    laesst sich diese Funktion ohne Loeser pruefen.

    Drei Ausgaenge, und der erste ist der interessante: reisst schon die
    **kleinste** Last, liegt es nicht am Moment. Die drehzahlabhaengigen
    Eisen- und Magnetverluste allein ueberschreiten dann die Grenze, und
    "0 Nm moeglich" waere als Zahl richtig und als Auskunft nutzlos -- es gibt
    bei dieser Drehzahl keinen zulaessigen Betrieb, auch nicht im Leerlauf.
    """
    t_lo = 0.0
    m0 = bewerte(TOLERANZ_NM)
    if "error" in (m0 or {}):
        return {"ok": False, "T_Nm": None, "grund": m0.get("error"),
                "bindend": "", "ausnutzung": []}
    a0 = ausnutzung(m0, grenzen)
    q0, n0 = _schlimmster(a0)
    if q0 is not None and q0 > 1.0:
        return {"ok": False, "T_Nm": None, "bindend": n0, "ausnutzung": a0,
                "leerlauf_reisst": True,
                "grund": (f"schon im Leerlauf verletzt: {n0} bei "
                          f"{q0 * 100:.0f} % -- es binden die drehzahlabhaengigen "
                          f"Verluste, nicht das Moment")}

    # Obergrenze suchen: verdoppeln, bis eine Grenze reisst. Die elektrische
    # Huellkurve deckelt mit; ist sie ueberall zulaessig, ist SIE das Ergebnis
    # und nicht die Thermik.
    t_hi = min(max(TOLERANZ_NM * 2, 1.0), t_obergrenze)
    letzte, bindend = a0, ""
    for _ in range(MAX_SCHRITTE):
        m = bewerte(t_hi)
        a = ausnutzung(m, grenzen)
        q, nm = _schlimmster(a)
        if q is not None and q > 1.0:
            bindend = nm
            break
        letzte, t_lo = a, t_hi
        if t_hi >= t_obergrenze - 1e-9:
            return {"ok": True, "T_Nm": t_obergrenze, "bindend": "umrichter",
                    "ausnutzung": letzte,
                    "grund": "die elektrische Huellkurve bindet, nicht die Thermik"}
        t_hi = min(t_hi * 2.0, t_obergrenze)
    else:
        return {"ok": True, "T_Nm": t_lo, "bindend": "",
                "ausnutzung": letzte, "grund": "keine Grenze erreicht"}

    # Bisektion zwischen der letzten zulaessigen und der ersten verletzten Last
    for _ in range(MAX_SCHRITTE):
        if t_hi - t_lo <= TOLERANZ_NM:
            break
        t_m = 0.5 * (t_lo + t_hi)
        a = ausnutzung(bewerte(t_m), grenzen)
        q, nm = _schlimmster(a)
        if q is not None and q > 1.0:
            t_hi, bindend = t_m, nm
        else:
            t_lo, letzte = t_m, a
    return {"ok": t_lo > TOLERANZ_NM, "T_Nm": t_lo, "bindend": bindend,
            "ausnutzung": letzte, "grund": ""}


# ── die Kennlinie ueber der Drehzahl ─────────────────────────────────────────

def _bausteine(payload: dict):
    """geom/axial/mats/cooling/T_amb -- gebaut wie in ``ema_optimize.optimize``.

    Bewusst von dort geholt und nicht noch einmal aus dem Payload gelesen: die
    Werkstoffzuordnung (``rotor_lam`` -> ``LAMINATES``) ist genau die Sorte
    Abschrift, die auseinanderlaeuft, sobald ein Werkstoff dazukommt.
    """
    import ema_optimize
    geom = payload["geom"]
    axial = float(payload.get("axial_len", geom.get("axialLen", 80)))
    return (geom, axial, ema_optimize._materials(payload),
            payload.get("cooling", "water"), float(payload.get("T_ambient", 25)))


def kennlinie(payload: dict, rpms=None, N: int = 140, melde=None) -> dict:
    """Was diese Geometrie ueber der Drehzahl hergibt -- und was jeweils bindet.

    Drei Schichten, jede aus ihrer eigenen Quelle:

    1. **Tore der Geometrie** -- ``baubar`` (Layouttor) und ``max_safe_rpm``
       (analytischer Festigkeits-Sweep). Beide haengen nicht an der Last; eine
       Drehzahl darueber ist gar nicht erst zulaessig.
    2. **Elektrische Huellkurve** -- ``ema_analysis.power_envelope``, unveraendert
       gerufen. Sie deckelt das Moment ueber Strom- und Spannungsgrenze.
    3. **Thermische Grenzen** -- Bisektion ueber das Moment gegen Magnet- und
       Wicklungstemperatur aus dem stationaeren LPTN.

    Das zulaessige Moment ist das **Minimum** aus 2 und 3, und der Befund sagt,
    welche der beiden es war.
    """
    import ema_analysis
    import ema_optimize
    import ema_thermal

    def _sag(msg, pct=None):
        if melde:
            melde(msg, pct)

    geom, axial, mats, cooling, T_amb = _bausteine(payload)
    grenzen = grenzwerte(payload)
    rpm_to = float(payload.get("rpm_to", 20000) or 20000)
    rpm_base = float(payload.get("rpm_from", 5000) or 5000)
    sweep = [round(rpm_to * f) for f in (0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0)]

    # ── 1. Tore ──────────────────────────────────────────────────────────────
    _sag("Tore der Geometrie", 5)
    op0 = {"rpm_thermal": rpm_to, "rpm_base": rpm_base, "load_nm": TOLERANZ_NM}
    m0 = ema_optimize._eval_geom(geom, axial, mats, op0, cooling, T_amb, sweep, N=N)
    if "error" in m0:
        return {"error": m0["error"]}
    # Zwei Tore, und sie meinen Verschiedenes: `stimmig` fragt, ob die RADIEN
    # ueberhaupt ineinander passen (das, was `_clamp` parameterweise nicht sehen
    # kann), `baubar` fragt das Magnet-Layout. Ein Kandidat, der am ersten
    # scheitert, hat gar keine Geometrie, ueber die sich das zweite aeussern
    # koennte -- deshalb in dieser Reihenfolge.
    if m0.get("stimmig") is False:
        return {"error": "Geometrie nicht stimmig: "
                         + str(m0.get("stimmig_grund") or "Radien passen nicht"),
                "stimmig": False}
    if m0.get("baubar") is False:
        return {"error": "nicht baubar: " + str(m0.get("baubar_grund") or
                                                 "Layouttor verletzt"),
                "baubar": False}
    n_sicher = float(m0.get("max_safe_rpm") or 0.0)

    if rpms is None:
        # Bis zur sicheren Drehzahl, nicht bis zur gewuenschten: eine Leistung
        # oberhalb davon zu buchen hiesse, sie einem Rotor zuzuschreiben, der
        # sich dort nicht drehen darf.
        obergrenze = min(rpm_to, n_sicher) if n_sicher > 0 else rpm_to
        rpms = [round(obergrenze * f) for f in
                (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)]
    rpms = [float(r) for r in rpms if r > 0]

    # ── 2. elektrische Huellkurve ────────────────────────────────────────────
    _sag("elektrische Huellkurve", 20)
    elektrisch, e_fehler = None, ""
    try:
        em = ema_analysis.run_em_analysis(geom, N=N, rotor_angle=0.0, axial_mm=axial)
        perf = em["performance"]
        adv = ema_analysis.compute_advanced_em(
            geom, perf, axial, rpm_base, max(rpms), float(payload.get("load_nm", 5)),
            mag=mats[3])
        t_rated = ema_thermal.rated_torque(geom, axial, cooling)
        elektrisch = ema_analysis.power_envelope(
            geom, adv, rpm_max=max(rpms), T_rated_Nm=t_rated)
        if "error" in elektrisch:
            e_fehler, elektrisch = elektrisch["error"], None
    except Exception as exc:                                    # noqa: BLE001
        e_fehler = f"{type(exc).__name__}: {exc}"

    def _t_elektrisch(rpm: float) -> float:
        """Spitzenmoment der elektrischen Huellkurve bei dieser Drehzahl."""
        if not elektrisch:
            # Ohne Huellkurve kein Deckel -- aber auch keine stille Unendlichkeit:
            # das Zehnfache des Dauermoments ist eine Schranke, die die Suche
            # beendet, und dass sie kuenstlich ist, steht im Ergebnis.
            return 10.0 * ema_thermal.rated_torque(geom, axial, cooling)
        xs, ys = elektrisch["rpm"], elektrisch["T_peak_Nm"]
        if rpm <= xs[0]:
            return float(ys[0])
        for i in range(1, len(xs)):
            if rpm <= xs[i]:
                f = (rpm - xs[i - 1]) / max(xs[i] - xs[i - 1], 1e-9)
                return float(ys[i - 1] + f * (ys[i] - ys[i - 1]))
        return float(ys[-1])

    # ── 3. thermische Grenze je Drehzahl ─────────────────────────────────────
    punkte = []
    for i, rpm in enumerate(rpms):
        _sag(f"{rpm:.0f} 1/min", 25 + int(70 * i / max(len(rpms), 1)))
        t_el = _t_elektrisch(rpm)

        def bewerte(T, _rpm=rpm):
            op = {"rpm_thermal": _rpm, "rpm_base": rpm_base, "load_nm": float(T)}
            return ema_optimize._eval_geom(geom, axial, mats, op, cooling,
                                           T_amb, sweep, N=N)

        erg = hoechstlast(bewerte, grenzen, t_el)
        T = erg.get("T_Nm")
        P = (T * 2.0 * math.pi * rpm / 60.0 / 1000.0) if T else 0.0
        punkte.append({
            "rpm": rpm, "T_Nm": (round(T, 1) if T else None),
            "P_kW": round(P, 2),
            "T_elektrisch_Nm": round(t_el, 1),
            "bindend": erg.get("bindend") or ("umrichter" if T and
                                              abs(T - t_el) < 2 * TOLERANZ_NM else ""),
            "moeglich": bool(erg.get("ok")),
            "grund": erg.get("grund") or "",
            "ausnutzung": erg.get("ausnutzung") or [],
        })

    gut = [p for p in punkte if p["moeglich"] and p["P_kW"] > 0]
    best = max(gut, key=lambda p: p["P_kW"]) if gut else None

    # ── Gegenprobe gegen die zweite Dauermoment-Aussage des Werkzeugs ────────
    #
    # ``ema_thermal.rated_torque`` ist eine BEMESSUNGSformel (2*sigma*V_rotor mit
    # sigma aus dem Kuehlungs-Preset) und traegt im Kennfeld die Kurve "Dauer";
    # ``power_envelope`` setzt darauf sogar ``cont_limited_by: "kuehlung"``. Das
    # ist eine Aussage ueber die Kuehlung -- gerechnet hat sie das LPTN-Netz aber
    # nie. Gemessen am 13.09.2026 an einer 305-mm-Maschine (forced): 122,6 Nm
    # laut Bemessung, und dieselbe Kette meldet bei genau diesem Moment
    # **277,6 °C** am Magneten gegen 80 °C Grenze (s. BEFUNDE.md).
    #
    # Aufgeloest wird das hier NICHT -- welche der beiden Seiten daneben liegt,
    # ist eine Frage an die Thermik und nicht an dieses Modul. Verschwiegen wird
    # es aber auch nicht: wer 13,9 kW neben den 223,4 kW aus derselben
    # results.json liest, muss erfahren, dass die Zahlen aus zwei Modellen
    # stammen, die einander widersprechen.
    widerspruch = None
    try:
        t_rated = ema_thermal.rated_torque(geom, axial, cooling)
        rpm_pr = (best["rpm"] if best else (rpms[len(rpms) // 2] if rpms else 0.0))
        if rpm_pr > 0:
            op_pr = {"rpm_thermal": rpm_pr, "rpm_base": rpm_base, "load_nm": t_rated}
            m_pr = ema_optimize._eval_geom(geom, axial, mats, op_pr, cooling,
                                           T_amb, sweep, N=N)
            a_pr = ausnutzung(m_pr, grenzen)
            q_pr, n_pr = _schlimmster(a_pr)
            if q_pr is not None and q_pr > 1.05:
                widerspruch = {
                    "T_rated_Nm": round(float(t_rated), 1),
                    "rpm": rpm_pr, "bindend": n_pr,
                    "ausnutzung": round(q_pr, 3),
                    "ausnutzung_liste": a_pr,
                    "text": (f"ema_thermal.rated_torque nennt {t_rated:.1f} Nm als "
                             f"DAUERmoment (daran haengt die Kurve 'Dauer' im "
                             f"Kennfeld und cont_limited_by='kuehlung'). Dasselbe "
                             f"LPTN-Netz meldet bei diesem Moment und "
                             f"{rpm_pr:.0f} 1/min {n_pr} bei {q_pr * 100:.0f} %. "
                             f"Die beiden Aussagen sind unvereinbar -- s. "
                             f"BEFUNDE.md, 13.09.2026."),
                }
    except Exception:                                            # noqa: BLE001
        widerspruch = None

    return {
        "punkte": punkte,
        "P_max_kW": (best["P_kW"] if best else 0.0),
        "P_max_rpm": (best["rpm"] if best else None),
        "P_max_bindend": (best["bindend"] if best else ""),
        "n_sicher_1_min": n_sicher,
        "rpm_gewuenscht": rpm_to,
        "grenzen": grenzen,
        "elektrisch": elektrisch,
        "elektrisch_fehler": e_fehler,
        "widerspruch": widerspruch,
        "ungeprueft": list(UNGEPRUEFT),
        "modell": {"N": N, "pfad": "schneller Bewerter (kein FreeCAD, keine FEM)"},
    }


def _umbrechen(text: str, breite: int) -> list:
    """Umbrechen statt abschneiden -- ein gekappter Befund ist kein Befund."""
    worte, zeilen, z = str(text).split(), [], ""
    for wort in worte:
        if z and len(z) + 1 + len(wort) > breite:
            zeilen.append(z)
            z = wort
        else:
            z = (z + " " + wort).strip()
    if z:
        zeilen.append(z)
    return zeilen


def als_text(erg: dict) -> str:
    """Menschenlesbar -- und die ungeprueften Groessen stehen IMMER darunter."""
    if erg.get("error"):
        return "Leistungsermittlung nicht moeglich: " + str(erg["error"])
    z = []
    a = z.append
    P, rpm = erg.get("P_max_kW") or 0.0, erg.get("P_max_rpm")
    if P > 0:
        a(f"Hoechste Dauerleistung: {P:.1f} kW bei {rpm:.0f} 1/min "
          f"(bindend: {erg.get('P_max_bindend') or 'keine Grenze erreicht'})")
    else:
        a("Kein zulaessiger Betriebspunkt gefunden -- bei JEDER geprueften "
          "Drehzahl reisst eine Grenze schon im Leerlauf.")
    ns, rw = erg.get("n_sicher_1_min") or 0, erg.get("rpm_gewuenscht") or 0
    if ns and rw and ns < rw:
        a(f"Hinweis: sichere Drehzahl {ns:.0f} < gewuenschte {rw:.0f} 1/min -- "
          f"oberhalb wurde nichts gerechnet.")
    if erg.get("elektrisch_fehler"):
        a(f"Hinweis: elektrische Huellkurve nicht verfuegbar "
          f"({erg['elektrisch_fehler']}) -- der Momentendeckel ist behelfsmaessig.")

    if (erg.get("P_max_bindend") or "") == "saettigung":
        a("")
        for zeile in _umbrechen(
                "Hinweis: bindend ist die SAETTIGUNG. Das ist keine Wand, an der "
                "die Maschine stehenbleibt -- sie laeuft weiter, liefert aber "
                "weniger Moment als hier gerechnet, weil das lineare Modell dem "
                "Eisen mehr abverlangt als es hergibt. Oberhalb dieses Punktes "
                "sind Kt, Moment und Leistung zu optimistisch.", 76):
            a("  " + zeile)

    w = erg.get("widerspruch")
    if w:
        a("")
        a("⚠ WIDERSPRUCH im Werkzeug (nicht in dieser Auslegung):")
        for zeile in _umbrechen(w["text"], 76):
            a("  " + zeile)

    a("")
    a(f"{'Drehzahl':>10} {'T_zul':>9} {'P':>8} {'T_elektr':>9}  bindend")
    a("-" * 62)
    for p in erg.get("punkte", []):
        t = f"{p['T_Nm']:9.1f}" if p["T_Nm"] else f"{'--':>9}"
        a(f"{p['rpm']:10.0f} {t} {p['P_kW']:7.1f}kW {p['T_elektrisch_Nm']:9.1f}  "
          f"{p['bindend'] or '-'}")
        if not p["moeglich"] and p.get("grund"):
            a(f"{'':>10} └─ {p['grund']}")

    best = next((p for p in erg.get("punkte", [])
                 if p["rpm"] == erg.get("P_max_rpm")), None)
    if best and best.get("ausnutzung"):
        a("")
        a(f"Ausnutzung im besten Punkt ({best['rpm']:.0f} 1/min) -- eine Grenze "
          f"weit unter 100 % ist verschenktes Material:")
        for x in best["ausnutzung"]:
            if x.get("quotient") is None:
                continue
            # Nachkommastellen nach der EINHEIT: 1,70 T ist eine Aussage,
            # "2 T" waere eine andere. Grad werden ganzzahlig gelesen.
            nk = 2 if x["einheit"] == "T" else 0
            a(f"  {x['name']:<16} {x['wert']:7.{nk}f} / {x['grenze']:.{nk}f} "
              f"{x['einheit']:<3} = {x['quotient'] * 100:5.1f} %")

    a("")
    a("NICHT geprueft (der schnelle Pfad sieht es nicht):")
    for u in erg.get("ungeprueft", []):
        a(f"  • {u['groesse']}: {u['grund']}")
        a(f"    -> {u['weg']}")
    return "\n".join(z)
