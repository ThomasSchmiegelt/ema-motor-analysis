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
    "structural_basis": dict(einheit="",      methode="abgeleitet",
                             detail="worauf die Festigkeitsaussage beruht: 'fem' = gerechnet, "
                                    "'analytisch' = die FEM lieferte nichts, es gilt die Ringformel"),
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
    "T_winding_C":      dict(einheit="°C",  methode="lptn", detail="Knoten Wicklung, stationaer"),
    "T_magnet_C":       dict(einheit="°C",  methode="lptn", detail="Knoten Magnet, stationaer"),
    "T_housing_C":      dict(einheit="°C",  methode="lptn", detail="Knoten Gehaeuse, stationaer"),
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
    -- Recherchierte REFERENZWERTE. Bewusst eine EIGENE Tabelle und nicht ein
    -- weiterer Eintrag in `kennwerte`: dort steht, was diese Toolchain GERECHNET
    -- hat. Ein Wert aus dem Internet ist etwas anderes -- er kann richtig sein,
    -- aber er ist nicht nachgerechnet. Stuende er in derselben Tabelle, faende ihn
    -- `db vergleich` und die Berichtstabelle wie einen eigenen, und die Trennung,
    -- um derentwillen die Datenbank ueberhaupt gebaut wurde, waere hin.
    CREATE TABLE IF NOT EXISTS referenzwerte (
        ref_id     INTEGER PRIMARY KEY,
        projekt_id TEXT,                     -- NULL = allgemein, nicht laufbezogen
        groesse    TEXT NOT NULL,
        wert_num   REAL,
        wert_text  TEXT,
        einheit    TEXT,
        zitat      TEXT NOT NULL,            -- die Belegstelle im Originaltext
        quelle_url TEXT NOT NULL,
        quelle_titel TEXT,
        abgerufen  TEXT,
        notiz      TEXT);
    CREATE INDEX IF NOT EXISTS idx_ref_groesse ON referenzwerte(groesse);
    CREATE INDEX IF NOT EXISTS idx_ref_projekt ON referenzwerte(projekt_id);
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
    # Die Stellschrauben des LAUFS, nicht der Maschine. Sie liegen nur im payload,
    # entscheiden aber, ob eine Stufe ueberhaupt durchkommt — an struct_mesh_mm=2
    # sind drei Laeufe in die Zeitueberschreitung gelaufen. Ohne sie in der Datenbank
    # kann niemand den Zusammenhang finden.
    for k in ("struct_mesh_mm", "struct_solver", "struct_deck", "struct_img_px",
              "struct_video", "struct_frames", "fdm_resolution", "frame_resolution",
              "rotor_lam", "stator_lam"):
        v = (meta.get("payload") or {}).get(k)
        if v is not None:
            n, t = _zahl(v)
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
    # Das Taschentor: war die Magnetgeometrie ueberhaupt im vernetzten Modell?
    tc = fem.get("taschen_check") or {}
    if tc:
        conn.execute("INSERT OR REPLACE INTO tore VALUES (?,?,?,?)",
                     (lauf_id, "magnettaschen",
                      1 if tc.get("ok") else 0,
                      f"{tc.get('befund')}: Netz {tc.get('volumen_netz_mm3')} mm3, "
                      f"{tc.get('abw_zu_taschen_pct')} % zur Parametrik"))
    if fem.get("fehlgrund"):
        conn.execute("INSERT OR REPLACE INTO tore VALUES (?,?,?,?)",
                     (lauf_id, "fem_gelaufen", 0,
                      f"{fem['fehlgrund']}: {(fem.get('fehlertext') or '')[:120]}"))
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


# ── Berichtsunterstuetzung ────────────────────────────────────────────────────

# Reihenfolge und Beschriftung der Kennwerte im Bericht. Wer eine Groesse ergaenzt,
# traegt sie auch in HERKUNFT ein — sonst erscheint sie ohne Herkunft, und genau das
# soll die Datenbank ja verhindern.
BERICHT_GRUPPEN = [
    ("Elektromagnetik", ["B_gap_T", "Kt_Nm_per_A", "T_maxwell_Nm", "lcm_slots_poles"]),
    ("Leistung",        ["P_max_kW", "P_max_rpm", "P_cont_max_kW", "T_peak_max_Nm"]),
    ("Festigkeit",      ["max_safe_rpm", "structural_ok", "structural_basis",
                         "safety_factor_fem", "fem_rpm", "fem_sigma_vm_MPa"]),
    ("Thermik",         ["T_winding_C", "T_magnet_C", "T_housing_C", "P_total_W",
                         "cooling", "htc_source"]),
    ("Fahrzyklus",      ["cycle_name", "cycle_kWh100km", "cycle_eta",
                         "anhaenger_kWh100km", "anhaenger_T_max_Nm"]),
    ("Werkstoff und Masse", ["rotor_lam", "stator_lam", "magnet", "hairpin",
                             "mass_g", "fill_factor", "P_fe_W_est"]),
]

