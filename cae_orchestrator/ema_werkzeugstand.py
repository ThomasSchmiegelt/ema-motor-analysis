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
    "ema_gsm.py",           # Gleichstrommaschine: Anker, Erregung, Kommutierung
    "ema_thermal.py",       # LPTN, Verluste am Betriebspunkt
    "ema_em2d_harm.py",     # 2-D-Feldstufe (Elmer, harmonisch)
    "ema_em2d_stat.py",     # 2-D-Feldstufe (Elmer, magnetostatisch) --
                            # heute Messinstrument gegen den FDM und in
                            # keiner ausgewiesenen Kennzahl; trotzdem hier,
                            # weil ein Feldloeser, der spaeter eine Zahl
                            # traegt, den Fingerabdruck von Anfang an
                            # bewegen muss statt ab dem Tag, an dem es
                            # jemand nachtraegt
    "ema_em3d.py",          # 3-D-Feldstufe
    "ema_em3d_harm.py",     # 3-D-Feldstufe (Elmer, harmonisch) -- die
                            # Kurzschlussring-Wirkung der ASM. Sie fehlte hier,
                            # solange der Weg nur ueber `cae_cli feld3d` zu
                            # erreichen war; seit dem 20.09.2026 haengt er am
                            # 3-D-Knopf der Oberflaeche, und was er liefert
                            # (`ring_wirkung`) ist eine Zahl wie jede andere.
    "ema_topology.py",      # Magnetgeometrie -- die Quelle beider Geometriewege
    "ema_wicklung.py",      # Wicklung, Widerstand, Kupfermasse
    "ema_radien.py",        # Radien und Luftspalt
    "ema_axial.py",         # Axialfluss: Ringraum, Rueckenblech, Anzug, Bandage
    "ema_axial_fdm.py",     # Axialfluss-Feldstufe: abgewickelter Mehrschnitt.
                            # Seine EICHUNG bewegt B_gap, psi und das Moment --
                            # am 06.10.2026 um 45 % (s. BEFUNDE.md).
    "ema_axial_em3d.py",    # Axialfluss in Elmer 3-D: der Ringsektor, mit dem
                            # der Mehrschnitt gegengerechnet wird
    # Die Scheiben-Geometrie bewegt keine Kennzahl DIREKT -- aber sie traegt
    # `nutbreite_mm`s Gegenstueck: wer hier die Zahnform aendert, aendert, was
    # gezeichnet UND was gesaettigt wird.
    "ema_axial_cad.py",     # Axialfluss als CAD: Schichtung, Zaehne, Sektormagnete
    # Das LPTN der Scheibe bewegt jede Temperatur und damit jedes Urteil
    # ueber Magnet- und Wicklungsgrenze.
    "ema_axial_thermik.py",
    # Der axiale Paarvergleich entscheidet keine Zahl selbst -- aber er ist
    # die Stufe, auf der eine Bauform GEWAEHLT wird, und seine Tore
    # (lambda_grenze/zahnform/ruecken) bestimmen, welche Option ueberhaupt
    # erscheint. Eine Aenderung daran bewegt also, was danach gerechnet wird.
    "ema_axial_vergleich.py",
    "ema_fluss.py",         # Flussweg: die zwei Integrale der Luftspaltflaeche
                            # (r^1 fuer psi_pm, r^2 fuer das Moment). Eine
                            # Aenderung daran bewegt Kt UND das Dauermoment.
    # Die Fliehkraft der MAGNETE. Sie bewegt den Gate-Wert der Struktur-FEM
    # gemessen um 53 % (582 -> 893 MPa P99) und den Steg-Richtwert, auf den
    # `sicherheit` stellt -- wer an der Zerlegung, der Dichte oder der
    # Knotenauswahl dreht, bewegt eine ausgewiesene Zahl.
    "ema_magnetlast.py",
    # Der Mehrkoerperlauf. Er traegt eigene Kennwerte (`magnet`-Block,
    # `anlagen`) und entscheidet ueber das Kriterium `magnetbruch`; seine
    # Anlagenmasse bewegen die Blechspannung um Faktor 1,9 gegenueber dem
    # verschmierten Modell.
    "ema_kontakt.py",
    "ema_grenzen.py",       # die Tore, die immer gelten
    "ema_schenkelpol.py",   # Polbefestigung (Fliehkraft am Polfuss) + Daempferkaefig
    "ema_eesm_cad.py",      # Schenkelpolgeometrie -- Quelle fuer CAD, Bild und Tor
    "ema_laeuferbild.py",   # **seit dem 20.09.2026 keine Zeichnung mehr, sondern
                            # eine QUELLE**: `ema_analysis._rasterise` stempelt
                            # den magnetlosen Laeufer aus `teile()` ins
                            # FDM-Gitter, `ema_em2d_stat` baut daraus seine
                            # OCC-Flaechen, und `ema_pipeline` zeichnet die
                            # Umrisse. Eine Aenderung daran bewegt damit
                            # Kennzahlen und nicht nur Bilder.
    "ema_synrm_cad.py",     # Flussbarrieren des Reluktanzlaeufers -- sie
                            # stehen im FDM-Raster und bewegen damit jede
                            # Kennzahl, die aus einem Feldlauf kommt
    "ema_deck.py",          # eigener Strukturweg (Gmsh + CalculiX)
    "ema_z88.py",           # zweite Meinung zur Struktur
    "ema_aster.py",         # dritte Meinung zur Struktur (Code Aster)
    "ema_pipeline.py",      # die Reihenfolge, in der all das laeuft
    "ema_magnetschluss.py", # Streuanteil und seine Schwellen: ein Urteil, das
                            # einen Entwurf abweist
    "ema_preistabelle.py",  # die Preisvariante des Paarvergleichs
    "ema_entscheidung.py",  # die Entscheidungsregel zwischen Entwuerfen --
                            # ihre Tore und ihre Knapp-Schwelle bestimmen, wer
                            # gewinnt
)

