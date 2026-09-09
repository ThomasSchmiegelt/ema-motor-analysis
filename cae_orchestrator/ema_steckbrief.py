"""Was ein Projekt ist, und was in ihm gerechnet wurde -- als Akte und als Steckbrief.

Warum es dieses Modul gibt -- zwei gemessene Luecken
----------------------------------------------------

**1. Die Ergebnisse der agentischen Rechnungen standen nirgends.**
Von den vierzehn oertlichen Verben der ``cae_cli.py`` schreiben nur ``feldbild``
(Bilder nach ``charts/``) und die HTTP-Verben (ueber den Server nach
``results.json``) etwas auf die Platte. ``paarvergleich``, ``screen``,
``rotor-check`` und ``sicherheit`` -- also genau die Verben, mit denen ein Agent
eine Auslegung *entscheidet* -- geben ihr Ergebnis auf ``stdout`` aus. Es
erscheint in der rechten Spalte, wandert nach oben aus dem Bild und ist beim
naechsten Start weg. Wer eine Woche spaeter fragt „warum eigentlich acht Pole?",
findet die Antwort nirgends, obwohl sie einmal ausgerechnet dastand.

**2. Der Lauf selbst war zwar geschrieben, aber nicht wieder aufzurufen.**
``ema_agent.Kopf.sichern()`` legt nach JEDEM Zug ein ``protokoll_*.md`` und eine
``ereignisse_*.jsonl`` ins Projekt. Gelesen hat das nie jemand: es gab keine
Route, kein Verb und keine Schaltflaeche, die zurueck in einen alten Lauf fuehrt.
Aus der Sicht dessen, der davorsitzt, ist „geschrieben, aber unerreichbar"
dasselbe wie „nicht gespeichert".

Beides ist dieselbe Sache -- was ein Projekt weiss -- und steht darum in einem
Modul: ``ablegen()`` schreibt hinein, ``steckbrief()`` liest zusammen.

Was der Steckbrief NICHT tut
----------------------------

Er rechnet nichts. Kein Wert wird hier abgeleitet, geschaetzt oder aufgefuellt.
Was nicht auf der Platte steht, steht als **fehlend** da -- nicht als 0 und nicht
als Naeherung. Das ist dieselbe Regel wie in ``.agents/projektstand.py``, und sie
hat denselben Grund: ein Agent, der eine analytische Ringformel fuer ein
FEM-Ergebnis haelt, zieht daraus falsche Schluesse, und die Zahl sieht in beiden
Faellen gleich aus.

Aus demselben Grund traegt jeder Kennwert im Steckbrief seine **Herkunft** mit
(``ema_db.HERKUNFT`` -- dieselbe Quelle, aus der die Rechnungsdatenbank ihre
Methodenspalte fuellt, nicht eine zweite Liste daneben).

Ablageort
---------

``<projekt>/rechnungen/<marke>_<verb>.txt`` -- der Wortlaut, wie er auf dem
Schirm stand -- und daneben ``.json``, wenn das Verb strukturierte Daten hat.
Nicht in ``results.json``: die gehoert dem Pipelinelauf und wird von ihm ganz
neu geschrieben; eine Zwischenrechnung darin waere beim naechsten ``run analyse``
weg. Zusaetzlich haengt jede Ablage eine Zeile an ``project.json``s
``evolution`` -- dort steht ohnehin schon, was mit dem Projekt geschah, und ein
zweites Tagebuch daneben waere eines zu viel.
"""

from __future__ import annotations

import json
import os
import re
import time

PROJEKTE = os.path.expanduser("~/cae_projekte")
UNTER = "rechnungen"          # Unterordner je Projekt

# Verben, deren Ergebnis eine Auslegungsentscheidung traegt und darum bleiben
# muss. Bewusst eine geschlossene Liste: ``status``, ``routes`` oder ``projects``
# sind Auskunft ueber den Dienst, kein Ergebnis ueber diese Maschine -- die
# wuerden den Ordner nur zumuellen und den Steckbrief unlesbar machen.
BLEIBENDE_VERBEN = ("paarvergleich", "screen", "rotor-check", "sicherheit",
                    "struktur", "topopt", "maschinenart", "aufgabe", "feldbild")

# Die Marke darf ein ``-2`` tragen: zwei Rechnungen in derselben Sekunde sind
# kein gedachter Fall (ein Agent ruft rotor-check und paarvergleich in einem Zug
# auf, beide in Millisekunden fertig). Ohne den Zusatz im Muster laege die
# zweite Datei zwar da, taeuchte aber in keiner Liste auf.
_MARKE = re.compile(r"^(\d{8}_\d{6}(?:-\d+)?)_(.+)\.(txt|json)$")


# ── Ablegen ─────────────────────────────────────────────────────────────────
def _luftspalt(g: dict):
    """Luftspalt aus ``ema_radien`` -- er kennt auch den Aussenlaeufer.

    Die frueher hier stehende Formel ``(statorID - rotorOD)/2`` haette an einem
    Aussenlaeufer eine negative Zahl gemeldet, und der Steckbrief haette sie
    ausgegeben. Er rechnet nichts nach; um so wichtiger ist, dass das, was er
    zeigt, aus der richtigen Quelle kommt.
    """
    try:
        import ema_radien
        return round(ema_radien.radien(g)["luftspalt_mm"], 3)
    except Exception:
        return None


