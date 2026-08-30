"""Tests fuer die Rechnungsdatenbank (ema_db).

Was hier festgehalten wird und warum:

* **Das Herkunftsregister darf keine Luecke haben.** Ein Kennwert ohne Herkunft
  waere in der Datenbank nicht von einem gerechneten zu unterscheiden — genau das,
  was die Datenbank verhindern soll. Der Test laeuft gegen die ECHTEN Projekte und
  meldet jede Groesse, die im ``summary`` auftaucht, aber nicht im Register steht.
* **Die Unterscheidung analytisch / aus dem Feld muss stimmen.** ``B_gap_T`` ist
  analytisch, ``T_maxwell_Nm`` kommt aus dem geloesten FDM-Feld. Beide stehen im
  selben ``summary`` nebeneinander; verwechselt man sie, behauptet die Dokumentation
  spaeter eine Feldrechnung, die es nicht gab.
* **Der Import muss wiederholbar sein.** Die Datenbank ist ein Index, kein zweiter
  Datenbestand — zweimal importieren darf nichts verdoppeln.
* **Abgebrochene Laeufe muessen sichtbar bleiben.** Gemessen haben 21 von 35
  Projektordnern keine ``results.json``. Sie stillschweigend zu ueberspringen liesse
  die Datenbank vollstaendiger aussehen, als der Bestand ist.

Lauf: ``python test_db.py``   (benutzt eine eigene Datenbank in /tmp, nie die echte)
"""

import json
import os
import sys
import tempfile

import ema_db as DB

_fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")
        _fails.append(name)


def _bau_projekt(wurzel, name, mit_results=True, summary=None, extra=None):
    """Ein kuenstliches Projekt auf die Platte legen."""
    p = os.path.join(wurzel, name)
    os.makedirs(os.path.join(p, "charts"), exist_ok=True)
    json.dump({"label": name, "created": "2026-08-01T10:00:00",
               "geom": {"statorOD": 280, "rotorOD": 188.6, "p": 3, "slots": 36},
               "axial_len": 120.0, "load_nm": 150.0, "cooling": "oil"},
              open(os.path.join(p, "meta.json"), "w"))
    open(os.path.join(p, "charts", "em_field.png"), "wb").write(b"\x89PNG\r\n")
    if mit_results:
        r = {"summary": summary if summary is not None else
             {"B_gap_T": 0.8, "T_maxwell_Nm": 300.0, "mass_g": 20000.0,
              "structural_ok": True, "safety_factor_fem": 2.1},
             "em": {"x": 1}, "thermal": {"y": 2},
             "structural_fem": {"solver_status": "OK", "max_von_mises_MPa": 130.0,
                                "struct_mesh_mm": 3.0},
             "structural_ok": True}
        r.update(extra or {})
        json.dump(r, open(os.path.join(p, "results.json"), "w"))
    return p


def test_register_vollstaendig():
    print("1. Herkunftsregister gegen die ECHTEN Projekte")
    wurzel = os.path.expanduser("~/cae_projekte")
    if not os.path.isdir(wurzel):
        print("  – uebersprungen (kein ~/cae_projekte)")
        return
    gesehen, fehlend = set(), {}
    for name in sorted(os.listdir(wurzel)):
        f = os.path.join(wurzel, name, "results.json")
        if name.startswith("_") or not os.path.isfile(f):
            continue
        try:
            s = (json.load(open(f, encoding="utf-8")).get("summary") or {})
        except (OSError, ValueError):
            continue
        for k in s:
            gesehen.add(k)
            if k not in DB.HERKUNFT:
                fehlend.setdefault(k, 0)
                fehlend[k] += 1
    check(f"alle {len(gesehen)} vorkommenden Kennwerte sind im Register",
          not fehlend, f"ohne Herkunft: {sorted(fehlend)}")
    check("jede Methode im Register gehoert zum Vokabular",
          all(h["methode"] in DB.METHODEN for h in DB.HERKUNFT.values()),
          str([h["methode"] for h in DB.HERKUNFT.values() if h["methode"] not in DB.METHODEN]))
    check("jeder Registereintrag hat eine Begruendung",
          all(h.get("detail") for h in DB.HERKUNFT.values()))


