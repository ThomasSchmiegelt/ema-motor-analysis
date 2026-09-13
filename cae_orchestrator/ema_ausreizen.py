"""Ausreizen -- die Auslegung ins Gleichgewicht bringen.

Der Wunsch war: *ein Optimierer, der alle Punkte ausreizt*. Die Grenzen liegen
seit ``ema_leistung`` samt Ausnutzungsgrad vor, und die Saettigung wird seit
``ema_saettigung`` mitgerechnet -- ohne sie liefe eine Suche in eine Luecke, in
der das Moment linear mit dem Strom weiterwaechst, als gaebe es kein Eisen.

**Gleichgewicht ist aber kein Ziel, sondern ein Symptom, und diese
Unterscheidung traegt das ganze Modul.** Wer schlicht die LEISTUNG maximiert,
laesst jede nicht bindende Grenze liegen, wo sie ist: das Joch der gemessenen
Maschine steht bei 25 % seiner Saettigungsflussdichte, und es duenner zu machen
bringt kein einziges Watt -- die Suche hat also keinen Grund dazu, und heraus
kommt eine starke, schwere Maschine. Maximiert man dagegen die
**Leistungsdichte**, wird aus jeder brachliegenden Grenze *entfernbares
Material*, und das Gleichgewicht stellt sich von selbst ein. Ein kuenstlicher
Ausgleichsterm ("belohne Ausnutzung nahe 100 %") taete das Gegenteil: er koennte
eine SCHLECHTERE Maschine vorziehen, die zufaellig gleichmaessig ausgelastet ist.

Deshalb zwei Ziele und kein drittes:

``dichte``    P_max / Gesamtmasse [kW/kg] -- Vorgabe. Das Gleichgewicht faellt
              hier als Ergebnis an, nicht als Vorgabe.
``leistung``  P_max [kW] -- wenn der Bauraum feststeht und die Masse egal ist.

**Gesucht wird deterministisch** (Musterschritt ueber die freien Parameter,
Schrittweite halbiert sich, wenn eine Runde nichts findet). Kein Sprachmodell in
der Schleife: derselbe Payload ergibt denselben Entwurf, und welcher Parameter
welchen Gewinn gebracht hat, steht im Protokoll. ``ema_optimize.FREE_PARAMS``
und ``_clamp`` bleiben die eine Quelle der Grenzen und ``_apply_params`` der eine
Weg in die Geometrie -- eine zweite Parametertabelle waere die Stelle, an der
Zielwertsuche und Ausreizen verschiedene Maschinen bauen.

**Was am Ende wirklich interessiert, ist nicht der Gewinner, sondern was noch
brachliegt.** ``brachliegend()`` nimmt jede Grenze unter der Schwelle und MISST
je freiem Parameter, welcher sie am staerksten bewegt -- eine Empfehlung, die
aus einer Messung kommt und nicht aus einer Tabelle im Kopf des Verfassers.

Grenzen, ausdruecklich: gerechnet wird auf dem schnellen Bewerter (kein FreeCAD,
keine FEM), die Suche kennt also dieselben vier Grenzen wie ``ema_leistung`` und
dieselben Luecken -- Rotorstege, oertliche Ueberhoehung, FEM-Festigkeit, Welle.
Der Sieger ist ein **Vorschlag**, kein Ergebnis; nachgerechnet wird er mit einem
Pipelinelauf.
"""

from __future__ import annotations

import math

import ema_leistung
import ema_optimize

# Umbrechen statt abschneiden -- dieselbe Funktion wie in ema_leistung, nicht
# abgeschrieben: ein gekappter Befund ist kein Befund.
_umbrechen = ema_leistung._umbrechen

# Ziele. Mehr braucht es nicht, und ein drittes waere schon eines zu viel --
# s. Modulkopf.
ZIELE = {
    "dichte":   {"text": "Leistungsdichte P_max/Masse", "einheit": "kW/kg"},
    "leistung": {"text": "Hoechstleistung P_max",       "einheit": "kW"},
}
ZIEL_VORGABE = "dichte"

# Suchparameter. Der Startschritt ist bewusst gross (20 %): ein zu feiner
# Anfang bleibt im ersten flachen Stueck stehen, und das Halbieren holt die
# Feinheit ohnehin nach.
SCHRITT_START = 0.20
SCHRITT_ENDE = 0.01
BUDGET_VORGABE = 200

# Ab wann eine Grenze als ausgereizt gilt. Nicht 1,00: eine Grenze, die auf
# 0,5 % genau erreicht wird, ist im Rahmen dieses Modells dasselbe wie erreicht.
AUSGEREIZT_AB = 0.90


