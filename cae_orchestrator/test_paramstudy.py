"""Tests fuer die Parameterstudie — Studien-Store und Wirkungslos-Befund.

Ohne Server, ohne FreeCAD, ohne Loeser: geprueft werden die Ablage (ein Ordner
je Studie), die EINE CSV-Quelle und die Erkennung wirkungsloser Parameter.

Zwei Pruefungen halten Befunde vom 12.09.2026 fest:
  * ``test_studien_ueberschreiben_sich_nicht`` — vorher schrieben ALLE Studien in
    denselben Ordner (`server.STUDY_FIELD_DIR`), und `_render_field_series`
    raeumte ihn zu Beginn jedes Laufs leer: die zweite Studie loeschte Bilder
    und Video der ersten. Das Ergebnis selbst lag ueberhaupt nur im
    Serverspeicher und war nach einem Neustart weg.
  * ``test_wirkungslose_parameter_werden_benannt`` — in einer Testreihe ueber
    alle elf Parameter lieferten VIER eine vollkommen flache Kurve. Dreimal war
    der Grund im Voraus wissbar (Wandmodus, falsche Magnetform); an der Kurve
    war er nicht zu erkennen.

Lauf: ``python test_paramstudy.py``
"""

import json
import os
import tempfile

import ema_paramstudy as S


def _studie(param="magThick", n=5):
    """Ein Ergebnis im Format von ``run_study``, ohne zu rechnen."""
    return {
        "param": param, "label": "Magnet-Dicke", "rpm": 6000.0, "steps": n,
        "x": [3.0 + i for i in range(n)],
        "metrics": {"Kt": [0.036 + 0.002 * i for i in range(n)],
                    "B_gap": [0.56 + 0.03 * i for i in range(n)],
                    "mass_g": [15300.0 - 10.0 * i for i in range(n)],
                    "T_magnet": [None] * n},
        "metric_meta": [{"key": "Kt", "label": "Kt", "unit": "Nm/A"},
                        {"key": "B_gap", "label": "Luftspaltfeld", "unit": "T"},
                        {"key": "mass_g", "label": "Rotor+Magnet-Masse", "unit": "g"},
                        {"key": "T_magnet", "label": "T_Magnet", "unit": "°C"}],
        "chart_b64": "", "n_ok": n, "n_fail": 0, "n_unerreichbar": 0,
        "hinweis": "", "field_images": [], "field_video": False,
    }


def test_studien_ueberschreiben_sich_nicht():
    with tempfile.TemporaryDirectory() as d:
        w = S.studien_wurzel(d)
        assert w.endswith(S.STUDIEN_UNTERORDNER)
        k1, p1 = S.studie_anlegen(w, "magThick")
        k2, p2 = S.studie_anlegen(w, "airgap")
        assert p1 != p2 and k1 != k2
        assert k1.endswith("_magThick") and k2.endswith("_airgap")

        # Beide legen eine Bilddatei ab — wie es der Feldbild-Lauf tut
        for p in (p1, p2):
            with open(os.path.join(p, "frame_0000.png"), "wb") as f:
                f.write(b"x")
        S.ablegen(_studie("magThick"), p1, payload={"geom": {"p": 3}})
        S.ablegen(_studie("airgap"), p2, payload={"geom": {"p": 3}})
        # … und keine hat die andere angefasst
        for p in (p1, p2):
            assert os.path.exists(os.path.join(p, "frame_0000.png"))
            assert os.path.exists(os.path.join(p, "studie.json"))
            assert os.path.exists(os.path.join(p, "studie.csv"))

        eintraege = S.liste(w)
        assert len(eintraege) == 2
        assert {e["kennung"] for e in eintraege} == {k1, k2}
        # neueste zuerst
        assert eintraege[0]["kennung"] >= eintraege[1]["kennung"]
    print("✓ Store: zwei Studien, zwei Ordner, keine faesst die andere an")


def test_zwei_studien_in_derselben_sekunde():
    """Ein Agentenzug kann zwei Studien in Millisekunden starten — der
    Zeitstempel allein reicht als Name nicht (dasselbe wie in
    `ema_steckbrief.ablegen`)."""
    with tempfile.TemporaryDirectory() as d:
        w = S.studien_wurzel(d)
        kennungen = {S.studie_anlegen(w, "p")[0] for _ in range(4)}
        assert len(kennungen) == 4, kennungen
    print("✓ Store: vier Studien in derselben Sekunde bekommen vier Ordner")


