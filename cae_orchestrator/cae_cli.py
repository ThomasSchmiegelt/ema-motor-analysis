#!/usr/bin/env python3
"""Kommandozeile für den CAE-Orchestrator — die Werkzeugfläche für Agent-Harnesses.

Gedacht für PI (https://pi.dev) und verwandte Harnesses, die Werkzeuge als **CLI mit
README** einbinden statt als Tool-Schemata. Ein lokales Modell kann 135 Flask-Routen
nicht sinnvoll als 135 Werkzeuge halten; es kann aber `cae_cli.py run em3d` aufrufen
und die Antwort lesen. Deshalb: wenige benannte Verben für den Alltagspfad, plus
``raw`` als Notausgang auf jede beliebige Route.

Bewusste Eigenschaften:
  * **Nur stdlib** (urllib/json/argparse) — wie der Rest des Orchestrators, kein
    ``requests``. Die Datei läuft mit jedem Python 3.10+, auch ohne das venv.
  * **Nur localhost.** Es gibt keinen Weg, eine andere Gegenstelle zu setzen als
    ``--url``, und der Vorgabewert ist http://localhost:5000. Das Repo redet
    absichtlich mit nichts sonst.
  * **Kontextschonend.** Ergebnisse enthalten eingebettete PNGs (``*_b64``,
    ``chart_b64``, ``png``…) mit Megabytes an Base64. Die werden IMMER durch einen
    Platzhalter ersetzt, bevor etwas gedruckt wird — sonst ist der Kontext eines
    lokalen Modells nach einer Antwort voll. ``--full`` hebt nur die Längenkappung
    auf, nicht die Bildfilterung.
  * **Exit-Code als Signal.** 0 = ok, 1 = Fehler der Gegenstelle, 2 = Bedienfehler,
    3 = Server nicht erreichbar, 4 = Zeitüberschreitung beim Warten. Ein Agent soll
    den Zustand am Code erkennen, nicht am Fließtext.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("CAE_URL", "http://localhost:5000")
TIMEOUT_S = 30

# Schlüssel, deren Werte eingebettete Binärdaten sind (Base64-PNG/VTP/PDF).
_BLOB_HINTS = ("_b64", "b64", "png", "image", "vtp", "pdf", "frames", "thumb")
EXIT_OK, EXIT_REMOTE, EXIT_USAGE, EXIT_DOWN, EXIT_TIMEOUT = 0, 1, 2, 3, 4


def _is_blob(key: str, val) -> bool:
    if not isinstance(val, str) or len(val) < 512:
        return False
    k = key.lower()
    return any(h in k for h in _BLOB_HINTS) or val[:20].isascii() and len(val) > 20000


def strip_blobs(obj, path=""):
    """Base64-Nutzlasten durch eine Notiz ersetzen. Rekursiv, formerhaltend."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _is_blob(k, v):
                out[k] = f"<{len(v)} Zeichen Binärdaten entfernt — mit 'fetch' holen>"
            else:
                out[k] = strip_blobs(v, f"{path}.{k}")
        return out
    if isinstance(obj, list):
        if len(obj) > 200 and all(isinstance(x, (int, float)) for x in obj):
            return obj[:20] + [f"... {len(obj) - 20} weitere Zahlen"]
        if len(obj) > 40 and all(isinstance(x, str) and len(x) > 512 for x in obj):
            return [f"<{len(obj)} eingebettete Bilder entfernt>"]
        return [strip_blobs(x, path) for x in obj]
    return obj


def request(method: str, path: str, payload=None, url=DEFAULT_URL, timeout=TIMEOUT_S):
    if not path.startswith("/"):
        path = "/" + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url.rstrip("/") + path, data=data,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ct = r.headers.get("Content-Type", "")
            if "json" in ct:
                return r.status, json.loads(raw.decode() or "null")
            return r.status, {"_content_type": ct, "_bytes": len(raw)}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, {"error": body[:500]}
    except urllib.error.URLError as e:
        raise SystemExit(_die(f"Server auf {url} nicht erreichbar ({e.reason}). "
                              f"Starten mit: cd cae_orchestrator && ./start.sh", EXIT_DOWN))
    except TimeoutError:
        raise SystemExit(_die(f"Zeitüberschreitung nach {timeout}s an {path}", EXIT_TIMEOUT))


def _die(msg: str, code: int) -> int:
    print(f"FEHLER: {msg}", file=sys.stderr)
    return code


def emit(obj, args) -> int:
    obj = strip_blobs(obj)
    text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    limit = None if getattr(args, "full", False) else 12000
    if limit and len(text) > limit:
        text = (text[:limit] + f"\n... [{len(text) - limit} Zeichen gekürzt — "
                               f"engeren Abschnitt wählen oder --full]")
    print(text)
    return EXIT_OK


# ── Verben ──────────────────────────────────────────────────────────────────────

def cmd_status(args) -> int:
    code, st = request("GET", "/status", url=args.url)
    if args.json:
        return emit(st, args)
    print(f"Zustand   : {st.get('status')}")
    print(f"Fortschritt: {st.get('progress')} %")
    print(f"Projekt   : {st.get('project_id') or '—'}")
    for line in (st.get("log") or [])[-args.log_lines:]:
        print(f"  {line}")
    return EXIT_OK if code < 400 else EXIT_REMOTE


def cmd_health(args) -> int:
    """Was ist überhaupt rechenbar? Fragt die Werkzeugketten ab."""
    code, st = request("GET", "/status", url=args.url)
    out = {"server": args.url, "erreichbar": code < 400, "pipeline": st.get("status")}
    for name, path in (("solver", "/param_schema"), ("projekte", "/projects")):
        c, b = request("GET", path, url=args.url)
        out[name] = "ok" if c < 400 else f"HTTP {c}"
        if name == "projekte" and c < 400:
            lst = b if isinstance(b, list) else b.get("projects", [])
            out["projekte_anzahl"] = len(lst)
    return emit(out, args)


def cmd_geom(args) -> int:
    """Parameterschema lesen — Namen, Grenzen, Vorgaben.

    Der Server liefert ``{"params": [{key, desc, lo, hi, def, kind, ...}, ...]}``.
    Gefiltert wird über Schlüssel UND Beschreibung, damit auch die deutsche
    Benennung trifft ("Magnet" findet magThick).
    """
    code, sch = request("GET", "/param_schema", url=args.url)
    if code >= 400:
        return emit(sch, args) or EXIT_REMOTE
    params = sch.get("params", sch) if isinstance(sch, dict) else sch
    if not isinstance(params, list):
        return emit(sch, args)
    if args.name:
        q = args.name.lower()
        params = [p for p in params
                  if q in str(p.get("key", "")).lower() or q in str(p.get("desc", "")).lower()]
        if not params:
            return _die(f"kein Parameter enthält '{args.name}' — "
                        f"'geom' ohne Argument listet alle", EXIT_USAGE)
    if args.json or args.full:
        return emit(params, args)
    for p in params:
        rng = (f"{p.get('lo')}…{p.get('hi')}" if p.get("kind") == "num"
               else "/".join(map(str, p.get("choices", []))) or p.get("kind", ""))
        print(f"{str(p.get('key','')):<22} {str(p.get('def','')):>10}   [{rng}]  {p.get('desc','')}")
    print(f"[{len(params)} Parameter]")
    return EXIT_OK


def frischer_payload() -> dict:
    """Ein NEUTRALER Grundpayload aus den Schemavorgaben — ohne jedes Altprojekt.

    Warum es den geben muss
    -----------------------

    Bis hierher gab es genau drei Quellen fuer einen Payload: ``--payload`` (90
    Schluessel von Hand, die zuverlaessigste Art, einen Lauf zu verderben),
    ``--payload-file`` und ``--from-project``. Praktisch blieb damit nur
    ``--from-project last``, und daran haengt ein Verhalten, das niemand wollte:
    **jede neue Auslegung erbt Polzahl, Nutzahl, Magnetanordnung, Kuehlung und
    Werkstoffe der vorigen**, obwohl gerade das die Entscheidungen sind, die neu
    zu treffen waeren. Der Skill warnte davor in Prosa — und zeigte in JEDEM
    Beispiel ``--from-project last``, weil es nichts anderes gab. Ein Modell folgt
    den Beispielen, nicht der Warnung.

    ``--frisch`` schliesst die Luecke: die Vorgaben kommen aus
    ``ema_text2ema.SCHEMA``, **derselben** Quelle, aus der auch die Eingabemasken
    und ``/param_schema`` speisen — keine zweite Vorgabetabelle, die driften
    koennte. Das Ergebnis ist ein baubarer, absichtlich unentschiedener
    Ausgangspunkt: nichts daran ist optimiert, und genau deshalb muss danach der
    ``paarvergleich`` laufen.
    """
    import ema_text2ema as T2E

    payload: dict = {"geom": {}}
    for key, spec in T2E.SCHEMA.items():
        if "def" not in spec:
            continue
        wert = spec["def"]
        if spec.get("geom"):
            payload["geom"][key] = wert
        else:
            ziel = _ALIAS.get(key, key)
            payload[ziel] = wert
            spiegel = _MIRROR.get(ziel)
            if spiegel:                       # axial_len fuehrt geom.axialLen mit
                payload[spiegel[0]][spiegel[1]] = wert

    # Einpassen, sonst waere --frisch eine Sackgasse. Gemessen: die rohen
    # Schemavorgaben fallen durch das Layouttor (Taschenkollision, Ueberlappung
    # 4,37 mm) -- die Vorgaben sind je Feld sinnvoll, aber niemand hat sie je
    # ALS SATZ gegeneinander geprueft. Ein Startpunkt, den ``rotor-check`` sofort
    # ablehnt, treibt den Aufrufer genau dorthin zurueck, wovon ihn ``--frisch``
    # abbringen soll. ``ema_screen.einpassen`` ist dieselbe Einpassung, die auch
    # die Vorauswahl und der Paarvergleich fuer JEDE Option fahren -- also keine
    # zweite Vorstellung davon, was baubar heisst.
    # Fahrzyklus und Fahrzeug gehoeren SICHTBAR in den Payload. Fehlten sie, fiel
    # die Pipeline still auf ``cycle="wltp3"`` zurueck -- und das zieht zusaetzlich
    # die Autobahn-Volllastfahrt nach sich, gerechnet am 1600-kg-Pkw. Ein
    # Fahrrad-Nabenmotor bekam so 23 km WLTP und 220 km/h Autobahn, und
    # ``--set cycle=off`` wurde abgewiesen, weil der Schluessel nirgends stand.
    # Vorgabe ist "off": der Zyklus ist eine WAHL am Anfang (Verb ``zyklus``),
    # keine stille Voreinstellung.
    try:
        import ema_drivecycle
        payload["cycle"] = "off"
        payload["cycle_csv"] = ""
        payload["vehicle"] = dict(ema_drivecycle.DEFAULT_VEHICLE)
    except Exception:                                        # noqa: BLE001
        pass

    try:
        from ema_screen import einpassen
        pas = einpassen(payload["geom"])
        if not pas["ok"] or pas["s_koerper"] < 0.999:
            # Der Stegabstand wird aufgemacht, bis der Magnet UNGESCHMAELERT
            # hineinpasst -- nicht bis er irgendwie hineinpasst.
            #
            # Vorher stand hier ein Erst-Treffer-Abbruch, und der war der Grund
            # fuer die duennen Magnete: ``einpassen`` liefert zu JEDEM magDist das
            # groesstmoegliche ``s_koerper``, und dieser Massstab greift auf
            # ``magWidth`` UND ``magThick`` zugleich. Gemessen an den Vorgaben
            # (V, p=3, magAngle 120, Rotor-Aussen-Ø 188,6 mm):
            #
            #   magDist   s_koerper   magThick   magWidth
            #     2,5 mm     0,44       2,6 mm    19,7 mm   <- erster Treffer
            #     3,0 mm     0,60       3,6 mm    25,8 mm
            #     3,5 mm     0,77       4,6 mm    24,9 mm
            #     4,0 mm     1,00       6,0 mm    24,7 mm   <- ungeschmaelert
            #
            # Der erste Treffer nahm also 56 % der Magnetdicke weg, obwohl ein
            # halber Millimeter mehr Stegabstand den Magneten ganz gelassen
            # haette. Eine duenne Tasche kostet doppelt: ueber die Arbeitsgerade
            # ``h_m/(h_m + mu_r*k_c*g)`` faellt B_gap, und die
            # Entmagnetisierungsreserve faellt mit.
            d0 = float(payload["geom"].get("magDist", 2.0))
            schritt, grenze = 0.5, float(T2E.SCHEMA["magDist"]["hi"])
            bestes = pas if pas["ok"] else None
            d = d0
            while d < grenze:
                d += schritt
                versuch = einpassen(dict(payload["geom"], magDist=round(d, 2)))
                if not versuch["ok"]:
                    continue
                if bestes is None or versuch["s_koerper"] > bestes["s_koerper"] + 1e-9:
                    bestes = versuch
                if bestes["s_koerper"] >= 0.999:      # mehr geht nicht
                    break
            if bestes is not None:
                pas = bestes
        payload["geom"] = pas["geom"]
    except Exception:                          # noqa: BLE001 — lieber roh als gar nicht
        pass
    return payload