def _freie_marke(ordner: str, verb: str) -> str:
    """Zeitmarke, die in diesem Ordner noch frei ist.

    Zwei Rechnungen in derselben Sekunde sind kein gedachter Fall: ein Agent
    ruft ``rotor-check`` und ``paarvergleich`` in einem Zug hintereinander auf,
    und beide sind in Millisekunden fertig. Ohne den Zaehler ueberschriebe die
    zweite die erste, und im Steckbrief fehlte sie, ohne dass etwas widerspraeche.
    """
    marke = time.strftime("%Y%m%d_%H%M%S")
    if not os.path.exists(os.path.join(ordner, f"{marke}_{verb}.txt")):
        return marke
    for n in range(2, 100):
        m = f"{marke}-{n}"
        if not os.path.exists(os.path.join(ordner, f"{m}_{verb}.txt")):
            return m
    return f"{marke}-{os.getpid()}"


def _werkzeugstand() -> str:
    """Der Fingerabdruck der Physikmodule als eine Zeile -- weich.

    Weich, weil das Ablegen nie am Nebenbefund scheitern darf (dieselbe Regel
    wie fuer ``ablegen`` selbst). Fehlt er, steht "unbekannt" da und nicht ein
    stillschweigendes "war schon in Ordnung".
    """
    try:
        import ema_werkzeugstand
        return ema_werkzeugstand.kurz(ema_werkzeugstand.stand())
    except Exception:                                        # noqa: BLE001
        return "unbekannt"


def ablegen(projekt_dir: str, verb: str, text: str, *, daten: dict | None = None,
            befehl: str = "", ok: bool = True) -> dict:
    """Ein Verbergebnis dauerhaft ins Projekt legen. Weich fehlschlagend.

    Weich, weil das Ablegen dem Rechnen nie im Weg stehen darf: ein volles
    Dateisystem soll einen ``paarvergleich`` nicht abbrechen, dessen Ergebnis
    bereits auf dem Schirm steht. Der Rueckgabewert sagt, ob es geklappt hat --
    der Aufrufer meldet das, statt es zu erzwingen.
    """
    if not projekt_dir or not os.path.isdir(projekt_dir):
        return {"ok": False, "grund": "kein Projektordner"}
    verb = re.sub(r"[^a-z0-9_-]+", "-", str(verb).lower()).strip("-") or "verb"
    try:
        ordner = os.path.join(projekt_dir, UNTER)
        os.makedirs(ordner, exist_ok=True)
        marke = _freie_marke(ordner, verb)
        pfad = os.path.join(ordner, f"{marke}_{verb}.txt")
        kopf = [f"# {verb} — {time.strftime('%d.%m.%Y %H:%M:%S')}",
                f"# Projekt: {os.path.basename(projekt_dir)}"]
        if befehl:
            kopf.append(f"# Aufruf : {befehl}")
        kopf.append(f"# Ausgang: {'bestanden' if ok else 'ABGELEHNT / verletzt'}")
        # Womit gerechnet wurde. Zwei Zahlen aus zwei Werkzeugstaenden sind nicht
        # vergleichbar, und man sieht ihnen das nicht an -- also steht es dran.
        kopf.append(f"# Werkzeug: {_werkzeugstand()}")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("\n".join(kopf) + "\n\n" + (text or "").rstrip() + "\n")
        if daten is not None:
            with open(os.path.join(ordner, f"{marke}_{verb}.json"), "w",
                      encoding="utf-8") as f:
                json.dump(daten, f, ensure_ascii=False, indent=1, default=str)
    except OSError as e:
        return {"ok": False, "grund": f"{type(e).__name__}: {e}"}

    # Und eine Zeile ins Projekttagebuch, damit die Rechnung auch dort auftaucht,
    # wo die Herkunft des Entwurfs steht -- nicht nur in einem Unterordner.
    try:
        import ema_projekt
        ema_projekt.append_evolution(projekt_dir, {
            "action": f"cli:{verb}",
            "note": (befehl or verb)[:200],
            "ref": os.path.join(UNTER, os.path.basename(pfad)),
            "werkzeug": _werkzeugstand(),
        })
    except Exception:                                        # noqa: BLE001
        pass
    return {"ok": True, "datei": pfad, "marke": marke, "verb": verb}


def _marke_key(marke: str) -> tuple:
    """Sortierschluessel einer Marke -- die Nummer als ZAHL, nicht als Text.

    ``_freie_marke`` haengt bei zwei Rechnungen in derselben Sekunde ein ``-2``
    an. Als Zeichenkette sortiert liegt ``20260101_000000`` dann HINTER
    ``20260101_000000-2`` (Unterstrich 0x5F vor Bindestrich 0x2D im
    Dateinamen) -- die aeltere Rechnung galt als die juengere. Zwei Verben in
    einem Agentenzug sind beide in Millisekunden fertig, das ist also der
    Normalfall und nicht der Sonderfall.
    """
    kopf, _, nr = marke.partition("-")
    try:
        return (kopf, int(nr) if nr else 1)
    except ValueError:
        return (kopf, 1)


