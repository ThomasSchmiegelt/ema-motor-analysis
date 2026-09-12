"""Tests fuer die Berichtserweiterung — ohne Server, ohne LLM, ohne Elmer.

Drei Teile, die zusammenhaengen:
  * `ema_ansichten` — im 3-D-Betrachter festgehaltene Bilder samt ihren
    Einstellungen (ein |B|-Bild ohne seine Skala ist kein Messwert),
  * `ema_report.sif_loeser`/`generate_em3d_report` — der Elmer-Bericht liest,
    womit wirklich gerechnet wurde, statt es aus dem Modul abzuschreiben,
  * `ema_bericht` — der selbst geschriebene Bericht aus Bloecken.

Lauf: ``python test_bericht.py``
"""

import base64
import json
import os
import tempfile

import ema_ansichten as AN
import ema_bericht as BR
import ema_report as R

# 1x1 PNG
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==")


# ── Festgehaltene Ansichten ──────────────────────────────────────────────────
def test_ansicht_nimmt_data_url_und_haelt_die_einstellungen():
    with tempfile.TemporaryDirectory() as d:
        r = AN.sichern(d, "data:image/png;base64," + base64.b64encode(_PNG).decode(),
                       name="3D Feld iso", beschriftung="Feld |B|",
                       einstellungen={"skala": "0…2,4 T", "lastfall": "6000 1/min",
                                      "schnitt": "Schnitt y"})
        assert r["ok"] and r["datei"].endswith(".png")
        e = AN.liste(d)[0]
        assert e["beschriftung"] == "Feld |B|"
        assert e["einstellungen"]["skala"] == "0…2,4 T"
        # Die Einstellungen stehen in der Bildunterschrift — ein Feldbild ohne
        # seine Skala ist im Bericht ein Muster, kein Messwert.
        rel, cap = AN.als_bildpaare(d)[0]
        assert rel.startswith("ansichten/")
        assert "0…2,4 T" in cap and "6000 1/min" in cap
    print("✓ Ansichten: data-URL angenommen, Einstellungen stehen in der Unterschrift")


def test_ansicht_weist_fremdes_ab():
    with tempfile.TemporaryDirectory() as d:
        assert AN.sichern(d, base64.b64encode(b"kein png").decode())["ok"] is False
        assert "PNG" in AN.sichern(d, base64.b64encode(b"kein png").decode())["grund"]
        assert AN.sichern(d, "data:image/jpeg;base64,AAAA")["ok"] is False
        assert AN.sichern(d, None)["ok"] is False
        gross = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * (AN.MAX_BYTES + 10)).decode()
        assert "zu gross" in AN.sichern(d, gross)["grund"]
        AN.sichern(d, base64.b64encode(_PNG).decode(), name="ok")
        assert AN.pfad(d, "../../etc/passwd") is None
        assert AN.pfad(d, "gibtsnicht.png") is None
    print("✓ Ansichten: kein PNG, kein JPEG, nichts Ueberformatiges, kein Pfad")


def test_ansicht_zwei_in_derselben_sekunde():
    with tempfile.TemporaryDirectory() as d:
        n = {AN.sichern(d, base64.b64encode(_PNG).decode(), name="x")["datei"]
             for _ in range(5)}
        assert len(n) == 5, n
    print("✓ Ansichten: fuenf Aufnahmen in derselben Sekunde, fuenf Dateien")


# ── Elmer: der Loeserstand wird GELESEN ──────────────────────────────────────
_SIF = """Header
  Mesh DB "." "mesh"
End

Solver 1
  Equation = "MgDyn"
  Procedure = "MagnetoDynamics" "WhitneyAVSolver"
  Use Piola Transform = Logical True
  Linear System Solver = Iterative
  Linear System Iterative Method = CG
  Linear System Preconditioning = ILU0
End

Solver 2
  Equation = "MgDynCalc"
  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"
  Linear System Solver = Direct
  Linear System Direct Method = MUMPS
End

Equation 1
  Active Solvers(2) = 1 2
End

Body 1
  Equation = 1
  Material = 1
End
"""


