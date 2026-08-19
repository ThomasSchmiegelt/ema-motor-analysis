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
        meta = os.path.expanduser(f"~/cae_projekte/{args.from_project}/meta.json")
        with open(meta, encoding="utf-8") as f:
            return json.load(f)["payload"]
    raise SystemExit(_die("Kein Payload: --payload, --payload-file oder --from-project "
                          "angeben.", EXIT_USAGE))


RUN_ROUTES = {
    "analyse":   "/analyse",      # volle Pipeline: CAD, 2D-Feld, Struktur, Thermik, Zyklus
    "cad":       "/cad_preview",  # nur die Geometrie bauen
    "em3d":      "/em3d",         # 3D-Elmer-Feld
    "em3d_sweep": "/em3d_sweep",
    "cfd":       "/cfd",          # OpenFOAM-Kühlung
    "oilspray":  "/oilspray",     # Blender/Mantaflow-Ölnebel
    "smoke":     "/smoke_test",
}


def cmd_run(args) -> int:
    path = RUN_ROUTES.get(args.stage)
    if path is None:
        return _die(f"Unbekannte Stufe '{args.stage}'. Bekannt: "
                    f"{', '.join(sorted(RUN_ROUTES))}", EXIT_USAGE)
    payload = _load_payload(args)
    code, body = request("POST", path, payload, url=args.url)
    if code >= 400:
        emit(body, args)
        return EXIT_REMOTE
    print(json.dumps({"gestartet": args.stage, "route": path, **(body or {})},
                     ensure_ascii=False))
    if args.wait:
        return _wait(args, status_path="/em3d/status" if args.stage.startswith("em3d")
                     else "/cfd/status" if args.stage == "cfd"
                     else "/oilspray/status" if args.stage == "oilspray"
                     else "/status")
    return EXIT_OK


def _wait(args, status_path="/status") -> int:
    t0, last = time.time(), None
    while time.time() - t0 < args.timeout:
        code, st = request("GET", status_path, url=args.url)
        s = st.get("status")
        if s != last:
            print(f"[{time.time()-t0:6.0f}s] {s} {st.get('progress', '')}%", flush=True)
            last = s
        if s in ("done", "error", "idle", "fertig", "abgebrochen"):
            for line in (st.get("log") or [])[-args.log_lines:]:
                print(f"  {line}")
            return EXIT_OK if s != "error" else EXIT_REMOTE
        time.sleep(args.poll)
    return _die(f"Kein Abschluss innerhalb {args.timeout}s (Zustand '{last}'). "
                f"Der Lauf läuft weiter — erneut mit 'wait' anhängen.", EXIT_TIMEOUT)


def cmd_wait(args) -> int:
    return _wait(args, status_path=args.status_path)


def cmd_results(args) -> int:
    if args.project:
        p = os.path.expanduser(f"~/cae_projekte/{args.project}/results.json")
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
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("health", help="Was ist erreichbar und rechenbar?")
    s.set_defaults(fn=cmd_health)

    s = sub.add_parser("geom", help="Parameterschema (Namen, Grenzen, Vorgaben)")
    s.add_argument("name", nargs="?", help="nur Parameter, die diesen Text enthalten")
    s.set_defaults(fn=cmd_geom)

    s = sub.add_parser("run", help="Rechenstufe starten")
    s.add_argument("stage", choices=sorted(RUN_ROUTES))
    g = s.add_mutually_exclusive_group()
    g.add_argument("--payload", help="JSON direkt")
    g.add_argument("--payload-file", help="Datei mit JSON (meta.json wird erkannt)")
    g.add_argument("--from-project", help="Payload aus ~/cae_projekte/<id>/meta.json")
    s.add_argument("--wait", action="store_true", help="bis zum Abschluss warten")
    s.add_argument("--timeout", type=int, default=7200)
    s.add_argument("--poll", type=float, default=5.0)
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("wait", help="auf den Abschluss eines laufenden Vorgangs warten")
    s.add_argument("--status-path", default="/status")
    s.add_argument("--timeout", type=int, default=7200)
    s.add_argument("--poll", type=float, default=5.0)
    s.set_defaults(fn=cmd_wait)

    s = sub.add_parser("results", help="Ergebnisse lesen (Abschnitt wählen!)")
    s.add_argument("section", nargs="?", help="Punktpfad, z. B. em.performance")
    s.add_argument("--project", help="aus ~/cae_projekte/<id>/results.json statt live")
    s.add_argument("--sections", action="store_true", help="nur die Abschnittsnamen")
    s.set_defaults(fn=cmd_results)

    s = sub.add_parser("projects", help="gespeicherte Projekte auflisten")
    s.add_argument("--limit", type=int, default=30)
    s.set_defaults(fn=cmd_projects)

    s = sub.add_parser("raw", help="beliebige Route aufrufen (Notausgang)")
    s.add_argument("method", choices=["GET", "POST", "get", "post"])
    s.add_argument("path")
    s.add_argument("--data", help="JSON-Rumpf")
    s.add_argument("--timeout", type=int, default=TIMEOUT_S)
    s.set_defaults(fn=cmd_raw)

    s = sub.add_parser("routes", help="alle Routen auflisten")
    s.add_argument("--grep", help="filtern")
    s.set_defaults(fn=cmd_routes)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