def rechnungen(projekt_dir: str) -> list[dict]:
    """Was in diesem Projekt abgelegt wurde, neueste zuerst."""
    ordner = os.path.join(projekt_dir, UNTER)
    if not os.path.isdir(ordner):
        return []
    aus = []
    for name in os.listdir(ordner):
        m = _MARKE.match(name)
        if not m or m.group(3) != "txt":
            continue
        pfad = os.path.join(ordner, name)
        kopf, ausgang = "", ""
        try:
            with open(pfad, encoding="utf-8") as f:
                for zeile in f:
                    if not zeile.startswith("#"):
                        if zeile.strip() and not kopf:
                            kopf = zeile.strip()[:120]
                        continue
                    if zeile.startswith("# Ausgang:"):
                        ausgang = zeile.split(":", 1)[1].strip()
        except OSError:
            continue
        aus.append({"marke": m.group(1), "verb": m.group(2), "datei": pfad,
                    "erste_zeile": kopf, "ausgang": ausgang,
                    "daten": os.path.isfile(pfad[:-4] + ".json")})
    aus.sort(key=lambda r: _marke_key(r["marke"]), reverse=True)
    return aus


def getriebe(projekt_dir: str) -> dict | None:
    """Die JUENGSTE abgelegte Getriebeauslegung, auf ihre Aussagen eingedampft.

    Sie steht schon in ``rechnungen`` -- aber dort als eine Zeile „getriebe
    (16:42)", und damit ist die Uebersetzung, mit der der Fahrzyklus gerechnet
    hat, im Steckbrief nicht zu sehen. Sie gehoert dorthin, denn sie ist eine
    Eigenschaft des Antriebs und nicht bloss eine gelaufene Rechnung.

    Wie ueberall hier wird **nichts nachgerechnet**: gelesen wird die abgelegte
    JSON. Und jede Zahl traegt, woher sie kommt -- die Uebersetzung folgt exakt
    aus ganzen Zaehnezahlen, die Sicherheiten aus ISO 6336 mit einem
    ANGENOMMENEN Werkstoffkennwert, und ob der Satz in die Welle passt, haengt
    daran, ob die magnetische Grenze wirklich gemessen wurde.
    """
    ordner = os.path.join(projekt_dir, UNTER)
    if not os.path.isdir(ordner):
        return None
    treffer = sorted((n for n in os.listdir(ordner)
                      if _MARKE.match(n) and _MARKE.match(n).group(2) == "getriebe"
                      and n.endswith(".json")),
                     key=lambda n: _marke_key(_MARKE.match(n).group(1)), reverse=True)
    if not treffer:
        return None
    g = _json(os.path.join(ordner, treffer[0]))
    if not g.get("ok"):
        return None
    stufen = g.get("stufen") or []
    iw = g.get("in_welle") or {}
    aus = {
        "marke": _MARKE.match(treffer[0]).group(1),
        "art": g.get("art"), "einbau": g.get("einbau"),
        "einbau_text": g.get("einbau_text", ""),
        "i_soll": g.get("i_soll"), "i_ist": g.get("i_ist"),
        "i_fehler_pct": g.get("i_fehler_pct"),
        "n_stufen": g.get("n_stufen"),
        "moduln_mm": [st.get("m_mm") for st in stufen if st.get("m_mm")]
                     or ([g["m_mm"]] if g.get("m_mm") else []),
        # Die SCHWAECHSTE Stufe zaehlt, nicht der Mittelwert: eine Kette ist so
        # tragfaehig wie ihr schwaechstes Glied. Beim Kegelrad steht die
        # Sicherheit auf der obersten Ebene, bei der Schnecke gar nicht.
        "S_F": None, "S_H": None,
        "bindend": [st.get("bindend") for st in stufen if st.get("bindend")],
        "haelt": g.get("haelt"),
        "eta_nenn": (g.get("wirkungsgrad") or {}).get("eta_nenn"),
        "masse_kg": g.get("masse_kg"), "J_red_kgm2": g.get("J_red_kgm2"),
        "werkstoff": g.get("werkstoff"), "werkstoff_beleg": g.get("werkstoff_beleg"),
        "verfahren": g.get("verfahren", ""),
        "zeichner": (g.get("cad") or {}).get("zeichner"),
        "bild": bool(g.get("bild")),
    }
    for schl in ("S_F", "S_H"):
        werte = [st[schl] for st in stufen if st.get(schl) is not None]
        if g.get(schl) is not None:
            werte.append(g[schl])
        if werte:
            aus[schl] = min(werte)
    if iw:
        aus["in_welle"] = {
            "passt": iw.get("passt"), "bindend": iw.get("bindend"),
            "d_noetig_mm": iw.get("d_noetig_mm"),
            "d_verfuegbar_mm": iw.get("d_verfuegbar_mm"),
            # Der eigentliche Punkt: „passt in die gezeichnete Bohrung" ist
            # nicht „zulaessig". Ohne Feldlauf steht die magnetische Grenze
            # ungeprueft da, und das ist eine Aussage ueber die Antwort.
            "magnetisch_geprueft": bool(iw.get("magnetisch_geprueft")),
        }
    return aus


