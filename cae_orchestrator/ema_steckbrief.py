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
        })
    except Exception:                                        # noqa: BLE001
        pass
    return {"ok": True, "datei": pfad, "marke": marke, "verb": verb}


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
    aus.sort(key=lambda r: r["marke"], reverse=True)
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
        "luftspalt_mm": (round((float(g["statorID"]) - float(g["rotorOD"])) / 2.0, 3)
                         if g.get("statorID") and g.get("rotorOD") else None),
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

    aus = {
        "ok": True, "id": pid, "ordner": projekt_dir,
        "label": akte.get("label") or pid,
        "status": akte.get("status") or ("gerechnet" if zus else "neu"),
        "angelegt": akte.get("created") or meta.get("created", ""),
        "geaendert": akte.get("updated", ""),
        "herkunft": {"eltern": (akte.get("lineage") or {}).get("parent"),
                     "ursprung": (akte.get("lineage") or {}).get("origin"),
                     "quelle": (akte.get("design") or {}).get("source")},
        "auftrag": (akte.get("design") or {}).get("brief") or "",
        "maschine": maschine(payload, akte),
        "gerechnet": gerechnet,
        "kennwerte": kennwerte,
        "sicherheit": sicher,
        "bestand": bestand,
        "rechnungen": rechnungen(projekt_dir),
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
    if sb["herkunft"]["eltern"]:
        z.append(f"  Abgeleitet aus: {sb['herkunft']['eltern']}")

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
    z = [f"- Maschinenart: {m['art_text']} (`{m['art']}`)"]
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
    for k in sb["kennwerte"]:
        z.append(f"- {k['schluessel']}: {_z(k['wert'], k['einheit'])} "
                 f"(Herkunft: {k['methode']})")
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