def _load_payload(args) -> dict:
    if getattr(args, "frisch", False):
        return frischer_payload()
    if args.payload_file:
        with open(args.payload_file, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("payload", data)
    if args.payload:
        return json.loads(args.payload)
    if args.from_project:
        pid = _newest_project() if args.from_project == "last" else args.from_project
        args._pid = pid          # wer den Payload stellt, benennt auch das Projekt
        meta = os.path.join(PROJECTS_ROOT, pid, "meta.json")
        try:
            with open(meta, encoding="utf-8") as f:
                return json.load(f)["payload"]
        except FileNotFoundError:
            raise SystemExit(_die(f"Kein meta.json fuer Projekt '{pid}' — "
                                  f"'projects' zeigt die vorhandenen.", EXIT_USAGE))
    raise SystemExit(_die("Kein Payload: --payload, --payload-file oder --from-project "
                          "angeben.", EXIT_USAGE))


# ── Parameter setzen (--set) ────────────────────────────────────────────────────
#
# Der Payload eines Laufs hat ~90 Schlüssel (63 davon in ``geom``); ihn von Hand zu
# schreiben ist für ein Modell die verlässlichste Art, einen Lauf zu verderben.
# Deshalb: eine bestehende Auslegung als Grundlage nehmen und einzelne Werte ändern.
#
# Zwei Wissensquellen, bewusst verschieden behandelt:
#   * ``/param_schema`` — der kuratierte Satz mit Grenzen, Typen und Auswahllisten.
#     Wer dort steht, wird GEPRUEFT und automatisch nach ``geom`` bzw. auf die obere
#     Ebene einsortiert (Feld ``in_geom``). Seit der Schemaerweiterung deckt er auch
#     die Feinparameter ab (``adv``: magLayers, poleArcFrac, conductorsPerSlot,
#     Flusssperren, Wuchtbohrungen …) — genau die, die vorher nur deshalb durchgingen,
#     weil sie zufaellig schon im Grundpayload standen: ohne Grenze, ohne Typ.
#   * der Grundpayload selbst — alles Weitere (reine CAD-Schalter wie ``genBearingA``
#     oder ``splineTeeth``). Kein Schema, also keine Grenzen; gesetzt wird dort, wo der
#     Schluessel schon liegt. Erfundene Namen fallen genau hier durch.
#
# Grenzverletzungen werden ABGEWIESEN, nicht stillschweigend geklemmt: ein geklemmter
# Wert sieht für den Aufrufer wie ein angenommener aus, und der Bericht rechnet dann
# eine andere Maschine als die bestellte. ``--force`` hebt die Pruefung auf.

PROJECTS_ROOT = os.path.expanduser("~/cae_projekte")

# Der Schemaname ist NICHT ueberall der Payloadname: /param_schema spiegelt das
# Vokabular von ``ema_text2ema.SCHEMA`` (Text -> Entwurf), der Payload das der Pipeline.
# Gegen ein reales meta.json geprueft weicht genau EIN Schluessel ab:
#   axialLen — ``ema_pipeline`` liest ``data["axial_len"]`` (:1547, :1619) von der oberen
#   Ebene. ``geom["axialLen"]`` existiert als Spiegel und wird nur als Rueckfall gelesen
#   (``server.py:2093``); ohne diese Tabelle landete der Wert in einem toten Schluessel.
_ALIAS  = {"axialLen": "axial_len"}            # Schemaname -> Payloadname
_MIRROR = {"axial_len": ("geom", "axialLen")}  # Payloadname -> mitzufuehrender Spiegel

_SCHEMA_CACHE: dict | None = None


def param_schema(url: str) -> dict:
    """{key: spec} aus /param_schema, einmal je Prozess geholt."""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        code, body = request("GET", "/param_schema", url=url)
        if code >= 400:
            raise SystemExit(_die(f"Parameterschema nicht lesbar (HTTP {code})", EXIT_REMOTE))
        _SCHEMA_CACHE = {p["key"]: p for p in (body or {}).get("params", [])}
    return _SCHEMA_CACHE


def _parse_value(raw: str):
    """JSON zuerst — so bleiben 12, 1.5, true, null und [1,2] das, was sie sind.
    Alles Uebrige ist Text (``magShape=v`` muss ohne Anfuehrungszeichen gehen).

    ``@datei`` liest den Wert aus einer Datei. Das ist fuer genau einen Fall da,
    der sonst nicht geht: ein selbst definierter Fahrzyklus (``cycle_csv``) sind
    hunderte Zeilen und taugt nicht als Kommandozeilenargument.
    """
    if raw.startswith("@"):
        with open(os.path.expanduser(raw[1:]), encoding="utf-8") as f:
            return f.read()
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _check_value(key: str, val, spec: dict):
    """(bereinigter Wert, Fehlertext|None) gegen eine Schema-Zeile."""
    if spec.get("kind") == "bool":
        # Nur echte Booleans. "true"/1 waeren bequem, aber ``genFluxBarrierQ=1`` liest
        # sich wie eine Anzahl — und die Pipeline prueft mit ``bool(...)``, wo jede
        # nichtleere Zeichenkette wahr ist. Ein Tippfehler wuerde dann still wirken.
        if not isinstance(val, bool):
            return val, f"{key}: true oder false erwartet, '{val}' bekommen"
        return val, None
    if spec.get("kind") == "num":
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            return val, f"{key}: Zahl erwartet, '{val}' bekommen"
        if spec.get("int"):
            if float(val) != int(val):
                return val, f"{key}: ganze Zahl erwartet, {val} bekommen"
            val = int(val)
        lo, hi = spec.get("lo"), spec.get("hi")
        if lo is not None and val < lo:
            return val, f"{key}: {val} liegt unter der Untergrenze {lo}"
        if hi is not None and val > hi:
            return val, f"{key}: {val} liegt ueber der Obergrenze {hi}"
        return val, None
    opts = [o.get("value") for o in (spec.get("options") or [])]
    if opts and val not in opts:
        return val, f"{key}: '{val}' unbekannt. Zulaessig: {', '.join(map(str, opts))}"
    return val, None


def _locate(key: str, payload: dict, schema: dict):
    """(Container, Name) — wohin der Wert gehoert; None, wenn der Name nirgends vorkommt."""
    if "." in key:                                    # expliziter Pfad, z. B. vehicle.mass_kg
        parts = key.split(".")
        node = payload
        for part in parts[:-1]:
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return (node, parts[-1]) if isinstance(node, dict) else None
    spec = schema.get(key)
    if spec is not None:
        geom = payload.setdefault("geom", {})
        want, other = (geom, payload) if spec.get("in_geom") else (payload, geom)
        if key not in want and key in other:
            return "drift"          # Schema und Payload sind sich uneins — s. _ALIAS
        return want, key
    if key in payload:
        return payload, key
    geom = payload.get("geom")
    if isinstance(geom, dict) and key in geom:
        return geom, key
    return None


def apply_sets(payload: dict, assignments, url: str, force: bool = False):
    """``--set`` anwenden. Sammelt ALLE Fehler, statt beim ersten abzubrechen —
    ein Agent soll in einem Durchgang erfahren, was falsch war."""
    import difflib
    schema = param_schema(url) if assignments else {}
    applied, errors = [], []
    for item in assignments or []:
        if "=" not in item:
            errors.append(f"'{item}': erwartet wird KEY=WERT")
            continue
        key, raw = item.split("=", 1)
        key = key.strip()
        spec_key = key                       # unter diesem Namen wird geprueft …
        key = _ALIAS.get(key, key)           # … unter diesem geschrieben
        target = _locate(key, payload, schema) if key == spec_key else (payload, key)
        if target == "drift":
            errors.append(f"'{key}': das Schema legt den Wert woanders ab, als der "
                          f"Payload ihn fuehrt — mit Punktpfad eindeutig setzen "
                          f"(geom.{key}=… oder einen anderen Grundpayload waehlen).")
            continue
        if target is None:
            pool = sorted(set(schema) | set(payload) | set(payload.get("geom") or {}))
            near = difflib.get_close_matches(key, pool, n=3, cutoff=0.6)
            errors.append(f"'{key}' steht weder im Schema noch im Grundpayload"
                          + (f" — gemeint war {', '.join(near)}?" if near
                             else " — 'geom' zeigt die bekannten Parameter"))
            continue
        container, name = target
        val = _parse_value(raw)
        # Auch der Punktpfad wird geprueft: 'geom.slotDepth=999' soll nicht stiller
        # an der Schemapruefung vorbeikommen als 'slotDepth=999'. Wer das braucht,
        # nimmt --force.
        spec = schema.get(spec_key.rsplit(".", 1)[-1])
        if spec is not None and not force:
            val, err = _check_value(spec_key, val, spec)
            if err:
                errors.append(err)
                continue
        old = container.get(name, "<nicht gesetzt>")
        container[name] = val
        note = f"{spec_key} -> {name}" if spec_key != name else None
        mirror = _MIRROR.get(name)
        if mirror and isinstance(payload.get(mirror[0]), dict) \
                and mirror[1] in payload[mirror[0]]:
            payload[mirror[0]][mirror[1]] = val
            note = f"{note or name} (+ {mirror[0]}.{mirror[1]})"
        applied.append({"key": spec_key, "alt": old, "neu": val,
                        "geprueft": spec is not None, "notiz": note})
    return applied, errors


def _newest_project() -> str:
    """Juengstes Projekt MIT meta.json — fuer ``--from-project last``.

    Die meta.json ist der Filter, nicht die Zierde: nur die volle Pipeline schreibt sie.
    Ein CAD-Vorschaulauf hinterlaesst ein Projektverzeichnis ohne Payload, und ohne
    diese Bedingung waehlte 'last' nach jedem ``run cad`` einen Ordner, aus dem sich
    kein Lauf ableiten laesst."""
    try:
        cands = [d for d in os.listdir(PROJECTS_ROOT)
                 if not d.startswith("_")
                 and os.path.exists(os.path.join(PROJECTS_ROOT, d, "meta.json"))]
    except OSError:
        cands = []
    if not cands:
        raise SystemExit(_die(
            f"Kein Projekt mit meta.json unter {PROJECTS_ROOT} — 'last' braucht eine "
            f"gerechnete Auslegung als Grundlage, eine CAD-Vorschau genuegt nicht.",
            EXIT_USAGE))
    return max(cands, key=lambda d: os.path.getmtime(os.path.join(PROJECTS_ROOT, d)))


# stage -> (Startroute, Statusroute). Die Statusroute ist NICHT ableitbar: jede Stufe
# hat ihren eigenen Zustand im Server (``_cad_state``, ``_em3d_state`` …), und nur die
# volle Pipeline meldet sich unter ``/status``. Wer hier ``/status`` fuer alle nimmt,
# bekommt beim CAD-Lauf den Zustand der Pipeline zurueck — also "idle" — und haelt den
# Lauf faelschlich fuer fertig.
RUN_ROUTES = {
    "analyse":    ("/analyse",     "/status"),   # volle Pipeline: CAD, 2D-Feld, Struktur, Thermik, Zyklus
    "cad":        ("/cad_preview", "/cad_preview/status"),   # nur die Geometrie bauen
    "em3d":       ("/em3d",        "/em3d/status"),          # 3D-Elmer-Feld
    "em3d_sweep": ("/em3d_sweep",  "/em3d/status"),
    "cfd":        ("/cfd",         "/cfd/status"),           # OpenFOAM-Kühlung
    "oilspray":   ("/oilspray",    "/oilspray/status"),      # Blender/Mantaflow-Ölnebel
    "smoke":      ("/smoke_test",  "/smoke_test/status"),
}


def cmd_run(args) -> int:
    route = RUN_ROUTES.get(args.stage)
    if route is None:
        return _die(f"Unbekannte Stufe '{args.stage}'. Bekannt: "
                    f"{', '.join(sorted(RUN_ROUTES))}", EXIT_USAGE)
    path, status_path = route
    payload = _load_payload(args)

    # Ein 3D-Lauf gehoert in DAS Projekt, dessen Payload er rechnet. Ohne
    # ``project_id`` nimmt ``/em3d`` das im Server zuletzt aktive Projekt -- und
    # das muss nicht dasselbe sein; dann liegen 2D und 3D derselben Maschine in
    # zwei Projekten und ``em3d.compare_2d`` vergleicht zwei Fremde. Steht der
    # Schluessel erst einmal im Payload, ist er auch mit ``--set`` erreichbar.
    if args.stage in ("em3d", "em3d_sweep"):
        pid = getattr(args, "_pid", "")
        if pid and not payload.get("project_id"):
            payload["project_id"] = pid

    # Fahrzyklus aus dem gemeinsamen Speicher (Verb ``zyklus``) einsetzen --
    # Zyklus UND Fahrzeug, nie einzeln.
    zyk = getattr(args, "zyklus", None)
    if zyk:
        import ema_zyklen
        try:
            ema_zyklen.anwenden(payload, zyk)
        except ValueError as e:
            return _die(str(e), EXIT_USAGE)

    applied, errors = apply_sets(payload, getattr(args, "set", None) or [],
                                 args.url, force=getattr(args, "force", False))
    if errors:
        for e in errors:
            print(f"FEHLER: {e}", file=sys.stderr)
        return _die(f"{len(errors)} Zuweisung(en) abgewiesen — nichts gestartet.",
                    EXIT_USAGE)
    for a in applied:
        mark = "" if a["geprueft"] else "  (ohne Schema, ungeprueft)"
        if a.get("notiz"):
            mark += f"  [{a['notiz']}]"
        print(f"  {a['key']}: {a['alt']} -> {a['neu']}{mark}")
    if applied and args.stage not in ("cad", "smoke"):
        geom_touched = any(a["geprueft"] or "." in a["key"] for a in applied)
        if geom_touched:
            print("  Hinweis: die Schemagrenzen sagen NICHT, ob die Geometrie baubar "
                  "ist. Bei geaenderter Geometrie zuerst 'run cad --wait' (~1 min).")
    # Welcher Lastfall gerechnet wird, muss VOR dem Lauf dastehen und nicht erst
    # im Ergebnis: eine volle Analyse dauert Stunden, und ein Fahrzyklus, der
    # nicht zur Maschine passt, faellt sonst erst am Bericht auf.
    if args.stage in ("analyse",):
        print("  " + _lastfall_zeile(payload))

    if getattr(args, "dry_run", False):
        print(f"[Probelauf — {path} NICHT aufgerufen]")
        return emit(payload, args)

    code, body = request("POST", path, payload, url=args.url)
    if code >= 400:
        emit(body, args)
        return EXIT_REMOTE
    print(json.dumps({"gestartet": args.stage, "route": path, **(body or {})},
                     ensure_ascii=False))
    if args.wait:
        return _wait(args, status_path=status_path)
    print(f"Laeuft. Fortschritt: cae_cli.py wait --status-path {status_path}")
    return EXIT_OK


def cmd_lernen(args) -> int:
    """Selbstlernfunktion: gemessene Regeln aus dem eigenen Bestand + belegte Erfahrungen.

    Exit: 0 = ok, 2 = Erfahrung ohne Beleg abgewiesen."""
    import ema_lernen as L

    if args.was == "zeige":
        if getattr(args, "json", False):
            return emit({"gemessen": L.gemessene_regeln(),
                         "erfahrungen": L.erfahrungen()}, args)
        print(L.als_text())
        return EXIT_OK

    if args.was == "merke":
        if not args.regel or not args.beleg:
            return _die("'lernen merke' braucht --regel und --beleg. "
                        "Eine Erfahrung ohne Beleg wird nicht angenommen.", EXIT_USAGE)
        try:
            satz = L.merke(args.regel, args.beleg, quelle=args.quelle or "")
        except L.OhneBeleg as e:
            return _die(str(e), EXIT_USAGE)
        emit(satz, args)
        print(f"  gemerkt: {satz['regel']}")
        return EXIT_OK

    if args.was == "probieren":
        # Der geplante Versuch. Bisher lernte dieses Modul nur aus dem, was zufaellig
        # gerechnet wurde -- was nie jemand ausprobiert hat, konnte es nicht wissen.
        # Hier wird der Raum absichtlich abgefahren: jede Bauform ueber jede Polzahl.
        import ema_screen as SC

        payload = _load_payload(args)
        if not payload.get("geom"):
            return _die("Keine Geometrie im Payload — probieren braucht geom.", EXIT_USAGE)
        achsen = dict(SC.VERSUCH_ACHSEN)
        for name, roh in (("p", args.pole), ("slots", args.nuten),
                          ("magShape", args.formen)):
            if roh:
                werte = [w.strip() for w in roh.split(",") if w.strip()]
                achsen[name] = werte if name == "magShape" else [int(w) for w in werte]

        befund = SC.durchprobieren(payload, achsen=achsen, n_max=args.n_max)
        if getattr(args, "json", False):
            emit(befund, args)
        else:
            print(SC.versuch_text(befund))

        if args.merken:
            aufgenommen = L.aus_versuch(befund, quelle=args.quelle or "lernen probieren")
            neu_n = sum(1 for a in aufgenommen if "abgewiesen" not in a)
            print(f"\n  {neu_n} Regeln in den Lernspeicher aufgenommen "
                  f"(sichtbar mit 'lernen zeige').")
            for a in aufgenommen:
                if "abgewiesen" in a:
                    print(f"    abgewiesen: {a['abgewiesen']}")
        else:
            print("\n  Nichts gemerkt. Mit --merken werden die Befunde als belegte "
                  "Regeln abgelegt.")
        return EXIT_OK

    if args.was == "pruefe":
        p = L.pruefe()
        emit(p, args)
        if not getattr(args, "json", False):
            print(f"  Bestand: {p['laeufe_jetzt']} Laeufe · "
                  f"{len(p['frisch'])} Erfahrungen frisch · "
                  f"{len(p['nachzupruefen'])} nachzupruefen")
            for x in p["nachzupruefen"]:
                print(f"    • {x['regel'][:70]} ({x['neue_laeufe_seither']} Laeufe seither)")
        return EXIT_OK

    return _die(f"unbekannt: {args.was}", EXIT_USAGE)


def cmd_recherche(args) -> int:
    """Internetrecherche — Websuche und Seitenabruf. Exit: 0 = ok, 1 = nichts gefunden."""
    import ema_recherche as R

    if args.was == "suche":
        if not args.frage:
            return _die("'recherche suche' braucht eine Frage.", EXIT_USAGE)
        try:
            t = R.suche(" ".join(args.frage), treffer=args.treffer)
        except Exception as e:                              # noqa: BLE001
            return _die(f"Suche fehlgeschlagen: {e}", EXIT_REMOTE)
        if not t:
            return _die("Keine Treffer.", EXIT_REMOTE)
        emit(t, args)
        if not getattr(args, "json", False):
            print(R.als_text(t, "suche"))
        return EXIT_OK

    if args.was == "hole":
        if not args.frage:
            return _die("'recherche hole' braucht eine Adresse.", EXIT_USAGE)
        try:
            d = R.hole(args.frage[0], max_zeichen=args.zeichen)
        except Exception as e:                              # noqa: BLE001
            return _die(f"Abruf fehlgeschlagen: {e}", EXIT_REMOTE)
        if d.get("fehler"):
            return _die(f"{d['fehler']} ({d['adresse']})", EXIT_REMOTE)
        emit(d, args)
        if not getattr(args, "json", False):
            print(R.als_text(d, "hole"))
        return EXIT_OK

    if args.was == "merke":
        adresse = args.adresse or (args.frage[0] if args.frage else None)
        if not args.projekt or not adresse:
            return _die("'recherche merke' braucht --projekt und --adresse.", EXIT_USAGE)
        pfad = _projekt_pfad(args.projekt)
        if not pfad:
            return _die(f"Projekt nicht gefunden: {args.projekt}", EXIT_USAGE)
        werte = []
        for w in (args.wert or []):
            # Form:  groesse=wert einheit :: Zitat
            try:
                kopf, zitat = w.split("::", 1)
                links, rechts = kopf.split("=", 1)
                stueck = rechts.strip().split(None, 1)
                werte.append({"groesse": links.strip(),
                              "wert": float(stueck[0].replace(",", ".")),
                              "einheit": stueck[1] if len(stueck) > 1 else "",
                              "zitat": zitat.strip()})
            except (ValueError, IndexError):
                return _die(f"--wert falsch aufgebaut: {w!r}\n"
                            "  Erwartet: \"groesse=ZAHL EINHEIT :: die Belegstelle\"",
                            EXIT_USAGE)
        try:
            import ema_recherche as R
            erg = R.speichere(pfad, adresse, notiz=args.notiz or "",
                              bilder=args.bild or [], werte=werte)
        except Exception as e:                              # noqa: BLE001
            return _die(f"Ablegen fehlgeschlagen: {e}", EXIT_REMOTE)
        if erg.get("fehler"):
            return _die(f"{erg['fehler']} ({erg.get('adresse')})", EXIT_REMOTE)
        emit(erg, args)
        print(f"  abgelegt unter {erg['abgelegt']}")
        print(f"  Bilder: {sum(1 for b in erg['bilder'] if b.get('datei'))} geladen, "
              f"Werte: {erg['werte_uebernommen']} in die Datenbank")
        for a in erg["werte_abgewiesen"]:
            print(f"  ABGEWIESEN: {a}")
        return EXIT_OK

    if args.was == "quellen":
        if not args.projekt:
            return _die("'recherche quellen' braucht --projekt.", EXIT_USAGE)
        pfad = _projekt_pfad(args.projekt)
        if not pfad:
            return _die(f"Projekt nicht gefunden: {args.projekt}", EXIT_USAGE)
        import ema_recherche as R
        q = R.quellen(pfad)
        if not q:
            return _die("Fuer dieses Projekt ist nichts abgelegt.", EXIT_REMOTE)
        emit(q, args)
        if not getattr(args, "json", False):
            print(R.quellen_markdown(pfad))
        return EXIT_OK

    return _die(f"unbekannt: {args.was}", EXIT_USAGE)


def _projekt_pfad(kennung: str) -> str | None:
    """Projekt-Id oder 'last' -> Pfad unter ~/cae_projekte.

    Die Aufloesung steht in ``ema_steckbrief`` und nicht hier, weil der Server
    sie ueber ``/agent/steckbrief`` genauso braucht. Zwei Auflegungen von 'last'
    waeren zwei, die auseinanderlaufen -- und ausgerechnet bei 'last' faellt das
    erst auf, wenn zwei Werkzeuge auf verschiedene Projekte zeigen.
    """
    import ema_steckbrief
    return ema_steckbrief.projekt_pfad(kennung) or None


def cmd_db(args) -> int:
    """Rechnungsdatenbank: importieren, auflisten, zeigen, vergleichen, Guete.

    Rein lokal — liest ~/cae_projekte und schreibt ~/cae_projekte/_db/rechnungen.db.
    Exit: 0 = ok, 1 = nichts gefunden."""
    import ema_db as DB

    conn = DB.oeffne()

    if args.was == "import":
        bilanz = DB.importiere_alle(conn)
        emit(bilanz, args)
        print(f"  {bilanz['vollstaendig']} vollstaendige, {bilanz['abgebrochen']} "
              f"abgebrochene Laeufe eingelesen")
        return EXIT_OK

    if args.was == "liste":
        zeilen = [dict(r) for r in DB.liste(conn, nur_vollstaendig=not args.alle)]
        if not zeilen:
            return _die("Keine Laeufe in der Datenbank — erst 'db import'.", EXIT_REMOTE)
        emit(zeilen, args)
        if not getattr(args, "json", False):
            for r in zeilen[:args.limit]:
                fest = {1: "gruen", 0: "rot"}.get(r["fest_ok"], "-")
                b = f"{r['b_gap']:.3f}" if r["b_gap"] else "-"
                pm = f"{r['p_max']:.0f}" if r["p_max"] else "-"
                print(f"  {r['lauf_id']:3d}  {(r['zeitpunkt'] or '')[:10]}  "
                      f"{(r['projekt_name'] or '')[:30]:32s} B_gap {b:>6s}  "
                      f"P {pm:>4s} kW  Festigkeit {fest:5s} {r['notiz'] or ''}")
        return EXIT_OK

    if args.was == "zeige":
        if not args.lauf:
            return _die("'db zeige' braucht --lauf <id|projekt_id>.", EXIT_USAGE)
        d = DB.zeige(conn, args.lauf)
        if not d:
            return _die(f"Lauf {args.lauf} nicht gefunden.", EXIT_REMOTE)
        emit(d, args)
        return EXIT_OK

    if args.was == "guete":
        if not args.lauf:
            return _die("'db guete' braucht --lauf <id|projekt_id>.", EXIT_USAGE)
        g = DB.guete(conn, args.lauf)
        if not g:
            return _die(f"Lauf {args.lauf} nicht gefunden.", EXIT_REMOTE)
        emit(g, args)
        if not getattr(args, "json", False):
            print(f"\n  Stufen gerechnet : {', '.join(g['stufen']) or 'KEINE (abgebrochen)'}")
            print(f"  Kennwerte je Verfahren:")
            for m, n in g["kennwerte_je_methode"].items():
                print(f"    {m:14s} {n:3d}   {DB.METHODEN.get(m, '')}")
            if g["fem_erwartet"]:
                print(f"  Festigkeit       : {g['fem_geliefert']}/{g['fem_erwartet']} "
                      f"Werte geliefert, Loeser {g['fem_loeser'] or '-'}, "
                      f"{g['fem_aufloesung'] or 'Aufloesung unbekannt'}")
            print(f"  Bilder vorhanden : {g['bilder_vorhanden']}")
            print(f"  Tore             : " +
                  ", ".join(f"{k}={'gruen' if v else 'rot'}" for k, v in g["tore"].items()))
        return EXIT_OK

    if args.was == "vergleich":
        groessen = args.groessen or ["B_gap_T", "Kt_Nm_per_A", "P_max_kW",
                                     "max_safe_rpm", "safety_factor_fem", "mass_g"]
        zeilen = DB.vergleiche(conn, groessen, args.lauf_liste)
        if not zeilen:
            return _die("Keine vergleichbaren Laeufe gefunden.", EXIT_REMOTE)
        emit(zeilen, args)
        if not getattr(args, "json", False):
            kopf = f"  {'Projekt':34s}" + "".join(f"{g[:13]:>15s}" for g in groessen)
            print(kopf); print("  " + "-" * (len(kopf) - 2))
            for z in zeilen:
                zeile = f"  {z['projekt'][:33]:34s}"
                for g in groessen:
                    v = z[g]
                    zeile += f"{v:>15.4g}" if isinstance(v, (int, float)) else f"{str(v)[:13]:>15s}"
                print(zeile)
            # Die Herkunft je Spalte dazu — sonst sehen ungleiche Zahlen gleich aus.
            print("\n  Herkunft der Spalten:")
            for g in groessen:
                m = next((z[g + "__methode"] for z in zeilen if z.get(g + "__methode")), "?")
                print(f"    {g:22s} {m:14s} {DB.METHODEN.get(m, '')}")
        return EXIT_OK

    return _die(f"unbekannt: {args.was}", EXIT_USAGE)


def _geom_und_material(args):
    """Payload -> (geom, mat, rpm). Gemeinsam fuer 'struktur' und 'topopt'."""
    payload = _load_payload(args)
    applied, errors = apply_sets(payload, getattr(args, "set", None) or [],
                                 args.url, force=getattr(args, "force", False))
    if errors:
        for e in errors:
            print(f"FEHLER: {e}", file=sys.stderr)
        raise SystemExit(_die(f"{len(errors)} Zuweisung(en) abgewiesen.", EXIT_USAGE))
    for a in applied:
        print(f"  {a['key']}: {a['alt']} -> {a['neu']}")

    geom = payload.get("geom") or {}
    if not geom:
        raise SystemExit(_die("Keine Geometrie im Payload.", EXIT_USAGE))

    from ema_pipeline import LAMINATES
    mat = LAMINATES.get(payload.get("rotor_lam", "m270_35a"),
                        LAMINATES["m270_35a"])
    rpm = float(getattr(args, "rpm", None)
                or (payload.get("target") or {}).get("n_max") or 15000.0)
    return geom, mat, rpm


def cmd_struktur(args) -> int:
    """Rotor-Festigkeit auf dem EIGENEN Rechensatz — ohne FreeCAD, in Sekunden.

    Wahlweise mit CalculiX, mit Z88 oder mit beiden. 'beide' rechnet dasselbe Netz
    zweimal und stellt die Zahlen gegenueber; das prueft Loeser und Rechensatz,
    NICHT das Netz und nicht das Modell.
    Exit: 0 = gerechnet, 1 = ein Loeser hat nicht geliefert."""
    import tempfile

    geom, mat, rpm = _geom_und_material(args)
    import ema_deck as D

    sektor = args.solver == "ccx" and not args.voll
    try:
        netz = D.baue(geom, mesh_mm=args.mesh, ordnung=args.ordnung,
                      sektoren=1 if sektor else 0)
    except Exception as e:                                  # gmsh meldet vielerlei
        return _die(f"Vernetzung fehlgeschlagen: {e}", EXIT_REMOTE)

    print(f"  Netz: {netz.n_knoten:,} Knoten, {netz.n_elemente:,} Tet"
          f"{4 if args.ordnung == 1 else 10}, "
          f"{'ein Polsektor' if sektor else 'voller Rotor'}, {rpm:.0f} min-1")

    ordner = args.out or tempfile.mkdtemp(prefix="cae_struktur_")
    os.makedirs(ordner, exist_ok=True)
    ergebnis = {"netz": {"knoten": netz.n_knoten, "elemente": netz.n_elemente,
                         "sektor": bool(sektor), "mesh_mm": args.mesh,
                         "ordnung": args.ordnung},
                "rpm": rpm, "werkstoff": mat["label"], "ordner": ordner}

    if args.solver in ("ccx", "beide"):
        pfad = D.schreibe_inp(netz, mat, rpm, os.path.join(ordner, "rotor.inp"))
        r = D.loese_ccx(pfad, kerne=args.kerne)
        if r["solver_status"] != "OK":
            return _die(f"CalculiX: {r.get('meldung', r['solver_status'])}", EXIT_REMOTE)
        ergebnis["calculix"] = D.kennzahlen(
            netz, D.lies_dat_spannungen(r["dat"]), mat["yield_mpa"])

    if args.solver in ("z88", "beide"):
        import ema_z88 as Z
        ok, warum = Z.verfuegbar()
        if not ok:
            return _die(f"Z88 nicht einsatzbereit: {warum}", EXIT_REMOTE)
        if sektor:
            return _die("Z88 kann keinen Polsektor rechnen (weder zyklische Symmetrie "
                        "noch schiefe Symmetrieebenen). --voll angeben.", EXIT_USAGE)
        zp = os.path.join(ordner, "z88")
        Z.schreibe_satz(netz, mat, rpm, zp, kerne=args.kerne)
        r = Z.loese(zp, netz=netz)
        if r["solver_status"] != "OK":
            return _die(f"Z88: {r.get('meldung', r['solver_status'])}", EXIT_REMOTE)
        ergebnis["z88"] = Z.kennzahlen_aus_lauf(netz, zp, mat["yield_mpa"])
        ergebnis["z88"]["solver"] = r["solver"]

    # Die analytische Formel als dritte, unabhaengige Zahl.
    from ema_rotorcheck import _bore_hoop_mpa
    w = 2 * math.pi * rpm / 60.0
    a_m, b_m = netz.r_shaft / 1e3, netz.r_rot / 1e3
    nu = float(mat["nu"])
    ergebnis["analytisch"] = {
        "bore_hoop_eb_spannung_MPa": round(
            _bore_hoop_mpa(a_m, b_m, mat["density"], w, nu), 2),
        "bore_hoop_eb_verzerrung_MPa": round(
            _bore_hoop_mpa(a_m, b_m, mat["density"], w, nu / (1 - nu)), 2),
        "hinweis": "frei rotierender Ring OHNE Magnettaschen"}

    emit(ergebnis, args)
    if args.solver == "beide":
        c, z = ergebnis["calculix"], ergebnis["z88"]
        print("\n  Groesse                        CalculiX          Z88      Abw.")
        for schl in ("stress_peak_MPa", "stress_p99_MPa",
                     "bore_hoop_median_MPa", "safety_factor_p99"):
            if schl in c and schl in z:
                d = 100 * abs(c[schl] - z[schl]) / max(abs(c[schl]), 1e-9)
                print(f"  {schl:28s} {c[schl]:10.2f} {z[schl]:12.2f} {d:7.2f} %")
        print("  Gleiches Netz, gleiche Last: das prueft die Loeser, nicht das Modell.")
    return EXIT_OK


def cmd_topopt(args) -> int:
    """Topologieoptimierung des Rotorblechs (SKO oder SIMP) auf dem Polsektor.

    Ergebnis ist ein DICHTEFELD, kein Bauteil. Exit: 0 = gelaufen."""
    import tempfile

    geom, mat, rpm = _geom_und_material(args)
    import ema_deck as D
    import ema_topopt as T

    try:
        netz = D.baue(geom, mesh_mm=args.mesh, ordnung=1,
                      sektoren=0 if args.solver == "z88" else 1)
    except Exception as e:
        return _die(f"Vernetzung fehlgeschlagen: {e}", EXIT_REMOTE)

    fest = T.sperrbereiche(netz, geom, bohrung_mm=args.fest_bohrung,
                           rand_mm=args.fest_rand, tasche_mm=args.fest_tasche)
    print(f"  Netz: {netz.n_elemente:,} Tets, davon {len(fest):,} gesperrt "
          f"({100*len(fest)/netz.n_elemente:.0f} %) -> "
          f"{netz.n_elemente-len(fest):,} optimierbar")
    if len(fest) >= netz.n_elemente:
        return _die("Die Sperrbereiche decken alles ab — --fest-* verkleinern.",
                    EXIT_USAGE)

    ordner = args.out or tempfile.mkdtemp(prefix="cae_topopt_")

    def melde(z):
        print(f"  Iter {z['iteration']:3d}  Volumenanteil {z['volumenanteil']:.3f}"
              f"  Spitze {z['stress_peak_MPa']:7.1f} MPa  {z['sekunden']:.2f}s")

    try:
        if args.verfahren == "sko":
            r = T.sko(netz, geom, mat, rpm, ordner, iterationen=args.iterationen,
                      vol_ziel=args.vol_ziel, loeser=args.solver, kerne=args.kerne,
                      sperr=fest, melde=melde)
        else:
            r = T.simp(netz, geom, mat, rpm, ordner,
                       vol_ziel=args.vol_ziel if args.vol_ziel is not None else 0.6,
                       iterationen=args.iterationen, loeser=args.solver,
                       kerne=args.kerne, sperr=fest, melde=melde)
    except T.TopOptFehler as e:
        return _die(str(e), EXIT_REMOTE)

    lese = T.ableseempfehlung(netz, geom, r)
    aus = {"verfahren": r["verfahren"], "loeser": r["loeser"], "rpm": rpm,
           "iterationen": len(r["verlauf"]), "verlauf": r["verlauf"],
           "sigma_ref_MPa": r.get("sigma_ref_MPa"), "ordner": ordner,
           "ableseempfehlung": lese}
    emit(aus, args)
    print(f"\n  {lese['empfehlung']}")
    print(f"  {lese['hinweis']}")
    return EXIT_OK


def _lastfall_zeile(payload: dict) -> str:
    """Fahrzyklus und Fahrzeug in einer Zeile — der Lastfall auf einen Blick."""
    zyk = payload.get("cycle")
    fz = payload.get("vehicle") or {}
    if zyk is None:
        return ("Lastfall: KEIN Zyklus im Payload — die Pipeline nimmt dann 'wltp3' "
                "(+ Autobahn-Volllast) am 1600-kg-Pkw")
    if zyk == "off":
        return "Lastfall: kein Fahrzyklus (cycle=off) — nur Auslegungspunkt und Kennfeld"
    name = zyk
    if zyk == "csv":
        name = "eigener Zyklus (csv)"
    elif zyk == "wltp3":
        name = "wltp3 (+ Autobahn-Volllast)"
    teile = [f"Lastfall: {name}"]
    if fz:
        teile.append(f"Fahrzeug {fz.get('mass_kg', '?')} kg, Rad "
                     f"{fz.get('r_wheel_m', '?')} m, Uebersetzung "
                     f"{fz.get('gear_ratio', '?')}")
    else:
        teile.append("Fahrzeug: Vorgabe (1600 kg Pkw, Uebersetzung 9,5)")
    return " · ".join(teile)


# Was VOR dem ersten Rechenlauf feststehen muss. Die Liste ist kurz und geschlossen:
# das sind genau die Angaben, ohne die ein Lauf zwar durchlaeuft, aber eine andere
# Maschine beschreibt als die bestellte. Je Punkt steht dabei, WOHER die Antwort
# kommen kann -- und ob es dafuer eine oertliche Quelle gibt oder nur die Rueckfrage
# bzw. die Recherche.
PFLICHTPUNKTE = [
    dict(name="einsatz", frage="Wofuer ist die Maschine? (Fahrzeug, Geraet, Pruefstand)",
         quelle="aufgabe", hinweis="steht in der Aufgabe oder wird erfragt"),
    # Die erste Entscheidung ueberhaupt -- und die einzige, die ueber die
    # Bedeutung fast aller uebrigen entscheidet. Steht sie nicht in der Aufgabe,
    # ist die Voreinstellung PSM, und die ist dann eine ANNAHME, keine Wahl.
    dict(name="maschinenart", frage="PSM, ASM, SynRM oder EESM? (geom.machineType)",
         quelle="paarvergleich",
         hinweis="Vorgabe pmsm. 'paarvergleich --achse maschinenart' stellt sie "
                 "gegeneinander. Getragen: analytisch pmsm+asm; Feld/CAD/3D nur pmsm"),
    dict(name="betriebspunkt", frage="Moment und Drehzahl im Dauerbetrieb",
         quelle="aufgabe", hinweis="load_nm, rpm_from/rpm_to — nicht ableitbar"),
    dict(name="lastfall", frage="Fahrzyklus UND Fahrzeug (oder ausdruecklich keiner)",
         quelle="zyklen", hinweis="'zyklus liste'; passt keiner: selbst anlegen"),
    dict(name="bauraum", frage="Aussendurchmesser, Baulaenge, Wellendurchmesser",
         quelle="aufgabe", hinweis="die Schemagrenzen sind die Suchbox, nicht der Bauraum"),
    dict(name="kuehlung", frage="Welche Kuehlung ist vorgesehen?",
         quelle="schema", hinweis="natural | air | water | oil"),
    dict(name="umgebung", frage="Umgebungstemperatur",
         quelle="schema", hinweis="T_ambient, Vorgabe 25 °C"),
    dict(name="werkstoffe", frage="Magnet- und Blechwerkstoff",
         quelle="schema", hinweis="entscheidet der Paarvergleich, wenn nichts vorgegeben ist"),
    dict(name="anordnung", frage="Magnetanordnung, Pol- und Nutzahl",
         quelle="paarvergleich", hinweis="'paarvergleich --frisch' entscheidet das"),
    dict(name="stromrichter", frage="Zwischenkreisspannung und Strangstromgrenze",
         quelle="fest", hinweis="FEST verdrahtet: 800 V / 800 A (ema_analysis.INVERTER_*). "
                                "Fuer ein 48-V-System ist das falsch und NICHT einstellbar "
                                "— im Bericht sagen"),
    dict(name="sicherheit", frage="Geforderter Sicherheitsfaktor, Isolierklasse, Grenztemperaturen",
         quelle="fest", hinweis="SF 1,5 · Klasse H 180 °C · Magnetgrenze aus der "
                                "Werkstofftabelle ('sicherheit' prueft danach)"),
]


def cmd_maschinenart(args) -> int:
    """Welche Maschinenarten es gibt und welche Rechenstufe jede heute traegt.

    Der Sinn ist die zweite Spalte: sie sagt, wo eine Art **aufhoert**. Ohne sie
    stuende die Wahl frei und der Lauf schluege erst spaeter fehl -- oder,
    schlimmer, er liefe durch und gaebe PSM-Zahlen unter fremdem Namen heraus.

    Exit: 0 = ok.
    """
    import ema_maschinenart as MA

    if getattr(args, "code", None):
        try:
            art = MA.hole(args.code)
        except MA.ArtNichtUnterstuetzt as e:
            print(e); return 2
        print(f"{art.code} — {art.label}")
        print(f"  Erregung:            {art.erregung}")
        print(f"  Permanentmagnete:    {'ja' if art.hat_magnete else 'nein'}")
        print(f"  Laeuferwicklung:     {'ja' if art.hat_laeuferwicklung else 'nein'}")
        print(f"  Schlupf:             {'ja' if art.hat_schlupf else 'nein'}")
        print(f"  Fluss einstellbar:   {'ja' if art.stellbarer_fluss else 'nein'}")
        for st in MA.STUFEN:
            zeichen = "getragen" if st in art.stufen else "NICHT getragen"
            print(f"  {MA.STUFEN_LABEL[st]:<34} {zeichen}")
        if art.ohne_bedeutung:
            print("  ohne Bedeutung fuer diese Art: " + ", ".join(art.ohne_bedeutung))
        if art.hinweis:
            print("  " + art.hinweis)
        return 0

    print(MA.uebersicht())
    print()
    print("Setzen:   --set geom.machineType=asm")
    print("Vergleich: paarvergleich --achse maschinenart")
    return 0


def cmd_aufgabe(args) -> int:
    """Eine neue Aufgabe zerlegen: was ist gefordert, was steht schon da, was fehlt.

    Der Schritt VOR der Recherche. Ins Netz zu gehen ist billig, aber ungezielt:
    ohne zu wissen, welche Angabe fehlt, sucht man nach dem, was man ohnehin schon
    hat. Deshalb wird hier zuerst der eigene Bestand befragt — abgelegte
    Fahrzyklen, gemessene Regeln, gerechnete Laeufe, die Wissensbasis und die
    recherchierten Vergleichswerte — und erst was dort NICHT steht, ist ein Grund
    fuer eine Suche oder eine Rueckfrage.

    Exit: 0 = ok, 2 = Bedienfehler.
    """
    text = " ".join(args.beschreibung or []).strip()
    if not text:
        return _die("'aufgabe' braucht die Aufgabenbeschreibung als Text.", EXIT_USAGE)

    bestand = {}

    # Was oertlich vorhanden ist -- jede Quelle einzeln, damit ein fehlendes
    # Teilstueck (kein Ollama, keine Datenbank) den Rest nicht mitnimmt.
    try:
        import ema_db
        import ema_zyklen
        conn = ema_db.oeffne()
        bestand["zyklen"] = [z for z in ema_zyklen.liste(conn) if z["herkunft"] == "eigen"]
        bestand["laeufe"] = len(ema_db.liste(conn))
    except Exception as e:                                   # noqa: BLE001
        bestand["zyklen"], bestand["laeufe"] = [], f"nicht lesbar ({e})"
    try:
        import ema_lernen
        bestand["regeln"] = len(ema_lernen.gemessene_regeln() or [])
        bestand["erfahrungen"] = len(ema_lernen.erfahrungen() or [])
    except Exception:                                        # noqa: BLE001
        bestand["regeln"] = bestand["erfahrungen"] = 0
    try:
        import ema_rag
        treffer = ema_rag.search(text, k=4) or []
        bestand["wissen"] = [{"dokument": t.get("doc") or t.get("title") or "?",
                              "auszug": (t.get("text") or "")[:160]} for t in treffer]
    except Exception as e:                                   # noqa: BLE001
        bestand["wissen"] = []
        bestand["wissen_fehler"] = str(e)

    offen = []
    zeilen = []
    for pkt in PFLICHTPUNKTE:
        stand, wie = "OFFEN", pkt["hinweis"]
        if pkt["quelle"] == "zyklen" and bestand["zyklen"]:
            stand = "PRUEFEN"
            wie = ("abgelegt: " + ", ".join(z["name"] for z in bestand["zyklen"][:5])
                   + " — passt einer? sonst neu anlegen")
        elif pkt["quelle"] == "fest":
            # Nicht „ableitbar", sondern unverrueckbar: das sind Annahmen der
            # Toolchain, die man nur NENNEN, nicht einstellen kann.
            stand = "FEST"
        elif pkt["quelle"] in ("schema", "paarvergleich"):
            stand = "ABLEITBAR"
        zeilen.append((pkt["name"], stand, pkt["frage"], wie))
        if stand == "OFFEN":
            offen.append(pkt)

    if getattr(args, "json", False):
        return emit({"aufgabe": text, "bestand": bestand,
                     "punkte": [dict(name=n, stand=s, frage=f, hinweis=h)
                                for n, s, f, h in zeilen],
                     "offen": [p["name"] for p in offen]}, args)

    print(f"Aufgabe: {text}\n")
    print("Was vor dem ersten Lauf feststehen muss")
    print("-" * 72)
    for name, stand, frage, wie in zeilen:
        print(f"  [{stand:9}] {name:14} {frage}")
        print(f"{'':14} {wie}")
    print()
    print("Eigener Bestand")
    print("-" * 72)
    print(f"  gerechnete Laeufe in der Datenbank : {bestand['laeufe']}")
    print(f"  gemessene Regeln / Erfahrungen     : {bestand['regeln']} / {bestand['erfahrungen']}")
    print(f"  eigene Fahrzyklen                  : "
          f"{', '.join(z['name'] for z in bestand['zyklen']) or '— keine —'}")
    if bestand["wissen"]:
        print("  Wissensbasis passt an:")
        for t in bestand["wissen"]:
            print(f"    · {t['dokument']}: {t['auszug']}…")
    else:
        print("  Wissensbasis                       : kein Treffer"
              + (f" ({bestand.get('wissen_fehler')})" if bestand.get("wissen_fehler") else ""))
    print()
    print("Offen — dafuer Rueckfrage oder Recherche, NICHT raten")
    print("-" * 72)
    if not offen:
        print("  nichts offen.")
    else:
        for p in offen:
            print(f"  · {p['name']}: {p['frage']}")
        stichworte = " ".join(text.split()[:8])
        print()
        print("  Naechste Schritte:")
        print(f"    python3 cae_cli.py recherche suche \"{stichworte}\" --treffer 5")
        print( "    python3 cae_cli.py recherche hole <adresse>")
        print( "    python3 cae_cli.py recherche merke --projekt last --adresse <adresse> \\")
        print( "        --wert \"groesse=wert einheit :: woertliches Zitat\"")
        print( "    (was nur der Auftraggeber weiss — Bauraum, Moment, Einsatz — wird GEFRAGT,")
        print( "     nicht recherchiert)")
    return EXIT_OK


def cmd_zyklus(args) -> int:
    """Fahrzyklen nachsehen, bauen, ablegen — der Speicher ist die gemeinsame DB.

    Exit: 0 ok, 2 Bedienfehler.
    """
    import ema_db
    import ema_zyklen
    conn = ema_db.oeffne()
    was = args.was

    if was == "liste":
        eintraege = ema_zyklen.liste(conn)
        if getattr(args, "json", False):
            return emit(eintraege, args)
        print(f"{'Name':22} {'Herkunft':10} {'v_max':>7} {'Dauer':>7} {'Weg':>7}  gedacht fuer")
        for z in eintraege:
            print(f"{z['name']:22} {z['herkunft']:10} "
                  f"{z.get('v_max_kmh', '—'):>7} {z.get('dauer_s', '—'):>7} "
                  f"{z.get('weg_km', '—'):>7}  {z['gedacht_fuer']}")
            if z.get("achtung"):
                print(f"{'':22} ACHTUNG: {z['achtung']}")
        return EXIT_OK

    if was == "zeigen":
        if args.name in ema_zyklen.EINGEBAUT:
            e = ema_zyklen.EINGEBAUT[args.name]
            return emit({"name": args.name, "herkunft": "eingebaut",
                         "beschreibung": e["beschreibung"],
                         "gedacht_fuer": e["gedacht_fuer"],
                         **ema_zyklen._kennzahlen(e["bauer"])}, args)
        z = ema_zyklen.holen(conn, args.name)
        if not z:
            return _die(f"Zyklus '{args.name}' nicht gefunden — 'zyklus liste' zeigt "
                        f"die vorhandenen.", EXIT_USAGE)
        if not getattr(args, "punkte", False):
            z = {k: v for k, v in z.items() if k != "punkte"}
        return emit(z, args)

    if was == "anlegen":
        try:
            phasen = ema_zyklen.phasen_lesen(args.phasen)
            csv = ema_zyklen.aus_phasen(phasen)
            fahrzeug = {}
            for zuweisung in (args.fahrzeug or []):
                if "=" not in zuweisung:
                    return _die(f"'{zuweisung}': erwartet wird GROESSE=WERT", EXIT_USAGE)
                k, v = zuweisung.split("=", 1)
                fahrzeug[k.strip()] = float(v)
            z = ema_zyklen.speichern(conn, args.name, csv,
                                     beschreibung=args.beschreibung or "",
                                     fahrzeug_dict=fahrzeug)
        except ValueError as e:
            return _die(str(e), EXIT_USAGE)
        print(f"Zyklus '{z['name']}' abgelegt ({len(z['punkte'].splitlines()) - 1} s, "
              f"Fahrzeug {z['fahrzeug']['mass_kg']:.0f} kg). "
              f"Verwenden mit: run analyse --zyklus {z['name']}")
        return EXIT_OK

    if was == "loeschen":
        if ema_zyklen.loeschen(conn, args.name):
            print(f"Zyklus '{args.name}' geloescht.")
            return EXIT_OK
        return _die(f"Zyklus '{args.name}' nicht gefunden.", EXIT_USAGE)

    return _die(f"Unbekannt: {was}", EXIT_USAGE)


def _ablegen(args, verb: str, text: str, *, daten=None, ok: bool = True,
             pid: str = "") -> None:
    """Das Ergebnis eines oertlichen Verbs bleibend ins Projekt legen.

    Warum ueberhaupt: von den oertlichen Verben schrieb bisher nur ``feldbild``
    etwas auf die Platte. ``paarvergleich``, ``screen``, ``rotor-check`` und
    ``sicherheit`` -- die Verben, mit denen ein Agent eine Auslegung tatsaechlich
    ENTSCHEIDET -- gaben ihr Ergebnis auf ``stdout`` aus. Im Agentenreiter stand
    es dann in der rechten Spalte, wanderte nach oben aus dem Bild und war beim
    naechsten Start weg. Die Begruendung eines Entwurfs ueberlebte den Entwurf
    nicht.

    Kein Projekt, keine Ablage: bei ``--frisch`` oder ``--payload`` gibt es
    schlicht keinen Ort dafuer, und ein Ordner „irgendwo" waere schlechter als
    keiner. Das wird gesagt, nicht verschwiegen.
    """
    if getattr(args, "ohne_ablage", False):
        return
    kennung = (pid or getattr(args, "projekt", "") or getattr(args, "_pid", "") or "")
    if not kennung:
        return
    pdir = _projekt_pfad(kennung)
    if not pdir:
        return
    import ema_steckbrief
    a = ema_steckbrief.ablegen(pdir, verb, text, daten=daten, ok=ok,
                               befehl=" ".join(sys.argv[1:])[:400])
    if a.get("ok"):
        print(f"  abgelegt: {os.path.relpath(a['datei'], os.path.dirname(pdir))}")
    else:
        print(f"  (nicht abgelegt: {a.get('grund')})", file=sys.stderr)


def cmd_steckbrief(args) -> int:
    """Was dieses Projekt IST und was daran gerechnet wurde -- in einem Absatz.

    Der Anlass war eine Beobachtung am fahrenden Agenten: auf „erstelle kurz
    einen Steckbrief ueber das Projekt" beschrieb er das **Monorepo** -- Ports,
    Teilprojekte, Git-Zweig -- statt der Maschine. Das war kein Fehlschluss,
    sondern die einzige Beschreibung, die er hatte: ueber die Maschine stand ihm
    nichts zur Verfuegung ausser einer ``results.json`` von 1,7 MB, und was sonst
    „Projekt" hiess, stand in ``CLAUDE.md``.

    Hier steht nichts Gerechnetes. Was auf der Platte fehlt, steht als fehlend
    da -- nicht als 0 und nicht als Naeherung -- und jeder Kennwert traegt seine
    Herkunft mit (``analytisch`` sieht sonst aus wie ``fdm2d``).

    Exit: 0 = Steckbrief steht, 1 = das Projekt hat eine Warnung (nichts
    gerechnet, Sicherheitskriterium verletzt, Festigkeit nur analytisch).
    """
    import ema_steckbrief as SB
    pdir = _projekt_pfad(args.projekt)
    if not pdir:
        return _die(f"Projekt '{args.projekt}' nicht gefunden — 'projects' zeigt "
                    f"die vorhandenen.", EXIT_USAGE)
    sb = SB.steckbrief(pdir)
    if not sb.get("ok"):
        return _die(sb.get("grund", "kein Steckbrief"), EXIT_USAGE)

    if getattr(args, "json", False):
        emit(sb, args)
        return EXIT_OK if not sb["warnungen"] else 1

    print(SB.als_text(sb, kurz=getattr(args, "kurz", False)))
    if getattr(args, "laeufe", False):
        print("")
        if sb.get("laeufe"):
            print(f"Fruehere Agentenlaeufe in diesem Projekt ({len(sb['laeufe'])}):")
            for l in sb["laeufe"]:
                dauer = int(l.get("sekunden") or 0)
                print(f"  {l['marke']}  {(l.get('kopf') or '?'):8s} "
                      f"{l.get('ereignisse', 0):5d} Ereignisse, "
                      f"{l.get('kacheln', 0):3d} Ergebnisse, {dauer // 60:02d}:"
                      f"{dauer % 60:02d}")
                for auftrag in (l.get("auftraege") or [])[:3]:
                    print(f"      > {auftrag}")
                if l.get("protokoll"):
                    print(f"      {l['protokoll']}")
        else:
            print("Fruehere Agentenlaeufe: keine.")
        print("")
        if sb["rechnungen"]:
            print(f"Abgelegte Rechnungen ({len(sb['rechnungen'])}):")
            for r in sb["rechnungen"]:
                print(f"  {r['marke']}  {r['verb']:14s} {r['ausgang']:22s} {r['datei']}")
        else:
            print("Abgelegte Rechnungen: keine.")
    return EXIT_OK if not sb["warnungen"] else 1


def cmd_sicherheit(args) -> int:
    """Sicherheitskriterien eines gerechneten Projekts pruefen.

    Exit: 0 = alle bestanden, 1 = mindestens eines verletzt (Muster ``rotor-check``).
    """
    import ema_sicherheit
    pid = _newest_project() if args.projekt == "last" else args.projekt
    ordner = os.path.join(PROJECTS_ROOT, pid)
    try:
        with open(os.path.join(ordner, "results.json"), encoding="utf-8") as f:
            results = json.load(f)
    except FileNotFoundError:
        return _die(f"Kein results.json in '{pid}' — die Analyse ist nicht gelaufen.",
                    EXIT_USAGE)
    meta = {}
    try:
        with open(os.path.join(ordner, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
    except FileNotFoundError:
        pass

    befund = ema_sicherheit.pruefen(results, meta)
    text = ema_sicherheit.als_text(befund)
    if getattr(args, "json", False):
        emit({"projekt": pid, **befund}, args)
    else:
        print(f"Projekt: {pid}")
        print(text)
    _ablegen(args, "sicherheit", text, daten=befund, ok=befund["ok"], pid=pid)
    return EXIT_OK if befund["ok"] else 1


def cmd_feldbild(args) -> int:
    """Magnetfeldlinien-Bilder in den Projektordner legen -- durchsichtig, geschnitten.

    Warum als eigenes Verb und nicht als Nebenprodukt eines Laufs
    -------------------------------------------------------------

    Die rechte Spalte des Agentenreiters zeigt, was im Projekt an Bildern NEU
    entsteht (Aenderungszeit in ``charts/``/``cad_images/``). Sie zeigt also
    genau das, was gerechnet wurde -- und Feldbilder fallen bisher nur als
    Beiwerk eines vollen Pipelinelaufs ab (``em_field.png``, Minuten bis
    Stunden). Wer beim Zusehen sagt „zeig mir das Feld", will keinen neuen
    Pipelinelauf, sondern ein Bild aus der Geometrie, die gerade zur Debatte
    steht. Das kostet hier EINEN FDM-Lauf.

    Weil die Bilder ganz normal in ``charts/`` landen, braucht es dafuer
    **keinen eigenen Meldeweg je Agentenkopf**: PI und Hermes sehen sie beide
    ueber denselben Bilderpfad, und der Bericht findet sie spaeter auch.
    """
    payload = _load_payload(args)
    applied, errors = apply_sets(payload, getattr(args, "set", None) or [],
                                 args.url, force=getattr(args, "force", False))
    if errors:
        for e in errors:
            print(f"FEHLER: {e}", file=sys.stderr)
        return _die(f"{len(errors)} Zuweisung(en) abgewiesen.", EXIT_USAGE)
    for a in applied:
        print(f"  {a['key']}: {a['alt']} -> {a['neu']}")

    geom = payload.get("geom") or {}
    if not geom:
        return _die("Keine Geometrie im Payload -- feldbild braucht geom.", EXIT_USAGE)

    kennung = getattr(args, "projekt", None) or getattr(args, "_pid", None)
    if not kennung:
        return _die("Kein Zielprojekt: --projekt <id> angeben (oder den Payload "
                    "mit --from-project holen, dann ist es dessen Projekt).",
                    EXIT_USAGE)
    pdir = _projekt_pfad(kennung)
    if not pdir:
        return _die(f"Projekt '{kennung}' nicht gefunden -- 'projects' zeigt die "
                    f"vorhandenen.", EXIT_USAGE)

    ansichten = [a.strip() for a in (args.ansicht or "").split(",") if a.strip()]
    import ema_feldbild as FB
    if not ansichten:
        ansichten = list(FB.ANSICHTEN)
    unbekannt = [a for a in ansichten if a not in FB.ANSICHTEN]
    if unbekannt:
        return _die(f"Unbekannte Ansicht(en): {', '.join(unbekannt)} -- waehlbar: "
                    f"{', '.join(FB.ANSICHTEN)}", EXIT_USAGE)

    # Betriebspunkt. --last leitet i_q/i_d aus Drehzahl und Last des Payloads ab,
    # ueber DIESELBE MTPA-Schaetzung, mit der auch die Pipeline ihre Lastbilder
    # rechnet -- ein eigener Stromansatz waere ein zweites Modell.
    iq = float(getattr(args, "iq", 0.0) or 0.0)
    id_ = float(getattr(args, "id_", 0.0) or 0.0)
    if getattr(args, "last", False) and abs(iq) + abs(id_) < 0.1:
        import ema_analysis as A
        rpm = float(payload.get("rpm_to") or payload.get("rpm_from") or 5000.0)
        last_nm = float(payload.get("load_nm") or 0.0)
        iq, id_ = A.estimate_dq_currents(geom, rpm, last_nm,
                                         b_gap_t=A._analytical_Bgap(geom))
        print(f"  Betriebspunkt aus dem Payload: {rpm:.0f} 1/min, {last_nm:.1f} Nm "
              f"-> i_q={iq:.0f} A, i_d={id_:.0f} A")

    sektor = tuple(float(x) for x in str(args.sektor).split(",")[:2])
    if len(sektor) != 2:
        return _die("--sektor braucht zwei Gradwerte, z.B. 25,115", EXIT_USAGE)

    ziel = os.path.join(pdir, "charts")
    bilder = FB.feldbilder(
        geom, ziel, ansichten=ansichten, N=int(args.n),
        rotor_angle=math.radians(float(args.winkel)), iq=iq, id_=id_,
        axial_mm=float(payload.get("axial_len") or geom.get("axialLen") or 80.0),
        projekt_dir=pdir, vtu=getattr(args, "vtu", None), sektor=sektor)

    aus = {"projekt": os.path.basename(pdir), "ordner": ziel,
           "betriebspunkt": {"iq_A": round(iq, 1), "id_A": round(id_, 1),
                             "winkel_grad": float(args.winkel)},
           "bilder": bilder}
    text = "\n".join([f"{len(bilder)} Feldbild(er) in {ziel}",
                      f"Betriebspunkt: i_q={iq:.0f} A, i_d={id_:.0f} A, "
                      f"Rotorwinkel {float(args.winkel):.0f}°"]
                     + [f"  {b['ansicht']:8s} {b['datei']}"
                        + (f"   ({b['hinweis']})" if b.get("hinweis") else "")
                        for b in bilder])
    _ablegen(args, "feldbild", text, daten=aus, pid=os.path.basename(pdir))
    if getattr(args, "json", False):
        return emit(aus, args)
    print(f"ERGEBNIS: {len(bilder)} Bild(er) in {ziel}")
    for b in bilder:
        print(f"  {b['ansicht']:8s} {b['datei']}"
              + (f"   ({b['hinweis']})" if b.get("hinweis") else ""))
    return 0


def cmd_rotor_check(args) -> int:
    """2D-Layoutgate lokal ausfuehren — ohne CAD, ohne serverseitige Pipeline.
    Exit: 0 = Layout OK, 1 = Check abgelehnt (defekte Geometrie)."""
    payload = _load_payload(args)

    applied, errors = apply_sets(payload, getattr(args, "set", None) or [],
                                 args.url, force=getattr(args, "force", False))
    if errors:
        for e in errors:
            print(f"FEHLER: {e}", file=sys.stderr)
        return _die(f"{len(errors)} Zuweisung(en) abgewiesen.", EXIT_USAGE)
    for a in applied:
        print(f"  {a['key']}: {a['alt']} -> {a['neu']}")

    geom = payload.get("geom") or {}
    if not geom:
        return _die("Keine Geometrie im Payload — rotor-check braucht geom.", EXIT_USAGE)

    from ema_rotorcheck import rotor_layout_check
    chk = rotor_layout_check(geom, min_web_mm=getattr(args, "web", None))
    emit(chk, args)
    if chk["ok"]:
        text = "Layout OK — keine Kollision, Stege ueber Grenze, Taschen im Ring."
    else:
        text = "ABGELEHNT:\n" + "\n".join("  ✗ " + m for m in chk["fatal"])
    print("ERGEBNIS: " + text)
    _ablegen(args, "rotor-check", text, daten=chk, ok=chk["ok"])
    return 0 if chk["ok"] else 1


# Die baubaren Magnetanordnungen. Aus ema_topology geholt statt abgeschrieben, damit
# die Liste nicht veraltet -- ein Agent, der eine erfundene Bauform uebergibt, bekommt
# sonst erst am Ende eine unverstaendliche Meldung. Der Import ist lokal gehalten, weil
# der Rest der CLI ohne die schweren Module auskommen soll.
def _magshapes() -> list[str]:
    try:
        from ema_topology import _BUILDERS
        return [k for k in _BUILDERS if k != "custom"]
    except Exception:                                        # noqa: BLE001
        return ["v", "vasym", "bar", "u", "vv", "delta", "pmasynrm", "spm",
                "halbach", "spoke"]


_MAGSHAPES = _magshapes()
_VERSUCH_P = [2, 3, 4, 5, 6, 8]


# Die Bildkante des Datensatzes steht in ema_bilddaten; hier nur geholt, damit sie in
# der Hilfe steht, ohne dass `--help` matplotlib laedt.
def _bd_px() -> int:
    try:
        from ema_bilddaten import PX
        return PX
    except Exception:                                        # noqa: BLE001
        return 384


_BD_PX = _bd_px()


def _pv_achsen() -> str:
    try:
        from ema_paarvergleich import ACHSEN
        return ", ".join(ACHSEN)
    except Exception:                                        # noqa: BLE001
        return ("anordnung, hairpins, magnetwerkstoff, blech, leiterwerkstoff, "
                "kuehlung, durchmesser, laenge")


_PV_ACHSEN = _pv_achsen()


def cmd_screen(args) -> int:
    """Konfigurationen grob durchspielen, bevor eine teuer gerechnet wird.

    Das loest ein Verhalten, das der Vorauswahl im Weg stand: mit ``--from-project last``
    beginnt jede Rechnung beim letzten Stand und aendert daran einzelne Werte. Polzahl,
    Nutzahl und Magnetanordnung des ERSTEN Entwurfs bleiben so stehen, obwohl gerade sie
    den Entwurf praegen. ``screen`` sieht sie sich zuerst an -- analytisch, in Sekunden.

    Exit: 0 = mindestens eine brauchbare Konfiguration, 1 = keine.
    """
    payload = _load_payload(args)
    applied, errors = apply_sets(payload, getattr(args, "set", None) or [],
                                 args.url, force=getattr(args, "force", False))
    if errors:
        for e in errors:
            print(f"FEHLER: {e}", file=sys.stderr)
        return _die(f"{len(errors)} Zuweisung(en) abgewiesen.", EXIT_USAGE)
    for a in applied:
        print(f"  {a['key']}: {a['alt']} -> {a['neu']}")
    if not payload.get("geom"):
        return _die("Keine Geometrie im Payload — screen braucht geom.", EXIT_USAGE)

    import ema_screen as SC

    ziel = args.ziel
    if ziel == "auto":
        quelle = args.auftrag or (payload.get("design_brief") or "")
        erkannt = SC.ziel_aus_text(quelle)
        ziel = erkannt["ziel"]
        belege = erkannt["belege_guenstig"] + erkannt["belege_leistung"]
        if erkannt["sicher"]:
            print(f"Ziel aus dem Auftrag erkannt: {ziel} (Belegwoerter: {', '.join(belege)})")
        else:
            # Ohne Belege ist "ausgewogen" eine ANNAHME, keine Erkennung. Das muss
            # dastehen -- sonst sieht eine Rangliste nach einer Absicht aus, die
            # niemand geaeussert hat.
            print(f"Kein Zielwort im Auftrag gefunden — angenommen: {ziel}. "
                  f"Mit --ziel guenstig|leistung festlegen.")

    achsen = dict(SC.ACHSEN_VORGABE)
    for name, roh in (("p", args.pole), ("slots", args.nuten),
                      ("magShape", args.formen), ("conductorsPerSlot", args.leiter)):
        if roh:
            werte = [w.strip() for w in roh.split(",") if w.strip()]
            achsen[name] = werte if name == "magShape" else [int(w) for w in werte]

    erg = SC.screene(payload, ziel, achsen=achsen, n_max=args.n_max, grenze=args.grenze)
    _ablegen(args, "screen", SC.bestenliste_text(erg, args.zeige),
             daten={"ziel": ziel, "rangliste": erg["rangliste"][:args.zeige],
                    "brauchbar": erg["brauchbar"]},
             ok=bool(erg["brauchbar"]))
    if args.json:
        # Die Verworfenen sind der laengste Teil und im JSON-Modus selten das Ziel;
        # ohne --alle wuerde eine Agentenantwort daran ihren Kontext verlieren.
        schlank = dict(erg)
        if not args.alle:
            schlank["verworfen"] = erg["verworfen"][:20]
            schlank["rangliste"] = erg["rangliste"][:args.zeige]
        emit(schlank, args)
    else:
        print(SC.bestenliste_text(erg, args.zeige))
    return 0 if erg["brauchbar"] else 1


def cmd_paarvergleich(args) -> int:
    """Die Gestaltungsentscheidungen gegeneinanderstellen, BEVOR gezeichnet wird.

    Der Unterschied zu ``screen``: ``screen`` gibt eine Rangliste heraus und
    beantwortet „welche Variante nehme ich?". Hier geht es eine Stufe frueher um
    „woran haengt das ueberhaupt?" -- je Achse jede Option gegen jede, mit der
    Spannweite je Kennzahl. Die sagt, welche Entscheidung zuerst ansteht.

    Exit: 0 = mindestens eine Achse mit zwei brauchbaren Optionen, 1 = keine.
    """
    if getattr(args, "referenz", False):
        import ema_referenz as REF
        if getattr(args, "json", False):
            return emit({"quellen": REF.QUELLEN, "messpunkte": REF.MESSPUNKTE,
                         "salienz_band": {k: {"min": v[0], "max": v[1],
                                              "stuetzen": list(v[2]), "bemerkung": v[3]}
                                          for k, v in REF.SALIENZ_BAND.items()},
                         "v_oeffnung": REF.V_OEFFNUNG_GRAD, "bauband": REF.BAUBAND},
                        args)
        print(REF.als_text())
        return EXIT_OK

    payload = _load_payload(args)
    applied, errors = apply_sets(payload, getattr(args, "set", None) or [],
                                 args.url, force=getattr(args, "force", False))
    if errors:
        for e in errors:
            print(f"FEHLER: {e}", file=sys.stderr)
        return _die(f"{len(errors)} Zuweisung(en) abgewiesen.", EXIT_USAGE)
    for a in applied:
        print(f"  {a['key']}: {a['alt']} -> {a['neu']}")
    if not payload.get("geom"):
        return _die("Keine Geometrie im Payload — paarvergleich braucht geom.", EXIT_USAGE)

    import ema_paarvergleich as PV

    achsen = None
    if args.achsen:
        achsen = [a.strip() for a in args.achsen.split(",") if a.strip()]
        unbekannt = [a for a in achsen if a not in PV.ACHSEN]
        if unbekannt:
            return _die(f"Unbekannte Achse(n): {', '.join(unbekannt)}. "
                        f"Bekannt: {', '.join(PV.ACHSEN)}", EXIT_USAGE)
    try:
        erg = PV.vergleiche(payload, achsen=achsen, n_max=args.n_max, rpm=args.rpm,
                            last_nm=args.last, min_web=args.web)
    except ValueError as e:
        return _die(str(e), EXIT_USAGE)

    text = PV.als_text(erg, paare=not args.ohne_paare, max_paare=args.max_paare)
    if getattr(args, "json", False):
        emit(erg, args)
    else:
        print(text)
    brauchbar = any(a["brauchbar"] >= 2 for a in erg["achsen"].values())
    _ablegen(args, "paarvergleich", text, daten=erg, ok=brauchbar)
    return EXIT_OK if brauchbar else EXIT_REMOTE


def cmd_bilddaten(args) -> int:
    """Bilddatensatz: Rotorquerschnitte ziehen, bewerten lassen, eine Regel daraus ziehen.

    Der Weg ist bewusst vierteilig und haelt zwischen jedem Schritt an, weil der
    dritte -- das Bewerten -- ein Mensch ist und nicht getaktet werden kann.

    Exit: 0 = ok, 1 = kein Ergebnis (keine Regel haelt / nichts abgelegt),
    2 = Bedienfehler.
    """
    import ema_bilddaten as BD

    if args.was == "stand":
        s = BD.stand()
        if getattr(args, "json", False):
            return emit(s, args)
        print(BD.stand_text(s))
        return EXIT_OK

    if args.was == "erzeugen":
        basis = None
        if args.payload or args.payload_file or args.from_project:
            basis = (_load_payload(args) or {}).get("geom")
        erg = BD.erzeuge(anzahl=args.anzahl, seed=args.seed, basis=basis,
                         px=args.px or BD.PX, min_web=args.web)
        if getattr(args, "json", False):
            return emit(erg, args)
        print(f"{erg['neu']} neue Varianten aus {erg['ziehungen']} Ziehungen "
              f"(Ausbeute {erg['ausbeute']:.0%}, {erg['durchgefallen']} am Layouttor "
              f"gescheitert, {erg['doppelt']} doppelt).")
        print(f"{erg['sekunden']} s, {erg['sekunden_je_bild']} s je Bild. "
              f"Bestand jetzt {erg['gesamt']}. Ablage: {erg['ablage']}")
        print("Weiter mit:  cae_cli.py bilddaten seite")
        return EXIT_OK if erg["neu"] else EXIT_REMOTE

    if args.was == "seite":
        pfad = BD.bewertungsseite(nur_offene=not args.alle, px=args.px or BD.PX)
        offen = BD.stand()["offen"] if not args.alle else BD.stand()["varianten"]
        if getattr(args, "json", False):
            return emit({"seite": pfad, "varianten": offen}, args)
        print(f"{offen} Varianten auf der Seite: {pfad}")
        print("Im Browser oeffnen (file://), Tasten 1/2/3, am Ende 's' zum Speichern.")
        print("Danach:  cae_cli.py bilddaten einlesen --datei ~/Downloads/urteile.json")
        return EXIT_OK if offen else EXIT_REMOTE

    if args.was == "einlesen":
        if not args.datei:
            return _die("'bilddaten einlesen' braucht --datei (die von der "
                        "Bewertungsseite gespeicherte urteile.json).", EXIT_USAGE)
        try:
            e = BD.einlesen(os.path.expanduser(args.datei))
        except (OSError, ValueError, json.JSONDecodeError) as ex:
            return _die(str(ex), EXIT_USAGE)
        if getattr(args, "json", False):
            return emit(e, args)
        print(f"{e['gesetzt']} Urteile uebernommen, {e['unveraendert']} unveraendert, "
              f"{e['unbekannt']} unbekannte Kennung, {e['ungueltig']} ungueltig.")
        print(f"Bewertet insgesamt: {e['bewertet_gesamt']}")
        return EXIT_OK

    # was == "regel"
    befund = BD.regel_suchen(mittel_als=args.mittel_als)
    if getattr(args, "json", False):
        emit(befund, args)
    else:
        print(BD.regel_text(befund))
    if args.merken:
        r = BD.merke_regel(befund, quelle=args.quelle or "bilddaten")
        if r["abgelegt"]:
            print(f"\n  gemerkt: {r['regel']}")
        else:
            print(f"\n  nichts abgelegt: {r['grund']}")
            return EXIT_REMOTE
    return EXIT_OK if befund.get("genug") and any(
        r["haelt"] for r in befund.get("regeln", [])) else EXIT_REMOTE


# ``idle`` ist zweideutig: es heisst "nichts laeuft" — und das ist unmittelbar nach dem
# Start genauso wahr wie lange nach dem Ende. Wer es sofort als Abschluss liest, meldet
# einen vierstuendigen Lauf nach 0 s als fertig. Deshalb gilt idle erst als Abschluss,
# nachdem einmal ein laufender Zustand gesehen wurde; davor ist es nur ein Hinweis
# darauf, dass der Start nicht gegriffen hat (Meldung nach ``_IDLE_GRACE_S``).
_DONE_STATES = ("done", "error", "fertig", "abgebrochen")
_IDLE_GRACE_S = 30.0


def _wait(args, status_path="/status") -> int:
    t0, last, seen_running = time.time(), None, False
    while time.time() - t0 < args.timeout:
        code, st = request("GET", status_path, url=args.url)
        s = st.get("status")
        if s != last:
            print(f"[{time.time()-t0:6.0f}s] {s} {st.get('progress', '')}%", flush=True)
            last = s
        if s not in _DONE_STATES + ("idle", None):
            seen_running = True
        if s in _DONE_STATES or (s == "idle" and seen_running):
            for line in (st.get("log") or [])[-args.log_lines:]:
                print(f"  {line}")
            if st.get("error"):
                print(f"FEHLER: {st['error']}", file=sys.stderr)
            return EXIT_REMOTE if (s == "error" or st.get("error")) else EXIT_OK
        if s == "idle" and not seen_running and time.time() - t0 > _IDLE_GRACE_S:
            return _die(f"{status_path} steht nach {_IDLE_GRACE_S:.0f}s noch auf 'idle' "
                        f"— der Lauf ist offenbar nicht angesprungen.", EXIT_REMOTE)
        time.sleep(args.poll)
    return _die(f"Kein Abschluss innerhalb {args.timeout}s (Zustand '{last}'). "
                f"Der Lauf läuft weiter — erneut mit 'wait' anhängen.", EXIT_TIMEOUT)


def cmd_wait(args) -> int:
    return _wait(args, status_path=args.status_path)


def cmd_results(args) -> int:
    if args.project:
        # 'last' bedeutet hier dasselbe wie bei ``run --from-project last``. Ohne diese
        # Zeile hiess dieselbe Kennung an zwei Stellen Verschiedenes: dort das juengste
        # Projekt, hier ein Verzeichnis namens "last" — und die Fehlermeldung ("existiert
        # nicht") half nicht weiter, weil sie den Tippfehler nahelegte statt der Ursache.
        pid = _newest_project() if args.project == "last" else args.project
        p = os.path.join(PROJECTS_ROOT, pid, "results.json")
        if not os.path.exists(p):
            return _die(f"{p} existiert nicht", EXIT_USAGE)
        with open(p, encoding="utf-8") as f:
            body = json.load(f)
        code = 200
    else:
        code, body = request("GET", "/results", url=args.url)
    if code >= 400:
        return emit(body, args) or EXIT_REMOTE
    if args.section:
        cur = body
        for part in args.section.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return _die(f"Abschnitt '{args.section}' fehlt. Vorhanden: "
                            f"{', '.join(sorted(body))}", EXIT_USAGE)
            cur = cur[part]
        return emit(cur, args)
    if args.sections:
        return emit(sorted(body) if isinstance(body, dict) else type(body).__name__, args)
    return emit(body, args)


def cmd_projects(args) -> int:
    code, body = request("GET", "/projects", url=args.url)
    if code >= 400:
        return emit(body, args) or EXIT_REMOTE
    lst = body if isinstance(body, list) else body.get("projects", [])
    if args.json:
        return emit(lst, args)
    for p in lst[: args.limit]:
        pid = p.get("id") or p.get("project_id") or p
        print(f"{pid}   {p.get('label', '') if isinstance(p, dict) else ''}")
    print(f"[{len(lst)} Projekte]")
    return EXIT_OK


def cmd_raw(args) -> int:
    payload = json.loads(args.data) if args.data else None
    code, body = request(args.method.upper(), args.path, payload,
                         url=args.url, timeout=args.timeout)
    emit(body, args)
    return EXIT_OK if code < 400 else EXIT_REMOTE


def cmd_routes(args) -> int:
    """Alle Routen des Servers auflisten — die Landkarte für 'raw'."""
    import re
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "server.py"), encoding="utf-8").read()
    found = re.findall(r'@app\.route\("([^"]+)"(?:\s*,\s*methods=(\[[^\]]*\]))?\)', src)
    rows = [(p, (m or "['GET']").replace('"', "'")) for p, m in found]
    if args.grep:
        rows = [r for r in rows if args.grep.lower() in r[0].lower()]
    for p, m in sorted(rows):
        print(f"{m:<28} {p}")
    print(f"[{len(rows)} Routen]")
    return EXIT_OK


def _add_ablage(s) -> None:
    """``--ohne-ablage`` fuer die Verben, deren Ergebnis im Projekt bleibt.

    Die Ablage ist die Vorgabe und nicht die Ausnahme: das Ergebnis, das man
    spaeter sucht, ist immer eines, das man beim Rechnen fuer nebensaechlich
    hielt. Wer nur eben etwas ausprobiert, schaltet sie ab.
    """
    s.add_argument("--ohne-ablage", dest="ohne_ablage", action="store_true",
                   help="Ergebnis NICHT ins Projekt schreiben (nur ansehen)")


def _add_globals(sp, json_hilfe: str | None = None) -> None:
    """Dieselben Schalter auch NACH dem Verb annehmen. Ohne das quittiert argparse
    ``run analyse --full`` mit einer nackten usage-Zeile — der haeufigste Fehlgriff,
    wenn ein Modell die Reihenfolge raet. ``SUPPRESS`` ist wesentlich: ein nicht
    angegebener Schalter setzt dann NICHTS und ueberschreibt den Wert des
    Hauptparsers nicht mit seinem eigenen Vorgabewert."""
    sp.add_argument("--url", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sp.add_argument("--full", action="store_true", default=argparse.SUPPRESS,
                    help=argparse.SUPPRESS)
    # Normalerweise ausgeblendet (ein Schalter, den jedes Verb hat, muss nicht in jeder
    # Hilfe stehen). Wo die Hilfe aber auf einen "JSON-Modus" VERWEIST, muss er
    # auffindbar sein: in einem echten Agentenlauf suchte das Modell ihn in
    # `screen --help`, fand ihn nicht und wich auf einen rohen HTTP-Aufruf aus.
    sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                    help=json_hilfe or argparse.SUPPRESS)
    sp.add_argument("--log-lines", type=int, default=argparse.SUPPRESS,
                    help=argparse.SUPPRESS)


# ── Argumentbaum ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cae_cli.py",
        description="CAE-Orchestrator von der Kommandozeile bedienen (nur localhost).")
    p.add_argument("--url", default=DEFAULT_URL, help=f"Vorgabe {DEFAULT_URL}")
    p.add_argument("--full", action="store_true",
                   help="Ausgabe nicht kürzen (Bilddaten bleiben trotzdem entfernt)")
    p.add_argument("--json", action="store_true", help="immer JSON statt Fließtext")
    p.add_argument("--log-lines", type=int, default=12)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="Zustand der laufenden Pipeline")
    _add_globals(s)
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("health", help="Was ist erreichbar und rechenbar?")
    _add_globals(s)
    s.set_defaults(fn=cmd_health)

    s = sub.add_parser("geom", help="Parameterschema (Namen, Grenzen, Vorgaben)")
    s.add_argument("name", nargs="?", help="nur Parameter, die diesen Text enthalten")
    _add_globals(s)
    s.set_defaults(fn=cmd_geom)

    s = sub.add_parser("run", help="Rechenstufe starten")
    s.add_argument("stage", choices=sorted(RUN_ROUTES))
    g = s.add_mutually_exclusive_group()
    g.add_argument("--payload", help="JSON direkt")
    g.add_argument("--payload-file", help="Datei mit JSON (meta.json wird erkannt)")
    g.add_argument("--from-project",
                   help="Payload aus ~/cae_projekte/<id>/meta.json ('last' = juengstes) — "
                        "erbt ALLE Entscheidungen dieses Projekts")
    g.add_argument("--frisch", action="store_true",
                   help="neutraler Grundpayload aus den Schemavorgaben, ohne Altprojekt "
                        "— der richtige Start fuer eine NEUE Auslegung")
    s.add_argument("--set", action="append", metavar="KEY=WERT",
                   help="einzelnen Parameter aendern, mehrfach angebbar. Geprueft gegen "
                        "'geom'. Punktpfade erlaubt (vehicle.mass_kg=1600)")
    s.add_argument("--force", action="store_true",
                   help="Grenzen und Typen aus dem Schema nicht pruefen")
    s.add_argument("--zyklus", metavar="NAME",
                   help="Fahrzyklus UND sein Fahrzeug einsetzen ('zyklus liste' zeigt "
                        "die waehlbaren; 'off' rechnet ohne Zyklus)")
    s.add_argument("--dry-run", action="store_true",
                   help="Payload nur bauen und zeigen, nichts starten")
    s.add_argument("--wait", action="store_true", help="bis zum Abschluss warten")
    s.add_argument("--timeout", type=int, default=7200)
    s.add_argument("--poll", type=float, default=5.0)
    _add_globals(s)
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("aufgabe",
                       help="eine neue Aufgabe zerlegen: was muss feststehen, was steht "
                            "schon im eigenen Bestand, was fehlt (der Schritt VOR der Recherche)")
    s.add_argument("beschreibung", nargs="+", help="die Aufgabe in eigenen Worten")
    _add_globals(s)
    s.set_defaults(fn=cmd_aufgabe)

    s = sub.add_parser("zyklus",
                       help="Fahrzyklen: nachsehen, eigene bauen und in der gemeinsamen "
                            "Datenbank behalten")
    zs = s.add_subparsers(dest="was", required=True)
    z1 = zs.add_parser("liste", help="alle waehlbaren Zyklen mit ihrem gedachten Fahrzeug")
    _add_globals(z1)
    z2 = zs.add_parser("zeigen", help="einen Zyklus im Einzelnen")
    z2.add_argument("name")
    z2.add_argument("--punkte", action="store_true", help="auch die CSV-Punkte ausgeben")
    _add_globals(z2)
    z3 = zs.add_parser("anlegen", help="eigenen Zyklus bauen und ablegen")
    z3.add_argument("name")
    z3.add_argument("--phasen", required=True, metavar="ZIEL:DAUER,...",
                    help="Phasen als ziel_kmh:dauer_s, z. B. '0:5,25:20,25:300,0:15' — "
                         "in jeder Phase laeuft v linear auf das Ziel")
    z3.add_argument("--fahrzeug", action="append", metavar="GROESSE=WERT",
                    help="mass_kg, r_wheel_m, gear_ratio, cwA_m2, cr, eta_drive, "
                         "regen_frac, slope_deg — mehrfach angebbar")
    z3.add_argument("--beschreibung", default="")
    _add_globals(z3)
    z4 = zs.add_parser("loeschen", help="abgelegten Zyklus entfernen")
    z4.add_argument("name")
    _add_globals(z4)
    s.set_defaults(fn=cmd_zyklus)

    s = sub.add_parser("maschinenart",
                       help="Maschinenarten (PSM/ASM/SynRM/EESM) und welche "
                            "Rechenstufe jede heute traegt")
    s.add_argument("code", nargs="?", help="eine Art im Einzelnen (pmsm|asm|synrm|eesm)")
    _add_globals(s)
    s.set_defaults(fn=cmd_maschinenart)

    s = sub.add_parser("steckbrief",
                       help="was ein Projekt IST und was daran gerechnet wurde — "
                            "Maschine, Stufen, Kennwerte samt Herkunft, offene Punkte")
    s.add_argument("projekt", nargs="?", default="last",
                   help="Projektkennung oder 'last' (Vorgabe)")
    s.add_argument("--laeufe", action="store_true",
                   help="zusaetzlich die frueheren Agentenlaeufe und die "
                        "abgelegten Rechnungen dieses Projekts auflisten")
    s.add_argument("--kurz", action="store_true",
                   help="ohne den Warnblock (nur die Fakten)")
    _add_globals(s)
    s.set_defaults(fn=cmd_steckbrief)

    s = sub.add_parser("sicherheit",
                       help="Sicherheitskriterien eines gerechneten Projekts pruefen "
                            "(Festigkeit, Temperaturen, Entmagnetisierung, Fahrprofil)")
    s.add_argument("--from-project", dest="projekt", default="last",
                   help="Projektkennung oder 'last' (Vorgabe)")
    _add_ablage(s)
    _add_globals(s)
    s.set_defaults(fn=cmd_sicherheit)

    s = sub.add_parser("rotor-check",
                       help="2D Rotorlayout-Check (Taschen: Kollision/Stege/Containment) — ohne CAD, in ms")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--payload", help="JSON direkt")
    g.add_argument("--payload-file", help="Datei mit JSON (meta.json wird erkannt)")
    g.add_argument("--from-project",
                   help="Payload aus ~/cae_projekte/<id>/meta.json ('last' = juengstes) — "
                        "erbt ALLE Entscheidungen dieses Projekts")
    g.add_argument("--frisch", action="store_true",
                   help="neutraler Grundpayload aus den Schemavorgaben, ohne Altprojekt "
                        "— der richtige Start fuer eine NEUE Auslegung")
    s.add_argument("--set", action="append", metavar="KEY=WERT",
                   help="einzelnen Parameter aendern, mehrfach angebbar (Geometrie-Test)")
    s.add_argument("--force", action="store_true",
                   help="Grenzen und Typen aus dem Schema nicht pruefen")
    s.add_argument("--web", type=float, default=None,
                   help="Mindeststege in mm (Vorgabe: ema_topology.BRIDGE_MM = 2.0)")
    _add_ablage(s)
    _add_globals(s)
    s.set_defaults(fn=cmd_rotor_check)

    s = sub.add_parser("feldbild",
                       help="Magnetfeldlinien als Bilder ins Projekt legen (durchsichtig, "
                            "aufgeschnitten, ein Pol, Laengsschnitt)")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--payload", help="JSON direkt")
    g.add_argument("--payload-file", help="Datei mit JSON (meta.json wird erkannt)")
    g.add_argument("--from-project",
                   help="Payload aus ~/cae_projekte/<id>/meta.json ('last' = juengstes); "
                        "dieses Projekt ist dann auch das Ziel der Bilder")
    g.add_argument("--frisch", action="store_true",
                   help="neutraler Grundpayload aus den Schemavorgaben (braucht dann --projekt)")
    s.add_argument("--projekt",
                   help="Zielprojekt fuer die Bilder (Vorgabe: das Projekt des Payloads)")
    s.add_argument("--ansicht", default="",
                   help="Auswahl mit Komma: linien,schnitt,pol,laengs (Vorgabe: alle vier)")
    s.add_argument("--n", type=int, default=560,
                   help="FDM-Aufloesung des einen Feldlaufs (Vorgabe 560)")
    s.add_argument("--winkel", type=float, default=0.0, help="Rotorwinkel in Grad")
    s.add_argument("--last", action="store_true",
                   help="Lastfall: i_q/i_d aus Drehzahl und Last des Payloads (MTPA)")
    s.add_argument("--iq", type=float, default=0.0, help="q-Strom in A (statt --last)")
    s.add_argument("--id", dest="id_", type=float, default=0.0, help="d-Strom in A")
    s.add_argument("--sektor", default="25,115",
                   help="Schnittsektor in Grad (von,bis) fuer die Schnittdarstellung")
    s.add_argument("--vtu",
                   help="3D-Elmer-VTU fuer den Laengsschnitt (Vorgabe: juengste im Projekt)")
    s.add_argument("--set", action="append", metavar="KEY=WERT",
                   help="einzelnen Parameter aendern, mehrfach angebbar")
    s.add_argument("--force", action="store_true",
                   help="Grenzen und Typen aus dem Schema nicht pruefen")
    _add_ablage(s)
    _add_globals(s)
    s.set_defaults(fn=cmd_feldbild)

    s = sub.add_parser("screen",
                       help="viele Konfigurationen (Pole/Nuten/Magnetform/Leiter) grob durchspielen und rangieren")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--payload", help="JSON direkt")
    g.add_argument("--payload-file", help="Datei mit JSON (meta.json wird erkannt)")
    g.add_argument("--from-project",
                   help="Payload aus ~/cae_projekte/<id>/meta.json ('last' = juengstes) — "
                        "erbt ALLE Entscheidungen dieses Projekts")
    g.add_argument("--frisch", action="store_true",
                   help="neutraler Grundpayload aus den Schemavorgaben, ohne Altprojekt "
                        "— der richtige Start fuer eine NEUE Auslegung")
    s.add_argument("--ziel", choices=["auto", "guenstig", "leistung", "ausgewogen"],
                   default="auto",
                   help="Auslegungsziel; auto liest es aus --auftrag bzw. dem design_brief")
    s.add_argument("--auftrag", default="",
                   help="Auslegungsauftrag im Klartext (Quelle fuer --ziel auto)")
    # Der Schalter nimmt POLPAARE (p), die Rangliste zeigt zusaetzlich die Polzahl
    # (2p) -- beide Spalten stehen jetzt nebeneinander, weil genau diese Verwechslung
    # in einem Agentenlauf zu "--pole 2,3 ergibt Pole 6 und 4? seltsam" gefuehrt hat.
    s.add_argument("--polpaare", "--pole", dest="pole",
                   help="Polpaarzahlen p, z.B. 2,3,4,5 (die Maschine hat dann 2p Pole)")
    s.add_argument("--nuten", help="Statornutzahlen, z.B. 24,36,48,60")
    s.add_argument("--formen",
                   help="Magnetanordnungen, mit Komma: " + ", ".join(_MAGSHAPES))
    s.add_argument("--leiter", help="Leiter je Nut, z.B. 4,6,8")
    s.add_argument("--n_max", type=float, default=None,
                   help="Hoechstdrehzahl fuer das Fliehkrafttor (Vorgabe: aus dem Payload)")
    s.add_argument("--zeige", type=int, default=12, help="Laenge der Bestenliste")
    s.add_argument("--alle", action="store_true",
                   help="im JSON-Modus auch alle Verworfenen ausgeben")
    s.add_argument("--grenze", type=int, default=400,
                   help="Obergrenze der Kombinationen (Schutz vor versehentlichen Riesenlaeufen)")
    s.add_argument("--set", action="append", metavar="KEY=WERT",
                   help="einzelnen Parameter der Basis aendern, mehrfach angebbar")
    s.add_argument("--force", action="store_true",
                   help="Grenzen und Typen aus dem Schema nicht pruefen")
    _add_ablage(s)
    _add_globals(s, json_hilfe="vollstaendig als JSON — je Zeile mit der EINGEPASSTEN "
                               "Geometrie, aus der sich die Variante nachbauen laesst")
    s.set_defaults(fn=cmd_screen)

    s = sub.add_parser("paarvergleich",
                       help="Gestaltungsentscheidungen gegeneinanderstellen (Anordnung, V-Öffnungswinkel, Hairpins, Material, Kühlung, Durchmesser, Länge, Welle) — vor der Geometrie")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--payload", help="JSON direkt")
    g.add_argument("--payload-file", help="Datei mit JSON (meta.json wird erkannt)")
    g.add_argument("--from-project",
                   help="Payload aus ~/cae_projekte/<id>/meta.json ('last' = juengstes) — "
                        "erbt ALLE Entscheidungen dieses Projekts")
    g.add_argument("--frisch", action="store_true",
                   help="neutraler Grundpayload aus den Schemavorgaben, ohne Altprojekt "
                        "— der richtige Start fuer eine NEUE Auslegung")
    s.add_argument("--achsen",
                   help="nur diese Achsen, mit Komma. Vorgabe: alle. Bekannt: " + _PV_ACHSEN)
    s.add_argument("--n_max", type=float, default=None,
                   help="Hoechstdrehzahl fuer das Fliehkrafttor (Vorgabe: aus dem Payload)")
    s.add_argument("--rpm", type=float, default=None,
                   help="Drehzahl des gemeinsamen Betriebspunkts (Vorgabe: rpm_from)")
    s.add_argument("--last", type=float, default=None,
                   help="Moment des gemeinsamen Betriebspunkts in Nm (Vorgabe: load_nm)")
    s.add_argument("--web", type=float, default=None,
                   help="Mindeststege in mm fuer die Einpassung (Vorgabe: BRIDGE_MM)")
    s.add_argument("--ohne-paare", dest="ohne_paare", action="store_true",
                   help="nur die Tabellen zeigen, die Paarliste weglassen")
    s.add_argument("--max-paare", dest="max_paare", type=int, default=10,
                   help="wie viele Paare je Achse gezeigt werden (Vorgabe 10)")
    s.add_argument("--set", action="append", metavar="KEY=WERT",
                   help="einzelnen Parameter der Basis aendern, mehrfach angebbar")
    s.add_argument("--force", action="store_true",
                   help="Grenzen und Typen aus dem Schema nicht pruefen")
    s.add_argument("--referenz", action="store_true",
                   help="nur die recherchierten Vergleichswerte zeigen (Salienzband je "
                        "Anordnung, V-Oeffnungswinkel, Bauverhaeltnisse) — Fremdtext "
                        "mit Quellen, ohne Payload")
    _add_ablage(s)
    _add_globals(s, json_hilfe="der vollstaendige Vergleich als JSON — je Achse "
                               "Optionen, Paare und Spannweiten")
    s.set_defaults(fn=cmd_paarvergleich)

    s = sub.add_parser("bilddaten",
                       help="Rotorquerschnitte zeichnen, optisch bewerten lassen und eine Regel daraus ziehen")
    s.add_argument("was", choices=["erzeugen", "stand", "seite", "einlesen", "regel"])
    s.add_argument("--anzahl", type=int, default=500,
                   help="erzeugen: wie viele Varianten, die das Layouttor BESTEHEN")
    s.add_argument("--seed", type=int, default=None,
                   help="erzeugen: Startwert des Zufalls (gleicher Wert, gleiche Ziehung)")
    s.add_argument("--px", type=int, default=None,
                   help=f"Bildkante in Pixeln (Vorgabe {_BD_PX})")
    s.add_argument("--web", type=float, default=None,
                   help="erzeugen: Mindeststege in mm fuer das Tor (Vorgabe: BRIDGE_MM)")
    s.add_argument("--alle", action="store_true",
                   help="seite: auch die schon bewerteten Varianten zeigen")
    s.add_argument("--datei", help="einlesen: die von der Seite gespeicherte urteile.json")
    s.add_argument("--mittel-als", dest="mittel_als",
                   choices=["aus", "gut", "schlecht"], default="aus",
                   help="regel: was mit den mittleren Urteilen geschieht (Vorgabe: weglassen)")
    s.add_argument("--merken", action="store_true",
                   help="regel: die beste Schranke als belegte Erfahrung ablegen — "
                        "nur wenn sie den Pruefteil haelt")
    s.add_argument("--quelle", dest="quelle", help="regel --merken: Herkunftsvermerk")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--payload", help="erzeugen: JSON direkt (Basis fuer die nicht gezogenen Werte)")
    g.add_argument("--payload-file", help="erzeugen: Datei mit JSON")
    g.add_argument("--from-project",
                   help="erzeugen: Basis aus ~/cae_projekte/<id>/meta.json ('last')")
    g.add_argument("--frisch", action="store_true",
                   help="neutraler Grundpayload aus den Schemavorgaben statt eines "
                        "Altprojekts")
    _add_globals(s, json_hilfe="der vollstaendige Befund als JSON")
    s.set_defaults(fn=cmd_bilddaten)

    s = sub.add_parser("lernen",
                       help="was die Toolchain aus ihren eigenen Laeufen weiss (gemessen + belegte Erfahrungen)")
    s.add_argument("was", choices=["zeige", "merke", "pruefe", "probieren"])
    s.add_argument("--regel", help="die Erfahrung in einem Satz")
    s.add_argument("--beleg", help="woran sie nachpruefbar ist — Lauf-Kennung, Zahl, Ausgabe")
    s.add_argument("--quelle", help="woher (z. B. Projekt-Id oder Befehl)")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--payload", help="probieren: JSON direkt")
    g.add_argument("--payload-file", help="probieren: Datei mit JSON")
    g.add_argument("--from-project",
                   help="probieren: Basis aus ~/cae_projekte/<id>/meta.json ('last')")
    g.add_argument("--frisch", action="store_true",
                   help="neutraler Grundpayload aus den Schemavorgaben statt eines "
                        "Altprojekts")
    s.add_argument("--merken", action="store_true",
                   help="probieren: die Befunde als belegte Regeln ablegen")
    s.add_argument("--polpaare", "--pole", dest="pole",
                   help="probieren: Polpaarzahlen, sonst " + str(_VERSUCH_P))
    s.add_argument("--nuten", help="probieren: Nutzahlen")
    s.add_argument("--formen", help="probieren: Bauformen, sonst alle: "
                                    + ", ".join(_MAGSHAPES))
    s.add_argument("--n_max", type=float, default=None,
                   help="probieren: Hoechstdrehzahl fuer das Fliehkrafttor")
    _add_globals(s, json_hilfe="der vollstaendige Befund als JSON")
    s.set_defaults(fn=cmd_lernen)

    s = sub.add_parser("recherche",
                       help="Internetrecherche: Websuche und Seitenabruf (fuer die Agenten)")
    s.add_argument("was", choices=["suche", "hole", "merke", "quellen"])
    s.add_argument("frage", nargs="*", help="Suchbegriffe bzw. die Adresse")
    s.add_argument("--treffer", type=int, default=5, help="Zahl der Suchtreffer (max 10)")
    s.add_argument("--zeichen", type=int, default=6000,
                   help="Hoechstlaenge des geholten Textes")
    s.add_argument("--projekt", help="Projekt-Id oder 'last' (fuer merke/quellen)")
    s.add_argument("--adresse", help="die abzulegende Seite (fuer merke)")
    s.add_argument("--notiz", help="wofuer die Quelle herangezogen wurde")
    s.add_argument("--bild", action="append", metavar="ADRESSE",
                   help="Bildadresse zum Mitladen, mehrfach angebbar")
    s.add_argument("--wert", action="append", metavar="G=ZAHL EINHEIT :: ZITAT",
                   help="entnommener Referenzwert MIT Belegstelle, mehrfach angebbar")
    _add_globals(s)
    s.set_defaults(fn=cmd_recherche)

    s = sub.add_parser("db",
                       help="Rechnungsdatenbank: Eingaben, Kennwerte MIT Herkunft, Bilder, Guete")
    s.add_argument("was", choices=["import", "liste", "zeige", "guete", "vergleich"],
                   help="import = ~/cae_projekte einlesen · liste · zeige · guete · vergleich")
    s.add_argument("--lauf", help="Lauf-Id oder Projekt-Id (fuer zeige/guete)")
    s.add_argument("--lauf-liste", nargs="*", dest="lauf_liste",
                   help="Projekt-Ids fuer den Vergleich (ohne Angabe: alle)")
    s.add_argument("--groessen", nargs="*",
                   help="Kennwerte fuer den Vergleich (ohne Angabe: die sechs wichtigsten)")
    s.add_argument("--alle", action="store_true",
                   help="auch abgebrochene Laeufe auflisten")
    s.add_argument("--limit", type=int, default=20, help="Zeilen in der Liste")
    _add_globals(s)
    s.set_defaults(fn=cmd_db)

    s = sub.add_parser("struktur",
                       help="Rotor-Festigkeit auf dem eigenen Rechensatz (ccx | z88 | beide) — ohne FreeCAD")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--payload", help="JSON direkt")
    g.add_argument("--payload-file", help="Datei mit JSON (meta.json wird erkannt)")
    g.add_argument("--from-project",
                   help="Payload aus ~/cae_projekte/<id>/meta.json ('last' = juengstes) — "
                        "erbt ALLE Entscheidungen dieses Projekts")
    g.add_argument("--frisch", action="store_true",
                   help="neutraler Grundpayload aus den Schemavorgaben, ohne Altprojekt "
                        "— der richtige Start fuer eine NEUE Auslegung")
    s.add_argument("--set", action="append", metavar="KEY=WERT",
                   help="einzelnen Parameter aendern, mehrfach angebbar")
    s.add_argument("--force", action="store_true", help="Schemagrenzen nicht pruefen")
    s.add_argument("--solver", choices=["ccx", "z88", "beide"], default="ccx",
                   help="Loeser. 'beide' rechnet dasselbe Netz zweimal und vergleicht")
    s.add_argument("--voll", action="store_true",
                   help="voller Rotor statt Polsektor (bei z88/beide zwingend)")
    s.add_argument("--mesh", type=float, default=6.0, help="Netzweite in mm (Vorgabe 6)")
    s.add_argument("--ordnung", type=int, choices=[1, 2], default=1,
                   help="1 = Tet4 (schnell), 2 = Tet10 (genauer, nur ccx)")
    s.add_argument("--rpm", type=float, default=None,
                   help="Drehzahl (Vorgabe: target.n_max aus dem Payload)")
    s.add_argument("--kerne", type=int, default=4, help="CPU-Kerne")
    s.add_argument("--out", default=None, help="Arbeitsverzeichnis behalten")
    _add_globals(s)
    s.set_defaults(fn=cmd_struktur)

    s = sub.add_parser("topopt",
                       help="Topologieoptimierung des Rotorblechs (SKO/SIMP) — Ergebnis ist ein Dichtefeld")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--payload", help="JSON direkt")
    g.add_argument("--payload-file", help="Datei mit JSON (meta.json wird erkannt)")
    g.add_argument("--from-project",
                   help="Payload aus ~/cae_projekte/<id>/meta.json ('last' = juengstes) — "
                        "erbt ALLE Entscheidungen dieses Projekts")
    g.add_argument("--frisch", action="store_true",
                   help="neutraler Grundpayload aus den Schemavorgaben, ohne Altprojekt "
                        "— der richtige Start fuer eine NEUE Auslegung")
    s.add_argument("--set", action="append", metavar="KEY=WERT")
    s.add_argument("--force", action="store_true")
    s.add_argument("--verfahren", choices=["sko", "simp"], default="sko",
                   help="sko = spannungsgetrieben (Vorgabe, fuer ein Blech das passende), "
                        "simp = Nachgiebigkeit unter Volumenschranke")
    s.add_argument("--solver", choices=["ccx", "z88"], default="ccx")
    s.add_argument("--mesh", type=float, default=6.0, help="Netzweite in mm")
    s.add_argument("--iterationen", type=int, default=30)
    s.add_argument("--vol-ziel", type=float, default=None, dest="vol_ziel",
                   help="Volumenanteil, bei dem abgebrochen wird (SIMP: Schranke)")
    s.add_argument("--rpm", type=float, default=None)
    s.add_argument("--fest-bohrung", type=float, default=3.0, dest="fest_bohrung",
                   help="Sperrsaum am Wellensitz in mm")
    s.add_argument("--fest-rand", type=float, default=2.0, dest="fest_rand",
                   help="Sperrsaum am Rotoraussenrand in mm")
    s.add_argument("--fest-tasche", type=float, default=1.5, dest="fest_tasche",
                   help="Sperrsaum um jede Magnettasche in mm")
    s.add_argument("--kerne", type=int, default=4)
    s.add_argument("--out", default=None)
    _add_globals(s)
    s.set_defaults(fn=cmd_topopt)

    s = sub.add_parser("wait", help="auf den Abschluss eines laufenden Vorgangs warten")
    s.add_argument("--status-path", default="/status")
    s.add_argument("--timeout", type=int, default=7200)
    s.add_argument("--poll", type=float, default=5.0)
    _add_globals(s)
    s.set_defaults(fn=cmd_wait)

    s = sub.add_parser("results", help="Ergebnisse lesen (Abschnitt wählen!)")
    s.add_argument("section", nargs="?", help="Punktpfad, z. B. em.performance")
    s.add_argument("--project", help="aus ~/cae_projekte/<id>/results.json statt live; "
                                     "'last' = juengstes Projekt mit meta.json")
    s.add_argument("--sections", action="store_true", help="nur die Abschnittsnamen")
    _add_globals(s)
    s.set_defaults(fn=cmd_results)

    s = sub.add_parser("projects", help="gespeicherte Projekte auflisten")
    s.add_argument("--limit", type=int, default=30)
    _add_globals(s)
    s.set_defaults(fn=cmd_projects)

    s = sub.add_parser("raw", help="beliebige Route aufrufen (Notausgang)")
    s.add_argument("method", choices=["GET", "POST", "get", "post"])
    s.add_argument("path")
    s.add_argument("--data", help="JSON-Rumpf")
    s.add_argument("--timeout", type=int, default=TIMEOUT_S)
    _add_globals(s)
    s.set_defaults(fn=cmd_raw)

    s = sub.add_parser("routes", help="alle Routen auflisten")
    s.add_argument("--grep", help="filtern")
    _add_globals(s)
    s.set_defaults(fn=cmd_routes)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
