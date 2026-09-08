"""Welches Werkzeug hat diese Zahl gerechnet -- und hat sich das mitten im Lauf geaendert?

Warum es dieses Modul gibt
--------------------------

Die Agentenkoepfe sind **Codieragenten**: ``pi --mode rpc`` und ``hermes acp``
haben Schreibrecht im Arbeitsverzeichnis, und im Browserpfad wird keine Freigabe
erfragt (``HermesKopf._freigabe`` stimmt sogar ausdruecklich zu, weil ein
unbeantworteter Zug sonst still stuende). Bei einer Zielwertsuche ist eine
Aenderung an ``ema_asm.py`` deshalb der KUERZESTE Weg zum Ziel -- und der
einzige, der die Zahl falsch macht, ohne dass es jemand sieht. Gemessen am
08.09.2026: ein Lauf meldete ``2,8e20 W`` als Verlustleistung, und die Frage,
die daraus folgte, war nicht "warum diese Zahl", sondern "woher weiss ich, dass
das noch dasselbe Werkzeug ist".

**Verhindern laesst sich das nicht.** Der Agent laeuft als derselbe Benutzer wie
der Server, ohne Sandkasten; wem eine Datei gehoert, der darf sie schreiben, und
ein ``chmod`` zurueck kostet eine Zeile. Ein Schloss, das man von innen
aufschliessen kann, ist kein Schloss, sondern eine Behauptung.

**Verbergen** laesst es sich aber sehr wohl verhindern, und das ist hier die
ganze Absicht:

* jede abgelegte Rechnung traegt den Fingerabdruck der Physikmodule, aus denen
  sie kam -- zwei Zahlen aus zwei Staenden sind dann sichtbar nicht vergleichbar;
* aendert sich der Stand WAEHREND ein Kopf laeuft, sagt es die Seite in dem
  Augenblick, in dem der Mensch ohnehin hinsieht, und es steht danach im
  Protokoll des Laufs.

Das ist dieselbe Regel, mit der dieses Repo schon die Agentenlaeufe behandelt:
geschrieben, aber unerreichbar ist dasselbe wie nicht gespeichert. Hier:
geaendert, aber unbenannt ist dasselbe wie erfunden.

Was in ``PHYSIK`` steht -- und warum es eine Liste ist und kein Muster
---------------------------------------------------------------------

Genau die Module, deren Aenderung eine **Kennzahl bewegt**. Ein ``glob`` ueber
``ema_*.py`` zoege jede neue Seite, jeden Bericht und jedes Werkzeug mit hinein;
der Fingerabdruck aenderte sich dann staendig aus Gruenden, die keine Physik
sind, und waere binnen einer Woche Rauschen, das niemand mehr liest. Eine Liste
muss gepflegt werden -- das ist der Preis dafuer, dass ihre Aenderung etwas
bedeutet.

Kosten
------

``stand()`` wird je Ereignis und im Sekundentakt der Arbeitsleiste gerufen. Es
liest die Dateien nur, wenn sich mtime oder Groesse geaendert haben; sonst kommt
die gemerkte Antwort zurueck. ``git`` wird hoechstens alle ``_GIT_SEK`` Sekunden
befragt und ist ueberdies weich: ohne Git-Baum steht dort ``None``, und der
Fingerabdruck steht trotzdem.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time

# Die Module, deren Aenderung eine gerechnete Zahl bewegt. Ausdruecklich, nicht
# als Muster -- s. Modulkopf.
PHYSIK: tuple[str, ...] = (
    "ema_analysis.py",      # Feld, Kt, Umrichtergrenze, Auslegungspunkt
    "ema_asm.py",           # Asynchronmaschine: Magnetisierung, Kaefig, Betriebspunkt
    "ema_thermal.py",       # LPTN, Verluste am Betriebspunkt
    "ema_em2d_harm.py",     # 2-D-Feldstufe (Elmer, harmonisch)
    "ema_em3d.py",          # 3-D-Feldstufe
    "ema_topology.py",      # Magnetgeometrie -- die Quelle beider Geometriewege
    "ema_wicklung.py",      # Wicklung, Widerstand, Kupfermasse
    "ema_radien.py",        # Radien und Luftspalt
    "ema_grenzen.py",       # die Tore, die immer gelten
    "ema_deck.py",          # eigener Strukturweg (Gmsh + CalculiX)
    "ema_z88.py",           # zweite Meinung zur Struktur
    "ema_pipeline.py",      # die Reihenfolge, in der all das laeuft
)

_HIER = os.path.dirname(os.path.abspath(__file__))
_GIT_SEK = 30.0

_datei_cache: dict = {}          # pfad -> (mtime, groesse, hash)
_git_cache: tuple = (0.0, None)  # (zeit, antwort)


def _datei_hash(pfad: str) -> str | None:
    """SHA-1 der Datei, gemerkt ueber (mtime, Groesse).

    Eine geaenderte Datei mit gleicher Groesse und zurueckgedrehter mtime waere
    nicht zu sehen -- das ist bewusst hingenommen: wer so weit geht, verbirgt
    absichtlich, und dagegen hilft dieses Modul ohnehin nicht. Gegen die
    Aenderung, um die es geht (der Agent schreibt eine Datei), hilft es.
    """
    try:
        st = os.stat(pfad)
    except OSError:
        return None
    schluessel = (st.st_mtime_ns, st.st_size)
    eintrag = _datei_cache.get(pfad)
    if eintrag and eintrag[0] == schluessel:
        return eintrag[1]
    try:
        with open(pfad, "rb") as fh:
            h = hashlib.sha1(fh.read()).hexdigest()[:12]
    except OSError:
        return None
    _datei_cache[pfad] = (schluessel, h)
    return h


def _git() -> dict:
    """Der Git-Stand -- weich. Ohne Baum, ohne ``git``, ohne alles: ``None``."""
    global _git_cache
    jetzt = time.time()
    if jetzt - _git_cache[0] < _GIT_SEK and _git_cache[1] is not None:
        return _git_cache[1]
    aus = {"kopf": None, "schmutzig": []}
    try:
        kopf = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=_HIER, capture_output=True, text=True, timeout=5)
        if kopf.returncode == 0:
            aus["kopf"] = kopf.stdout.strip() or None
        # Nur die PHYSIK-Dateien, nicht der ganze Baum: dass die Seite gerade
        # umgebaut wird, ist fuer die Zahlen ohne Belang.
        st = subprocess.run(["git", "status", "--porcelain", "--"] + list(PHYSIK),
                            cwd=_HIER, capture_output=True, text=True, timeout=5)
        if st.returncode == 0:
            # ``git status`` schreibt repo-relativ, ``abweichung()`` nackte
            # Modulnamen. Beide landen in derselben Lampe -- also dieselbe Form.
            aus["schmutzig"] = sorted(
                os.path.basename(z[3:].strip())
                for z in st.stdout.splitlines() if len(z) > 3)
    except (OSError, subprocess.SubprocessError):
        pass
    _git_cache = (jetzt, aus)
    return aus


def stand() -> dict:
    """Der Fingerabdruck der Physikmodule -- eine Zahl, und woraus sie entsteht.

    ``hash`` ist ueber (Name, Dateihash) aller vorhandenen Module gebildet, in
    fester Reihenfolge. ``fehlt`` nennt Module, die die Liste kennt und die es
    nicht gibt -- das ist selbst eine Aussage und darf nicht still verschwinden.
    """
    dateien, fehlt = {}, []
    for name in PHYSIK:
        h = _datei_hash(os.path.join(_HIER, name))
        if h is None:
            fehlt.append(name)
        else:
            dateien[name] = h
    roh = "\n".join(f"{n}:{dateien[n]}" for n in sorted(dateien))
    g = _git()
    return {"hash": hashlib.sha1(roh.encode("utf-8")).hexdigest()[:12],
            "dateien": dateien, "fehlt": fehlt,
            "git": g["kopf"], "schmutzig": g["schmutzig"],
            "zeit": round(time.time(), 1)}


def abweichung(a: dict, b: dict) -> list:
    """Welche Module unterscheiden zwei Staende -- mit Namen, nicht nur „anders"."""
    da = (a or {}).get("dateien") or {}
    db = (b or {}).get("dateien") or {}
    return sorted(n for n in set(da) | set(db) if da.get(n) != db.get(n))


def kurz(s: dict) -> str:
    """Eine Zeile fuer Steckbrief, Ablage und Protokoll."""
    if not s:
        return "unbekannt"
    t = s.get("hash", "?")
    if s.get("git"):
        t += f" (git {s['git']}"
        n = len(s.get("schmutzig") or [])
        t += f", {n} Datei{'en' if n != 1 else ''} geändert)" if n else ")"
    if s.get("fehlt"):
        t += f" — fehlt: {', '.join(s['fehlt'])}"
    return t