# Die Dateien der Oberflaeche. GETRENNT von PHYSIK, und zwar mit Absicht: eine
# geaenderte Seite bewegt keine Kennzahl, und beides in einen Fingerabdruck zu
# werfen hiesse, dass ein Knopfumbau wie eine Modelaenderung aussieht.
#
# Wozu er dann gut ist: eine Agentenseite steht STUNDENLANG offen (ein Lauf
# dauert so lange), und eine Aenderung an ihr wirkt erst nach dem Neuladen.
# Gemessen am 08.09.2026: die Studio-Seite war seit 09:44 offen, die
# Bereichsaufnahme kam um 10:19 dazu, und der Mitschnitt um 10:27 nahm weiter
# den ganzen Reiter auf -- der Browser fuhr die alte Seite, und nichts sagte es.
# Der Server meldet den Stand jetzt in der Arbeitsanzeige mit; aendert er sich,
# waehrend eine Seite offen ist, sagt sie es EINMAL.
#
# Seit dem 16.10.2026 liegt das JavaScript der Hauptmaske in `oberflaeche/`
# (vorher zwei <script>-Bloecke mit zusammen 11.568 Zeilen IN `ema.html`).
# Die Liste wird deshalb NICHT von Hand gefuehrt, sondern aus der Seite
# gelesen -- `ema_seite.skriptnamen()` nimmt die `<script src>`-Folge, und
# damit ist eine neue Datei an genau EINER Stelle einzutragen.
def _oberflaeche_dateien() -> tuple[str, ...]:
    fest = ("ema.html",             # die Hauptmaske -- seit 04.10.2026 mit drin
            "ema_studio.html",      # Studio-Seite
            "ema_agent.html",       # Schreibtischseite (PI/Hermes)
            "agent_gemein.js",      # das gemeinsame Verhalten beider
            "ema_laeufer.js")       # der Zeichner fuer Laeufer ohne Magnete
    try:
        import ema_seite
        skripte = tuple("oberflaeche/" + n for n in ema_seite.skriptnamen())
    except Exception:
        # Lieber eine unvollstaendige Liste als gar kein Fingerabdruck: ohne
        # ihn saehe eine geaenderte Seite aus wie eine unveraenderte.
        skripte = ()
    return fest + skripte


OBERFLAECHE: tuple[str, ...] = _oberflaeche_dateien()

_HIER = os.path.dirname(os.path.abspath(__file__))
_GIT_SEK = 30.0

_datei_cache: dict = {}          # pfad -> (mtime, groesse, hash)
_git_cache: tuple = (0.0, None)  # (zeit, antwort)


#: Weitere PYTHON-Dateien, deren Aenderung man im Browser sieht -- fuer
#: `geladen_veraltet`, nicht fuer den Fingerabdruck.
_WEITERE: tuple[str, ...] = ("server.py", "ema_diagnose.py", "ema_eesm_cad.py",
                             "ema_asm.py", "ema_gsm.py", "ema_topology.py",
                             "ema_schenkelpol.py", "ema_synrm_cad.py")

#: Dateien, die der Server AUSLIEFERT statt sie zu importieren. Sie brauchen
#: keinen Neustart -- ein Neuladen der Seite genuegt. Der Unterschied gehoert
#: in die Meldung: „Server neu starten" an der falschen Stelle kostet einen
#: Serverstart mitten in einem Lauf, und „Seite neu laden" an der falschen
#: Stelle kostet die naechste halbe Stunde Fehlersuche.
_AUSGELIEFERT: tuple[str, ...] = ("ema.html", "ema_laeufer.js",
                                  "ema_mobil.html", "ema_studio.html",
                                  "ema_agent.html", "agent_gemein.js"
                                  ) + tuple(n for n in OBERFLAECHE
                                            if n.startswith("oberflaeche/"))


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