def startwerte(payload: dict, frei) -> dict:
    """Die aktuellen Werte der freien Parameter AUS dem Payload.

    Die Gegenrichtung zu ``ema_optimize._apply_params`` -- und sie muss dieselbe
    Tabelle lesen, sonst startet die Suche woanders, als der Payload steht.
    """
    geom = payload.get("geom") or {}
    axial = float(payload.get("axial_len") or geom.get("axialLen") or 80.0)
    aus = {}
    for k in frei:
        spec = ema_optimize.FREE_PARAMS.get(k)
        if not spec:
            continue
        if spec.get("special") == "axial":
            aus[k] = axial
        elif spec.get("special") == "airgap":
            aus[k] = max(0.05, (float(geom.get("statorID", 0.0))
                                - float(geom.get("rotorOD", 0.0))) / 2.0)
        else:
            v = geom.get(spec["geom"])
            if v is not None:
                aus[k] = spec["type"](v)
    return ema_optimize._clamp(aus)


def _payload_mit(payload: dict, params: dict) -> dict:
    """Ein Payload mit gesetzten Parametern -- ueber den EINEN Weg dorthin."""
    geom = payload.get("geom") or {}
    axial = float(payload.get("axial_len") or geom.get("axialLen") or 80.0)
    g2, a2 = ema_optimize._apply_params(geom, axial, ema_optimize._clamp(params))
    neu = dict(payload)
    neu["geom"] = g2
    neu["axial_len"] = a2
    return neu


def bewerten(payload: dict, params: dict, ziel: str = ZIEL_VORGABE,
             rpms=None, N: int = 110) -> dict:
    """EIN Kandidat: Leistung, Masse, Zielwert, Ausnutzung je Grenze.

    Gemessen kostet das 0,24...0,41 s -- die Kennlinie laeuft auf einem groben
    Drehzahlraster, weil die SUCHE nur eine Rangfolge braucht. Der Sieger wird
    danach auf dem feinen Raster nachgerechnet; wer beides gleich fein macht,
    zahlt den Faktor drei fuer eine Genauigkeit, die in der Rangfolge untergeht.
    """
    import ema_screen

    pl = _payload_mit(payload, params)
    try:
        erg = ema_leistung.kennlinie(pl, rpms=rpms, N=N)
    finally:
        # Die Faktorisierung NACH jedem Kandidaten wegwerfen. Innerhalb einer
        # Kennlinie traegt der LU-Cache alles (eine Geometrie, ein Rotorwinkel,
        # viele Lasten -- das ist der Grund, warum eine Bisektion hier 0,01 s je
        # Schritt kostet). ZWISCHEN Kandidaten ist er reine Verschwendung: jede
        # Geometrie kommt genau einmal vor, der Eintrag wird nie wieder
        # getroffen und bleibt trotzdem liegen. Gemessen wuchs ein Suchlauf so
        # auf 1,23 GB nach einer Minute und waere bis an den 6-GB-Deckel
        # (`_LU_CACHE_GB`) gelaufen -- auf einer 31-GiB-Maschine, auf der
        # daneben ein Server, ein Browser und womoeglich Ollama stehen. Dasselbe
        # `finally` fuehrt `run_pipeline` aus demselben Grund.
        try:
            import ema_analysis
            ema_analysis.clear_lu_cache()
        except Exception:                                        # noqa: BLE001
            pass
    if erg.get("error") or not erg.get("P_max_kW"):
        return {"ok": False, "ziel": -math.inf, "grund": erg.get("error") or
                "kein zulaessiger Betriebspunkt", "payload": pl, "kennlinie": erg}
    try:
        masse = float(ema_screen.massen_und_kosten(pl).get("gesamt_kg") or 0.0)
    except Exception:                                            # noqa: BLE001
        masse = 0.0
    P = float(erg["P_max_kW"])
    if ziel == "leistung":
        wert = P
    else:
        wert = (P / masse) if masse > 1e-6 else -math.inf
    best = next((q for q in erg.get("punkte", [])
                 if q["rpm"] == erg.get("P_max_rpm")), None)
    return {"ok": True, "ziel": wert, "P_kW": P, "masse_kg": round(masse, 2),
            "bindend": erg.get("P_max_bindend") or "",
            "rpm": erg.get("P_max_rpm"),
            "ausnutzung": (best or {}).get("ausnutzung") or [],
            "payload": pl, "kennlinie": erg}


