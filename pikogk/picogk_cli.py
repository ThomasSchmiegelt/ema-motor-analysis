#!/usr/bin/env python3
"""Kommandozeile für die PicoGK-Web-API — die Werkzeugfläche für Agent-Harnesses.

Dasselbe Muster wie ``cae_orchestrator/cae_cli.py``: wenige benannte Verben statt
HTTP-Aufrufe von Hand, damit ein lokales Modell die Werkzeugfläche im Kopf behalten
kann (Skill = CLI + README, bewusst kein MCP). Der Vertrag der Gegenstelle steht in
``INTEGRATION.md``; diese Datei fügt nichts hinzu, sie macht ihn nur bedienbar.

Bewusste Eigenschaften:
  * **Nur stdlib** (urllib/json/argparse). Läuft mit jedem Python 3.10+, ohne venv.
  * **Nur localhost.** Vorgabe http://localhost:5266, änderbar allein über ``--url``.
  * **Exit-Code als Signal.** 0 = ok, 1 = Fehler der Gegenstelle, 2 = Bedienfehler,
    3 = Server nicht erreichbar, 4 = Zeitüberschreitung. Am Code entscheiden, nicht
    am Fließtext.
  * **Ein Auftrag zur Zeit.** PicoGK erlaubt genau eine Library je Prozess und
    arbeitet alle Aufträge seriell über einen Worker ab — zwei gleichzeitige
    Aufrufe werden nicht parallel, sondern nacheinander bedient.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("PICOGK_URL", "http://localhost:5266")
# Die Gegenstelle bricht eine Geometrieerzeugung selbst nach 60 s ab (504).
# Etwas mehr, damit ihre eigene Meldung ankommt statt unserer.
TIMEOUT_S = 75
EXIT_OK, EXIT_REMOTE, EXIT_USAGE, EXIT_DOWN, EXIT_TIMEOUT = 0, 1, 2, 3, 4


def _call(url: str, pfad: str, nutzlast=None, timeout=TIMEOUT_S, roh=False):
    """Ein HTTP-Aufruf. Gibt (status, objekt_oder_bytes) zurück.

    Eine Fehlerantwort ist keine Ausnahme: die Gegenstelle legt ihre Begründung in
    ``error`` (400) oder ``detail`` (500/503/504), und die soll der Aufrufer sehen.
    """
    daten = None
    kopf = {"Accept": "application/json"}
    if nutzlast is not None:
        daten = json.dumps(nutzlast).encode()
        kopf["Content-Type"] = "application/json"

    anfrage = urllib.request.Request(url.rstrip("/") + pfad, data=daten, headers=kopf)
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            inhalt = antwort.read()
            if roh:
                return antwort.status, inhalt
            return antwort.status, json.loads(inhalt) if inhalt else {}
    except urllib.error.HTTPError as fehler:
        inhalt = fehler.read()
        try:
            return fehler.code, json.loads(inhalt)
        except ValueError:
            return fehler.code, {"detail": inhalt.decode(errors="replace")[:500]}
    except urllib.error.URLError as fehler:
        grund = getattr(fehler, "reason", fehler)
        if "timed out" in str(grund):
            raise TimeoutError(grund) from fehler
        raise ConnectionError(grund) from fehler
    except TimeoutError:
        raise


def _begruendung(objekt) -> str:
    if isinstance(objekt, dict):
        for schluessel in ("error", "detail", "title"):
            if objekt.get(schluessel):
                return str(objekt[schluessel])
    return json.dumps(objekt, ensure_ascii=False)[:400]


def _server_aus(fehler) -> int:
    print(f"Server auf {DEFAULT_URL} antwortet nicht ({fehler}).", file=sys.stderr)
    print("Starten mit: cd ~/ai-workspace/pikogk && ./start.sh", file=sys.stderr)
    print("Er braucht ein X-Display (DISPLAY, Vorgabe :1) und ~/Documents muss "
          "existieren — PicoGK legt sein Protokoll dort ab und bricht sonst ab.",
          file=sys.stderr)
    return EXIT_DOWN


# ---------------------------------------------------------------- Verben


def verb_health(args) -> int:
    try:
        status, formen = _call(args.url, "/skills", timeout=10)
    except (ConnectionError, TimeoutError) as fehler:
        return _server_aus(fehler)
    if status != 200:
        print(f"Server antwortet, aber /skills gibt HTTP {status}: {_begruendung(formen)}")
        return EXIT_REMOTE
    print(f"PicoGK-Web-API auf {args.url} erreichbar, {len(formen)} Formen geladen.")
    print("Namen: " + ", ".join(f.get("name", "?") for f in formen))
    return EXIT_OK


def verb_formen(args) -> int:
    try:
        status, formen = _call(args.url, "/skills")
    except (ConnectionError, TimeoutError) as fehler:
        return _server_aus(fehler)
    if status != 200:
        print(_begruendung(formen), file=sys.stderr)
        return EXIT_REMOTE

    for form in formen:
        print(f"\n{form.get('name')} — {form.get('description', '').strip()}")
        for p in form.get("parameters", []):
            zeile = (f"  {p.get('name'):<18} {p.get('label', ''):<22}"
                     f" {str(p.get('default')):>8} {p.get('unit', ''):<4}"
                     f" [{p.get('min')} .. {p.get('max')}]")
            optionen = p.get("options")
            if optionen:
                zeile += "  " + " | ".join(f"{i}={o}" for i, o in enumerate(optionen))
            print(zeile)
    return EXIT_OK


def _werte(paare: list[str]) -> dict:
    """``--set radius=15`` → ``{"radius": 15.0}``. Zahlen bleiben Zahlen."""
    werte: dict[str, float] = {}
    for paar in paare:
        if "=" not in paar:
            raise ValueError(f"'{paar}' ist kein name=wert")
        name, wert = paar.split("=", 1)
        try:
            werte[name.strip()] = float(wert)
        except ValueError as fehler:
            raise ValueError(f"'{wert}' für '{name}' ist keine Zahl") from fehler
    return werte


def _zeige_ergebnis(args, ergebnis: dict) -> int:
    print(f"Datei      {args.url}{ergebnis['fileUrl']}")
    print(f"Dreiecke   {ergebnis.get('triangleCount')}")
    box = ergebnis.get("boundingBoxMM") or {}
    print(f"Hüllquader {box.get('x')} x {box.get('y')} x {box.get('z')} mm")
    if args.ziel:
        status, inhalt = _call(args.url, ergebnis["fileUrl"], roh=True)
        if status != 200:
            print(f"Datei nicht abholbar: HTTP {status}", file=sys.stderr)
            return EXIT_REMOTE
        with open(args.ziel, "wb") as datei:
            datei.write(inhalt)
        print(f"Abgelegt   {os.path.abspath(args.ziel)} ({len(inhalt)} Bytes)")
    return EXIT_OK


def verb_erzeuge(args) -> int:
    try:
        werte = _werte(args.set or [])
    except ValueError as fehler:
        print(fehler, file=sys.stderr)
        return EXIT_USAGE

    try:
        status, antwort = _call(args.url, "/generate-shape",
                                {"type": args.typ, "values": werte})
    except TimeoutError as fehler:
        print(f"Zeitüberschreitung nach {TIMEOUT_S} s ({fehler}). Die Gegenstelle "
              "bricht eine Erzeugung selbst nach 60 s ab — die Abmessungen oder die "
              "Zellgröße sind für diese Voxelgröße zu groß.", file=sys.stderr)
        return EXIT_TIMEOUT
    except (ConnectionError,) as fehler:
        return _server_aus(fehler)

    if status != 200:
        print(f"HTTP {status}: {_begruendung(antwort)}", file=sys.stderr)
        return EXIT_REMOTE
    return _zeige_ergebnis(args, antwort)


def verb_deuten(args) -> int:
    text = " ".join(args.text).strip()
    if not text:
        print("Kein Text angegeben.", file=sys.stderr)
        return EXIT_USAGE

    try:
        status, antwort = _call(args.url, "/interpret", {"text": text}, timeout=120)
    except TimeoutError as fehler:
        print(f"Zeitüberschreitung ({fehler}).", file=sys.stderr)
        return EXIT_TIMEOUT
    except ConnectionError as fehler:
        return _server_aus(fehler)

    if status == 400:
        print(f"Der Text passt zu keiner bekannten Form: {_begruendung(antwort)}",
              file=sys.stderr)
        return EXIT_REMOTE
    if status != 200:
        # 502 heißt hier fast immer: das Modell aus CAE_LLM_MODEL ist nicht
        # geladen. Ein kalter Ladevorgang dauert laenger als das Zeitlimit des
        # Servers, der zweite Aufruf geht dann durch.
        print(f"HTTP {status}: {_begruendung(antwort)}", file=sys.stderr)
        return EXIT_REMOTE

    print(json.dumps(antwort, ensure_ascii=False, indent=2))

    if not args.und_erzeuge:
        print("\nWerte prüfen, dann mit 'erzeuge' bauen. Die Deutung ist ein "
              "Vorschlag des Modells, keine Auslegung.")
        return EXIT_OK

    try:
        status, ergebnis = _call(args.url, "/generate-shape", antwort)
    except TimeoutError as fehler:
        print(f"Zeitüberschreitung ({fehler}).", file=sys.stderr)
        return EXIT_TIMEOUT
    if status != 200:
        print(f"HTTP {status}: {_begruendung(ergebnis)}", file=sys.stderr)
        return EXIT_REMOTE
    print()
    return _zeige_ergebnis(args, ergebnis)


def verb_hol(args) -> int:
    try:
        status, inhalt = _call(args.url, args.pfad, roh=True)
    except (ConnectionError, TimeoutError) as fehler:
        return _server_aus(fehler)
    if status != 200:
        print(f"HTTP {status}", file=sys.stderr)
        return EXIT_REMOTE
    with open(args.ziel, "wb") as datei:
        datei.write(inhalt)
    print(f"{os.path.abspath(args.ziel)} ({len(inhalt)} Bytes)")
    return EXIT_OK


def main() -> int:
    zerleger = argparse.ArgumentParser(
        prog="picogk_cli.py",
        description="PicoGK-Web-API bedienen (Voxel-/Implizitgeometrie, STL-Ausgabe).")
    zerleger.add_argument("--url", default=DEFAULT_URL, help=f"Vorgabe {DEFAULT_URL}")
    unter = zerleger.add_subparsers(dest="verb", required=True)

    u = unter.add_parser("health", help="Erreichbarkeit und geladene Formen")
    u.set_defaults(func=verb_health)

    u = unter.add_parser("formen", help="alle Formen mit Parametern, Vorgaben, Grenzen")
    u.set_defaults(func=verb_formen)

    u = unter.add_parser("erzeuge", help="eine Form bauen und als STL ablegen")
    u.add_argument("--typ", required=True, help="Formname, siehe 'formen'")
    u.add_argument("--set", action="append", metavar="NAME=WERT",
                   help="Parameter, mehrfach angebbar")
    u.add_argument("--ziel", metavar="DATEI", help="STL zusätzlich hierher holen")
    u.set_defaults(func=verb_erzeuge)

    u = unter.add_parser("deuten", help="Freitext durch das lokale Modell in Typ+Werte")
    u.add_argument("text", nargs="+")
    u.add_argument("--und-erzeuge", action="store_true", dest="und_erzeuge",
                   help="gedeutete Werte direkt bauen (ungeprüft!)")
    u.add_argument("--ziel", metavar="DATEI", help="STL zusätzlich hierher holen")
    u.set_defaults(func=verb_deuten)

    u = unter.add_parser("hol", help="eine erzeugte Datei abholen")
    u.add_argument("pfad", help="z.B. /stl/cylinder_20261023_205927_80e06faf.stl")
    u.add_argument("--ziel", required=True, metavar="DATEI", help="Zielpfad")
    u.set_defaults(func=verb_hol)

    args = zerleger.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
