"""Magnetischer Kurzschluss im Laeufer -- gemessen, und vom Bild gegengelesen.

Die Frage
---------

Fliesst der Fluss der Magnete durch den Luftspalt zum Stator, oder schliesst er
sich im Laeufer ueber Stege und die duenne Haut ueber den Taschen kurz? Ein
Laeufer, der sich kurzschliesst, rechnet sich im Bericht gut (die Magnete sind
ja da) und liefert kein Moment.

Wer entscheidet
---------------

**Die Zahl entscheidet, das Bild liest nur gegen.** Das ist eine Folge einer
Messung, nicht eine Vorliebe: dasselbe Feldbild (``ema_feldbild.bild_pol``) ging
an zwei Sehmodelle (ministral-3:14b, qwen3.8:27b), jeweils fuer eine gute, eine
flache und eine nachweislich kurzgeschlossene Geometrie. Beide antworteten
dreimal dasselbe -- „teilweise“, 0,20 bzw. 0,15 -- ohne die Geometrien zu
unterscheiden (Messwerte im Ereignisprotokoll). Ein Urteil, das fuer jedes Bild
gleich ausfaellt, ist keines. Deshalb:

* ``messen``  -- Flussbilanz aus dem Vektorpotential A der 2-D-FDM. In der Ebene
  ist der Fluss zwischen zwei Punkten die Differenz von A (mal Laenge). Der
  Magnet liefert im Leerlauf am staerksten ``A_magnet`` (Spitzenwert in den
  Magnetpixeln); durch den Luftspalt kommt davon ``A_spalt`` an (Spitzenwert auf
  dem Kreis in der Spaltmitte). Der Rest schliesst sich im Laeufer:
  ``streuanteil = 1 - A_spalt / A_magnet``.
* ``bild``    -- dieselbe Zahl als Bild: Feldlinien mit Pegel ueber ``A_spalt``
  erreichen den Luftspalt nie und sind **rot**, alle anderen cyan. So ist die
  Frage fuer ein Sehmodell eine, die man im Bild beantworten kann (Anteil Rot),
  statt eine, die ein Verstaendnis der Topologie verlangt.
* ``sehen``   -- fragt ein Sehmodell nach dem EIGENEN Bild (nicht dem Feldbild).
  Gemessen an den drei Eichgeometrien (Streuanteil flach 0,26 / gut 0,33 / kurz
  0,56): ``qwen3.8:27b`` schaetzt Rot 0,35 / 0,40 / 0,60 -- Rangfolge richtig und
  jeder Wert innerhalb 0,2 der Messung; ``ministral-3:14b`` 0,35 / 0,65 / 0,75 --
  Rangfolge richtig, aber die gute Geometrie als „kurzschluss". Das ist die
  Begruendung fuer die Vorgabe ``SEH_MODELL``. In KEINEM Fall nennt ein Modell von
  sich aus die Stufe richtig (qwen: dreimal „auffaellig"): taugt als Gegenlese der
  ZAHL, nicht als Urteil. Das Ergebnis steht NEBEN der
  Zahl und kann sie nie ersetzen; widerspricht es, steht ``uneins`` im Urteil.
* ``urteil``  -- beides in einem Aufruf.

Die Schwellen
-------------

``STREU_AUFFAELLIG`` = 0,35 und ``STREU_KURZ`` = 0,50 sind an **drei Geometrien
der frischen Vorgabe** geeicht: V-Magnete 120 deg -> 0,33, flach 170 deg -> 0,26,
fast radial 20 deg -> 0,56. Innerhalb dessen, was das Schema erlaubt (``magAngle`` >= 40), sind es 0,40
(40 deg), 0,33 (60 deg) und 0,24 (90 deg); der Eichpunkt 20 deg liegt
ausserhalb davon und ist ueber ``--set`` nicht erreichbar. Die Zahl streut ueber
N = 300...500 um etwa +-0,03. Das ist eine Eichung an Beispielen, keine an
Messung einer gebauten Maschine; die Zahl ist ein Vergleichsmass zwischen Entwuerfen,
kein Streufaktor im Sinne von ``ema_analysis.K_LEAK_*`` (der kennt den Weg nicht,
nur die Summe). **Geltungsbereich:** geeicht und gegengeprueft an V-Anordnungen (dreilagig,
V 40...120 deg) und -- als untere Gegenprobe -- an Oberflaechenmagneten
(SPM: 2,7 %, wie zu erwarten ohne Steg). **Fuer Speichen- (``spoke``) und
Balkenmagnete (``bar``) ist die Zahl NICHT geprueft:** dort lieferte sie 75...85 %,
und ob der Referenzpunkt A = 0 fuer diese Anordnungen an der richtigen Stelle
liegt (die Magnete sitzen an der q-Achse), ist offen. Ein Urteil „Kurzschluss"
an einer dieser Bauformen ist deshalb ein Hinweis, kein Beleg.

Wer die Schwelle verschiebt, soll die drei Punkte neu messen
(``selbsttest``).
"""
from __future__ import annotations