def test_analytisch_vs_feld():
    print("2. Analytisch und aus-dem-Feld duerfen nicht verwechselt werden")
    check("B_gap_T ist analytisch",
          DB.HERKUNFT["B_gap_T"]["methode"] == "analytisch")
    check("die Begruendung sagt es ausdruecklich",
          "NICHT aus dem Feldbild" in DB.HERKUNFT["B_gap_T"]["detail"])
    check("Kt_Nm_per_A ist analytisch",
          DB.HERKUNFT["Kt_Nm_per_A"]["methode"] == "analytisch")
    check("T_maxwell_Nm kommt aus dem geloesten FDM-Feld",
          DB.HERKUNFT["T_maxwell_Nm"]["methode"] == "fdm2d")
    check("und nennt seine Fundstelle",
          "ema_analysis" in (DB.HERKUNFT["T_maxwell_Nm"].get("quelle") or ""))
    check("Festigkeitswerte sind fem3d",
          all(DB.HERKUNFT[k]["methode"] == "fem3d"
              for k in ("safety_factor_fem", "fem_sigma_vm_MPa", "fem_rpm")))


def test_import_wiederholbar():
    print("3. Import ist wiederholbar (die Datenbank ist ein Index)")
    with tempfile.TemporaryDirectory() as d:
        wurzel = os.path.join(d, "projekte")
        os.makedirs(wurzel)
        _bau_projekt(wurzel, "20260801_100000_A")
        _bau_projekt(wurzel, "20260801_110000_B")
        conn = DB.oeffne(os.path.join(d, "test.db"))
        b1 = DB.importiere_alle(conn, wurzel)
        n1 = conn.execute("SELECT COUNT(*) c FROM kennwerte").fetchone()["c"]
        b2 = DB.importiere_alle(conn, wurzel)
        n2 = conn.execute("SELECT COUNT(*) c FROM kennwerte").fetchone()["c"]
        check(f"zwei Laeufe eingelesen ({b1['vollstaendig']})", b1["vollstaendig"] == 2)
        check(f"zweiter Import verdoppelt nichts ({n1} -> {n2})", n1 == n2 and n1 > 0)
        check("auch die Laufzahl bleibt",
              conn.execute("SELECT COUNT(*) c FROM laeufe").fetchone()["c"] == 2)
        # Aendert sich results.json, muss der Wert nachziehen.
        _bau_projekt(wurzel, "20260801_100000_A",
                     summary={"B_gap_T": 0.95, "mass_g": 1.0})
        DB.importiere_alle(conn, wurzel)
        neu = conn.execute("""SELECT wert_num FROM kennwerte k JOIN laeufe l USING(lauf_id)
                              WHERE l.projekt_id='20260801_100000_A' AND k.groesse='B_gap_T'"""
                           ).fetchone()["wert_num"]
        check(f"geaenderter Wert zieht nach (0.8 -> {neu})", abs(neu - 0.95) < 1e-9)
        conn.close()


def test_abgebrochene_sichtbar():
    print("4. Abgebrochene Laeufe bleiben sichtbar")
    with tempfile.TemporaryDirectory() as d:
        wurzel = os.path.join(d, "projekte")
        os.makedirs(wurzel)
        _bau_projekt(wurzel, "20260801_100000_ganz")
        _bau_projekt(wurzel, "20260801_120000_halb", mit_results=False)
        conn = DB.oeffne(os.path.join(d, "test.db"))
        b = DB.importiere_alle(conn, wurzel)
        check(f"1 vollstaendig, 1 abgebrochen ({b})",
              b["vollstaendig"] == 1 and b["abgebrochen"] == 1)
        check("der abgebrochene steht in der Datenbank",
              conn.execute("SELECT COUNT(*) c FROM laeufe").fetchone()["c"] == 2)
        check("er ist als abgebrochen erkennbar",
              "abgebrochen" in (conn.execute(
                  "SELECT notiz FROM laeufe WHERE projekt_id LIKE '%halb'"
              ).fetchone()["notiz"] or ""))
        check("er taucht in der Vorgabeliste NICHT auf",
              len(DB.liste(conn, nur_vollstaendig=True)) == 1)
        check("mit --alle schon", len(DB.liste(conn)) == 2)
        check("seine Bilder sind trotzdem vermerkt",
              conn.execute("""SELECT COUNT(*) c FROM bilder b JOIN laeufe l USING(lauf_id)
                              WHERE l.projekt_id LIKE '%halb' AND b.vorhanden=1"""
                           ).fetchone()["c"] >= 1)
        g = DB.guete(conn, "20260801_120000_halb")
        check("die Guete meldet ihn als unvollstaendig", g["unvollstaendig"] is True)
        conn.close()


