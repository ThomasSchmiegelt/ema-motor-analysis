"""Tests fuer Recherche und Selbstlernfunktion.

Der Kern beider Module ist eine Trennung, die leicht verloren geht:

* **Recherche** liefert FREMDTEXT. Er darf in einem Bericht nicht neben einer
  gerechneten Zahl stehen, als waere er gleichwertig. Der Test verlangt, dass jede
  Ausgabe die Herkunftsmarke traegt und dass lange Seiten gekuerzt werden — ein
  46.000-Zeichen-Artikel fuellt sonst zwei Drittel des Kontextfensters und draengt
  die Rechenergebnisse heraus.
* **Lernen** trennt GEMESSENE Regeln (aus der Datenbank hergeleitet, bei jedem
  Aufruf neu) von ERFAHRUNGEN (abgelegte Notizen). Notizen werden nur mit Beleg
  angenommen. Ohne diese Schranke fuellt sich der Speicher mit Folklore, die das
  naechste Modell als Tatsache liest.

Lauf: ``python test_lernen.py``   (ohne Netz; die Netzteile werden uebersprungen)
"""

import json
import os
import sys
import tempfile

import ema_db as DB
import ema_lernen as L
import ema_recherche as R

_fails, _sprung = [], []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")
        _fails.append(name)


def test_fremdtext_markiert():
    print("1. Recherche liefert erkennbaren FREMDTEXT")
    t = R.als_text([{"titel": "T", "adresse": "https://x.y", "anriss": "A"}], "suche")
    check("Suchausgabe traegt die Herkunftsmarke", "FREMDTEXT AUS DEM INTERNET" in t)
    check("und den Vorrang der Datenbank", "Rechnungsdatenbank" in t)
    d = {"adresse": "https://x.y", "titel": "T", "datum": "", "text": "x" * 100,
         "zeichen": 100, "gekuerzt": False}
    check("Seitenausgabe traegt sie ebenfalls",
          "FREMDTEXT AUS DEM INTERNET" in R.als_text(d, "hole"))
    check("und nennt die Quelle", "https://x.y" in R.als_text(d, "hole"))
    lang = dict(d, text="y" * R.MAX_ZEICHEN, zeichen=46000, gekuerzt=True)
    aus = R.als_text(lang, "hole")
    check(f"lange Seiten werden sichtbar gekuerzt (auf {R.MAX_ZEICHEN})",
          "gekuerzt auf" in aus and "46000" in aus,
          "sonst frisst eine Seite das Kontextfenster")
    check("Fehlerfall bleibt lesbar",
          "Fehler:" in R.als_text({"adresse": "u", "fehler": "weg"}, "hole"))


def test_erfahrung_braucht_beleg():
    print("2. Eine Erfahrung ohne Beleg wird abgewiesen")
    with tempfile.TemporaryDirectory() as d:
        alt = L.ERFAHRUNGEN
        L.ERFAHRUNGEN = os.path.join(d, "e.jsonl")
        conn = DB.oeffne(os.path.join(d, "t.db"))
        try:
            for regel, beleg, warum in (
                    ("Feinere Netze sind besser", "glaube ich", "kein Zahl/Kennung"),
                    ("Zu kurz", "Lauf 20260827_170019 zeigt es", "Regel zu kurz"),
                    ("Eine ordentlich lange Regel ueber Netze", "ja", "Beleg zu kurz")):
                try:
                    L.merke(regel, beleg, conn=conn)
                    check(f"abgewiesen: {warum}", False, "wurde angenommen")
                except L.OhneBeleg:
                    check(f"abgewiesen: {warum}", True)
            satz = L.merke("struct_mesh_mm=2 laeuft in die Zeitueberschreitung",
                           "3 Laeufe 20260827_*: solver_status FAILED; 3 mm dauerte 414 s",
                           conn=conn)
            check("mit Beleg angenommen", satz["regel"].startswith("struct_mesh_mm"))
            check("der Bestandsstand wird mitgeschrieben",
                  "laeufe_bei_aufnahme" in satz,
                  "sonst laesst sich Veralten nicht feststellen")
            check("und ist wieder lesbar", len(L.erfahrungen()) == 1)
        finally:
            L.ERFAHRUNGEN = alt
        conn.close()


def _bau(wurzel, name, mesh, fem_wert):
    p = os.path.join(wurzel, name)
    os.makedirs(p, exist_ok=True)
    json.dump({"label": name, "created": "2026-08-01T10:00:00",
               "geom": {"statorOD": 280, "rotorOD": 188.6, "p": 3, "slots": 36},
               "axial_len": 120.0,
               "payload": {"struct_mesh_mm": mesh}},
              open(os.path.join(p, "meta.json"), "w"))
    json.dump({"summary": {"B_gap_T": 0.8, "fem_sigma_vm_MPa": fem_wert},
               "em": {"a": 1}, "structural_ok": True},
              open(os.path.join(p, "results.json"), "w"))