# ── Steckbrief ──────────────────────────────────────────────────────────────
def _json(pfad: str) -> dict:
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _zaehle(ordner: str, endung: str = "") -> int:
    try:
        return sum(1 for n in os.listdir(ordner)
                   if not endung or n.lower().endswith(endung))
    except OSError:
        return 0


def _vtu_zaehlen(projekt_dir: str) -> int:
    n = 0
    for unter in ("em3d", "em3d_runs"):
        for wurzel, _, dateien in os.walk(os.path.join(projekt_dir, unter)):
            n += sum(1 for d in dateien if d.lower().endswith(".vtu"))
    return n


# Die Stufen der Leiter, in der Reihenfolge, in der sie gefahren werden. Der
# Schluessel ist der Abschnitt in ``results.json`` -- steht er nicht drin, ist die
# Stufe nicht gelaufen.
STUFEN = [("em", "2D-EM-Feld (FDM)"),
          ("structural_fem", "Festigkeit (FEM)"),
          ("thermal", "Thermik"),
          ("drivecycle", "Fahrzyklus"),
          ("em3d", "3D-EM-Feld (Elmer)")]

# Was einen Entwurf in einem Satz beschreibt. Knapp gehalten: der Steckbrief soll
# in den Kontext eines Modells passen, nicht ihn fuellen.
KENNWERTE = ["B_gap_T", "Kt_Nm_per_A", "T_maxwell_Nm", "T_peak_max_Nm",
             "P_max_kW", "max_safe_rpm", "safety_factor_fem", "structural_basis",
             "T_winding_C", "T_magnet_C", "mass_g", "cycle_kWh100km"]


def maschine(payload: dict, projektakte: dict) -> dict:
    """Die Maschine in Stichworten -- aus dem Payload, nicht aus dem Datenblatt.

    Das Datenblatt in ``project.json`` ist Fliesstext fuer den Bericht; hier
    werden die Felder einzeln gebraucht (der Agent soll die Polzahl lesen, nicht
    einen Satz danach absuchen).
    """
    g = (payload.get("geom") or {})
    art = str(g.get("machineType") or "pmsm")
    try:
        import ema_maschinenart as MA
        art_text = MA.hole(art).bezeichnung
    except Exception:                                        # noqa: BLE001
        art_text = art.upper()
    try:
        from ema_topology import TOPOLOGY_LABELS
        anordnung_text = TOPOLOGY_LABELS.get(str(g.get("magShape")), "")
    except Exception:                                        # noqa: BLE001
        anordnung_text = ""
    p = g.get("p")
    return {
        "art": art, "art_text": art_text,
        "p": p, "pole": (int(p) * 2 if isinstance(p, (int, float)) and p else None),
        "nuten": g.get("slots"),
        "anordnung": g.get("magShape"), "anordnung_text": anordnung_text,
        "statorOD_mm": g.get("statorOD"), "statorID_mm": g.get("statorID"),
        "rotorOD_mm": g.get("rotorOD"),
        "axial_mm": payload.get("axial_len") or g.get("axialLen"),
        "luftspalt_mm": _luftspalt(g),
        "kuehlung": payload.get("cooling"),
        "magnet": payload.get("magnet"),
        "rotor_blech": payload.get("rotor_lam"),
        "stator_blech": payload.get("stator_lam"),
        "leiter": payload.get("hairpin_mat"),
        "rpm_von": payload.get("rpm_from"), "rpm_bis": payload.get("rpm_to"),
        "last_nm": payload.get("load_nm"),
        "zyklus": (payload.get("cycle") or {}).get("name")
                  if isinstance(payload.get("cycle"), dict) else payload.get("cycle"),
    }


