"""Fahrzyklen: nachsehen, was es gibt — und Eigenes behalten.

Warum es das gibt
-----------------

Der Payload kannte den Fahrzyklus gar nicht: weder ``--frisch`` noch das Schema
trugen ``cycle``/``vehicle``, also fiel jeder Lauf auf die Vorgabe der Pipeline
zurueck (``cycle="wltp3"``) — und ``wltp3`` zieht zusaetzlich die
Autobahn-Volllastfahrt nach sich. Ein Nabenmotor fuer ein 140-kg-Fahrrad wurde so
ueber 23 km WLTP und 220 km/h Autobahn gerechnet, mit dem Fahrzeugmodell eines
1600-kg-Autos (Uebersetzung 9,5, Radhalbmesser 0,32 m). Die Zahlen waren nicht
falsch gerechnet — sie beschrieben nur eine andere Maschine als die bestellte.
Und **abwaehlen liess es sich nicht**: ``--set cycle=off`` wurde abgewiesen, weil
der Schluessel im Grundpayload fehlte.

Zwei Dinge folgen daraus, und beide stehen hier:

* Der Zyklus ist eine **Wahl am Anfang**, keine stille Vorgabe. ``EINGEBAUT``
  sagt zu jedem mitgelieferten Zyklus, **fuer welches Fahrzeug** er gedacht ist —
  daran erkennt man, dass keiner passt, bevor vier Stunden gerechnet sind.
* Passt keiner, wird einer **definiert und behalten**. Ein selbst gebauter Zyklus
  ist Arbeit; ihn bei der naechsten Auslegung erneut zu erfinden, waere Arbeit
  zweimal — und zwei Auslegungen, die sich auf denselben Einsatz berufen, waeren
  ueber verschiedene Zyklen gerechnet und damit nicht vergleichbar. Der Speicher
  liegt deshalb in der **gemeinsamen** Rechnungsdatenbank (``ema_db``), nicht im
  Projekt.

Das Fahrzeugmodell gehoert dazu
-------------------------------

Ein Fahrzyklus ist eine Geschwindigkeit ueber der Zeit — welches Moment daraus
wird, entscheidet das **Fahrzeug** (Masse, Radhalbmesser, Uebersetzung, Luft- und
Rollwiderstand). Ein Fahrzyklus ohne sein Fahrzeug ist deshalb kein
vollstaendiger Lastfall, und beide werden hier zusammen abgelegt.

Und wenn es gar kein Fahrzeug gibt
----------------------------------

Der Fahrrad-Fall oben war die Frage „welches Fahrzeug?". Es gibt eine zweite,
die davor liegt und die laenger unbemerkt blieb: **ist es ueberhaupt eines?**

Gemessen am 06.09.2026 an einem Roboterarm-Antrieb. Der Agent hat richtig
erkannt, dass keiner der abgelegten Zyklen passt, und sich pflichtgemaess einen
eigenen gebaut — nur konnte er das ausschliesslich in km/h. Um „2200 1/min" zu
schreiben, musste er ein Fahrzeug **erfinden**: Radhalbmesser 0,12 m,
Uebersetzung 4, Masse 15 kg. Der Lauf meldete daraufhin, das Gelenk lege
**14,2 km bei 345 kWh/100 km** zurueck. Nichts davon ist falsch gerechnet; es
beschreibt nur wieder eine andere Maschine als die bestellte — derselbe Fehler
wie beim Fahrrad, eine Ebene tiefer.

Deshalb gibt es hier **zwei Arten von Lastfall**, und die Wahl zwischen ihnen ist
die erste Frage, nicht eine Feinheit:

``fahrt``
    Geschwindigkeit ueber der Zeit **plus Fahrzeug**. Fuer alles, was auf Raedern
    faehrt. Ergebnis in km und kWh/100 km.
``lastspiel``
    **Drehzahl und Moment der Welle** ueber der Zeit. Kein Fahrzeug, kein Rad,
    kein Weg. Fuer Roboter- und Werkzeugachsen, Spindeln, Pumpen, Luefter,
    Winden, Pruefstaende — alles, was dreht, ohne zu fahren. Ergebnis in
    Verlustenergie, ``T_rms`` gegen das Dauermoment und der Betriebspunktwolke;
    Weg und Verbrauch je 100 km stehen als **None** und nicht als 0.

Beide durchlaufen dieselbe Verlust-, Thermik- und Energierechnung: die haengt
ohnehin nur an ``rpm_motor`` und ``T_motor``. Der einzige Unterschied ist, ob
diese beiden aus einem Fahrzeugmodell gerechnet oder direkt angegeben werden.
"""