def test_guete_trennt_verfahren():
    print("5. Die Guete trennt die Verfahren, statt sie zu mitteln")
    with tempfile.TemporaryDirectory() as d:
        wurzel = os.path.join(d, "projekte")
        os.makedirs(wurzel)
        # Feld gerechnet, Festigkeit NICHT geliefert — der typische Halbfall.
        _bau_projekt(wurzel, "20260801_100000_teil",
                     summary={"B_gap_T": 0.8, "T_maxwell_Nm": 300.0,
                              "safety_factor_fem": None, "fem_sigma_vm_MPa": None,
                              "T_winding_C": 90.0})
        conn = DB.oeffne(os.path.join(d, "test.db"))
        DB.importiere_alle(conn, wurzel)
        g = DB.guete(conn, "20260801_100000_teil")
        check(f"Kennwerte nach Verfahren aufgeschluesselt "
              f"({g['kennwerte_je_methode']})", len(g["kennwerte_je_methode"]) >= 3)
        check(f"FEM als 'erwartet, aber nicht geliefert' erkannt "
              f"({g['fem_geliefert']}/{g['fem_erwartet']})",
              g["fem_erwartet"] >= 2 and g["fem_geliefert"] == 0,
              "sonst sieht ein Lauf ohne Festigkeit aus wie einer mit")
        check("die Loeserauflösung ist vermerkt",
              g["fem_aufloesung"] is not None and "mm" in g["fem_aufloesung"])
        conn.close()


def test_vergleich_traegt_herkunft():
    print("6. Der Vergleich traegt die Herkunft mit")
    with tempfile.TemporaryDirectory() as d:
        wurzel = os.path.join(d, "projekte")
        os.makedirs(wurzel)
        _bau_projekt(wurzel, "20260801_100000_A", summary={"B_gap_T": 0.8, "T_maxwell_Nm": 300.0})
        _bau_projekt(wurzel, "20260801_110000_B", summary={"B_gap_T": 0.6, "T_maxwell_Nm": 280.0})
        conn = DB.oeffne(os.path.join(d, "test.db"))
        DB.importiere_alle(conn, wurzel)
        z = DB.vergleiche(conn, ["B_gap_T", "T_maxwell_Nm"])
        check(f"zwei Zeilen ({len(z)})", len(z) == 2)
        check("je Spalte steht die Methode dabei",
              all(r["B_gap_T__methode"] == "analytisch"
                  and r["T_maxwell_Nm__methode"] == "fdm2d" for r in z),
              "ohne das sehen ungleiche Zahlen gleich aus")
        conn.close()


def test_berichtstabelle():
    print("7. Die Berichtstabelle traegt die Herkunft — und erfindet keine Laeufe")
    with tempfile.TemporaryDirectory() as d:
        wurzel = os.path.join(d, "projekte")
        os.makedirs(wurzel)
        p = _bau_projekt(wurzel, "20260801_100000_A",
                         summary={"B_gap_T": 0.8, "T_maxwell_Nm": 300.0,
                                  "structural_ok": True, "safety_factor_fem": None,
                                  "T_winding_C": 90.0})
        conn = DB.oeffne(os.path.join(d, "test.db"))
        DB.importiere_alle(conn, wurzel)
        md = DB.bericht_tabelle(conn, "20260801_100000_A")
        check("Herkunftsspalte vorhanden", "Woher die Zahl kommt" in md)
        check("analytisch und Feld sind unterscheidbar",
              "analytische Formel" in md and "2D-FDM-Feld" in md,
              "sonst behauptet die Doku eine Feldrechnung, die es nicht gab")
        check("Wahrheitswerte lesbar statt 1/0",
              "| structural_ok | ja |" in md, md[md.find("structural_ok"):][:40])
        check("fehlender Wert wird benannt statt verschwiegen",
              "Ohne Wert geblieben" in md and "safety_factor_fem" in md)
        check("die Quelle steht darunter", "Rechnungsdatenbank" in md)
        conn.close()

    # Der Fehler, der beim Bau auffiel: ein nicht vorhandener Pfad legte ueber
    # importiere_projekt einen leeren "abgebrochenen" Lauf an — ein Phantom.
    vorher = len(DB.liste(DB.oeffne(), nur_vollstaendig=False))
    leer = DB.fuer_bericht("/gibt/es/ganz/sicher/nicht")
    nachher = len(DB.liste(DB.oeffne(), nur_vollstaendig=False))
    check("nicht vorhandener Pfad gibt leer zurueck", leer == "")
    check(f"und legt KEINEN Phantomlauf an ({vorher} -> {nachher})", vorher == nachher)


if __name__ == "__main__":
    for t in (test_register_vollstaendig, test_analytisch_vs_feld,
              test_import_wiederholbar, test_abgebrochene_sichtbar,
              test_guete_trennt_verfahren, test_vergleich_traegt_herkunft,
              test_berichtstabelle):
        t()
    print()
    if _fails:
        print(f"FEHLGESCHLAGEN: {len(_fails)}  ->  " + ", ".join(_fails))
        sys.exit(1)
    print("Alle Pruefungen bestanden.")