def steckbrief(projekt_dir: str, *, mit_laeufen: bool = True) -> dict:
    """Alles, was ueber dieses Projekt auf der Platte steht -- ohne zu rechnen."""
    if not os.path.isdir(projekt_dir):
        return {"ok": False, "grund": f"Kein Projektordner: {projekt_dir}"}
    pid = os.path.basename(projekt_dir.rstrip("/"))
    akte = _json(os.path.join(projekt_dir, "project.json"))
    meta = _json(os.path.join(projekt_dir, "meta.json"))
    erg = _json(os.path.join(projekt_dir, "results.json"))
    payload = meta.get("payload") or (akte.get("inputs") or {}).get("payload") or {}

    zus = erg.get("summary") or {}
    try:
        import ema_db
        herk = ema_db.HERKUNFT
        methoden = ema_db.METHODEN
    except Exception:                                        # noqa: BLE001
        herk, methoden = {}, {}
    kennwerte = []
    for k in KENNWERTE:
        if zus.get(k) is None:
            continue
        h = herk.get(k) or {}
        kennwerte.append({"schluessel": k, "wert": zus[k],
                          "einheit": h.get("einheit", ""),
                          "methode": h.get("methode", "unbekannt"),
                          "methode_text": methoden.get(h.get("methode", ""), "")})

    gerechnet = [{"schluessel": k, "name": n, "da": bool(erg.get(k))}
                 for k, n in STUFEN]

    # Sicherheitsbefund. Nur wenn gerechnet wurde -- ``pruefen`` auf einem leeren
    # Lauf gaebe ein „bestanden", das nichts geprueft hat.
    sicher = None
    if zus:
        try:
            import ema_sicherheit
            b = ema_sicherheit.pruefen(erg, meta)
            sicher = {"ok": bool(b.get("ok")),
                      "verletzt": [k.get("name") or k.get("kriterium") or str(k)
                                   for k in (b.get("kriterien") or [])
                                   if k.get("ok") is False]}
        except Exception:                                    # noqa: BLE001
            sicher = None

    bestand = {
        "cad_fcstd": os.path.isfile(os.path.join(projekt_dir, "motor.FCStd")),
        "cad_step": os.path.isfile(os.path.join(projekt_dir, "motor.step")),
        "bericht_pdf": os.path.isfile(os.path.join(projekt_dir, "bericht.pdf")),
        "diagramme": _zaehle(os.path.join(projekt_dir, "charts"), ".png"),
        "feldbilder": sum(1 for n in os.listdir(os.path.join(projekt_dir, "charts"))
                          if n.startswith("feld_"))
                      if os.path.isdir(os.path.join(projekt_dir, "charts")) else 0,
        "cad_bilder": _zaehle(os.path.join(projekt_dir, "cad_images"), ".png"),
        # Nicht flach gezaehlt: Elmer legt seine VTU unter ``em3d/results/`` ab,
        # und ein flaches ``listdir`` haette hier „0 3D-Feldnetze" gemeldet,
        # waehrend das Feld danebenlag.
        "vtu": _vtu_zaehlen(projekt_dir),
    }

    # Mit welchem Werkzeug ist hier gerechnet worden? Stehen in der Evolution
    # mehrere Staende, sind die Kennwerte NICHT ohne Weiteres vergleichbar -- und
    # das ist eine Aussage ueber die Zahlen, keine ueber die Ablage.
    _staende = []
    for e in (akte.get("evolution") or []):
        w = str(e.get("werkzeug") or "").split(" ")[0]
        if w and w != "unbekannt" and w not in _staende:
            _staende.append(w)
    # Und: liegt dieser Fall ueberhaupt in der Klasse, auf die diese Kette
    # geeicht ist? Zusammen mit der Herkunft je Kennwert ist das die Gewichtung
    # einer Zahl -- s. ema_referenz.GELTUNG.
    try:
        import ema_referenz
        geltung = ema_referenz.geltung_pruefen(payload.get("geom") or {}, payload)
    except Exception:                                        # noqa: BLE001
        geltung = []

    werkzeug = {"jetzt": _werkzeugstand(),
                "staende": _staende,
                "gemischt": len(_staende) > 1}

    aus = {
        "ok": True, "id": pid, "ordner": projekt_dir, "werkzeug": werkzeug,
        "geltung": geltung,
        "label": akte.get("label") or pid,
        "status": akte.get("status") or ("gerechnet" if zus else "neu"),
        "angelegt": akte.get("created") or meta.get("created", ""),
        "geaendert": akte.get("updated", ""),
        "herkunft": {"eltern": (akte.get("lineage") or {}).get("parent"),
                     "ursprung": (akte.get("lineage") or {}).get("origin"),
                     "quelle": (akte.get("design") or {}).get("source")},
        "auftrag": (akte.get("design") or {}).get("brief") or "",
        # Der Unterschied, auf den beim Agentenstart alles ankommt: ein
        # gebundenes Projekt ist sonst ausdruecklich KEINE Vorlage (dagegen
        # wurde ``--frisch`` gebaut). Eine im Designer vorgezeichnete Geometrie
        # ist das Gegenteil -- sie ist als Startpunkt GEWOLLT.
        "vorgabe": bool((akte.get("design") or {}).get("vorgabe")),
        "maschine": maschine(payload, akte),
        "gerechnet": gerechnet,
        "kennwerte": kennwerte,
        "sicherheit": sicher,
        "bestand": bestand,
        "rechnungen": rechnungen(projekt_dir),
        "getriebe": getriebe(projekt_dir),
        "notizen": akte.get("notes") or "",
    }
    if mit_laeufen:
        try:
            import ema_agent
            aus["laeufe"] = ema_agent.laeufe_im_ordner(
                os.path.join(projekt_dir, "agent"), pid)
        except Exception:                                    # noqa: BLE001
            aus["laeufe"] = []
    aus["warnungen"] = _warnungen(aus, zus)
    return aus