def stand_oberflaeche() -> dict:
    """Fingerabdruck der Agentenseiten -- damit eine offene Seite merkt, dass sie
    veraltet ist. Keine Git-Abfrage: das hier wird im Sekundentakt gebraucht und
    beantwortet nur die Frage „liegt auf der Platte noch dasselbe wie vorhin"."""
    dateien, fehlt = {}, []
    for name in OBERFLAECHE:
        h = _datei_hash(os.path.join(_HIER, name))
        if h is None:
            fehlt.append(name)
        else:
            dateien[name] = h
    roh = "\n".join(f"{n}:{dateien[n]}" for n in sorted(dateien))
    return {"hash": hashlib.sha1(roh.encode("utf-8")).hexdigest()[:12],
            "dateien": dateien, "fehlt": fehlt}


#: Der Stand der Dateien in dem Augenblick, in dem DIESER Prozess sie geladen
#: hat. Wird beim ersten Aufruf von `geladen_veraltet` gefuellt -- spaeter ist
#: es zu spaet, dann steht die Datei schon anders auf der Platte.
_geladen_beim_start: dict | None = None


def geladen_veraltet() -> dict:
    """Laeuft dieser Prozess noch mit dem Code, der auf der Platte liegt?

    **Warum das eine eigene Frage ist.** Python laedt ein Modul EINMAL; ein
    ``import`` mitten in einer Route sieht danach aus, als hole er die Datei
    frisch, und tut es nicht. Wer waehrend eines laufenden Servers eine
    Rechendatei aendert, bekommt im Browser weiter die alte Fassung -- ohne
    dass irgendetwas widerspricht.

    Gemessen am 20.09.2026 und zweimal am selben Tag gemeldet: der Laeufer der
    Reluktanzmaschine kam als ``tasche``-Langloch statt als Flussbarriere
    heraus (also „wieder eine PSM ohne Magnete"), und ein Polkern schien im
    CAD zu fehlen. Beide Male lag es nicht am Code, sondern daran, dass der
    Serverprozess aelter war als er. Das ist die schlimmste Sorte Fehler, weil
    sie das Vertrauen in das Gemessene kostet: man sucht im Quelltext nach
    etwas, das dort laengst richtig steht.

    Verglichen werden die Dateihashes von JETZT mit denen beim ersten Aufruf
    (der beim Serverstart passiert). Gibt ``{"veraltet": [...], "seit": ...}``
    zurueck -- die Liste ist leer, solange nichts angefasst wurde.
    """
    global _geladen_beim_start
    jetzt = {}
    for name in tuple(PHYSIK) + tuple(_WEITERE) + tuple(_AUSGELIEFERT):
        h = _datei_hash(os.path.join(_HIER, name))
        if h is not None:
            jetzt[name] = h
    if _geladen_beim_start is None:
        _geladen_beim_start = {"dateien": dict(jetzt), "zeit": time.time()}
        return {"veraltet": [], "seit": _geladen_beim_start["zeit"], "n": 0,
                "neustart": [], "neuladen": []}
    alt = _geladen_beim_start["dateien"]
    veraltet = sorted(n for n in set(alt) | set(jetzt)
                      if alt.get(n) != jetzt.get(n))
    # **Zwei Faelle, und sie brauchen zwei verschiedene Handgriffe.** Eine
    # importierte Python-Datei liegt seit dem Start im Speicher -- da hilft nur
    # ein Serverneustart. Eine ausgelieferte Datei (`ema.html`,
    # `ema_laeufer.js`, …) liest der Browser bei jedem Aufruf neu -- da genuegt
    # ein Neuladen der Seite. Beides in einen Satz zu werfen kostet entweder
    # einen Serverstart mitten in einem vierstuendigen Lauf oder die naechste
    # halbe Stunde Fehlersuche.
    neuladen = [n for n in veraltet if n in _AUSGELIEFERT]
    neustart = [n for n in veraltet if n not in _AUSGELIEFERT]
    return {"veraltet": veraltet, "seit": _geladen_beim_start["zeit"],
            "n": len(veraltet), "neustart": neustart, "neuladen": neuladen}


def veraltet_text(v: dict) -> str:
    """Eine Zeile fuer die Oberflaeche -- oder leer, wenn alles frisch ist.

    Sie sagt, WELCHER Handgriff hilft, und nicht bloss, dass etwas alt ist.
    """
    v = v or {}
    if not (v.get("n") or 0):
        return ""

    def _liste(xs):
        xs = list(xs)
        return ", ".join(xs[:4]) + (f" (+{len(xs) - 4})" if len(xs) > 4 else "")

    z = []
    if v.get("neustart"):
        z.append(f"Der Server laeuft noch mit dem Code von seinem Start: "
                 f"{_liste(v['neustart'])} wurde(n) seither geaendert. Python "
                 f"laedt ein Modul EINMAL \u2014 was der Browser zeigt, kommt "
                 f"aus der ALTEN Fassung. **Server neu starten**; Neuladen der "
                 f"Seite genuegt hier nicht.")
    if v.get("neuladen"):
        z.append(f"Ausgelieferte Dateien haben sich geaendert "
                 f"({_liste(v['neuladen'])}) \u2014 **Seite neu laden** "
                 f"(Strg+F5). Dafuer braucht es keinen Serverneustart.")
    return "  ".join(z)


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
