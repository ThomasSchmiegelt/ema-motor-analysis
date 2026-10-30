"""Der Wächter über PI -- rechnet, ob der Agent arbeitet oder redet.

Warum es ihn gibt
-----------------

Ein lokales Modell, das nach einem Auftrag minutenlang „denkt" und dabei kaum
etwas aufruft, kostet Zeit und liefert nichts, und von aussen sieht ein
Strom aus Denkzeichen genau so aus wie Arbeit. Dieses Modul liest PIs
Sitzungsdatei (``~/.pi/agent/sessions/<cwd>/*.jsonl``, eine Zeile je Ereignis)
und beantwortet **ohne ein Sprachmodell** vier Fragen mit Zahlen:

* **Redet er?**       Denkzeichen je Werkzeugaufruf, und der Lauf der letzten
                      Zuege ohne einen einzigen Aufruf.
* **Dreht er sich?**  identische Aufrufe (gleicher Name, gleiche Argumente),
                      derselbe Aufruf mehrfach hintereinander, dieselbe Datei
                      wieder und wieder gelesen.
* **Scheitert er?**   Fehlerergebnisse in Folge.
* **Erfindet er?**    Zahlen im Antworttext, die in KEINEM Werkzeugergebnis der
                      Sitzung stehen (``ungedeckte_zahlen``) -- dieselbe Frage wie
                      die Deckungspruefung in ``ema_chat``, aber ueber die ganze
                      Sitzung und ohne Netz.

Das Urteil ist ``ok`` / ``warnen`` / ``eingreifen``, jedes mit den Kennzahlen,
die es ausgeloest haben, und einem **Vorschlag, was dem Agenten zu sagen ist**.
Der Waechter greift selbst nicht ein: er hat keine Hand an PIs Prozess, und ein
Abbruch ist eine Entscheidung des Menschen (oder des beaufsichtigenden Claude).

Die Schwellen
-------------

Geeicht an PIs eigenen Sitzungen, nicht gesetzt: die sechs juengsten Laeufe
(Stand 30.10.2026) liegen bei 0 bis 2,7 k Denkzeichen je Aufruf; der laengste
(40 Aufrufe, 107 k Denkzeichen) hat KEINE identischen Aufrufe -- eine erste
Zaehlung mit auf 80 Zeichen gekuerzten Argumenten hatte zehn gemeldet, das war
ein Artefakt des Kuerzens. Zwei der acht juengsten Sitzungen (31 k und 81 k
Denkzeichen am Stueck ohne Aufruf) sind die, die ``eingreifen`` ausloest. ``DENKEN_JE_AUFRUF_WARNEN`` liegt knapp ueber dem
Normalen, ``..._EINGREIFEN`` beim Doppelten. Wer sie aendert, soll
``python ema_pi_waechter.py --eichung`` neu laufen lassen.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time

SITZUNGEN = os.path.expanduser("~/.pi/agent/sessions")

DENKEN_JE_AUFRUF_WARNEN = 4000
DENKEN_JE_AUFRUF_EINGREIFEN = 8000
#: Denkzeichen in den letzten Zuegen OHNE Aufruf, ab denen es ein Eingreifen ist.
STUMM_DENKEN_EINGREIFEN = 12000
DOPPELT_ANTEIL_WARNEN = 0.20
DOPPELT_ANTEIL_EINGREIFEN = 0.35
HINTEREINANDER_EINGREIFEN = 3
#: Dasselbe Verb hintereinander mit WECHSELNDEN Argumenten -- Handsuche: gemessen 46 mal
#: ``magnetschluss`` mit anderen ``--set``-Werten, in 90 Minuten ein Rechenlauf. Die
#: Identitaetspruefung oben sieht das nicht, jeder Aufruf ist ein anderer.
SERIE_VERB_WARNEN = 8
SERIE_VERB_EINGREIFEN = 14
#: Dasselbe Verb INSGESAMT sehr oft (zwischendurch unterbrochen): 44 magnetschluss-Rechnungen.
VERB_GESAMT_WARNEN = 20
VERB_GESAMT_EINGREIFEN = 30
LESEND = {"hilfe", "geom", "status", "health", "results", "steckbrief", "projects", "routes", "aufgabe", "wait"}
FEHLER_IN_FOLGE_EINGREIFEN = 3
#: Mehr als so viele ungedeckte Zahlen im Antworttext -> warnen.
UNGEDECKT_WARNEN = 3

_ZAHL = re.compile(r"\d[\d.,]*\d")


def neueste_sitzung(projekt_dir: str | None = None) -> str | None:
    """Die zuletzt beschriebene Sitzungsdatei, optional nur fuer ein Arbeitsverzeichnis."""
    muster = os.path.join(SITZUNGEN, "*", "*.jsonl")
    dateien = glob.glob(muster)
    if projekt_dir:
        kodiert = "--" + os.path.abspath(projekt_dir).strip("/").replace("/", "-") + "--"
        dateien = [d for d in dateien if os.path.basename(os.path.dirname(d)) == kodiert]
    return max(dateien, key=os.path.getmtime) if dateien else None


def _ereignisse(pfad: str):
    with open(pfad, encoding="utf-8", errors="replace") as f:
        for zeile in f:
            try:
                yield json.loads(zeile)
            except json.JSONDecodeError:
                continue


def _zahlen(text: str) -> set[str]:
    """Zahlen mit mindestens drei Ziffern, auf die Ziffernfolge verkuerzt.

    ``120.000``, ``120,000`` und ``120000`` sind dieselbe Zahl; ``1.200`` und
    ``1,2`` kollidieren dabei -- hingenommen, das Mass soll Erfundenes finden und
    nicht Schreibweisen unterscheiden."""
    aus = set()
    for z in _ZAHL.findall(text):
        ziffern = re.sub(r"\D", "", z).lstrip("0")
        if len(ziffern) >= 3:
            aus.add(ziffern)
    return aus


def kennzahlen(pfad: str, letzte_zuege: int | None = None) -> dict:
    """Die Zaehlung. ``letzte_zuege`` beschraenkt auf die letzten Assistentenzuege."""
    zuege: list[dict] = []        # je Assistentenzug: denken, text, aufrufe[(name,args)]
    ergebnisse: list[tuple[str, bool, str]] = []   # (werkzeug, isError, text)
    nutzer = 0
    eingabe_token: list[int] = []     # Eingabelaenge je Zug = so voll war das Fenster
    erster = letzter = None
    for e in _ereignisse(pfad):
        t = e.get("timestamp")
        if t and not erster:
            erster = t
        letzter = t or letzter
        m = e.get("message") or {}
        rolle = m.get("role")
        if rolle == "user":
            nutzer += 1
        elif rolle == "assistant":
            z = {"denken": 0, "text": "", "aufrufe": []}
            u = m.get("usage") or {}
            if isinstance(u.get("input"), int):
                eingabe_token.append(u["input"] + int(u.get("cacheRead") or 0))
            inhalt = m.get("content")
            if isinstance(inhalt, str):
                z["text"] = inhalt
            for p in inhalt if isinstance(inhalt, list) else []:
                if not isinstance(p, dict):
                    continue
                if p.get("type") == "thinking":
                    z["denken"] += len(p.get("thinking", ""))
                elif p.get("type") == "text":
                    z["text"] += p.get("text", "")
                elif p.get("type") == "toolCall":
                    z["aufrufe"].append((p.get("name", "?"),
                                         json.dumps(p.get("arguments"), sort_keys=True,
                                                    ensure_ascii=False)))
            zuege.append(z)
        elif rolle == "toolResult":
            txt = ""
            for p in m.get("content") or []:
                if isinstance(p, dict) and p.get("type") == "text":
                    txt += p.get("text", "")
            ergebnisse.append((m.get("toolName", "?"), bool(m.get("isError")), txt))
    if letzte_zuege:
        zuege = zuege[-letzte_zuege:]

    aufrufe = [a for z in zuege for a in z["aufrufe"]]
    n = len(aufrufe)
    denken = sum(z["denken"] for z in zuege)
    text = sum(len(z["text"]) for z in zuege)
    doppelt = n - len(set(aufrufe))

    serie, ser, vorher, zaehl = 0, 0, None, {}
    for a in aufrufe:
        # Ein Aufruf kann mehrere Verben tragen (Schleife, &&); jedes zaehlt. Aufrufe ohne
        # cae_cli (lesen, ls) unterbrechen die Serie nicht -- sie suchen nichts.
        for v in re.findall(r"cae_cli\.py\s+([a-z][\w-]*)", str(a)):
            ser = ser + 1 if v == vorher else 1
            vorher = v
            serie = max(serie, ser)
            zaehl[v] = zaehl.get(v, 0) + 1
    serie_verb = vorher if ser == serie else None

    hint = lauf = 1
    for a, b in zip(aufrufe, aufrufe[1:]):
        lauf = lauf + 1 if a == b else 1
        hint = max(hint, lauf)
    if n < 2:
        hint = n

    gelesen = [a[1] for a in aufrufe if a[0] == "read"]
    mehrfach_gelesen = len(gelesen) - len(set(gelesen))

    stumm = 0
    for z in reversed(zuege):
        if z["aufrufe"]:
            break
        stumm += z["denken"]

    # Echte Rechenlaeufe: `run analyse` ohne --dry-run. Ein Auftrag mit Obergrenze
    # ("hoechstens drei Varianten") ist das, was ein Modell am leichtesten vergisst.
    laeufe = sum(1 for _, a in aufrufe
                 if "run analyse" in a and "--dry-run" not in a and "--hilfe" not in a)

    fehler_folge = lauf_f = 0
    for _, err, _t in ergebnisse:
        lauf_f = lauf_f + 1 if err else 0
        fehler_folge = max(fehler_folge, lauf_f)

    belegt: set[str] = set()
    for _, _e, t in ergebnisse:
        belegt |= _zahlen(t)
    # Auftrag und Nutzertexte zaehlen als gedeckt: sie stehen nicht im Werkzeugstrom.
    behauptet: set[str] = set()
    for z in zuege:
        behauptet |= _zahlen(z["text"])
    ungedeckt = sorted(behauptet - belegt)

    return {
        "datei": os.path.basename(pfad), "zuege": len(zuege), "aufrufe": n,
        "denkzeichen": denken, "textzeichen": text,
        "denken_je_aufruf": round(denken / n) if n else (denken or 0),
        "doppelte_aufrufe": doppelt,
        "doppelt_anteil": round(doppelt / n, 3) if n else 0.0,
        "hintereinander_gleich": hint,
        "verb_serie": serie,
        "verb_oft": max(((v, c) for v, c in zaehl.items() if v not in LESEND), key=lambda x: x[1], default=("", 0)),
        "mehrfach_gelesen": mehrfach_gelesen,
        "rechenlaeufe": laeufe,
        "stumm_denken": stumm,
        "fehler_in_folge": fehler_folge,
        "ungedeckte_zahlen": ungedeckt[:12], "ungedeckt_n": len(ungedeckt),
        "nutzer_nachrichten": nutzer,
        "kontext_token": eingabe_token[-1] if eingabe_token else None,
        "kontext_max_token": max(eingabe_token) if eingabe_token else None,
        "kontext_anteil": (round(eingabe_token[-1] / KONTEXT_FENSTER, 2) if eingabe_token else None),
        "sekunden": _spanne(erster, letzter),
    }


def _spanne(a, b) -> int | None:
    try:
        from datetime import datetime
        f = lambda s: datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return int((f(b) - f(a)).total_seconds())
    except Exception:                                            # noqa: BLE001
        return None


def urteil(k: dict, max_laeufe: int | None = None) -> dict:
    """Die Regeln. Jeder Befund nennt Kennzahl, Schwelle und was zu sagen ist.

    ``max_laeufe``: die Obergrenze aus dem Auftrag. Sie steht NICHT in der Sitzung
    und wird vom Aufsehenden mitgegeben (erster PI-Lauf am 30.10.2026: Auftrag
    „hoechstens drei Varianten", gerechnet wurden acht, und kein anderer Befund
    des Waechters hat das gesehen)."""
    eingreifen: list[tuple[str, str]] = []
    warnen: list[tuple[str, str]] = []
    if max_laeufe is not None and k.get("rechenlaeufe", 0) > max_laeufe:
        eingreifen.append((f"{k['rechenlaeufe']} Rechenlaeufe, erlaubt waren {max_laeufe}",
                           f"Du hast die erlaubten {max_laeufe} Rechenlaeufe ueberschritten. Hoer auf zu rechnen "
                           "und schliesse mit dem besten bisherigen Entwurf ab (`entscheide`)."))

    if k["aufrufe"] == 0 and k["denkzeichen"] > STUMM_DENKEN_EINGREIFEN:
        eingreifen.append((f"{k['denkzeichen']} Denkzeichen und kein einziger Werkzeugaufruf",
                           "Du denkst, ohne etwas zu tun. Ruf JETZT ein Werkzeug auf oder sag in einem Satz, was dich blockiert."))
    if k["stumm_denken"] > STUMM_DENKEN_EINGREIFEN:
        eingreifen.append((f"{k['stumm_denken']} Denkzeichen seit dem letzten Aufruf",
                           "Du denkst seit dem letzten Werkzeugaufruf zu lang. Entscheide dich und rufe den naechsten Schritt auf."))
    if k["denken_je_aufruf"] >= DENKEN_JE_AUFRUF_EINGREIFEN:
        eingreifen.append((f"{k['denken_je_aufruf']} Denkzeichen je Aufruf (Schwelle {DENKEN_JE_AUFRUF_EINGREIFEN})",
                           "Weniger ueberlegen, mehr messen: jeder Schritt ein Werkzeugaufruf, Begruendung in einem Satz."))
    elif k["denken_je_aufruf"] >= DENKEN_JE_AUFRUF_WARNEN:
        warnen.append((f"{k['denken_je_aufruf']} Denkzeichen je Aufruf (Schwelle {DENKEN_JE_AUFRUF_WARNEN})", ""))
    if k["hintereinander_gleich"] >= HINTEREINANDER_EINGREIFEN:
        eingreifen.append((f"derselbe Aufruf {k['hintereinander_gleich']}x hintereinander",
                           "Du wiederholst denselben Aufruf. Das Ergebnis aendert sich nicht: werte es aus oder waehle einen anderen Schritt."))
    vo, vn = k.get("verb_oft") or ("", 0)
    if vn >= VERB_GESAMT_EINGREIFEN:
        eingreifen.append((f"`{vo}` {vn}x aufgerufen",
                           "Du suchst von Hand: dieses Verb wurde immer wieder mit anderen Werten gerufen. Das ist Aufgabe von zielwert "
                           "(Parametervektoren, geklammert und gerankt) oder paarvergleich -- stelle die Suche dort auf."))
    elif vn >= VERB_GESAMT_WARNEN:
        warnen.append((f"`{vo}` {vn}x aufgerufen (Handsuche?)", ""))
    if k.get("verb_serie", 0) >= SERIE_VERB_EINGREIFEN:
        eingreifen.append((f"dasselbe Verb {k['verb_serie']}x hintereinander mit wechselnden Argumenten",
                           "Du suchst von Hand. Das ist Aufgabe von zielwert (Parametervektoren, geklammert und gerankt) oder paarvergleich: "
                           "stelle die Suche dort auf, statt Werte einzeln durchzuprobieren."))
    elif k.get("verb_serie", 0) >= SERIE_VERB_WARNEN:
        warnen.append((f"dasselbe Verb {k['verb_serie']}x hintereinander (Handsuche?)", ""))
    if k["doppelt_anteil"] >= DOPPELT_ANTEIL_EINGREIFEN:
        eingreifen.append((f"{k['doppelt_anteil']:.0%} identische Aufrufe",
                           "Du rufst vieles mehrfach auf. Notiere, was du schon weisst, und frage nichts zweimal."))
    elif k["doppelt_anteil"] >= DOPPELT_ANTEIL_WARNEN:
        warnen.append((f"{k['doppelt_anteil']:.0%} identische Aufrufe", ""))
    if k["fehler_in_folge"] >= FEHLER_IN_FOLGE_EINGREIFEN:
        eingreifen.append((f"{k['fehler_in_folge']} Fehlerergebnisse in Folge",
                           "Drei Fehler hintereinander: lies die Fehlermeldung, aendere den Aufruf, wiederhole ihn nicht unveraendert."))
    if k["ungedeckt_n"] > UNGEDECKT_WARNEN:
        warnen.append((f"{k['ungedeckt_n']} Zahlen im Text stehen in keinem Werkzeugergebnis: "
                       f"{', '.join(k['ungedeckte_zahlen'][:5])}",
                       "Nenne nur Zahlen, die ein Werkzeug geliefert hat, mit Quelle."))
    ka = k.get("kontext_anteil")
    if ka is not None and ka >= KONTEXT_EINGREIFEN:
        eingreifen.append((f"Kontextfenster zu {ka:.0%} voll ({k['kontext_token']} von {KONTEXT_FENSTER} Token)",
                           "Dein Kontext ist fast voll; was darueber liegt, wird still abgeschnitten. Schreib "
                           "auf, was feststeht (`auftrag`), lies nichts Grosses mehr (Skill nur ueber `hilfe <verb>`) "
                           "und schliesse ab oder starte frisch."))
    elif ka is not None and ka >= KONTEXT_WARNEN:
        warnen.append((f"Kontextfenster zu {ka:.0%} voll ({k['kontext_token']} von {KONTEXT_FENSTER} Token)",
                       "Lies nichts Grosses mehr; Skill-Stellen nur ueber `cae_cli.py hilfe <verb>`."))
    stufe = "eingreifen" if eingreifen else "warnen" if warnen else "ok"
    return {"stufe": stufe,
            "befunde": [b for b, _ in eingreifen + warnen],
            "sage_ihm": next((s for _, s in eingreifen + warnen if s), ""),
            "kennzahlen": k}


def pruefen(pfad: str | None = None, letzte_zuege: int | None = None,
            max_laeufe: int | None = None) -> dict:
    pfad = pfad or neueste_sitzung()
    if not pfad or not os.path.exists(pfad):
        return {"stufe": "unbekannt", "befunde": ["keine Sitzungsdatei gefunden"], "kennzahlen": {}}
    return urteil(kennzahlen(pfad, letzte_zuege), max_laeufe)


#: Phasen aus den Messwerten. Gemessen am 30.10.2026: das 17-GB-Modell liegt
#: dauerhaft im VRAM (21 GB belegt), die GPU-AUSLASTUNG zeigt aber nur, ob gerade
#: Token entstehen -- 11 % heisst "rechnet nicht", nicht "kaputt".
#: Das Kontextfenster des Modells (Token) -- dieselbe Quelle wie die Berichte und Chats.
#: Ollama schneidet still ab, was darueber liegt; der Agent merkt es nicht.
try:
    from ema_report import DEFAULT_NUM_CTX as KONTEXT_FENSTER      # EINE Quelle
except Exception:                                                  # noqa: BLE001
    KONTEXT_FENSTER = int(os.environ.get("CAE_LLM_NUM_CTX", "98304"))
KONTEXT_WARNEN = 0.70
KONTEXT_EINGREIFEN = 0.85

GPU_AKTIV_PROZENT = 30
CPU_AKTIV_PROZENT = 35


def _cpu_prozent(dauer: float = 1.0) -> float:
    def lesen():
        with open("/proc/stat") as f:
            w = [int(x) for x in f.readline().split()[1:]]
        return sum(w), w[3] + (w[4] if len(w) > 4 else 0)     # gesamt, idle+iowait
    g0, i0 = lesen()
    time.sleep(dauer)
    g1, i1 = lesen()
    return round(100.0 * (1 - (i1 - i0) / max(1, g1 - g0)), 1)


def ressourcen(dauer: float = 1.0) -> dict:
    """GPU-Auslastung, VRAM und CPU-Last -- und die Phase, die daraus folgt."""
    import subprocess
    gpu = vram = vram_max = None
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        gpu, vram, vram_max = [float(x) for x in o.stdout.strip().splitlines()[0].split(",")]
    except Exception:                                            # noqa: BLE001
        pass
    cpu = _cpu_prozent(dauer)
    if gpu is not None and gpu >= GPU_AKTIV_PROZENT:
        phase = "Modell denkt (GPU)"
    elif cpu >= CPU_AKTIV_PROZENT:
        phase = "Rechnung laeuft (CPU)"
    else:
        phase = "nichts arbeitet"
    return {"gpu_prozent": gpu, "vram_mb": vram, "vram_max_mb": vram_max,
            "cpu_prozent": cpu, "phase": phase}


def eichung(anzahl: int = 8) -> list[dict]:
    """Die Schwellen gegen die juengsten Sitzungen halten -- zeigt, wen sie treffen wuerden."""
    dateien = sorted(glob.glob(os.path.join(SITZUNGEN, "*", "*.jsonl")), key=os.path.getmtime)[-anzahl:]
    return [{"datei": os.path.basename(d)[:19], **{k: v for k, v in pruefen(d).items() if k != "kennzahlen"},
             "aufrufe": kennzahlen(d)["aufrufe"], "denken_je_aufruf": kennzahlen(d)["denken_je_aufruf"]}
            for d in dateien]


def _ausgabe(u: dict) -> str:
    k = u["kennzahlen"]
    z = [f"PI-Wächter: {u['stufe'].upper()}"]
    if k:
        z.append(f"  {k['zuege']} Züge · {k['aufrufe']} Aufrufe · {k['denkzeichen']} Denkzeichen "
                 f"({k['denken_je_aufruf']}/Aufruf) · {k['doppelte_aufrufe']} doppelt · {k.get('rechenlaeufe', 0)} Rechenläufe · "
                 f"{k['fehler_in_folge']} Fehler in Folge · {k['ungedeckt_n']} ungedeckte Zahlen")
    z += [f"  - {b}" for b in u["befunde"]]
    r = u.get("ressourcen")
    if r:
        g = "—" if r["gpu_prozent"] is None else f"{r['gpu_prozent']:.0f} %"
        v = "" if r["vram_mb"] is None else f" · VRAM {r['vram_mb'] / 1024:.1f}/{r['vram_max_mb'] / 1024:.0f} GB"
        z.append(f"  GPU {g}{v} · CPU {r['cpu_prozent']:.0f} % → {r['phase']}")
    if u.get("sage_ihm"):
        z.append(f"  Vorschlag an PI: \"{u['sage_ihm']}\"")
    return "\n".join(z)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Wächter über PI (algorithmisch, ohne Modell)")
    ap.add_argument("sitzung", nargs="?", help="Sitzungsdatei (Vorgabe: die neueste)")
    ap.add_argument("--letzte", type=int, default=None, help="nur die letzten N Züge werten")
    ap.add_argument("--folge", type=int, metavar="SEK", help="alle SEK Sekunden erneut prüfen")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-laeufe", type=int, default=None, dest="max_laeufe",
                    help="Obergrenze der Rechenläufe aus dem Auftrag (`run analyse` ohne --dry-run)")
    ap.add_argument("--ressourcen", action="store_true", help="GPU, VRAM, CPU und Phase mit ausgeben")
    ap.add_argument("--eichung", action="store_true", help="Schwellen gegen die jüngsten Sitzungen halten")
    a = ap.parse_args(argv)
    if a.eichung:
        for r in eichung():
            print(json.dumps(r, ensure_ascii=False))
        return 0
    while True:
        u = pruefen(a.sitzung, a.letzte, a.max_laeufe)
        if a.ressourcen:
            u["ressourcen"] = ressourcen()
        print(json.dumps(u, ensure_ascii=False) if a.json else _ausgabe(u), flush=True)
        if not a.folge:
            return {"ok": 0, "warnen": 0, "eingreifen": 1}.get(u["stufe"], 2)
        time.sleep(a.folge)


if __name__ == "__main__":
    sys.exit(main())