def _warnungen(sb: dict, zus: dict) -> list[str]:
    """Was einem Leser sonst als gerechnet durchginge.

    Der wichtigste Einzelfall steht auch in ``.agents/projektstand.py``:
    ``structural_basis == "analytisch"`` heisst, dass die FEM NICHT gelaufen ist
    -- die Zahl kommt aus der Ringformel und kennt die Spannungsspitzen an den
    Stegen nicht. Sie sieht aber genauso aus wie ein FEM-Ergebnis.
    """
    w = []
    if zus.get("structural_basis") == "analytisch":
        w.append("Die Festigkeitszahl ist ANALYTISCH — die FEM ist nicht gelaufen. "
                 "Sie kennt die Spannungsspitzen an den Stegen nicht.")
    if zus and zus.get("safety_factor_fem") is None:
        w.append("safety_factor_fem fehlt: das heisst 'keine FEM gerechnet', "
                 "nicht 'sicher'.")
    offen = [s["name"] for s in sb["gerechnet"] if not s["da"]]
    if offen:
        w.append("Noch nicht gerechnet: " + ", ".join(offen) + ".")
    if sb["sicherheit"] and not sb["sicherheit"]["ok"]:
        w.append("Sicherheitskriterien VERLETZT: "
                 + ", ".join(sb["sicherheit"]["verletzt"] or ["—"]))
    g = sb.get("getriebe")
    if g:
        # Der Werkstoffkennwert ist eine ANNAHME, und jede Sicherheit haengt
        # daran. Das ist nicht dasselbe wie eine gerechnete Zahl und sieht
        # genauso aus -- also steht es hier.
        if g.get("werkstoff_beleg") == "annahme" and (g.get("S_F") is not None
                                                      or g.get("S_H") is not None):
            w.append("Die Getriebesicherheiten ruhen auf einem ANGENOMMENEN "
                     f"Werkstoffkennwert ({g.get('werkstoff') or '?'}) — "
                     "Groessenordnung der Werkstoffklasse, nicht zitiert.")
        if g.get("haelt") is False:
            w.append("Die Verzahnung TRAEGT NICHT: mindestens eine Sicherheit "
                     "liegt unter ihrem Zielwert.")
        iw = g.get("in_welle") or {}
        if iw and not iw.get("magnetisch_geprueft"):
            w.append("Beim Einbau in der Welle wurde die magnetisch zulaessige "
                     "Bohrung NICHT geprueft (kein Feldlauf).")
    return w


def _z(wert, einheit: str = "") -> str:
    if wert is None or wert == "":
        return "—"
    if isinstance(wert, float):
        wert = f"{wert:.4g}"
    return f"{wert}{(' ' + einheit) if einheit else ''}"


