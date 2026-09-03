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

Ein Zyklus ist eine Geschwindigkeit ueber der Zeit — welches Moment daraus wird,
entscheidet das **Fahrzeug** (Masse, Radhalbmesser, Uebersetzung, Luft- und
Rollwiderstand). Ein Zyklus ohne sein Fahrzeug ist deshalb kein vollstaendiger
Lastfall, und beide werden hier zusammen abgelegt.
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
        "beschreibung": "WLTP Class 3b (approximiert) — Pkw-Zyklus, Stadt bis Autobahn",
        "gedacht_fuer": "Personenkraftwagen, 1000-2500 kg, mit Getriebe",
        "achtung": "zieht ZUSAETZLICH die Autobahn-Volllastfahrt nach sich",
        "bauer": ema_drivecycle.wltp_class3,
    },
    "stadtland": {
        "beschreibung": "Stadt und Landstrasse",
        "gedacht_fuer": "Personenkraftwagen ohne Autobahnanteil",
        "bauer": ema_drivecycle.stadtland_cycle,
    },
    "vollast": {
        "beschreibung": "Autobahn-Volllast bis 220 km/h",
        "gedacht_fuer": "Personenkraftwagen, Dauerleistung an der Spitze",
        "bauer": ema_drivecycle.fullload_cycle,
    },
    "anhaenger": {
        "beschreibung": "Anhaenger am Bergpass (Steigung einstellbar)",
        "gedacht_fuer": "Zugfahrzeug mit Anhaenger",
        "bauer": ema_drivecycle.trailer_mountain_cycle,
    },
    "off": {
        "beschreibung": "kein Fahrzyklus — die Stufe wird uebersprungen",
        "gedacht_fuer": "Maschinen ohne Fahrprofil (Spindel, Pumpe, Pruefstand)",
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


def speichern(conn, name: str, punkte_csv: str, beschreibung: str = "",
              fahrzeug_dict: dict | None = None, quelle: str = "agent") -> dict:
    """Zyklus samt Fahrzeug ablegen. Gleicher Name ersetzt den alten."""
    name = str(name).strip()
    if not name:
        raise ValueError("Ein Zyklus braucht einen Namen.")
    if name in EINGEBAUT:
        raise ValueError(f"'{name}' ist ein eingebauter Zyklus — bitte anders nennen.")
    ema_drivecycle.load_csv_cycle(punkte_csv)      # erst pruefen, dann ablegen
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
        aus.append({"name": name, "herkunft": "eingebaut",
                    "beschreibung": e["beschreibung"],
                    "gedacht_fuer": e["gedacht_fuer"],
                    "achtung": e.get("achtung", ""),
                    **_kennzahlen(e["bauer"])})
    _tabelle(conn)
    for r in conn.execute("SELECT * FROM fahrzyklen ORDER BY name"):
        z = ema_drivecycle.load_csv_cycle(r["punkte"])
        v = np.asarray(z["v_kmh"], dtype=float)
        t = np.asarray(z["t"], dtype=float)
        fz = json.loads(r["fahrzeug"])
        aus.append({"name": r["name"], "herkunft": "eigen",
                    "beschreibung": r["beschreibung"],
                    "gedacht_fuer": f"{fz['mass_kg']:.0f} kg, Rad {fz['r_wheel_m']:.3f} m, "
                                    f"Uebersetzung {fz['gear_ratio']:.2f}",
                    "v_max_kmh": round(float(v.max()), 1),
                    "dauer_s": round(float(t[-1] - t[0]), 1),
                    "weg_km": round(_weg_km(v, t), 2),
                    "angelegt": r["angelegt"]})
    return aus


def holen(conn, name: str) -> dict | None:
    """Einen abgelegten Zyklus samt Fahrzeug und Punkten."""
    _tabelle(conn)
    r = conn.execute("SELECT * FROM fahrzyklen WHERE name=?", (name,)).fetchone()
    if not r:
        return None
    return {"name": r["name"], "beschreibung": r["beschreibung"],
            "fahrzeug": json.loads(r["fahrzeug"]), "punkte": r["punkte"],
            "quelle": r["quelle"], "angelegt": r["angelegt"]}


def loeschen(conn, name: str) -> bool:
    _tabelle(conn)
    c = conn.execute("DELETE FROM fahrzyklen WHERE name=?", (name,))
    conn.commit()
    return c.rowcount > 0


# ── In einen Payload einsetzen ───────────────────────────────────────────────

def anwenden(payload: dict, name: str, conn=None) -> dict:
    """Zyklus UND Fahrzeug in den Payload schreiben.

    Beides zusammen, nie einzeln: ein eigener Zyklus mit dem Fahrzeugmodell eines
    1600-kg-Autos ergibt wieder die Momente eines Autos.
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
    payload["cycle"] = "csv"
    payload["cycle_csv"] = z["punkte"]
    payload["vehicle"] = dict(z["fahrzeug"])
    return payload