def test_gemessene_regel_findet_die_netzweite():
    print("3. Die gemessene Regel findet den Zusammenhang Netzweite -> FEM-Ausbeute")
    with tempfile.TemporaryDirectory() as d:
        wurzel = os.path.join(d, "p"); os.makedirs(wurzel)
        for i in range(4):
            _bau(wurzel, f"20260801_10000{i}_fein", 2.0, None)      # feines Netz, nichts
        for i in range(3):
            _bau(wurzel, f"20260801_11000{i}_grob", 4.0, 130.0)     # grobes Netz, Werte
        conn = DB.oeffne(os.path.join(d, "t.db"))
        DB.importiere_alle(conn, wurzel)
        r = L.regel_fem_nach_netzweite(conn)
        nach = {n["struct_mesh_mm"]: n for n in r["netzweiten"]}
        check(f"beide Netzweiten erkannt ({sorted(nach)})", set(nach) == {2.0, 4.0})
        check("2 mm: 0 von 4 mit FEM-Wert",
              nach[2.0]["mit_fem_wert"] == 0 and nach[2.0]["laeufe"] == 4)
        check("4 mm: 3 von 3 mit FEM-Wert",
              nach[4.0]["mit_fem_wert"] == 3 and nach[4.0]["laeufe"] == 3)
        alt = L.ERFAHRUNGEN
        L.ERFAHRUNGEN = os.path.join(d, "leer.jsonl")
        try:
            t = L.als_text(conn)
        finally:
            L.ERFAHRUNGEN = alt
        check("der Text warnt vor der schlechten Netzweite",
              "2.0 mm" in t and "Beobachtung" in t)
        check("und nennt den schnellen Ausweg", "struct_solver='ccx'" in t)
        check("die gute Netzweite wird NICHT bemaengelt",
              "bei 4.0 mm lieferten nur" not in t)
        conn.close()


def test_veralten():
    print("4. Erfahrungen veralten sichtbar")
    with tempfile.TemporaryDirectory() as d:
        wurzel = os.path.join(d, "p"); os.makedirs(wurzel)
        _bau(wurzel, "20260801_100000_a", 3.0, 130.0)
        conn = DB.oeffne(os.path.join(d, "t.db"))
        DB.importiere_alle(conn, wurzel)
        alt = L.ERFAHRUNGEN
        L.ERFAHRUNGEN = os.path.join(d, "e.jsonl")
        try:
            L.merke("Eine Regel mit ordentlicher Laenge",
                    "Lauf 20260801_100000_a, sigma 130 MPa", conn=conn)
            p = L.pruefe(conn)
            check("frisch aufgenommen gilt als frisch",
                  len(p["frisch"]) == 1 and not p["nachzupruefen"])
            for i in range(L.VERALTET_AB + 2):
                _bau(wurzel, f"20260901_1000{i:02d}_neu", 3.0, 130.0)
            DB.importiere_alle(conn, wurzel)
            p2 = L.pruefe(conn)
            check(f"nach {L.VERALTET_AB}+ neuen Laeufen nachzupruefen "
                  f"({len(p2['nachzupruefen'])})", len(p2["nachzupruefen"]) == 1)
            check("mit der Zahl der Laeufe seither",
                  p2["nachzupruefen"][0]["neue_laeufe_seither"] >= L.VERALTET_AB)
        finally:
            L.ERFAHRUNGEN = alt
        conn.close()


def test_gemessen_und_erfahrung_getrennt():
    print("5. Gemessenes und Abgelegtes bleiben getrennt")
    r = L.gemessene_regeln()
    check("gemessene Regeln kommen ohne Erfahrungsdatei aus",
          "ausbeute" in r and "erfahrungen" not in r,
          "sonst koennte eine Notiz eine Messung ueberschreiben")
    check("sie tragen einen Stand", "stand" in r)
    t = L.als_text()
    check("der Text trennt die beiden Abschnitte sichtbar",
          "## Gemessen" in t and "## Erfahrungen" in t)


if __name__ == "__main__":
    for t in (test_fremdtext_markiert, test_erfahrung_braucht_beleg,
              test_gemessene_regel_findet_die_netzweite, test_veralten,
              test_gemessen_und_erfahrung_getrennt):
        t()
    print()
    if _sprung:
        print(f"uebersprungen: {', '.join(_sprung)}")
    if _fails:
        print(f"FEHLGESCHLAGEN: {len(_fails)}  ->  " + ", ".join(_fails))
        sys.exit(1)
    print("Alle Pruefungen bestanden.")