from __future__ import annotations

import json
import os
import time

import numpy as np

import ema_db
import ema_drivecycle


# ── Die mitgelieferten Zyklen, mit dem Fahrzeug, fuer das sie gedacht sind ────
#
# Die Kennzahlen sind aus den Modulen gerechnet (``_kennzahlen``), nicht
# abgeschrieben: sie muessen mit dem uebereinstimmen, was der Lauf spaeter faehrt.
EINGEBAUT = {
    "wltp3": {
        "art": "fahrt",
        "beschreibung": "WLTP Class 3b (approximiert) — Pkw-Zyklus, Stadt bis Autobahn",
        "gedacht_fuer": "Personenkraftwagen, 1000-2500 kg, mit Getriebe",
        "achtung": "zieht ZUSAETZLICH die Autobahn-Volllastfahrt nach sich",
        "bauer": ema_drivecycle.wltp_class3,
    },
    "stadtland": {
        "art": "fahrt",
        "beschreibung": "Stadt und Landstrasse",
        "gedacht_fuer": "Personenkraftwagen ohne Autobahnanteil",
        "bauer": ema_drivecycle.stadtland_cycle,
    },
    "vollast": {
        "art": "fahrt",
        "beschreibung": "Autobahn-Volllast bis 220 km/h",
        "gedacht_fuer": "Personenkraftwagen, Dauerleistung an der Spitze",
        "bauer": ema_drivecycle.fullload_cycle,
    },
    "anhaenger": {
        "art": "fahrt",
        "beschreibung": "Anhaenger am Bergpass (Steigung einstellbar)",
        "gedacht_fuer": "Zugfahrzeug mit Anhaenger",
        "bauer": ema_drivecycle.trailer_mountain_cycle,
    },
    "off": {
        "art": "keiner",
        "beschreibung": "kein Lastfall — die Stufe wird uebersprungen",
        "gedacht_fuer": "wenn Auslegungspunkt und Kennfeld genuegen. Fuer eine "
                        "Maschine, die zwar kein Fahrzeug treibt, aber ein "
                        "wiederkehrendes Lastspiel faehrt (Roboterachse, Spindel, "
                        "Pumpe), ist ein eigenes 'lastspiel' die bessere Antwort",
        "bauer": None,
    },
}


def _weg_km(v_kmh, t_s) -> float:
    """Weg aus der Trapezregel — von Hand, nicht ueber die NumPy-Funktion.

    Die heisst je nach Fassung ``trapz`` oder ``trapezoid`` (die eine ist in 2.0
    entfallen, die andere fehlt in aelteren), und die Kommandozeile laeuft mit dem
    System-Python, nicht mit der venv.
    """
    v = np.asarray(v_kmh, dtype=float) / 3.6
    t = np.asarray(t_s, dtype=float)
    return float(np.sum(np.diff(t) * (v[:-1] + v[1:]) / 2.0) / 1000.0)


def _kennzahlen(bauer) -> dict:
    """v_max, Dauer und Weg eines eingebauten Zyklus — gerechnet, nicht notiert."""
    if bauer is None:
        return {}
    z = bauer()
    v = np.asarray(z["v_kmh"], dtype=float)
    t = np.asarray(z["t"], dtype=float)
    return {"v_max_kmh": round(float(v.max()), 1),
            "dauer_s": round(float(t[-1] - t[0]), 1),
            "weg_km": round(_weg_km(v, t), 2)}


# ── Einen eigenen Zyklus bauen ───────────────────────────────────────────────