_METHODE_KURZ = {
    "analytisch":  "analytische Formel",
    "fdm2d":       "2D-FDM-Feld",
    "fem3d":       "3D-FEM",
    "lptn":        "Waermenetzwerk",
    "zyklus":      "Fahrzyklus",
    "geometrisch": "Geometrie",
    "tabelle":     "Tabellenwert",
    "abgeleitet":  "abgeleitet",
    "unbekannt":   "**ohne Herkunft**",
}


def _md_wert(k: dict) -> str:
    if k["wert_num"] is None and k["wert_text"] is None:
        return "—"
    # Wahrheitswerte tragen BEIDES (1.0 und "ja"), damit man danach filtern UND sie
    # lesen kann. Im Bericht gilt der Text — "structural_ok = 1" liest niemand.
    if k["wert_text"] in ("ja", "nein"):
        return k["wert_text"]
    if k["wert_text"] is not None and k["wert_num"] is None:
        return str(k["wert_text"])
    v = k["wert_num"]
    if k["einheit"] == "" and float(v).is_integer() and abs(v) < 1e6:
        return f"{int(v)}"
    txt = f"{v:.4g}"
    return f"{txt} {k['einheit']}" if k["einheit"] else txt


def bericht_tabelle(conn: sqlite3.Connection, lauf: str | int) -> str:
    """Markdown-Tabelle der Kennwerte **mit Herkunftsspalte** — aus der Datenbank.

    Das ist der Punkt, an dem die Dokumentation datenbankgestuetzt wird: die Zahlen
    kommen aus der Datenbank, und jede traegt sichtbar, aus welchem Verfahren sie
    stammt. Die Auswertung darum herum schreibt weiter das Sprachmodell — es sieht
    diese Tabelle, darf aber laut Prompt keine Zahlen in den Fliesstext nehmen.

    Leere Groessen werden ausgelassen; eine Gruppe ohne einen einzigen Wert entfaellt.
    Ein Kennwert, der ERWARTET war und fehlt (etwa die Festigkeit, wenn der Loeser
    nichts lieferte), erscheint mit „—" statt zu verschwinden — sonst sieht ein
    halber Lauf aus wie ein ganzer.
    """
    d = zeige(conn, lauf)
    if not d:
        return ""
    nach_name = {k["groesse"]: k for k in d["kennwerte"]}

    zeilen = ["### Ergebniskennwerte und ihre Herkunft", "",
              "| Kennwert | Wert | Woher die Zahl kommt |", "|---|---|---|"]
    for gruppe, groessen in BERICHT_GRUPPEN:
        vorhanden = [g for g in groessen if g in nach_name]
        if not vorhanden:
            continue
        zeilen.append(f"| **{gruppe}** | | |")
        for g in vorhanden:
            k = nach_name[g]
            herkunft = _METHODE_KURZ.get(k["methode"], k["methode"])
            zusatz = []
            if k["loeser"]:
                zusatz.append(k["loeser"])
            if k["aufloesung"]:
                zusatz.append(k["aufloesung"])
            if zusatz:
                herkunft += " (" + ", ".join(zusatz) + ")"
            zeilen.append(f"| {g} | {_md_wert(k)} | {herkunft} |")

    lauf_r = d["lauf"]
    zeilen += ["", f"Quelle: Rechnungsdatenbank, Lauf `{lauf_r['projekt_id']}`"
                   f"{', gerechnet ' + lauf_r['zeitpunkt'][:10] if lauf_r['zeitpunkt'] else ''}."]
    if lauf_r["stufen"]:
        zeilen.append(f"Gerechnete Stufen: {lauf_r['stufen'].replace(',', ', ')}.")
    fehlend = [g for _gr, gs in BERICHT_GRUPPEN for g in gs
               if g in nach_name and nach_name[g]["wert_num"] is None
               and nach_name[g]["wert_text"] is None]
    if fehlend:
        zeilen.append(f"**Ohne Wert geblieben:** {', '.join(fehlend)} — die zugehoerige "
                      f"Stufe hat nichts geliefert.")
    return "\n".join(zeilen) + "\n"