def test_sif_loeser_liest_und_schliesst_bloecke():
    """Der Block endet bei `End`. Ohne das sammelt der Leser weiter, und die
    `Equation = 1` eines Body-Blocks landet im letzten Solver — gemessen stand
    dort „Equation = 1" statt „SaveScalars"."""
    b = R.sif_loeser(_SIF)
    assert len(b) == 2, b
    assert b[0]["Equation"] == "MgDyn"
    assert b[0]["Procedure"].endswith("WhitneyAVSolver")
    assert b[0]["Use Piola Transform"] == "Logical True"
    assert b[1]["Equation"] == "MgDynCalc"          # NICHT "1" aus dem Body-Block
    assert "Use Piola Transform" not in b[1]
    md = R._em3d_md_loeser(b)
    assert "CG + ILU0" in md and "Direct / MUMPS" in md
    assert "Piola" in md
    assert "nicht belegt" in R._em3d_md_loeser([])
    print("✓ Elmer: case.sif gelesen, Bloecke sauber getrennt, Piola erkannt")


def test_em3d_tabellen_sind_lesbar():
    e3 = {"mesh": {"n_nodes": 164912, "n_magnets": 12, "n_pockets": 18,
                   "n_pockets_want": 18, "target_nodes": 145000,
                   "bodies": {"shaft": 1, "rotor": 1, "stator": 1, "air": 21, "ring": 0},
                   "pocket_clear_mm": 0.3},
          "mesh_zones": {"gap_cl": 1.4455, "mag_cl": 3.6137, "mesh_cl": 7.7093,
                         "mag_grow": 3.36},
          "axial_mm": 150.0, "skew_deg": 0.0, "skew_segments": 1,
          "b_gap_mid_peak": 0.319, "b_gap_axial": [0.142, 0.3, 0.384],
          "torque_Nm": 7.09, "torque_note": "Leerlauf",
          "operating_point": {"excitation": "open_circuit", "rpm": 3000.0,
                              "load_nm": 150.0, "iq_A": 0.0},
          "compare_2d": {"B_gap_2D": 0.553, "fundamental_2D": 0.1175,
                         "fundamental_3D": 0.1656, "phase_shift_mech_deg": -1.28,
                         "phase_tol_mech_deg": 3.0, "orientation_ok": True,
                         "excitation": "open_circuit"}}
    netz = R._em3d_md_netz(e3)
    # Anzahlen sind Anzahlen: "164 912.000 Knoten" liest sich wie eine Messgroesse
    assert ".000" not in netz.split("Zellgroesse")[0], netz
    assert "18 von 18 zugeordnet" in netz
    assert "1/1/1/21/0" in netz
    erg = R._em3d_md_ergebnis(e3)
    assert "0.319" in erg and "0.553" in erg
    assert "stimmt ueberein" in erg
    assert "Endeffekt" in erg
    print("✓ Elmer: Netz- und Ergebnistabelle ohne Schein-Nachkommastellen")


def test_maschinenzeile_statt_prompt():
    pl = {"geom": {"magShape": "v", "p": 3, "slots": 54, "statorOD": 280,
                   "statorID": 190, "rotorOD": 188.6}, "axial_len": 80,
          "cooling": "oil", "load_nm": 20}
    z = R._maschine_zeile(pl)
    assert "?" not in z and "Spezifikation" not in z
    assert "0.70 mm Luftspalt" in z
    print("✓ Elmer/Reihe: Kopfzeile ist eine Maschine, keine Aufforderung")