import base64
import json
import math
import os
import urllib.request

import numpy as np

import ema_feldbild as FB

#: Ab hier ist der Entwurf auffaellig / ein Kurzschluss. Eichung: siehe Kopf.
STREU_AUFFAELLIG = 0.35
STREU_KURZ = 0.50

#: Kleinste FDM-Aufloesung, bei der die Zahl gilt. Gemessen am selben Entwurf:
#: N=240 -> Streuanteil 0,03 (V 40 deg) / 0,06 (90 deg); N=300/400/500 -> 0,40 /
#: 0,41 / 0,42 (40 deg) und 0,24 / 0,29 / 0,26 (90 deg). Unter 300 ist die
#: Luftspaltwelle nicht aufgeloest (vgl. CLAUDE.md, „Voreinstellungen"); darueber
#: streut die Zahl um etwa +-0,03.
N_MIN = 300

#: Sehmodell fuer die Gegenlese. Eigenes Modell als Vorgabe, nicht das des
#: Agenten: ein Urteil vom selben Modell, das den Entwurf gemacht hat, ist keins.
SEH_MODELL = os.environ.get("CAE_SEH_MODELL", "qwen3.8:27b-mtp-q4_K_M")
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")

_ROT = "#ff4d4d"
_CYAN = "#3fe0ff"


#: Streuanteil bei zwei Aufloesungen darf hoechstens so weit auseinanderliegen.
#: V-Anordnungen: +-0,03 (N=300...500); Speichen am 30.10.2026: 0,81 -> 0,68 bei
#: N=300 -> 400, also 0,13 -- dort sind duenne Stege bei 300 Pixeln nicht aufgeloest.
STABIL_TOL = 0.08