def _groesse(start: dict, best: dict) -> dict:
    """Wie stark hat sich die MASCHINE veraendert -- nicht nur ihre Ausnutzung?

    Der Grund, aus dem das mitlaufen muss: die spezifische Leistung steigt, wenn
    Maschinen kleiner werden (die Kuehlflaeche waechst gegenueber dem Volumen).
    Eine Suche auf Leistungsdichte verkuerzt das Blechpaket deshalb, und der
    Gewinn ist dann zum Teil gar keine bessere Ausnutzung, sondern **eine andere
    Maschine**. Gemessen am ersten sauberen Lauf: +831 % Leistungsdichte, aber
    die Baulaenge fiel von 150 auf 39,3 mm und die Masse von 74,2 auf 20,5 kg.

    Beides ist ein zulaessiges Ergebnis -- aber wer es fuer "dieselbe Maschine,
    besser ausgelegt" haelt, liest es falsch. Also steht es da.
    """
    m0 = float(start.get("masse_kg") or 0.0)
    m1 = float(best.get("masse_kg") or 0.0)
    g0 = (start.get("payload") or {}).get("geom") or {}
    g1 = (best.get("payload") or {}).get("geom") or {}
    l0 = float(g0.get("axialLen") or 0.0)
    l1 = float(g1.get("axialLen") or 0.0)
    d_m = (m1 / m0 - 1.0) * 100.0 if m0 > 1e-9 else 0.0
    d_l = (l1 / l0 - 1.0) * 100.0 if l0 > 1e-9 else 0.0
    return {"masse_kg": [round(m0, 2), round(m1, 2)], "masse_pct": round(d_m, 1),
            "laenge_mm": [round(l0, 1), round(l1, 1)], "laenge_pct": round(d_l, 1),
            "wesentlich": bool(abs(d_m) > 5.0 or abs(d_l) > 5.0)}


def ausreizen(payload: dict, ziel: str = ZIEL_VORGABE, frei=None,
              budget: int = BUDGET_VORGABE, rpms=None, N: int = 110,
              melde=None) -> dict:
    """Musterschritt ueber die freien Parameter -- deterministisch.

    Kein Sprachmodell in der Schleife. Der Ablauf: je Parameter einen Schritt
    nach oben und einen nach unten probieren, die beste Verbesserung behalten,
    und wenn eine ganze Runde nichts bringt, die Schrittweite halbieren. Das
    findet kein globales Optimum und behauptet das auch nicht -- es findet den
    naechsten besseren Entwurf und sagt, welcher Griff ihn gebracht hat.
    """
    if ziel not in ZIELE:
        raise ValueError(f"Unbekanntes Ziel {ziel!r} -- bekannt: "
                         + ", ".join(ZIELE))
    frei = list(frei or ema_optimize.FREE_PARAMS.keys())
    unbekannt = [k for k in frei if k not in ema_optimize.FREE_PARAMS]
    if unbekannt:
        raise ValueError("Unbekannte Parameter: " + ", ".join(unbekannt))

    def sag(m, pct=None):
        if melde:
            melde(m, pct)

    x = startwerte(payload, frei)
    if not x:
        return {"error": "keiner der gewaehlten Parameter steht im Payload"}

    start = bewerten(payload, x, ziel, rpms, N)
    if not start["ok"]:
        return {"error": f"Der Ausgangsentwurf hat keinen zulaessigen "
                         f"Betriebspunkt: {start.get('grund')}",
                "start": start}
    best, n_eval, protokoll = dict(start), 1, []
    schritt = SCHRITT_START
    sag(f"Start: {start['ziel']:.4f} {ZIELE[ziel]['einheit']}", 2)

    while schritt >= SCHRITT_ENDE and n_eval < budget:
        verbessert = False
        for k in frei:
            if n_eval >= budget:
                break
            spec = ema_optimize.FREE_PARAMS[k]
            v0 = x.get(k)
            if v0 is None:
                continue
            # Ganzzahlige Parameter in ganzen Schritten -- 0,2 Polpaare gibt es
            # nicht, und ein Rundungsschritt von 0 laeuft in eine Endlosrunde.
            if spec["type"] is int:
                d = max(1, int(round(abs(v0) * schritt)))
                kand = [v0 + d, v0 - d]
            else:
                d = max(abs(v0) * schritt, (spec["hi"] - spec["lo"]) * 1e-3)
                kand = [v0 + d, v0 - d]
            for v in kand:
                if n_eval >= budget:
                    break
                if not (spec["lo"] - 1e-12 <= v <= spec["hi"] + 1e-12):
                    continue
                probe = dict(x, **{k: v})
                e = bewerten(payload, probe, ziel, rpms, N)
                n_eval += 1
                if e["ok"] and e["ziel"] > best["ziel"] * (1 + 1e-6):
                    protokoll.append({
                        "parameter": k, "von": round(float(v0), 4),
                        "nach": round(float(v), 4),
                        "ziel_vorher": round(best["ziel"], 5),
                        "ziel_nachher": round(e["ziel"], 5),
                        "bindend": e["bindend"]})
                    x, best, verbessert = probe, e, True
                    sag(f"{k}: {v0:.4g} -> {v:.4g}  "
                        f"{ZIELE[ziel]['einheit']} {e['ziel']:.4f}",
                        min(95, int(100 * n_eval / max(budget, 1))))
                    v0 = v
        if not verbessert:
            schritt *= 0.5
    return {"ziel": ziel, "ziel_text": ZIELE[ziel]["text"],
            "einheit": ZIELE[ziel]["einheit"],
            "groesse": _groesse(start, best),
            "start": start, "best": best, "params": x,
            "protokoll": protokoll, "auswertungen": n_eval,
            "frei": frei, "budget": budget}