# ── Der selbst geschriebene Bericht ─────────────────────────────────────────
def _projekt(d):
    for sub in ("charts", "frames_oil"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    with open(os.path.join(d, "charts", "em_field.png"), "wb") as f:
        f.write(_PNG)
    with open(os.path.join(d, "frames_oil", "anim.mp4"), "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypmp42")          # kein echtes Video
    return d


def test_bestand_findet_bilder_und_videos():
    with tempfile.TemporaryDirectory() as d:
        _projekt(d)
        os.makedirs(os.path.join(d, "parameterstudien", "s1"), exist_ok=True)
        with open(os.path.join(d, "parameterstudien", "s1", "verlauf.png"), "wb") as f:
            f.write(_PNG)
        with open(os.path.join(d, "parameterstudien", "s1", "frame_0000.png"), "wb") as f:
            f.write(_PNG)
        b = BR.bestand(d)
        pfade = {x["pfad"] for x in b["bilder"]}
        assert "charts/em_field.png" in pfade
        assert "parameterstudien/s1/verlauf.png" in pfade
        # Einzelframes einer Animation sind kein Berichtsbild — sonst stuenden
        # hunderte davon in der Auswahl
        assert "parameterstudien/s1/frame_0000.png" not in pfade
        assert {"frames_oil/anim.mp4"} <= {x["pfad"] for x in b["videos"]}
    print("✓ Bericht: Bestand findet Diagramme, Studien und Videos, keine Einzelframes")


def test_bloecke_werden_geprueft():
    with tempfile.TemporaryDirectory() as d:
        _projekt(d)
        k = BR.anlegen(d, "Probe")
        r = BR.speichern(d, k, {"titel": "T", "bloecke": [
            {"art": "text", "text": "## Hallo"},
            {"art": "bild", "pfad": "charts/em_field.png", "breite": 400},
            {"art": "bild", "pfad": "../../../etc/passwd"},
            {"art": "bild", "pfad": "charts/gibtsnicht.png"},
            {"art": "unfug", "text": "x"},
            {"art": "umbruch"},
        ]})
        arten = [b["art"] for b in r["bloecke"]]
        assert arten == ["text", "bild", "umbruch"], arten
        assert r["bloecke"][1]["breite"] == 100            # geklemmt
        assert len(r["meldungen"]) == 3
        assert any("passwd" in m for m in r["meldungen"])
        assert any("unbekannte Art" in m for m in r["meldungen"])
        zurueck = BR.laden(d, k)
        assert zurueck["titel"] == "T" and len(zurueck["bloecke"]) == 3
    print("✓ Bericht: Pfad ausserhalb des Projekts, fehlende Datei und Unfug-Art abgewiesen")


def test_html_hat_base_und_echtes_video():
    """Die HTML-Datei liegt zwei Ebenen unter dem Projekt; ohne `base href`
    zeigen alle Bilder und Videos ins Leere, sobald man sie oeffnet — und mit
    ihr oeffnet man sie, sie ist ja die Fassung MIT laufendem Video."""
    with tempfile.TemporaryDirectory() as d:
        _projekt(d)
        k = BR.anlegen(d, "P")
        BR.speichern(d, k, {"titel": "Mit Video", "bloecke": [
            {"art": "text", "text": "## Kopf\n\nText."},
            {"art": "bild", "pfad": "charts/em_field.png", "beschriftung": "Feld"},
            {"art": "video", "pfad": "frames_oil/anim.mp4", "beschriftung": "Spray"},
        ]})
        html = BR.als_html(d, BR.laden(d, k))
        assert '<base href="../../">' in html
        assert "<video src='frames_oil/anim.mp4'" in html
        assert "controls" in html
        assert "charts/em_field.png" in html
        md = BR.als_markdown(d, BR.laden(d, k), standbilder=False)
        # Im PDF steht KEIN Video, sondern der Hinweis samt Dateiname
        assert "frames_oil/anim.mp4" in md
        assert "kann es nicht abspielen" in md
        assert "![Feld](charts/em_field.png)" in md
    print("✓ Bericht: HTML mit base+Video, Markdown mit ehrlichem Hinweis statt Video")


def test_umbruch_und_liste():
    with tempfile.TemporaryDirectory() as d:
        _projekt(d)
        k = BR.anlegen(d, "P")
        BR.speichern(d, k, {"titel": "X", "bloecke": [
            {"art": "text", "text": "a"}, {"art": "umbruch"}, {"art": "text", "text": "b"}]})
        md = BR.als_markdown(d, BR.laden(d, k), standbilder=False)
        assert "\\newpage" in md
        e = BR.liste(d)[0]
        assert e["n_bloecke"] == 3 and e["arten"]["text"] == 2
        assert e["pdf"] is False and e["html"] is False
        assert BR.loeschen(d, k) is True and BR.liste(d) == []
        assert BR.loeschen(d, k) is False
    print("✓ Bericht: Seitenumbruch, Uebersicht, loeschen")


def test_zwei_berichte_in_derselben_sekunde():
    with tempfile.TemporaryDirectory() as d:
        _projekt(d)
        assert len({BR.anlegen(d, "gleich") for _ in range(4)}) == 4
    print("✓ Bericht: vier Anlagen in derselben Sekunde, vier Ordner")


def test_fassungen_und_dedup():
    """Jedes Speichern legt eine Fassung ab — unveraendert aber KEINE neue,
    sonst waere die Liste nach einem Nachmittag unlesbar."""
    with tempfile.TemporaryDirectory() as d:
        _projekt(d)
        k = BR.anlegen(d, "H")
        for t in ("A", "A", "A", "B"):
            BR.speichern(d, k, {"titel": "Stand " + t,
                                "bloecke": [{"art": "text", "text": t}]})
        f = BR.fassungen(d, k)
        # anlegen() + A + B = 3 (die beiden Wiederholungen von A fallen weg)
        assert len(f) == 3, [(x["titel"], x["marke"]) for x in f]
        assert f[0]["titel"] == "Stand B", f[0]
    print("✓ Fassungen: Wiederholung ohne Aenderung legt keine neue an")


def test_marken_sortieren_nach_ZAHL_nicht_nach_zeichen():
    """Zwei Fassungen derselben Sekunde heissen ``…038`` und ``…038-2``. Im
    Dateinamen sortiert der Bindestrich (0x2D) UNTER den Punkt (0x2E) — als
    Zeichenkette sortiert gaelte die aeltere als die juengere, und die
    Dubletten-Erkennung verglich gegen den falschen Stand. Derselbe Fehler
    steht schon in `ema_getriebe.rechnungen()`."""
    roh = ["20260912_165038", "20260912_165038-2", "20260912_165038-10",
           "20260912_165039"]
    assert sorted(roh, key=BR._marke_key, reverse=True) == [
        "20260912_165039", "20260912_165038-10", "20260912_165038-2",
        "20260912_165038"]
    # die naive Sortierung stellt es falsch herum — Gegenprobe
    assert sorted(roh, reverse=True)[1] != "20260912_165038-10"
    with tempfile.TemporaryDirectory() as d:
        _projekt(d)
        k = BR.anlegen(d, "H")
        marken = {BR.fassung_ablegen(d, k, {"titel": "T", "bloecke":
                  [{"art": "text", "text": str(i)}]}) for i in range(5)}
        assert len(marken) == 5, marken
    print("✓ Marken: nach Zeit UND laufender Nummer sortiert, nicht als Zeichenkette")


def test_zurueck_schreibt_die_geschichte_nicht_um():
    with tempfile.TemporaryDirectory() as d:
        _projekt(d)
        k = BR.anlegen(d, "H")
        BR.speichern(d, k, {"titel": "A", "bloecke": [{"art": "text", "text": "a"}]})
        marke_a = BR.fassungen(d, k)[0]["marke"]
        BR.speichern(d, k, {"titel": "B", "bloecke": [{"art": "text", "text": "b"},
                                                     {"art": "umbruch"}]})
        vorher = len(BR.fassungen(d, k))
        r = BR.zurueck(d, k, marke_a)
        assert r["ok"]
        jetzt = BR.laden(d, k)
        assert jetzt["titel"] == "A" and len(jetzt["bloecke"]) == 1
        # Der VERLASSENE Stand ist auffindbar — sonst waere der Rueckweg der
        # einzige Schritt, den man nicht rueckgaengig machen kann. Eine eigene
        # "vor der Rueckkehr"-Fassung entsteht dabei NICHT immer, und das ist
        # richtig: der verlassene Stand IST schon die neueste Fassung, eine
        # zweite mit demselben Inhalt waere eine Dublette.
        f = BR.fassungen(d, k)
        assert len(f) > vorher, "die Rueckkehr selbst ist eine Fassung"
        assert any(x["titel"] == "B" for x in f), "der Stand B ist noch da"
        assert any("zurueck auf" in (x["anlass"] or "") for x in f), \
            [x["anlass"] for x in f]
        # …und von dort geht es auch wieder vorwaerts
        zu_b = next(x["marke"] for x in f if x["titel"] == "B")
        assert BR.zurueck(d, k, zu_b)["ok"]
        assert BR.laden(d, k)["titel"] == "B"
        assert BR.zurueck(d, k, marke_a)["ok"]
        assert BR.zurueck(d, k, "gibtsnicht")["ok"] is False
    print("✓ Zurueck: der verlassene Stand wird gesichert, B bleibt auffindbar")


def test_abzweig_und_baum():
    with tempfile.TemporaryDirectory() as d:
        _projekt(d)
        a = BR.anlegen(d, "Haupt")
        BR.speichern(d, a, {"titel": "Haupt", "bloecke": [{"art": "text", "text": "x"}]})
        b = BR.abzweigen(d, a, titel="Variante 1")["kennung"]
        c = BR.abzweigen(d, b, titel="Variante 1.1")["kennung"]
        baum = BR.baum(d)
        tiefen = {e["kennung"]: e["tiefe"] for e in baum}
        assert tiefen[a] == 0 and tiefen[b] == 1 and tiefen[c] == 2, tiefen
        eltern = {e["kennung"]: e["eltern"] for e in baum}
        assert eltern[b] == a and eltern[c] == b
        # Die Herkunft ueberlebt ein Speichern, auch ohne dass sie mitgeschickt wird
        BR.speichern(d, b, {"titel": "Variante 1", "bloecke": []})
        assert (BR.laden(d, b).get("eltern") or {}).get("kennung") == a
        assert {e["kennung"] for e in BR.baum(d)} == {a, b, c}
    print("✓ Baum: Varianten haengen unter ihrer Vorlage, Herkunft ueberlebt das Speichern")


def test_bausteine_werden_frisch_geholt():
    """Ein Baustein friert nichts ein — er wird beim Setzen aus dem Projekt
    geholt. Eine eingefrorene Zahl, die von der Ablage abweicht, sieht richtig
    aus und ist es nicht."""
    with tempfile.TemporaryDirectory() as d:
        _projekt(d)
        k = BR.anlegen(d, "G")
        r = BR.speichern(d, k, {"titel": "Gesamt", "bloecke": [
            {"art": "baustein", "quelle": "getriebe"},
            {"art": "baustein", "quelle": "gibtsnicht"}]})
        assert [b["art"] for b in r["bloecke"]] == ["baustein"]
        assert any("unbekannter Baustein" in m for m in r["meldungen"])
        md = BR.als_markdown(d, BR.laden(d, k), standbilder=False)
        # Was es nicht gibt, sagt das auch — das Fehlen ist die Auskunft
        assert "keine Getriebeauslegung abgelegt" in md
        assert "## " + BR.BAUSTEINE["getriebe"] in md
        html = BR.als_html(d, BR.laden(d, k))
        assert BR.BAUSTEINE["getriebe"] in html
        assert set(BR.BAUSTEINE) >= {"steckbrief", "getriebe", "elmer",
                                     "studien", "sicherheit"}
    print("✓ Bausteine: frisch geholt, Unbekanntes abgewiesen, Fehlendes benannt")


def test_alle_berichte_findet_jede_stufe():
    with tempfile.TemporaryDirectory() as d:
        _projekt(d)
        for rel in ("bericht_elmer.pdf", "studienreihe.pdf"):
            with open(os.path.join(d, rel), "wb") as f:
                f.write(b"%PDF-1.4")
        os.makedirs(os.path.join(d, "parameterstudien", "s1"), exist_ok=True)
        with open(os.path.join(d, "parameterstudien", "s1", "parameterstudie.pdf"), "wb") as f:
            f.write(b"%PDF-1.4")
        k = BR.anlegen(d, "Eigen")
        with open(os.path.join(BR.wurzel(d), k, "bericht.pdf"), "wb") as f:
            f.write(b"%PDF-1.4")
        pfade = {e["pfad"] for e in BR.alle_berichte(d)}
        assert "bericht_elmer.pdf" in pfade
        assert "studienreihe.pdf" in pfade
        assert "parameterstudien/s1/parameterstudie.pdf" in pfade
        assert ("berichte/%s/bericht.pdf" % k) in pfade
        assert all(e["mb"] is not None and e["zeit"] for e in BR.alle_berichte(d))
    print("✓ Uebersicht: jede Stufe wird gefunden, wo immer sie ablegt")


def main():
    test_ansicht_nimmt_data_url_und_haelt_die_einstellungen()
    test_ansicht_weist_fremdes_ab()
    test_ansicht_zwei_in_derselben_sekunde()
    test_sif_loeser_liest_und_schliesst_bloecke()
    test_em3d_tabellen_sind_lesbar()
    test_maschinenzeile_statt_prompt()
    test_bestand_findet_bilder_und_videos()
    test_bloecke_werden_geprueft()
    test_html_hat_base_und_echtes_video()
    test_umbruch_und_liste()
    test_zwei_berichte_in_derselben_sekunde()
    test_fassungen_und_dedup()
    test_marken_sortieren_nach_ZAHL_nicht_nach_zeichen()
    test_zurueck_schreibt_die_geschichte_nicht_um()
    test_abzweig_und_baum()
    test_bausteine_werden_frisch_geholt()
    test_alle_berichte_findet_jede_stufe()
    print("\nALLE BERICHTS-TESTS BESTANDEN ✅  (PDF-Rendern separat, braucht pandoc)")


if __name__ == "__main__":
    main()