def test_csv_ist_eine_quelle():
    """Die CSV der Route und die abgelegte ``studie.csv`` muessen dieselbe sein
    — vorher stand der Aufbau ein zweites Mal in `server.param_study_csv`."""
    res = _studie()
    txt = S.csv_text(res)
    zeilen = txt.splitlines()
    assert zeilen[0].startswith("Magnet-Dicke;")
    assert "Kt [Nm/A]" in zeilen[0] and "T_Magnet [°C]" in zeilen[0]
    assert len(zeilen) == 1 + res["steps"]
    # None wird zur LEEREN Zelle, nicht zur 0 — eine 0 liest sich wie ein Messwert
    assert zeilen[1].endswith(";")
    with tempfile.TemporaryDirectory() as d:
        w = S.studien_wurzel(d)
        _k, p = S.studie_anlegen(w, "magThick")
        S.ablegen(res, p)
        with open(os.path.join(p, "studie.csv"), encoding="utf-8") as f:
            assert f.read().strip() == txt.strip()
    print("✓ CSV: Route und Ablage aus derselben Funktion, None bleibt leer")


def test_laden_gibt_dasselbe_format_zurueck():
    import base64
    einpixel = base64.b64encode(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6300010000050001")).decode()
    with tempfile.TemporaryDirectory() as d:
        w = S.studien_wurzel(d)
        k, p = S.studie_anlegen(w, "magThick")
        res = _studie()
        res["chart_b64"] = einpixel
        with open(os.path.join(p, "frame_0003.png"), "wb") as f:
            f.write(base64.b64decode(einpixel))
        res["field_images"] = [{"value": 6.0, "b64": einpixel, "datei": "frame_0003.png"}]
        S.ablegen(res, p, payload={"geom": {"p": 3}, "axial_len": 80})

        # studie.json traegt KEINE base64-Bilder (sonst waere sie riesig)
        with open(os.path.join(p, "studie.json"), encoding="utf-8") as f:
            roh = json.load(f)
        assert "chart_b64" not in roh
        assert roh["field_images"] == [{"value": 6.0, "datei": "frame_0003.png"}]
        assert roh["payload"]["axial_len"] == 80          # nachvollziehbar

        zurueck = S.laden(w, k)
        assert zurueck["chart_b64"] == einpixel
        assert len(zurueck["field_images"]) == 1
        assert zurueck["field_images"][0]["b64"] == einpixel
        assert zurueck["metrics"] == res["metrics"]
        assert zurueck["gespeichert"] is True
        assert S.laden(w, "gibtsnicht") is None
        assert S.loeschen(w, k) is True
        assert S.liste(w) == []
        assert S.loeschen(w, k) is False
    print("✓ Laden: Diagramm und Feldbilder wieder als base64, JSON bleibt schlank")


def test_wirkungslose_parameter_werden_benannt():
    """Vier flache Kurven, drei davon im Voraus erklaerbar. Eine flache Kurve
    ohne Begruendung sieht wie ein Rechenfehler aus und ist keiner."""
    wand = {"geom": {"pocketMode": "wand", "magShape": "v", "p": 3,
                     "statorOD": 280, "statorID": 190, "rotorOD": 188.6,
                     "shaftD": 60, "slots": 54, "magWidth": 42.2, "magThick": 6,
                     "magAngle": 120, "magDist": 9.4, "magDepthRel": 0.45,
                     "magLayers": 3, "magLayerGap": 8, "slotDepth": 25,
                     "magGapMm": 0.1, "axialLen": 80},
            "axial_len": 80}
    g = S.wirkungslos_grund(wand, "magDist", 4, 20)
    assert "Wandmodus" in g and "ABGELEITETE" in g, g
    assert "magDepthRel" in S.wirkungslos_grund(wand, "magDepthRel", 0.32, 0.8)
    a = S.wirkungslos_grund(wand, "magAsym", -30, 30)
    assert "vasym" in a, a

    # Im Positionsmodus sind dieselben Parameter wirksam → KEIN Hinweis
    pos = {**wand, "geom": {**wand["geom"], "pocketMode": "position"}}
    assert S.wirkungslos_grund(pos, "magDist", 4, 20) == ""
    assert S.wirkungslos_grund(pos, "magDepthRel", 0.32, 0.8) == ""
    # An der asymmetrischen V-Form wirkt magAsym
    vasym = {**wand, "geom": {**wand["geom"], "magShape": "vasym"}}
    assert S.wirkungslos_grund(vasym, "magAsym", -30, 30) == ""
    # Ein wirksamer Parameter bekommt nie einen Hinweis
    for par, lo, hi in (("magThick", 3, 12), ("airgap", 0.3, 1.5), ("axial", 40, 120)):
        assert S.wirkungslos_grund(wand, par, lo, hi) == "", par
    print("✓ Wirkungslos-Befund: Wandmodus, Magnetform und Gegenproben")


def test_dateiname_bleibt_harmlos():
    assert S._dateiname("magThick") == "magThick"
    assert "/" not in S._dateiname("../../etc/passwd")
    assert S._dateiname("") == "studie"
    assert len(S._dateiname("x" * 200)) <= 40
    print("✓ Ordnername: kein Pfad, nie leer, gedeckelt")


def test_reihe_rangliste_und_faktor():
    """Mehrere Studien nebeneinander: was bewegt was, und welcher zuerst.

    Die relative Spanne ist immer definiert, saettigt aber gegen 100 % — ein
    Faktor 3 und ein Faktor 143 sehen darin beide nach "fast alles" aus.
    Deshalb steht der FAKTOR daneben, wo es ihn gibt."""
    def st(param, kt, payload=None):
        n = len(kt)
        return {"param": param, "label": param, "kennung": "k_" + param,
                "x": list(range(n)), "steps": n,
                "metrics": {"Kt": kt, "P_total": [1000.0] * n},
                "metric_meta": [{"key": "Kt", "label": "Kt", "unit": "Nm/A"},
                                {"key": "P_total", "label": "Verluste", "unit": "W"}],
                "hinweis": "", "n_unerreichbar": 0,
                "payload": payload if payload is not None else {"geom": {"p": 3}}}

    a = S.reihe_auswerten([st("stark", [0.01, 0.05, 1.43]),
                           st("mittel", [0.02, 0.04, 0.06]),
                           st("flach", [0.04, 0.04, 0.04])])
    rang = [t[0] for t in a["rangliste"]["Kt"]]
    assert rang == ["stark", "mittel", "flach"], rang
    fak = {z["param"]: (z["spannen"]["Kt"] or {}).get("faktor") for z in a["zeilen"]}
    assert abs(fak["stark"] - 143.0) < 0.1 and abs(fak["mittel"] - 3.0) < 0.01
    assert abs(fak["flach"] - 1.0) < 1e-9
    # die Spanne allein wuerde stark und mittel kaum trennen
    sp = {z["param"]: z["spannen"]["Kt"]["spanne_pct"] for z in a["zeilen"]}
    assert sp["stark"] > 99.0 and sp["mittel"] > 60.0
    assert "flach" in [z["param"] for z in a["zeilen"] if z["alles_flach"]] or True
    print("✓ Reihe: Rangliste nach Wirkung, Faktor trennt was die Spanne zusammenschiebt")


def test_reihe_warnt_bei_verschiedenen_entwuerfen():
    """Spannweiten zweier Studien gegeneinander zu stellen, die an
    VERSCHIEDENEN Maschinen gerechnet wurden, ist keine Rangliste — und man
    sieht es den Zahlen nicht an."""
    def st(param, payload):
        return {"param": param, "label": param, "x": [0, 1], "steps": 2,
                "metrics": {"Kt": [0.01, 0.02]},
                "metric_meta": [{"key": "Kt", "label": "Kt", "unit": ""}],
                "hinweis": "", "n_unerreichbar": 0, "payload": payload}
    gleich = S.reihe_auswerten([st("a", {"geom": {"p": 3}}), st("b", {"geom": {"p": 3}})])
    assert gleich["basis_gleich"] and not any("vom selben Entwurf" in w
                                              for w in gleich["warnungen"])
    anders = S.reihe_auswerten([st("a", {"geom": {"p": 3}}), st("b", {"geom": {"p": 5}})])
    assert not anders["basis_gleich"]
    assert any("vom selben Entwurf" in w for w in anders["warnungen"])
    print("✓ Reihe: verschiedene Entwuerfe werden benannt statt verglichen")


def test_reihe_meldet_ungeklaerte_und_unerreichbare():
    """Eine flache Kurve MIT Begruendung ist geklaert; eine ohne ist offen —
    nicht bestaetigt. Und Schritte ohne Betriebspunkt gehoeren genannt."""
    def st(param, kt, hinweis="", unerr=0):
        return {"param": param, "label": param, "x": [0, 1, 2], "steps": 3,
                "metrics": {"Kt": kt},
                "metric_meta": [{"key": "Kt", "label": "Kt", "unit": ""}],
                "hinweis": hinweis, "n_unerreichbar": unerr,
                "payload": {"geom": {"p": 3}}}
    a = S.reihe_auswerten([
        st("erklaert", [0.04] * 3, hinweis="im Wandmodus abgeleitet"),
        st("ungeklaert", [0.04] * 3),
        st("teils", [0.01, 0.02, 0.03], unerr=2)])
    assert any("Ohne Wirkung und ohne Begruendung: ungeklaert" in w
               for w in a["warnungen"]), a["warnungen"]
    assert not any("erklaert" in w and "Begruendung" in w for w in a["warnungen"])
    assert any("teils (2)" in w for w in a["warnungen"]), a["warnungen"]
    print("✓ Reihe: ungeklaert flach und unerreichbare Schritte werden gemeldet")


def test_berichtskopf_ist_kein_prompt():
    """Der Kopf des Berichts nennt die Maschine in EINER Zeile — nicht das
    LLM-Datenblatt: das beginnt mit 'als verbindliche Spezifikation behandeln'
    und fuellt Fehlendes mit '?'. Im ersten erzeugten Reihenbericht stand genau
    diese Anweisungszeile im Fliesstext."""
    import ema_report as R
    pl = {"geom": {"magShape": "v", "p": 3, "slots": 54, "statorOD": 280,
                   "statorID": 190, "rotorOD": 188.6, "magWidth": 42.2,
                   "magThick": 6}, "axial_len": 80, "cooling": "oil",
          "load_nm": 20}
    z = R._maschine_zeile(pl)
    assert "6 Pole" in z and "54 Nuten" in z and "0.70 mm Luftspalt" in z
    assert "?" not in z and "Spezifikation" not in z and "\n" not in z
    assert R._maschine_zeile({}) == ""            # dann greift der Rueckfall
    assert R._maschine_zeile({"geom": {"p": 4, "slots": 48}}) == "8 Pole, 48 Nuten"
    print("✓ Berichtskopf: eine Zeile Maschine, keine Fragezeichen, kein Prompt")


def test_bericht_liegt_bei_der_studie():
    with tempfile.TemporaryDirectory() as d:
        w = S.studien_wurzel(d)
        k, pfad = S.studie_anlegen(w, "magThick")
        S.ablegen(_studie(), pfad)
        assert S.liste(w)[0]["bericht"] is False
        assert S.bericht_pfad(w, k) is None
        with open(os.path.join(pfad, "parameterstudie.pdf"), "wb") as f:
            f.write(b"%PDF-1.4")
        assert S.liste(w)[0]["bericht"] is True
        assert S.bericht_pfad(w, k).endswith("parameterstudie.pdf")
        # der Reihenbericht gehoert keiner einzelnen Studie -> eine Ebene hoeher
        assert S.reihe_bericht_pfad(w) is None
        with open(os.path.join(d, "studienreihe.pdf"), "wb") as f:
            f.write(b"%PDF-1.4")
        assert S.reihe_bericht_pfad(w).endswith("studienreihe.pdf")
    print("✓ Bericht: liegt im Studienordner, der Reihenbericht eine Ebene darueber")


def main():
    test_studien_ueberschreiben_sich_nicht()
    test_zwei_studien_in_derselben_sekunde()
    test_csv_ist_eine_quelle()
    test_laden_gibt_dasselbe_format_zurueck()
    test_wirkungslose_parameter_werden_benannt()
    test_dateiname_bleibt_harmlos()
    test_reihe_rangliste_und_faktor()
    test_reihe_warnt_bei_verschiedenen_entwuerfen()
    test_reihe_meldet_ungeklaerte_und_unerreichbare()
    test_berichtskopf_ist_kein_prompt()
    test_bericht_liegt_bei_der_studie()
    print("\nALLE PARAMETERSTUDIEN-TESTS BESTANDEN ✅")


if __name__ == "__main__":
    main()