def als_text(sb: dict, *, kurz: bool = False) -> str:
    """Der Steckbrief als Text -- das, was ein Agent vorliest.

    Kurz gehalten und in fester Reihenfolge: was die Maschine IST, was daran
    gerechnet WURDE, was dabei herauskam, was noch offen ist. Wer im Gespraech
    „gib mir einen Steckbrief" sagt, will diese vier Dinge und nicht die Akte.
    """
    if not sb.get("ok"):
        return f"FEHLER: {sb.get('grund', 'kein Steckbrief')}"
    m = sb["maschine"]
    z = [f"STECKBRIEF {sb['id']}"
         + (f"  ({sb['label']})" if sb["label"] != sb["id"] else ""),
         f"  Stand    : {sb['status']}"
         + (f", angelegt {sb['angelegt'][:16].replace('T', ' ')}" if sb["angelegt"] else "")
         + (f", zuletzt {sb['geaendert'][:16].replace('T', ' ')}" if sb["geaendert"] else ""),
         f"  Maschine : {m['art_text']}"
         + (f", {m['anordnung_text']}" if m["anordnung_text"] else "")
         + (f", {m['pole']} Pole" if m["pole"] else "")
         + (f", {m['nuten']} Nuten" if m["nuten"] else ""),
         f"  Bauraum  : Stator-Aussen-D {_z(m['statorOD_mm'], 'mm')}, "
         f"Bohrung {_z(m['statorID_mm'], 'mm')}, Laenge {_z(m['axial_mm'], 'mm')}, "
         f"Luftspalt {_z(m['luftspalt_mm'], 'mm')}",
         f"  Betrieb  : {_z(m['rpm_von'])}–{_z(m['rpm_bis'])} 1/min, "
         f"{_z(m['last_nm'], 'Nm')}, Kuehlung {_z(m['kuehlung'])}"
         + (f", Zyklus {m['zyklus']}" if m["zyklus"] else ""),
         f"  Werkstoff: Magnet {_z(m['magnet'])}, Blech {_z(m['rotor_blech'])}, "
         f"Leiter {_z(m['leiter'])}"]
    if sb["auftrag"]:
        z.append(f"  Auftrag  : {sb['auftrag'][:180]}")
    if sb.get("vorgabe"):
        z.append("  VORGABE  : die Geometrie ist von Hand vorgezeichnet und als "
                 "Startpunkt gemeint")
    if sb["herkunft"]["eltern"]:
        z.append(f"  Abgeleitet aus: {sb['herkunft']['eltern']}")
    w = sb.get("werkzeug") or {}
    if w.get("jetzt"):
        z.append(f"  Werkzeug : {w['jetzt']}")
    if w.get("gemischt"):
        z.append("  ACHTUNG  : die abgelegten Rechnungen stammen aus "
                 f"{len(w['staende'])} verschiedenen Werkzeugstaenden "
                 f"({', '.join(w['staende'])}) — ihre Zahlen sind nicht ohne "
                 "Weiteres vergleichbar.")

    if sb.get("geltung"):
        z += ["", "  Geltungsbereich — was hier ausserhalb der geprueften Klasse liegt:"]
        for e in sb["geltung"]:
            z.append(f"    {e['feld']}: {e['text']}")
    da = [s["name"] for s in sb["gerechnet"] if s["da"]]
    z += ["", "  Gerechnet: " + (", ".join(da) if da else "— noch nichts —")]
    if sb["kennwerte"]:
        z.append("  Kennwerte (mit Herkunft):")
        for k in sb["kennwerte"]:
            z.append(f"    {k['schluessel']:<20s} {_z(k['wert'], k['einheit']):<16s} "
                     f"[{k['methode']}]")
    if sb["sicherheit"] is not None:
        z.append("  Sicherheit: " + ("alle Kriterien bestanden"
                                     if sb["sicherheit"]["ok"] else
                                     "VERLETZT — " + ", ".join(
                                         sb["sicherheit"]["verletzt"] or ["?"])))

    g = sb.get("getriebe")
    if g:
        z += ["", f"  Getriebe : {g['art']}, {g.get('einbau_text') or g['einbau']}"
                  f" — i {_z(g['i_ist'])} (gefordert {_z(g['i_soll'])}, "
                  f"{_z(g['i_fehler_pct'], '%')} daneben)  [zaehnezahlen]"]
        if g["moduln_mm"]:
            z.append("    Modul     : "
                     + ", ".join(f"{m:g} mm" for m in g["moduln_mm"])
                     + (f"  (gebunden hat: {', '.join(g['bindend'])})"
                        if g["bindend"] else ""))
        if g["S_F"] is not None or g["S_H"] is not None:
            z.append(f"    Sicherheit: Zahnfuss {_z(g['S_F'])}, "
                     f"Flanke {_z(g['S_H'])}  [iso6336, Werkstoff "
                     f"{g.get('werkstoff') or '?'} — {g.get('werkstoff_beleg') or '?'}]")
        if g["eta_nenn"] is not None:
            z.append(f"    Wirkungsgrad {_z(g['eta_nenn'])} am Nennpunkt "
                     f"(lastabhaengig), Masse {_z(g['masse_kg'], 'kg')}, "
                     f"J_red {_z(g['J_red_kgm2'], 'kgm2')}")
        iw = g.get("in_welle")
        if iw:
            z.append(f"    In der Welle: "
                     + ("PASST" if iw["passt"] else "PASST NICHT")
                     + f" — gebraucht {_z(iw['d_noetig_mm'], 'mm')}, "
                     f"verfuegbar {_z(iw['d_verfuegbar_mm'], 'mm')}"
                     + (f" (bindend: {iw['bindend']})" if iw.get("bindend") else ""))
            if not iw["magnetisch_geprueft"]:
                z.append("      ACHTUNG: die magnetisch zulaessige Bohrung wurde "
                         "NICHT geprueft (kein Feldlauf) — „passt in die "
                         "gezeichnete Bohrung\" ist nicht „zulaessig\".")
        if g.get("verfahren"):
            z.append(f"    Verfahren : {g['verfahren'][:160]}")
        if g.get("zeichner") == "ersatz":
            z.append("    Zeichnung : ERSATZKOERPER ohne Zaehne (FCGear fehlte) — "
                     "sie zeigt Lage und Platzbedarf, keine Verzahnung.")

    b = sb["bestand"]
    z += ["", f"  Bestand  : {b['diagramme']} Diagramme "
              f"(davon {b['feldbilder']} Feldbilder), {b['cad_bilder']} CAD-Bilder, "
              f"{b['vtu']} 3D-Feldnetze"
              + (", CAD (FCStd/STEP)" if b["cad_fcstd"] or b["cad_step"] else "")
              + (", PDF-Bericht" if b["bericht_pdf"] else "")]

    if sb.get("laeufe"):
        z.append(f"  Agentenlaeufe: {len(sb['laeufe'])} — "
                 + ", ".join(f"{l['marke']} ({l.get('kopf') or '?'}, "
                             f"{l.get('ereignisse', 0)} Ereignisse)"
                             for l in sb["laeufe"][:4])
                 + (" …" if len(sb["laeufe"]) > 4 else ""))
    if sb["rechnungen"]:
        z.append(f"  Abgelegte Rechnungen: {len(sb['rechnungen'])} — "
                 + ", ".join(f"{r['verb']} ({r['marke'][9:11]}:{r['marke'][11:13]})"
                             for r in sb["rechnungen"][:6])
                 + (" …" if len(sb["rechnungen"]) > 6 else ""))

    if sb["warnungen"] and not kurz:
        z += ["", "  ACHTUNG:"] + [f"    - {w}" for w in sb["warnungen"]]
    return "\n".join(z)