def brachliegend(payload: dict, params: dict, ausnutzung, frei=None,
                 schwelle: float = AUSGEREIZT_AB, ziel: str = ZIEL_VORGABE,
                 rpms=None, N: int = 110, melde=None) -> dict:
    """Welche Grenze liegt brach -- und WELCHER Griff bewegt sie?

    Der eigentliche Ertrag des Ausreizens. Eine Grenze bei 25 % ist entfernbares
    Material, aber die Angabe nuetzt erst etwas, wenn danebensteht, an welcher
    Schraube man dreht.

    **Gemessen, nicht behauptet.** Jeder freie Parameter wird einmal nach oben
    und einmal nach unten gestoert, und dabei wird die VOLLE Ausnutzungsliste
    mitgeschrieben. So kosten alle Grenzen zusammen einen Durchgang (2 x Anzahl
    Parameter) statt einen je Grenze -- und die Empfehlung kommt aus derselben
    Rechenkette wie das Ergebnis, statt aus einer Faustregel im Kopf des
    Verfassers.

    Ausgegeben wird nur, was die Grenze wirklich **hebt** und die Zielgroesse
    dabei nicht ruiniert: ein Griff, der das Joch auslastet und die Leistung
    halbiert, ist kein Vorschlag.
    """
    frei = list(frei or ema_optimize.FREE_PARAMS.keys())
    offen = [a for a in (ausnutzung or [])
             if a.get("quotient") is not None and a["quotient"] < schwelle]
    if not offen:
        return {"offen": [], "hinweise": [], "auswertungen": 0}

    basis = {a["name"]: a["quotient"] for a in ausnutzung if a.get("quotient")}
    grund = bewerten(payload, params, ziel, rpms, N)
    wirkung, n = {}, 1
    for i, k in enumerate(frei):
        spec = ema_optimize.FREE_PARAMS[k]
        v0 = params.get(k)
        if v0 is None:
            continue
        d = (max(1, int(round(abs(v0) * 0.15))) if spec["type"] is int
             else max(abs(v0) * 0.15, (spec["hi"] - spec["lo"]) * 1e-2))
        for richtung, v in (("hoch", v0 + d), ("runter", v0 - d)):
            if not (spec["lo"] - 1e-12 <= v <= spec["hi"] + 1e-12):
                continue
            e = bewerten(payload, dict(params, **{k: v}), ziel, rpms, N)
            n += 1
            if melde:
                melde(f"Empfindlichkeit {k} {richtung}",
                      min(98, int(100 * (i + 1) / max(len(frei), 1))))
            if not e["ok"]:
                continue
            q = {a["name"]: a["quotient"] for a in e["ausnutzung"]
                 if a.get("quotient") is not None}
            for name, wert in q.items():
                delta = wert - basis.get(name, 0.0)
                cur = wirkung.get(name)
                if delta > 1e-4 and (cur is None or delta > cur["delta"]):
                    wirkung[name] = {
                        "parameter": k, "richtung": richtung,
                        "von": round(float(v0), 4), "nach": round(float(v), 4),
                        "delta": delta,
                        "ziel_danach": round(e["ziel"], 5),
                        "ziel_vorher": round(grund["ziel"], 5)}

    hinweise = []
    for a in offen:
        w = wirkung.get(a["name"])
        if not w:
            hinweise.append({"grenze": a["name"], "ausnutzung": a["quotient"],
                             "parameter": "", "text":
                             "keiner der freien Parameter hebt diese Grenze "
                             "messbar -- sie haengt an etwas, das hier nicht "
                             "frei ist (Bauraum, Werkstoff, Kuehlung)"})
            continue
        schadet = w["ziel_danach"] < w["ziel_vorher"] * 0.98
        hinweise.append({
            "grenze": a["name"], "ausnutzung": a["quotient"],
            "parameter": w["parameter"], "richtung": w["richtung"],
            "von": w["von"], "nach": w["nach"],
            "delta_pp": round(w["delta"] * 100, 1),
            "schadet": schadet,
            "text": (f"{w['parameter']} {w['richtung']} "
                     f"({w['von']:.4g} -> {w['nach']:.4g}) hebt sie um "
                     f"{w['delta'] * 100:.1f} Prozentpunkte"
                     + (" -- kostet aber Zielwert" if schadet else ""))})
    return {"offen": [a["name"] for a in offen], "hinweise": hinweise,
            "auswertungen": n}