def fuer_bericht(projekt_pfad: str) -> str:
    """Bequemer Einstieg fuer ``ema_report``: Projekt notfalls nachtragen, Tabelle liefern.

    Weich gehalten — schlaegt irgendetwas fehl, kommt ein leerer String zurueck und der
    Bericht laeuft ohne diesen Block weiter. Eine Datenbank darf keinen Bericht
    verhindern.
    """
    # Erst pruefen, DANN nachtragen. Ohne diese Schranke legte ein Aufruf mit einem
    # nicht vorhandenen Pfad ueber importiere_projekt einen leeren "abgebrochenen"
    # Lauf in der Datenbank an — ein Phantom, das nie gerechnet wurde.
    if not os.path.isfile(os.path.join(str(projekt_pfad), "results.json")):
        return ""
    try:
        conn = oeffne()
        pid = os.path.basename(str(projekt_pfad).rstrip("/"))
        if not conn.execute("SELECT 1 FROM laeufe WHERE projekt_id=?", (pid,)).fetchone():
            importiere_projekt(conn, projekt_pfad)
        md = bericht_tabelle(conn, pid)
        conn.close()
        return md
    except Exception:                                    # noqa: BLE001
        return ""


# ── Recherchierte Referenzwerte ───────────────────────────────────────────────

class OhneQuelle(ValueError):
    pass


def referenz_hinzufuegen(conn: sqlite3.Connection, groesse: str, wert, einheit: str,
                         zitat: str, quelle_url: str, quelle_titel: str = "",
                         projekt_id: str | None = None, notiz: str = "") -> int:
    """Einen recherchierten Wert ablegen — **nur mit Quelle und Zitat**.

    Beides ist Pflicht, und zwar aus demselben Grund wie der Belegzwang in
    ``ema_lernen``: ein Zahlenwert ohne Belegstelle ist von einer erfundenen Zahl
    nicht zu unterscheiden. Das Zitat muss den Wert enthalten oder ihn wenigstens
    erkennbar stuetzen; geprueft wird, dass es ueberhaupt eines gibt und nicht bloss
    die Zahl noch einmal wiederholt.
    """
    if not (quelle_url or "").startswith(("http://", "https://")):
        raise OhneQuelle("Ein Referenzwert braucht eine Quellen-Adresse (http/https).")
    zitat = (zitat or "").strip()
    if len(zitat) < 20:
        raise OhneQuelle(
            "Kein Zitat. Ein recherchierter Wert ohne Belegstelle ist von einer "
            "erfundenen Zahl nicht zu unterscheiden — die Textstelle mitgeben, "
            "aus der der Wert stammt.")
    n, t = _zahl(wert)
    cur = conn.execute(
        "INSERT INTO referenzwerte (projekt_id, groesse, wert_num, wert_text, einheit,"
        " zitat, quelle_url, quelle_titel, abgerufen, notiz) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (projekt_id, groesse, n, t, einheit, zitat, quelle_url, quelle_titel,
         time.strftime("%Y-%m-%dT%H:%M:%S"), notiz))
    conn.commit()
    return cur.lastrowid


def referenzen(conn: sqlite3.Connection, projekt_id: str | None = None,
               groesse: str | None = None) -> list:
    """Recherchierte Werte lesen. Ohne Projekt: auch die allgemeinen."""
    wo, args = [], []
    if projekt_id:
        wo.append("(projekt_id = ? OR projekt_id IS NULL)"); args.append(projekt_id)
    if groesse:
        wo.append("groesse = ?"); args.append(groesse)
    sql = "SELECT * FROM referenzwerte"
    if wo:
        sql += " WHERE " + " AND ".join(wo)
    return [dict(r) for r in conn.execute(sql + " ORDER BY groesse, abgerufen", args)]


def referenz_tabelle(conn: sqlite3.Connection, projekt_id: str | None = None) -> str:
    """Markdown der Referenzwerte — fuer den Bericht, klar getrennt von den eigenen."""
    refs = referenzen(conn, projekt_id)
    if not refs:
        return ""
    z = ["### Recherchierte Vergleichswerte (Fremdquellen, nicht nachgerechnet)", "",
         "| Groesse | Wert | Quelle |", "|---|---|---|"]
    for r in refs:
        wert = (f"{r['wert_num']:.4g} {r['einheit'] or ''}".strip()
                if r["wert_num"] is not None else (r["wert_text"] or "—"))
        titel = r["quelle_titel"] or r["quelle_url"]
        z.append(f"| {r['groesse']} | {wert} | [{titel[:60]}]({r['quelle_url']}) |")
    z += ["", "Diese Werte stammen aus fremden Veroeffentlichungen und wurden von "
              "dieser Toolchain **nicht nachgerechnet**. Sie dienen der Einordnung, "
              "nicht als Ergebnis. Die Belegstellen:", ""]
    for r in refs:
        z.append(f"* **{r['groesse']}** — „{r['zitat'][:220]}“ "
                 f"({r['quelle_url']}, abgerufen {(r['abgerufen'] or '')[:10]})")
    return "\n".join(z) + "\n"
