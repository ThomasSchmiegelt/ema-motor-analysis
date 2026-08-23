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


def _load_payload(args) -> dict:
    if args.payload_file:
        with open(args.payload_file, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("payload", data)
    if args.payload:
        return json.loads(args.payload)
    if args.from_project:
        pid = _newest_project() if args.from_project == "last" else args.from_project
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
    Alles Uebrige ist Text (``magShape=v`` muss ohne Anfuehrungszeichen gehen)."""
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
        print("ERGEBNIS: Layout OK — keine Kollision, Stege ueber Grenze, Taschen im Ring.")
        return 0
    print("ERGEBNIS: ABGELEHNT:")
    for m in chk["fatal"]:
        print("  ✗ " + m)
    return 1


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


def _add_globals(sp) -> None:
    """Dieselben Schalter auch NACH dem Verb annehmen. Ohne das quittiert argparse
    ``run analyse --full`` mit einer nackten usage-Zeile — der haeufigste Fehlgriff,
    wenn ein Modell die Reihenfolge raet. ``SUPPRESS`` ist wesentlich: ein nicht
    angegebener Schalter setzt dann NICHTS und ueberschreibt den Wert des
    Hauptparsers nicht mit seinem eigenen Vorgabewert."""
    sp.add_argument("--url", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sp.add_argument("--full", action="store_true", default=argparse.SUPPRESS,
                    help=argparse.SUPPRESS)
    sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                    help=argparse.SUPPRESS)
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
                   help="Payload aus ~/cae_projekte/<id>/meta.json ('last' = juengstes)")
    s.add_argument("--set", action="append", metavar="KEY=WERT",
                   help="einzelnen Parameter aendern, mehrfach angebbar. Geprueft gegen "
                        "'geom'. Punktpfade erlaubt (vehicle.mass_kg=1600)")
    s.add_argument("--force", action="store_true",
                   help="Grenzen und Typen aus dem Schema nicht pruefen")
    s.add_argument("--dry-run", action="store_true",
                   help="Payload nur bauen und zeigen, nichts starten")
    s.add_argument("--wait", action="store_true", help="bis zum Abschluss warten")
    s.add_argument("--timeout", type=int, default=7200)
    s.add_argument("--poll", type=float, default=5.0)
    _add_globals(s)
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("rotor-check",
                       help="2D Rotorlayout-Check (Taschen: Kollision/Stege/Containment) — ohne CAD, in ms")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--payload", help="JSON direkt")
    g.add_argument("--payload-file", help="Datei mit JSON (meta.json wird erkannt)")
    g.add_argument("--from-project",
                   help="Payload aus ~/cae_projekte/<id>/meta.json ('last' = juengstes)")
    s.add_argument("--set", action="append", metavar="KEY=WERT",
                   help="einzelnen Parameter aendern, mehrfach angebbar (Geometrie-Test)")
    s.add_argument("--force", action="store_true",
                   help="Grenzen und Typen aus dem Schema nicht pruefen")
    s.add_argument("--web", type=float, default=None,
                   help="Mindeststege in mm (Vorgabe: ema_topology.BRIDGE_MM = 2.0)")
    _add_globals(s)
    s.set_defaults(fn=cmd_rotor_check)

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