def aus_phasen(phasen, start_kmh: float = 0.0) -> str:
    """Phasen ``[(ziel_kmh, dauer_s), ...]`` zu einem 1-Hz-CSV (t,v_kmh).

    In jeder Phase laeuft die Geschwindigkeit **linear** von der vorigen auf die
    Zielgeschwindigkeit. Konstantfahrt schreibt man, indem man denselben Wert
    wiederholt: ``[(25, 20), (25, 300)]`` = in 20 s auf 25 km/h, dann 5 min halten.
    Mehr Modell steckt bewusst nicht darin — ``load_csv_cycle`` liest ohnehin nur
    Zeit und Geschwindigkeit, alles Weitere kommt aus dem Fahrzeugmodell.
    """
    if not phasen:
        raise ValueError("Keine Phasen angegeben.")
    t, v = [0.0], [float(start_kmh)]
    for ziel, dauer in phasen:
        dauer = float(dauer)
        if dauer <= 0:
            raise ValueError(f"Phasendauer muss groesser als 0 sein: {dauer}")
        n = max(1, int(round(dauer)))
        v0, v1 = v[-1], float(ziel)
        for k in range(1, n + 1):
            t.append(t[-1] + 1.0)
            v.append(v0 + (v1 - v0) * k / n)
    if len(t) < 5:
        raise ValueError("Zu kurz — load_csv_cycle braucht mindestens 5 Punkte.")
    return "t_s,v_kmh\n" + "\n".join(f"{a:.0f},{b:.3f}" for a, b in zip(t, v))


def aus_lastspiel(phasen, start_rpm: float = 0.0, start_nm: float = 0.0) -> str:
    """Phasen ``[(ziel_rpm, ziel_nm, dauer_s), ...]`` zu einem 1-Hz-CSV (t,rpm,T_Nm).

    Das Gegenstueck zu ``aus_phasen`` fuer alles, was dreht, ohne zu fahren.
    Drehzahl und Moment laufen in jeder Phase **linear** auf ihr Ziel; halten
    schreibt man, indem man dasselbe Paar wiederholt. Ein negatives Moment ist
    Bremsen (generatorisch) und ausdruecklich erlaubt — bei einer Roboterachse
    ist das die halbe Bewegung.

    Warum Drehzahl UND Moment und nicht nur eines: bei einem Fahrzeug rechnet das
    Fahrzeugmodell das Moment aus der Geschwindigkeit. Hier gibt es kein Modell,
    das das koennte — was eine Achse an Last sieht, weiss nur der, der sie baut.
    """
    if not phasen:
        raise ValueError("Keine Phasen angegeben.")
    t, n, m = [0.0], [float(start_rpm)], [float(start_nm)]
    for ziel_rpm, ziel_nm, dauer in phasen:
        dauer = float(dauer)
        if dauer <= 0:
            raise ValueError(f"Phasendauer muss groesser als 0 sein: {dauer}")
        anz = max(1, int(round(dauer)))
        n0, n1 = n[-1], float(ziel_rpm)
        m0, m1 = m[-1], float(ziel_nm)
        for k in range(1, anz + 1):
            t.append(t[-1] + 1.0)
            n.append(n0 + (n1 - n0) * k / anz)
            m.append(m0 + (m1 - m0) * k / anz)
    if len(t) < 5:
        raise ValueError("Zu kurz — load_csv_cycle braucht mindestens 5 Punkte.")
    return ("t_s,rpm,T_Nm\n"
            + "\n".join(f"{a:.0f},{b:.2f},{c:.4f}" for a, b, c in zip(t, n, m)))


def lastspiel_lesen(text: str) -> list:
    """``"1200:6:8,0:0:20"`` → ``[(1200,6,8), (0,0,20)]`` (rpm:Nm:dauer_s)."""
    aus = []
    for stueck in str(text).split(","):
        stueck = stueck.strip()
        if not stueck:
            continue
        teile = stueck.split(":")
        if len(teile) != 3:
            raise ValueError(f"'{stueck}': erwartet wird drehzahl:moment:dauer_s "
                             f"(z. B. '1200:6:8')")
        aus.append(tuple(float(x) for x in teile))
    return aus


def phasen_lesen(text: str) -> list:
    """``"0:5,25:20,25:300"`` → ``[(0,5), (25,20), (25,300)]`` (ziel_kmh:dauer_s)."""
    aus = []
    for stueck in str(text).split(","):
        stueck = stueck.strip()
        if not stueck:
            continue
        if ":" not in stueck:
            raise ValueError(f"'{stueck}': erwartet wird ziel_kmh:dauer_s")
        a, b = stueck.split(":", 1)
        aus.append((float(a), float(b)))
    return aus