def als_text(erg: dict, brach: dict | None = None) -> str:
    """Der Bericht -- und er nennt zuerst, was der Griff war."""
    if erg.get("error"):
        return "Ausreizen nicht moeglich: " + str(erg["error"])
    s, b = erg["start"], erg["best"]
    e = erg["einheit"]
    z = []
    a = z.append
    gewinn = ((b["ziel"] / s["ziel"] - 1.0) * 100.0
              if s["ziel"] > 0 else float("nan"))
    a(f"Ziel: {erg['ziel_text']}")
    a(f"  Start  {s['ziel']:8.4f} {e}   ({s['P_kW']:.1f} kW, "
      f"{s['masse_kg']:.1f} kg, bindend {s['bindend'] or '-'})")
    a(f"  Ende   {b['ziel']:8.4f} {e}   ({b['P_kW']:.1f} kW, "
      f"{b['masse_kg']:.1f} kg, bindend {b['bindend'] or '-'})"
      + (f"   {gewinn:+.1f} %" if gewinn == gewinn else ""))
    a(f"  {erg['auswertungen']} Auswertungen, {len(erg['protokoll'])} "
      f"Verbesserungen")

    gr = erg.get("groesse") or {}
    if gr.get("wesentlich"):
        a("")
        for zeile in _umbrechen(
                f"⚠ Die MASCHINE hat sich dabei veraendert, nicht nur ihre "
                f"Ausnutzung: Baulaenge {gr['laenge_mm'][0]:.0f} -> "
                f"{gr['laenge_mm'][1]:.0f} mm ({gr['laenge_pct']:+.0f} %), "
                f"Masse {gr['masse_kg'][0]:.1f} -> {gr['masse_kg'][1]:.1f} kg "
                f"({gr['masse_pct']:+.0f} %). Die spezifische Leistung steigt, "
                f"wenn Maschinen kleiner werden -- ein Teil des Gewinns ist "
                f"also eine ANDERE Maschine und keine besser ausgenutzte. Wer "
                f"den Bauraum festhalten will, nimmt die Groessenparameter aus "
                f"--frei heraus (axial, shaftD).", 76):
            a("  " + zeile)

    if erg["protokoll"]:
        a("")
        a("Die Griffe, in der Reihenfolge, in der sie gewirkt haben:")
        for p in erg["protokoll"]:
            a(f"  {p['parameter']:<16} {p['von']:>9.4g} -> {p['nach']:<9.4g} "
              f"{e} {p['ziel_vorher']:.4f} -> {p['ziel_nachher']:.4f}"
              f"   (bindend: {p['bindend'] or '-'})")

    a("")
    a("Ausnutzung am Ende:")
    for x in b.get("ausnutzung", []):
        if x.get("quotient") is None:
            continue
        nk = 2 if x["einheit"] == "T" else 0
        marke = "AUSGEREIZT" if x["quotient"] >= AUSGEREIZT_AB else ""
        a(f"  {x['name']:<16} {x['wert']:8.{nk}f} / {x['grenze']:.{nk}f} "
          f"{x['einheit']:<3} = {x['quotient'] * 100:5.1f} %  {marke}")

    if brach and brach.get("hinweise"):
        a("")
        a("Was noch brachliegt -- und was es heben wuerde (gemessen):")
        for h in brach["hinweise"]:
            a(f"  {h['grenze']} bei {h['ausnutzung'] * 100:.0f} %:")
            a(f"    {h['text']}")
    elif brach is not None:
        a("")
        a("Alle Grenzen sind ausgereizt -- kein Parameter liegt brach.")

    a("")
    a("Der Sieger ist ein VORSCHLAG, kein Ergebnis: gerechnet wurde auf dem")
    a("schnellen Bewerter (kein FreeCAD, keine FEM). Nachrechnen mit einem")
    a("Pipelinelauf; was dabei ungeprueft bleibt, sagt `leistung`.")
    return "\n".join(z)