def als_markdown(sb: dict) -> str:
    """Fuer ``AGENTS.projekt.md`` -- derselbe Inhalt, aber als Stichpunkte.

    Eigene Form und nicht ``als_text`` mit Einrueckung: die Projektakte wird von
    einem Sprachmodell gelesen, und eine Tabelle mit Doppelpunkten liest es
    zuverlaessiger als eine ausgerichtete Textspalte.
    """
    if not sb.get("ok"):
        return f"- Steckbrief nicht lesbar: {sb.get('grund', '')}"
    m = sb["maschine"]
    z = []
    if sb.get("auftrag"):
        # Mehrzeilig eingeruecken: eine rohe Leerzeile im Auftrag beendete
        # sonst die Aufzaehlung, und der Rest stuende danach wie Fliesstext da.
        auftrag = "\n  ".join(zeile for zeile in
                              str(sb["auftrag"])[:1500].splitlines() if zeile.strip())
        z.append(f"- **Auftrag des Menschen**: {auftrag}")
    if sb.get("vorgabe"):
        z += ["- **Diese Geometrie ist eine VORGABE, kein Altbestand.** Sie wurde",
              "  von Hand im Designer vorgezeichnet und ausdruecklich als Startpunkt",
              "  uebergeben. Fang damit an. Aendern darfst du sie -- sag dann aber,",
              "  WAS du geaendert hast und warum. Sie ist NICHT der Fall, gegen den",
              "  `--frisch` gebaut wurde."]
    z.append(f"- Maschinenart: {m['art_text']} (`{m['art']}`)")
    if m["anordnung_text"]:
        z.append(f"- Magnetanordnung: {m['anordnung_text']} (`{m['anordnung']}`)")
    z += [f"- Pole/Nuten: {_z(m['pole'])} / {_z(m['nuten'])}",
          f"- Bauraum: Stator-Aussen-D {_z(m['statorOD_mm'], 'mm')}, Bohrung "
          f"{_z(m['statorID_mm'], 'mm')}, Paketlaenge {_z(m['axial_mm'], 'mm')}, "
          f"Luftspalt {_z(m['luftspalt_mm'], 'mm')}",
          f"- Betriebspunkt: {_z(m['rpm_von'])}–{_z(m['rpm_bis'])} 1/min bei "
          f"{_z(m['last_nm'], 'Nm')}, Kuehlung {_z(m['kuehlung'])}",
          f"- Werkstoffe: Magnet {_z(m['magnet'])}, Blech {_z(m['rotor_blech'])}, "
          f"Leiter {_z(m['leiter'])}"]
    da = [s["name"] for s in sb["gerechnet"] if s["da"]]
    z.append("- Gerechnet: " + (", ".join(da) if da else "**noch nichts**"))
    for e in (sb.get("geltung") or []):
        z.append(f"- **Geltungsbereich / {e['feld']}**: {e['text']}")
    w = sb.get("werkzeug") or {}
    if w.get("jetzt"):
        z.append(f"- Werkzeugstand: `{w['jetzt']}`")
    if w.get("gemischt"):
        z.append("- **Die abgelegten Rechnungen stammen aus verschiedenen "
                 f"Werkzeugstaenden** ({', '.join(w['staende'])}). Zahlen aus "
                 "zwei Staenden sind nicht ohne Weiteres vergleichbar; sag das "
                 "dazu, statt sie nebeneinanderzustellen.")
    for k in sb["kennwerte"]:
        z.append(f"- {k['schluessel']}: {_z(k['wert'], k['einheit'])} "
                 f"(Herkunft: {k['methode']})")
    g = sb.get("getriebe")
    if g:
        z.append(f"- Getriebe: {g['art']}, {g.get('einbau_text') or g['einbau']}, "
                 f"i = {_z(g['i_ist'])} (gefordert {_z(g['i_soll'])})"
                 + (f", Modul {', '.join(f'{m:g}' for m in g['moduln_mm'])} mm"
                    if g["moduln_mm"] else "")
                 + (f", S_F {_z(g['S_F'])} / S_H {_z(g['S_H'])}"
                    if g["S_F"] is not None or g["S_H"] is not None else "")
                 + (f", eta {_z(g['eta_nenn'])}" if g["eta_nenn"] is not None else ""))
        iw = g.get("in_welle")
        if iw:
            z.append("- Getriebe in der Welle: "
                     + ("passt" if iw["passt"] else "**passt NICHT**")
                     + f" — gebraucht {_z(iw['d_noetig_mm'], 'mm')}, verfuegbar "
                     f"{_z(iw['d_verfuegbar_mm'], 'mm')}"
                     + (f", bindend: {iw['bindend']}" if iw.get("bindend") else ""))
    if sb["rechnungen"]:
        z.append(f"- Abgelegte Rechnungen in `{UNTER}/`: "
                 + ", ".join(f"{r['marke']}_{r['verb']}"
                             for r in sb["rechnungen"][:8]))
    if sb.get("laeufe"):
        z.append(f"- Fruehere Agentenlaeufe in `agent/`: "
                 + ", ".join(l["marke"] for l in sb["laeufe"][:8]))
    for w in sb["warnungen"]:
        z.append(f"- ACHTUNG: {w}")
    return "\n".join(z)


# ── Projektsuche ────────────────────────────────────────────────────────────
def projekt_pfad(kennung: str, wurzel: str = PROJEKTE) -> str:
    """``last`` oder eine Kennung zu einem Ordner. Leer, wenn es ihn nicht gibt.

    ``last`` ist das juengste Projekt **mit ``meta.json``** -- nicht schlicht der
    juengste Ordner. Der Unterschied ist keiner auf dem Papier: jede CAD-Vorschau
    legt einen ``*_cad_vorschau``-Ordner an, und der ist regelmaessig juenger als
    das Projekt, um das es gerade geht.
    """
    if kennung in ("last", "letztes", ""):
        try:
            kandidaten = sorted(
                d for d in os.listdir(wurzel)
                if not d.startswith("_")
                and os.path.isfile(os.path.join(wurzel, d, "meta.json")))
        except OSError:
            return ""
        return os.path.join(wurzel, kandidaten[-1]) if kandidaten else ""
    p = os.path.join(wurzel, kennung)
    return p if os.path.isdir(p) else ""