def fahrzeug(**felder) -> dict:
    """Ein Fahrzeug auf Grundlage der Vorgaben — nur Bekanntes ist erlaubt."""
    fz = dict(ema_drivecycle.DEFAULT_VEHICLE)
    unbekannt = [k for k in felder if k not in fz]
    if unbekannt:
        raise ValueError(f"Unbekannte Fahrzeuggroesse(n): {', '.join(unbekannt)} — "
                         f"bekannt sind: {', '.join(sorted(fz))}")
    fz.update({k: float(v) for k, v in felder.items()})
    return fz


# ── Speicher in der gemeinsamen Datenbank ────────────────────────────────────

def _tabelle(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS fahrzyklen (
        name         TEXT PRIMARY KEY,
        beschreibung TEXT,
        fahrzeug     TEXT,
        punkte       TEXT,
        quelle       TEXT,
        angelegt     TEXT)""")
    conn.commit()


def art_von(punkte_csv: str) -> str:
    """``fahrt`` oder ``lastspiel`` — aus den Punkten selbst, nicht aus einer Spalte.

    Die Punkte wissen es ohnehin (zwei Spalten = Zeit und Geschwindigkeit, drei =
    Zeit, Drehzahl und Moment). Eine eigene Spalte in der Datenbank waere eine
    zweite Quelle, die von der ersten abweichen kann — und dann waere die Frage
    „welcher glaube ich?" genau die, die dieses Modul abschaffen soll. Ein
    Nebeneffekt, der zaehlt: die schon abgelegten Zyklen brauchen keine Wanderung.
    """
    return ema_drivecycle.load_csv_cycle(punkte_csv).get("art", "fahrt")


def speichern(conn, name: str, punkte_csv: str, beschreibung: str = "",
              fahrzeug_dict: dict | None = None, quelle: str = "agent") -> dict:
    """Lastfall ablegen. Gleicher Name ersetzt den alten.

    Ein **Fahrzyklus** wird samt Fahrzeug abgelegt (beides zusammen, nie einzeln).
    Ein **Lastspiel** hat keines und darf auch keines bekommen: Drehzahl und
    Moment stehen schon in den Punkten, ein Fahrzeug daneben koennte ihnen nur
    widersprechen.
    """
    name = str(name).strip()
    if not name:
        raise ValueError("Ein Zyklus braucht einen Namen.")
    if name in EINGEBAUT:
        raise ValueError(f"'{name}' ist ein eingebauter Zyklus — bitte anders nennen.")
    ema_drivecycle.load_csv_cycle(punkte_csv)      # erst pruefen, dann ablegen
    if art_von(punkte_csv) == "lastspiel":
        if fahrzeug_dict:
            raise ValueError(
                "Ein Lastspiel hat kein Fahrzeug: Drehzahl und Moment stehen schon "
                "in den Punkten. Gib entweder ein Lastspiel (drehzahl:moment:dauer) "
                "ODER einen Fahrzyklus (ziel_kmh:dauer) mit Fahrzeug an.")
        fz = {}
    else:
        fz = fahrzeug(**(fahrzeug_dict or {}))
    _tabelle(conn)
    conn.execute("INSERT OR REPLACE INTO fahrzyklen VALUES (?,?,?,?,?,?)",
                 (name, beschreibung, json.dumps(fz), punkte_csv, quelle,
                  time.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    return holen(conn, name)


def liste(conn) -> list:
    """Alles Waehlbare: die eingebauten Zyklen und die selbst abgelegten."""
    aus = []
    for name, e in EINGEBAUT.items():
        aus.append({"name": name, "herkunft": "eingebaut", "art": e.get("art", "fahrt"),
                    "beschreibung": e["beschreibung"],
                    "gedacht_fuer": e["gedacht_fuer"],
                    "achtung": e.get("achtung", ""),
                    **_kennzahlen(e["bauer"])})
    _tabelle(conn)
    for r in conn.execute("SELECT * FROM fahrzyklen ORDER BY name"):
        z = ema_drivecycle.load_csv_cycle(r["punkte"])
        t = np.asarray(z["t"], dtype=float)
        fz = json.loads(r["fahrzeug"]) or {}
        satz = {"name": r["name"], "herkunft": "eigen", "art": z.get("art", "fahrt"),
                "beschreibung": r["beschreibung"],
                "dauer_s": round(float(t[-1] - t[0]), 1),
                "angelegt": r["angelegt"]}
        if z.get("art") == "lastspiel":
            n = np.asarray(z["rpm"], dtype=float)
            m = np.asarray(z["T_Nm"], dtype=float)
            # Was ein Lastspiel kennzeichnet, ist NICHT v_max und Weg -- es ist,
            # wie hart die Welle im Mittel arbeitet. T_rms gegen das Dauermoment
            # ist die Frage, die der Lauf spaeter beantwortet; hier steht schon
            # einmal, worauf man dabei blickt.
            satz.update({"n_max_rpm": round(float(np.abs(n).max()), 0),
                         "T_max_Nm": round(float(np.abs(m).max()), 2),
                         "T_rms_Nm": round(float(np.sqrt(np.mean(m ** 2))), 2),
                         "gedacht_fuer": (f"Welle direkt: bis {np.abs(n).max():.0f} 1/min, "
                                          f"{np.abs(m).max():.2f} Nm Spitze, "
                                          f"{np.sqrt(np.mean(m ** 2)):.2f} Nm effektiv")})
        else:
            v = np.asarray(z["v_kmh"], dtype=float)
            satz.update({"v_max_kmh": round(float(v.max()), 1),
                         "weg_km": round(_weg_km(v, t), 2),
                         "gedacht_fuer": f"{fz.get('mass_kg', 0):.0f} kg, "
                                         f"Rad {fz.get('r_wheel_m', 0):.3f} m, "
                                         f"Uebersetzung {fz.get('gear_ratio', 0):.2f}"})
        aus.append(satz)
    return aus


def holen(conn, name: str) -> dict | None:
    """Einen abgelegten Zyklus samt Fahrzeug und Punkten."""
    _tabelle(conn)
    r = conn.execute("SELECT * FROM fahrzyklen WHERE name=?", (name,)).fetchone()
    if not r:
        return None
    return {"name": r["name"], "beschreibung": r["beschreibung"],
            "art": art_von(r["punkte"]),
            "fahrzeug": json.loads(r["fahrzeug"]) or {}, "punkte": r["punkte"],
            "quelle": r["quelle"], "angelegt": r["angelegt"]}


def loeschen(conn, name: str) -> bool:
    _tabelle(conn)
    c = conn.execute("DELETE FROM fahrzyklen WHERE name=?", (name,))
    conn.commit()
    return c.rowcount > 0


# ── In einen Payload einsetzen ───────────────────────────────────────────────

def anwenden(payload: dict, name: str, conn=None) -> dict:
    """Den Lastfall in den Payload schreiben — Zyklus UND Fahrzeug, oder Lastspiel.

    Bei einem Fahrzyklus beides zusammen, nie einzeln: ein eigener Zyklus mit dem
    Fahrzeugmodell eines 1600-kg-Autos ergibt wieder die Momente eines Autos.
    Bei einem Lastspiel wird das Fahrzeug **entfernt** statt stehen gelassen —
    ein geerbtes Fahrzeug neben einer Wellenvorgabe waere genau die zweite
    Quelle, die es nicht geben soll.
    """
    if name in EINGEBAUT:
        payload["cycle"] = name
        payload.pop("cycle_csv", None)
        return payload
    if conn is None:
        conn = ema_db.oeffne()
    z = holen(conn, name)
    if not z:
        bekannt = ", ".join(x["name"] for x in liste(conn))
        raise ValueError(f"Zyklus '{name}' nicht gefunden. Bekannt: {bekannt}")
    payload["cycle_csv"] = z["punkte"]
    if z["art"] == "lastspiel":
        payload["cycle"] = "lastspiel"
        payload.pop("vehicle", None)
    else:
        payload["cycle"] = "csv"
        payload["vehicle"] = dict(z["fahrzeug"])
    return payload