def messen(geom: dict, N: int = 300, f: dict | None = None) -> dict:
    """Streuanteil aus EINEM Leerlauf-Feld. ``f`` darf ein fertiges
    ``ema_feldbild.feld_rechnen``-Ergebnis sein (dann kostet es nichts).

    Eine Geometrie, die das Layouttor reisst (Taschenkollision, Mindeststeg),
    wird NICHT gemessen: die V-Form der verkleinerten Maschine kam bei 6,2 mm
    ueberlappenden Taschen auf 94 % -- eine Zahl fuer eine Maschine, die es nicht
    geben kann."""
    try:
        from ema_rotorcheck import rotor_layout_check
        lay = rotor_layout_check(geom)
        if lay.get("ok") is False:
            grund = ("Layout ungueltig, Streuanteil sinnlos: "
                     + str(lay.get("fatal") or lay.get("findings") or lay)[:200])
            out = {"ok": False, "grund": grund}
            try:
                import ema_magnetheilung
                h = ema_magnetheilung.heile(geom)
                out["heilung"] = {k: h[k] for k in ("set", "hinweis") if k in h}
                if h["set"]:
                    out["grund"] += " -> naechste gueltige Einstellung: " + " ".join(f"--set {x}" for x in h["set"])
                else:
                    out["grund"] += " -> " + h["hinweis"]
            except Exception:                                    # noqa: BLE001
                pass
            return out
    except Exception:                                            # noqa: BLE001
        pass
    f = f or FB.feld_rechnen(geom, N=max(int(N), N_MIN))
    A, r = f["A"], f["r_mm"]
    ro, rs = geom["rotorOD"] / 2.0, geom["statorID"] / 2.0
    ring = np.abs(r - 0.5 * (ro + rs)) < 0.4
    mag = np.asarray(f["magnet"], dtype=bool)
    if not ring.any() or not mag.any():
        return {"ok": False, "grund": "kein Luftspaltring oder keine Magnete im Raster "
                "(Maschinenart ohne Magnete?) -- nichts zu messen"}
    a_spalt = float(np.nanmax(np.abs(A[ring])))
    a_magnet = float(np.nanmax(np.abs(A[mag])))
    if a_magnet <= 0:
        return {"ok": False, "grund": "Magnetfluss null im Feld"}
    anteil = max(0.0, 1.0 - a_spalt / a_magnet)
    if anteil >= STREU_KURZ:
        stufe = "kurzschluss"
        grund = (f"{anteil:.0%} des Magnetflusses schliesst sich im Laeufer "
                 f"(Schwelle {STREU_KURZ:.0%}) -- Magnete steiler stellen, Stege "
                 "dicker/laenger oder die Taschen weiter vom Rand")
    elif anteil >= STREU_AUFFAELLIG:
        stufe = "auffaellig"
        grund = f"{anteil:.0%} Streuung (Schwelle {STREU_AUFFAELLIG:.0%}) -- pruefen, kein Ausschluss"
    else:
        stufe = "ok"
        grund = f"{anteil:.0%} Streuung, unter {STREU_AUFFAELLIG:.0%}"
    return {"ok": True, "A_spalt": round(a_spalt, 3), "A_magnet": round(a_magnet, 3),
            "streuanteil": round(anteil, 3), "stufe": stufe, "grund": grund,
            "N": f["N"]}


def messen_stabil(geom: dict, N: int = 300) -> dict:
    """``messen`` bei N und bei 4N/3; weichen beide um mehr als ``STABIL_TOL`` ab,
    ist die Stufe ``unsicher`` -- die Aufloesung bindet, nicht der Entwurf."""
    a = messen(geom, N=N)
    if not a.get("ok"):
        return a
    b = messen(geom, N=int(max(N, N_MIN) * 4 / 3))
    if not b.get("ok"):
        return a
    ab = abs(a["streuanteil"] - b["streuanteil"])
    b["streuanteil_n_klein"] = a["streuanteil"]
    b["abweichung_n"] = round(ab, 3)
    if ab > STABIL_TOL:
        b["stufe"] = "unsicher"
        b["grund"] = (f"Streuanteil {a['streuanteil']:.0%} bei N={a['N']} gegen {b['streuanteil']:.0%} "
                      f"bei N={b['N']} (Abweichung {ab:.2f} > {STABIL_TOL}): nicht belastbar -- "
                      "zu duenne Stege fuer diese Aufloesung. Weder Freispruch noch Kurzschluss.")
    return b


def bild(geom: dict, f: dict, a_spalt: float, pfad: str) -> str:
    """Feldlinien, nach dem Weg gefaerbt: rot = bleibt im Laeufer, cyan = durch den Spalt."""
    fig, ax = FB._leinwand()
    FB._silhouette(ax, f)
    A = np.asarray(f["A"], dtype=float)
    spitze = float(np.nanmax(np.abs(A[f["r_mm"] < geom["rotorOD"] / 2.0])))
    n = 14
    pegel = np.linspace(spitze / n, spitze, n)
    for sgn in (1, -1):
        for p in pegel:
            ax.contour(A, levels=[sgn * p], zorder=10, linewidths=0.9,
                       colors=_ROT if p > a_spalt else _CYAN)
    FB._umrisse(ax, geom, f)
    FB._magnete(ax, geom, f)
    ax.set_aspect("equal")
    FB._titel(ax, "Feldlinien nach Weg: rot = bleibt im Laeufer, cyan = durch den Luftspalt")
    return FB._speichern(fig, pfad)


