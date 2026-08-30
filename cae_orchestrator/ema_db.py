"""Rechnungsdatenbank: Eingaben, Ergebnisse, Bilder — und die **Herkunft jeder Zahl**.

Warum es sie gibt
-----------------

Heute liegt alles im Dateisystem: 35 Projekte, 20 GB, je Lauf eine ``results.json``
von rund 1,7 MB. Davon sind aber **884 kB Verformungsbilder und Diagramme als
Base64** — der eigentliche Kennwertsatz (``summary``) ist **0,9 kB mit 34 Einträgen**.
Wer zwei Auslegungen vergleichen will, muss heute beide JSON-Dateien laden und von
Hand zusammensuchen; wer wissen will, „in welchem Lauf war ``B_gap`` über 0,8 T und
die Festigkeit grün", kann es gar nicht fragen.

Diese Datenbank hält genau das Fragbare: **Eingabeparameter, Kennwerte, Tore, Bilder
und die Güte**. Sie **ersetzt ``results.json`` nicht** — die bleibt der vollständige,
maßgebliche Lauf-Datensatz. Die Datenbank ist der durchsuchbare Index darüber und
lässt sich jederzeit daraus neu aufbauen (``importiere_alle``). Geht sie verloren, ist
nichts verloren.

Die Güte: Herkunft je Größe, nicht eine Note
--------------------------------------------

Der springende Punkt. Dieses Werkzeug rechnet **eine Maschine mit sehr verschiedenen
Verfahren gleichzeitig** — und die Wurzel-``AGENTS.md`` schreibt vor, dass jede Zahl
sagen können muss, woher sie kommt. Ein einzelner Gütewert je Lauf würde genau das
verwischen: ein Lauf kann beim Feld fein und bei der Festigkeit grob sein.

Darum trägt **jeder Kennwert seine eigene Herkunft** (``METHODE``), dazu Auflösung,
Löser und Löserstatus. Nachgeprüft im Quelltext, nicht angenommen — zwei Beispiele,
an denen der Unterschied hängt:

* ``B_gap_T`` und ``Kt_Nm_per_A`` kommen aus der **analytischen** Luftspaltformel
  (``ema_analysis.compute_performance``), **nicht** aus dem Feldbild. Das Feldbild ist
  Anschauung.
* ``T_maxwell_Nm`` kommt dagegen wirklich **aus dem gelösten FDM-Feld**
  (Maxwell-Spannungstensor über ``mean(Br·Bt)``, ``ema_analysis.py:1344``).

Beide stehen im selben ``summary`` nebeneinander und sähen ohne Register gleichwertig
aus. Sie sind es nicht.

Schema
------

``laeufe`` ein Lauf je Projekt · ``parameter`` die Eingaben · ``kennwerte`` die
Ergebnisse **mit** Herkunft · ``bilder`` Verweise auf eine kuratierte Auswahl (die
Dateien bleiben, wo sie sind — nichts wird verdoppelt) · ``tore`` die Torergebnisse.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time

DB_ORDNER = os.path.expanduser("~/cae_projekte/_db")
DB_PFAD   = os.path.join(DB_ORDNER, "rechnungen.db")

SCHEMA_VERSION = 1

# ── Das Vokabular der Herkunft ────────────────────────────────────────────────
# Bewusst klein und geschlossen. Wer eine Methode hinzufügt, trägt sie hier ein —
# sonst wandern Freitexte in die Datenbank und der Vergleich zerfällt.
METHODEN = {
    "analytisch":   "geschlossene Formel (kalibriert), kein Feld- oder Netzlauf",
    "fdm2d":        "aus dem geloesten 2D-FDM-Feld",
    "fem3d":        "3D-FEM (CalculiX bzw. Z88Aurora)",
    "lptn":         "6-Knoten-Waermenetzwerk, stationaer/transient",
    "zyklus":       "Fahrzyklus-Integration ueber Betriebspunkte",
    "geometrisch":  "reine Geometrie, kein Loeser",
    "tabelle":      "Werkstofftabelle bzw. Vorgabewert",
    "abgeleitet":   "aus anderen Kennwerten gerechnet",
    "unbekannt":    "nicht zugeordnet — Register ergaenzen",
}

# ── Herkunftsregister ─────────────────────────────────────────────────────────
# Je Kennwert: Einheit, Methode, Kurzbegruendung und (wo zutreffend) die Fundstelle.
# Im Quelltext nachgeprueft, nicht geraten.
HERKUNFT: dict[str, dict] = {
    # Elektromagnetik
    "B_gap_T":          dict(einheit="T",     methode="analytisch",
                             detail="Luftspaltformel, auf das FDM-Feld kalibriert — NICHT aus dem Feldbild",
                             quelle="ema_analysis.compute_performance"),
    "Kt_Nm_per_A":      dict(einheit="Nm/A",  methode="analytisch",
                             detail="dq-Modell auf derselben Luftspaltformel",
                             quelle="ema_analysis.compute_performance"),
    "T_maxwell_Nm":     dict(einheit="Nm",    methode="fdm2d",
                             detail="Maxwell-Spannungstensor ueber mean(Br*Bt) des geloesten Feldes",
                             quelle="ema_analysis.py:1344"),
    "lcm_slots_poles":  dict(einheit="",      methode="geometrisch",
                             detail="kgV aus Nutzahl und Polzahl (Rastmoment-Ordnung)"),

    # Leistung
    "P_max_kW":         dict(einheit="kW",    methode="analytisch", detail="dq-Modell ueber der Drehzahl"),
    "P_max_rpm":        dict(einheit="1/min", methode="analytisch", detail="Drehzahl der Spitzenleistung"),
    "P_cont_max_kW":    dict(einheit="kW",    methode="analytisch", detail="Dauerleistung, thermisch begrenzt"),
    "T_peak_max_Nm":    dict(einheit="Nm",    methode="analytisch", detail="Spitzenmoment aus dem dq-Modell"),

    # Festigkeit
    "max_safe_rpm":     dict(einheit="1/min", methode="analytisch",
                             detail="analytischer Festigkeits-Sweep; von der FEM gedeckelt, WENN sie lief",
                             quelle="ema_pipeline.py:2323/2345", bedingt="fem3d"),
    "structural_ok":    dict(einheit="",      methode="abgeleitet", detail="Toraussage der Festigkeitsstufe"),
    "safety_factor_fem":dict(einheit="",      methode="fem3d",
                             detail="Fliessgrenze / max(FEM-P99, Ringformel*Kt) — der bindende Torwert"),
    "fem_rpm":          dict(einheit="1/min", methode="fem3d",   detail="Drehzahl, bei der die FEM gerechnet hat"),
    "fem_sigma_vm_MPa": dict(einheit="MPa",   methode="fem3d",   detail="Rohmaximum der Vergleichsspannung"),

    # Werkstoffe und Geometrie
    "rotor_lam":        dict(einheit="",      methode="tabelle",     detail="Blechsorte Rotor"),
    "stator_lam":       dict(einheit="",      methode="tabelle",     detail="Blechsorte Stator"),
    "hairpin":          dict(einheit="",      methode="tabelle",     detail="Leiterwerkstoff"),
    "magnet":           dict(einheit="",      methode="tabelle",     detail="Magnetwerkstoff"),
    "mass_g":           dict(einheit="g",     methode="geometrisch", detail="Rotor + Magnete aus Volumen und Dichte"),
    "fill_factor":      dict(einheit="",      methode="geometrisch",
                             detail="Leiterquerschnitt / Nutquerschnitt, 2 Lagen, 0,8 mm Isolation",
                             quelle="ema_pipeline.py:2570"),
    "P_fe_W_est":       dict(einheit="W",     methode="analytisch",
                             detail="Bertotti vereinfacht, Leerlauf — SCHAETZUNG, kein Verlustmodell",
                             quelle="ema_pipeline.py:2592"),

    # Thermik
    "T_winding_C":      dict(einheit="degC",  methode="lptn", detail="Knoten Wicklung, stationaer"),
    "T_magnet_C":       dict(einheit="degC",  methode="lptn", detail="Knoten Magnet, stationaer"),
    "T_housing_C":      dict(einheit="degC",  methode="lptn", detail="Knoten Gehaeuse, stationaer"),
    "P_total_W":        dict(einheit="W",     methode="abgeleitet", detail="Summe der Verlustanteile"),
    "cooling":          dict(einheit="",      methode="tabelle",    detail="gewaehltes Kuehlungs-Preset"),
    "htc_source":       dict(einheit="",      methode="tabelle",
                             detail="'preset' = Tabellenwert, 'cfd' = aus der Stroemungsrechnung uebernommen"),
    "htc_oil_Wm2K":     dict(einheit="W/m2K", methode="tabelle",    detail="Waermeuebergang Oel"),

    # Fahrzyklus
    "cycle_kWh100km":   dict(einheit="kWh/100km", methode="zyklus", detail="Integration ueber den Zyklus"),
    "cycle_eta":        dict(einheit="",          methode="zyklus", detail="Wirkungsgrad ueber den Zyklus"),
    "cycle_name":       dict(einheit="",          methode="tabelle", detail="Name des gefahrenen Zyklus"),
    "vollast_kWh100km": dict(einheit="kWh/100km", methode="zyklus", detail="Volllastfahrt"),
    "vollast_eta":      dict(einheit="",          methode="zyklus", detail="Wirkungsgrad Volllastfahrt"),
    "anhaenger_kWh100km": dict(einheit="kWh/100km", methode="zyklus", detail="Anhaengerzyklus"),
    "anhaenger_T_max_Nm": dict(einheit="Nm",       methode="zyklus", detail="groesstes Moment im Anhaengerzyklus"),
}

# ── Die kuratierte Bildauswahl ────────────────────────────────────────────────
# Verweise, keine Kopien: die Dateien liegen schon unter charts/ bzw. cad_images/.
BILDAUSWAHL = [
    ("charts/em_field.png",          "feld_leerlauf",  "2D-Feldbild, Leerlauf"),
    ("charts/em_field_load.png",     "feld_last",      "2D-Feldbild, unter Last"),
    ("charts/airgap.png",            "luftspalt",      "Luftspaltinduktion ueber dem Umfang"),
    ("charts/em_curve.png",          "em_kennlinie",   "EM-Kennlinien ueber der Drehzahl"),
    ("charts/power.png",             "leistung",       "Leistung und Moment ueber der Drehzahl"),
    ("charts/structural_sweep.png",  "festigkeit",     "Spannung ueber der Drehzahl"),
    ("charts/deformation.png",       "verformung",     "Verformung bei Maximaldrehzahl"),
    ("charts/deformation_burst.png", "verformung_berst", "Verformung an der Berstdrehzahl"),
    ("charts/thermal.png",           "thermik",        "Temperaturen im Waermenetzwerk"),
    ("charts/drivecycle.png",        "fahrzyklus",     "Fahrzyklus"),
    ("charts/connection.png",        "wellenverbindung", "Wellenverbindung"),
    ("cad_images/motor_cross_section.png", "cad_schnitt", "CAD-Querschnitt"),
    ("cad_images/motor_side_view.png",     "cad_seite",   "CAD-Seitenansicht"),
]


# ── Datenbank ─────────────────────────────────────────────────────────────────

def oeffne(pfad: str = DB_PFAD) -> sqlite3.Connection:
    """Verbindung oeffnen, Schema anlegen falls noetig."""
    os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
    conn = sqlite3.connect(pfad)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS meta (
        schluessel TEXT PRIMARY KEY, wert TEXT);
    CREATE TABLE IF NOT EXISTS laeufe (
        lauf_id      INTEGER PRIMARY KEY,
        projekt_id   TEXT UNIQUE NOT NULL,   -- Ordnername unter ~/cae_projekte
        projekt_name TEXT,
        zeitpunkt    TEXT,                   -- ISO, aus meta.json
        pfad         TEXT,
        importiert   TEXT,
        stufen       TEXT,                   -- welche Stufen Ergebnisse haben
        notiz        TEXT);
    CREATE TABLE IF NOT EXISTS parameter (
        lauf_id   INTEGER NOT NULL REFERENCES laeufe(lauf_id) ON DELETE CASCADE,
        schluessel TEXT NOT NULL,
        wert_num  REAL,
        wert_text TEXT,
        ebene     TEXT,                      -- 'geom' | 'lauf'
        PRIMARY KEY (lauf_id, schluessel, ebene));
    CREATE TABLE IF NOT EXISTS kennwerte (
        lauf_id       INTEGER NOT NULL REFERENCES laeufe(lauf_id) ON DELETE CASCADE,
        groesse       TEXT NOT NULL,
        wert_num      REAL,
        wert_text     TEXT,
        einheit       TEXT,
        methode       TEXT,                  -- aus METHODEN
        detail        TEXT,
        quelle        TEXT,                  -- Fundstelle im Quelltext
        loeser        TEXT,
        loeser_status TEXT,
        aufloesung    TEXT,                  -- Netzweite / FDM-N, wo zutreffend
        PRIMARY KEY (lauf_id, groesse));
    CREATE TABLE IF NOT EXISTS bilder (
        lauf_id   INTEGER NOT NULL REFERENCES laeufe(lauf_id) ON DELETE CASCADE,
        art       TEXT NOT NULL,
        pfad      TEXT,
        titel     TEXT,
        vorhanden INTEGER,
        PRIMARY KEY (lauf_id, art));
    CREATE TABLE IF NOT EXISTS tore (
        lauf_id  INTEGER NOT NULL REFERENCES laeufe(lauf_id) ON DELETE CASCADE,
        tor      TEXT NOT NULL,
        ok       INTEGER,
        meldung  TEXT,
        PRIMARY KEY (lauf_id, tor));
    CREATE INDEX IF NOT EXISTS idx_kennwerte_groesse ON kennwerte(groesse);
    CREATE INDEX IF NOT EXISTS idx_kennwerte_methode ON kennwerte(methode);
    """)
    conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)",
                 (str(SCHEMA_VERSION),))
    conn.commit()
    return conn