_FRAGE = (
    "Das Bild zeigt den Querschnitt einer E-Maschine. Feldlinien sind ROT, wenn sie im "
    "Laeufer bleiben (magnetischer Kurzschluss), und CYAN, wenn sie durch den Luftspalt zum "
    "Stator gehen. Schaetze den Anteil der roten Linien an allen Feldlinien im Laeufer. "
    "Antworte NUR als JSON: {\"anteil_rot\": Zahl 0..1, \"urteil\": \"ok\"|\"auffaellig\"|\"kurzschluss\", "
    "\"stelle\": kurzer Text}"
)


def sehen(pfad: str, modell: str | None = None, timeout: int = 600) -> dict:
    """Ein Sehmodell fragen. Fehler werden gemeldet, nie geraten."""
    modell = modell or SEH_MODELL
    try:
        b = base64.b64encode(open(pfad, "rb").read()).decode()
        d = {"model": modell, "stream": False, "format": "json", "think": False,
             "options": {"temperature": 0, "num_ctx": 8192},
             "messages": [{"role": "user", "content": _FRAGE, "images": [b]}]}
        req = urllib.request.Request(OLLAMA + "/api/chat", json.dumps(d).encode(),
                                     {"Content-Type": "application/json"})
        antwort = json.loads(json.load(urllib.request.urlopen(req, timeout=timeout))
                             ["message"]["content"])
        return {"ok": True, "modell": modell,
                "anteil_rot": float(antwort.get("anteil_rot")),
                "urteil": str(antwort.get("urteil")), "stelle": antwort.get("stelle", "")}
    except Exception as e:                                       # noqa: BLE001
        return {"ok": False, "modell": modell, "grund": f"{type(e).__name__}: {e}"}


def urteil(geom: dict, ziel_dir: str | None = None, mit_bild: bool = True,
           N: int = 300) -> dict:
    """Messung + (wenn gewuenscht) Gegenlese durch das Sehmodell. Die Zahl gilt."""
    m = messen_stabil(geom, N=N)
    if not m.get("ok") or not mit_bild:
        return m
    f = FB.feld_rechnen(geom, N=m["N"])
    pfad = os.path.join(ziel_dir or ".", "magnetschluss.png")
    bild(geom, f, m["A_spalt"], pfad)
    s = sehen(pfad)
    m["bild"] = pfad
    m["sehen"] = s
    if s.get("ok"):
        # Gegenlese: weicht das Sehmodell um mehr als 0,2 vom Messwert ab, wird es
        # genannt -- und die Messung bleibt trotzdem das Urteil.
        m["uneins"] = abs(s["anteil_rot"] - m["streuanteil"]) > 0.2
    return m


def selbsttest(basis: dict, modell: str | None = None, ziel_dir: str = ".") -> list[dict]:
    """Die drei Eichpunkte neu messen UND dem Sehmodell vorlegen -- belegt, ob das
    Sehmodell die Geometrien ueberhaupt unterscheidet."""
    aus = []
    for name, aend in (("gut", {}), ("flach", {"magAngle": 170, "magLayers": 1}),
                       ("kurz", {"magAngle": 20})):
        g = {**basis, **aend}
        f = FB.feld_rechnen(g, N=300)
        m = messen(g, f=f)
        pfad = bild(g, f, m["A_spalt"], os.path.join(ziel_dir, f"selbsttest_{name}.png"))
        aus.append({"name": name, "streuanteil": m["streuanteil"], "stufe": m["stufe"],
                    "sehen": sehen(pfad, modell)})
    return aus