def _zahl(v):
    """(wert_num, wert_text) — Bool zaehlt als Zahl, damit man danach filtern kann."""
    if isinstance(v, bool):
        return (1.0 if v else 0.0), ("ja" if v else "nein")
    if isinstance(v, (int, float)):
        return float(v), None
    if v is None:
        return None, None
    return None, str(v)


def _stufen(results: dict) -> str:
    """Welche Stufen haben ueberhaupt Ergebnisse? Grundlage jeder Guete-Aussage."""
    da = []
    for name, schl in (("geometrie", "geometry"), ("feld", "em"), ("leistung", "power"),
                       ("festigkeit", "structural_fem"), ("verformung", "deformation"),
                       ("thermik", "thermal"), ("fahrzyklus", "drivecycle"),
                       ("welle", "connection"), ("feld3d", "em3d"),
                       ("oelkuehlung", "oilspray")):
        v = results.get(schl)
        if v:
            da.append(name)
    return ",".join(da)


def importiere_projekt(conn: sqlite3.Connection, projektpfad: str,
                       ersetzen: bool = True) -> int | None:
    """Ein Projekt einlesen; gibt ``lauf_id`` zurueck (oder ``None``, wenn unbrauchbar).

    Idempotent: ein erneuter Import desselben Projekts ersetzt seine Zeilen, statt sie
    zu verdoppeln. Damit laesst sich die Datenbank jederzeit aus dem Dateisystem neu
    aufbauen — sie ist ein Index, kein zweiter Datenbestand.
    """
    projekt_id = os.path.basename(projektpfad.rstrip("/"))
    p_res  = os.path.join(projektpfad, "results.json")
    p_meta = os.path.join(projektpfad, "meta.json")
    if not os.path.isfile(p_res):
        # KEIN stilles Ueberspringen. Ein Ordner mit CAD-Bildern und Diagrammen, aber
        # ohne results.json, ist ein ABGEBROCHENER Lauf — gemessen betrifft das 21 von
        # 35 Ordnern. Wer die Datenbank nach der Ausbeute fragt, soll das sehen, statt
        # sie fuer vollstaendig zu halten.
        return _vermerke_unvollstaendig(conn, projektpfad, projekt_id, ersetzen)
    try:
        with open(p_res, encoding="utf-8") as f:
            results = json.load(f)
        meta = {}
        if os.path.isfile(p_meta):
            with open(p_meta, encoding="utf-8") as f:
                meta = json.load(f)
    except (OSError, ValueError):
        return None

    vorhanden = conn.execute("SELECT lauf_id FROM laeufe WHERE projekt_id=?",
                             (projekt_id,)).fetchone()
    if vorhanden and not ersetzen:
        return vorhanden["lauf_id"]
    if vorhanden:
        for t in ("parameter", "kennwerte", "bilder", "tore"):
            conn.execute(f"DELETE FROM {t} WHERE lauf_id=?", (vorhanden["lauf_id"],))
        conn.execute("DELETE FROM laeufe WHERE lauf_id=?", (vorhanden["lauf_id"],))

    cur = conn.execute(
        "INSERT INTO laeufe (projekt_id, projekt_name, zeitpunkt, pfad, importiert, stufen)"
        " VALUES (?,?,?,?,?,?)",
        (projekt_id, meta.get("label") or projekt_id, meta.get("created"),
         projektpfad, time.strftime("%Y-%m-%dT%H:%M:%S"), _stufen(results)))
    lauf_id = cur.lastrowid

    # Parameter: Geometrie und die Laufgroessen daneben
    for k, v in (meta.get("geom") or {}).items():
        n, t = _zahl(v)
        conn.execute("INSERT OR REPLACE INTO parameter VALUES (?,?,?,?,?)",
                     (lauf_id, k, n, t, "geom"))
    for k in ("axial_len", "load_nm", "cooling", "T_ambient", "rpm_thermal",
              "rpm_range", "rpm_step", "n_frames", "design_source"):
        if k in meta:
            n, t = _zahl(meta[k])
            conn.execute("INSERT OR REPLACE INTO parameter VALUES (?,?,?,?,?)",
                         (lauf_id, k, n, t, "lauf"))

    # Kennwerte mit Herkunft
    fem = results.get("structural_fem") or {}
    loeser = fem.get("solver_verwendet") or ("CalculiX" if fem else None)
    loeser_status = fem.get("solver_status")
    netz = fem.get("struct_mesh_mm")
    for k, v in (results.get("summary") or {}).items():
        h = HERKUNFT.get(k, {})
        n, t = _zahl(v)
        ist_fem = h.get("methode") == "fem3d"
        conn.execute("INSERT OR REPLACE INTO kennwerte VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (lauf_id, k, n, t, h.get("einheit"),
                      h.get("methode", "unbekannt"), h.get("detail"), h.get("quelle"),
                      loeser if ist_fem else None,
                      loeser_status if ist_fem else None,
                      (f"Netz {netz} mm" if (ist_fem and netz) else None)))

    # Bilder: Verweise auf die kuratierte Auswahl
    for rel, art, titel in BILDAUSWAHL:
        voll = os.path.join(projektpfad, rel)
        conn.execute("INSERT OR REPLACE INTO bilder VALUES (?,?,?,?,?)",
                     (lauf_id, art, voll, titel, 1 if os.path.isfile(voll) else 0))

    # Tore
    conn.execute("INSERT OR REPLACE INTO tore VALUES (?,?,?,?)",
                 (lauf_id, "festigkeit", 1 if results.get("structural_ok") else 0,
                  fem.get("solver_status")))
    conn.commit()
    return lauf_id


def _vermerke_unvollstaendig(conn, projektpfad, projekt_id, ersetzen) -> int | None:
    """Abgebrochenen Lauf eintragen — ohne Kennwerte, aber sichtbar."""
    vorhanden = conn.execute("SELECT lauf_id FROM laeufe WHERE projekt_id=?",
                             (projekt_id,)).fetchone()
    if vorhanden and not ersetzen:
        return vorhanden["lauf_id"]
    if vorhanden:
        for t in ("parameter", "kennwerte", "bilder", "tore"):
            conn.execute(f"DELETE FROM {t} WHERE lauf_id=?", (vorhanden["lauf_id"],))
        conn.execute("DELETE FROM laeufe WHERE lauf_id=?", (vorhanden["lauf_id"],))

    meta = {}
    p_meta = os.path.join(projektpfad, "meta.json")
    if os.path.isfile(p_meta):
        try:
            with open(p_meta, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            pass
    # Woran man sieht, wie weit er kam: welche Ordner er hinterlassen hat.
    reste = [d for d in ("cad_images", "charts", "frames", "ccx_rotor", "em3d_runs")
             if os.path.isdir(os.path.join(projektpfad, d))]
    cur = conn.execute(
        "INSERT INTO laeufe (projekt_id, projekt_name, zeitpunkt, pfad, importiert,"
        " stufen, notiz) VALUES (?,?,?,?,?,?,?)",
        (projekt_id, meta.get("label") or projekt_id, meta.get("created"), projektpfad,
         time.strftime("%Y-%m-%dT%H:%M:%S"), "",
         "abgebrochen: keine results.json" + (f"; vorhanden: {', '.join(reste)}" if reste else "")))
    lauf_id = cur.lastrowid
    for rel, art, titel in BILDAUSWAHL:
        voll = os.path.join(projektpfad, rel)
        if os.path.isfile(voll):
            conn.execute("INSERT OR REPLACE INTO bilder VALUES (?,?,?,?,?)",
                         (lauf_id, art, voll, titel, 1))
    conn.commit()
    return lauf_id


# ── Abfragen ──────────────────────────────────────────────────────────────────

def liste(conn: sqlite3.Connection, nur_vollstaendig: bool = False) -> list:
    """Alle Laeufe mit Kurzbefund."""
    wo = "WHERE l.stufen <> ''" if nur_vollstaendig else ""
    return list(conn.execute(f"""
        SELECT l.lauf_id, l.projekt_id, l.projekt_name, l.zeitpunkt, l.stufen, l.notiz,
               (SELECT COUNT(*) FROM kennwerte k WHERE k.lauf_id=l.lauf_id) AS n_kennwerte,
               (SELECT wert_num FROM kennwerte k WHERE k.lauf_id=l.lauf_id
                                             AND k.groesse='B_gap_T')        AS b_gap,
               (SELECT wert_num FROM kennwerte k WHERE k.lauf_id=l.lauf_id
                                             AND k.groesse='P_max_kW')       AS p_max,
               (SELECT wert_num FROM kennwerte k WHERE k.lauf_id=l.lauf_id
                                             AND k.groesse='structural_ok')  AS fest_ok
        FROM laeufe l {wo} ORDER BY l.zeitpunkt DESC, l.lauf_id DESC"""))


def zeige(conn: sqlite3.Connection, lauf: str | int) -> dict:
    """Ein Lauf vollstaendig: Kopf, Parameter, Kennwerte MIT Herkunft, Bilder, Tore."""
    r = conn.execute("SELECT * FROM laeufe WHERE lauf_id=? OR projekt_id=?",
                     (lauf, str(lauf))).fetchone()
    if not r:
        return {}
    lid = r["lauf_id"]
    q = lambda sql: [dict(x) for x in conn.execute(sql, (lid,))]
    return {
        "lauf":      dict(r),
        "parameter": q("SELECT schluessel, wert_num, wert_text, ebene FROM parameter"
                       " WHERE lauf_id=? ORDER BY ebene, schluessel"),
        "kennwerte": q("SELECT groesse, wert_num, wert_text, einheit, methode, detail,"
                       " quelle, loeser, loeser_status, aufloesung FROM kennwerte"
                       " WHERE lauf_id=? ORDER BY methode, groesse"),
        "bilder":    q("SELECT art, titel, pfad, vorhanden FROM bilder WHERE lauf_id=?"),
        "tore":      q("SELECT tor, ok, meldung FROM tore WHERE lauf_id=?"),
    }


def guete(conn: sqlite3.Connection, lauf: str | int) -> dict:
    """Die Guete eines Laufs — als Aufstellung nach Methode, NICHT als eine Note.

    Eine einzelne Note wuerde verwischen, dass ein Lauf beim Feld fein und bei der
    Festigkeit grob sein kann. Zurueck kommt darum, wie viele Kennwerte aus welchem
    Verfahren stammen, welche Stufen ueberhaupt liefen und was die Tore sagen.
    """
    d = zeige(conn, lauf)
    if not d:
        return {}
    nach_methode = {}
    for k in d["kennwerte"]:
        nach_methode.setdefault(k["methode"], []).append(k["groesse"])
    fem = [k for k in d["kennwerte"] if k["methode"] == "fem3d"]
    return {
        "projekt":        d["lauf"]["projekt_id"],
        "stufen":         d["lauf"]["stufen"].split(",") if d["lauf"]["stufen"] else [],
        "unvollstaendig": not d["lauf"]["stufen"],
        "notiz":          d["lauf"]["notiz"],
        "kennwerte_je_methode": {m: len(v) for m, v in sorted(nach_methode.items())},
        "fem_geliefert":  sum(1 for k in fem if k["wert_num"] is not None),
        "fem_erwartet":   len(fem),
        "fem_loeser":     next((k["loeser"] for k in fem if k["loeser"]), None),
        "fem_aufloesung": next((k["aufloesung"] for k in fem if k["aufloesung"]), None),
        "bilder_vorhanden": sum(1 for b in d["bilder"] if b["vorhanden"]),
        "tore":           {t["tor"]: bool(t["ok"]) for t in d["tore"]},
    }


def vergleiche(conn: sqlite3.Connection, groessen: list, laeufe: list | None = None) -> list:
    """Eine Zeile je Lauf, eine Spalte je Kennwert — der Vergleich, der bisher fehlte."""
    wo, args = "", []
    if laeufe:
        wo = " AND l.projekt_id IN (%s)" % ",".join("?" * len(laeufe))
        args = [str(x) for x in laeufe]
    zeilen = []
    for l in conn.execute(f"SELECT lauf_id, projekt_id, projekt_name FROM laeufe l"
                          f" WHERE l.stufen <> ''{wo} ORDER BY l.zeitpunkt", args):
        z = {"projekt": l["projekt_id"], "name": l["projekt_name"]}
        for g in groessen:
            k = conn.execute("SELECT wert_num, wert_text, einheit, methode FROM kennwerte"
                             " WHERE lauf_id=? AND groesse=?", (l["lauf_id"], g)).fetchone()
            z[g] = (k["wert_num"] if k and k["wert_num"] is not None
                    else (k["wert_text"] if k else None))
            z[g + "__methode"] = k["methode"] if k else None
        zeilen.append(z)
    return zeilen


def importiere_alle(conn: sqlite3.Connection, wurzel: str | None = None) -> dict:
    """Alle Projekte unter ``wurzel`` einlesen. Gibt eine kleine Bilanz zurueck."""
    wurzel = wurzel or os.path.expanduser("~/cae_projekte")
    voll = teil = fehler = 0
    for name in sorted(os.listdir(wurzel)):
        if name.startswith("_"):
            continue
        pfad = os.path.join(wurzel, name)
        if not os.path.isdir(pfad):
            continue
        lid = importiere_projekt(conn, pfad)
        if lid is None:
            fehler += 1
        elif os.path.isfile(os.path.join(pfad, "results.json")):
            voll += 1
        else:
            teil += 1
    return {"vollstaendig": voll, "abgebrochen": teil, "unlesbar": fehler}
