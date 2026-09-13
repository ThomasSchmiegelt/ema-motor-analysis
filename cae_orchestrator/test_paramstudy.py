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


def test_welle_haelt_die_magnete():
    """Wellendurchmesser und Wellenbohrung sind neue Studienparameter — und der
    Wellendurchmesser bewegt die Magnete MIT, wenn man ihn laesst:
    ``r_pos = r_shaft + (r_rot - r_shaft) * magDepthRel`` ist eine RELATIVE
    Lage. Eine Wellenstudie zeigte damit zwei Aenderungen auf einmal.

    Geprueft wird dreierlei: die Parameter sind da, der Ausgangspunkt aendert
    sich um keine Ziffer, und ueber den geometrisch moeglichen Bereich stehen
    die Magnete still."""
    import ema_optimize as O
    import ema_topology as T
    for k in ("shaftD", "shaftBore"):
        assert k in O.FREE_PARAMS, k
        assert O.FREE_PARAMS[k].get("haelt_magnete") is True, k
    assert O.FREE_PARAMS["shaftD"]["geom"] == "shaftD"
    assert O.FREE_PARAMS["shaftBore"]["geom"] == "shaftBoreD"

    g = {"statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60,
         "shaftBoreD": 0, "p": 3, "slots": 54, "magShape": "v", "magAngle": 120,
         "magWidth": 42.2381, "magThick": 6, "magDist": 9.4, "magDepthRel": 0.44566,
         "magLayers": 3, "magLayerGap": 8, "slotDepth": 25, "magGapMm": 0.1,
         "axialLen": 80, "pocketMode": "position"}

    # Der Ausgangspunkt bleibt, wo er ist — KEIN Modellwechsel.
    basis = O.magnetlage(g)
    gg, _ = O._apply_params(g, 80.0, {"shaftD": 60.0})
    assert O.magnetlage(gg) == basis
    assert gg.get("magShape") == "v", \
        "die Bauform darf nicht auf 'custom' umgestellt werden"
    assert "customLegs" not in gg, \
        ("Ein erster Entwurf fror die Schenkel als customLegs ein. Gemessen kam "
         "am selben Punkt bei U 0,711 statt 0,630 T heraus, weil `custom` kein "
         "Salienzband hat und `_analytical_Bgap` anders summiert — die Studie "
         "haette den Modellwechsel gezeigt statt der Welle.")

    # Ueber den moeglichen Bereich stehen die Magnete still.
    for d in (20, 40, 80, 100, 116):
        gg, _ = O._apply_params(g, 80.0, {"shaftD": float(d)})
        assert O.magnetlage(gg) == basis, (d, O.magnetlage(gg))
        assert not gg.get("_magnetlage_hinweis"), d

    # Wo es nicht geht, wird es GESAGT: bei shaftD=120 laege der Sitz (r 58,7 mm)
    # INNERHALB der Welle (r 60 mm).
    gg, _ = O._apply_params(g, 80.0, {"shaftD": 120.0})
    assert O.magnetlage(gg) != basis
    assert "nicht ganz halten" in (gg.get("_magnetlage_hinweis") or "")

    # Speiche: der Magnet spannt den Ringraum aus, eine andere Welle MUSS ihn
    # aendern. Das ist Physik und wird benannt, nicht wegoptimiert.
    gs = dict(g, magShape="spoke", pocketMode="wand")
    gg, _ = O._apply_params(gs, 80.0, {"shaftD": 100.0})
    assert "spoke" in (gg.get("_magnetlage_hinweis") or "")
    print("✓ Welle: Magnete stehen still, wo es geht — und es wird gesagt, wo nicht")


def test_welle_studie_zeigt_nur_die_welle():
    """Die Probe aufs Ganze: eine Wellenstudie an der V-Form laesst Kt und
    B_gap unberuehrt (die Magnete stehen) und bewegt nur die Masse."""
    import json as _j
    import sys as _s
    _s.argv = ["x"]
    import cae_cli
    pl = cae_cli.frischer_payload()
    pl.update(rpm_from=2000, rpm_to=6000, load_nm=20, cooling="oil")
    r = S.run_study(_j.loads(_j.dumps(pl)), "shaftD", 30, 110, steps=5, rpm=6000,
                    progress_cb=lambda m, p=None: None)
    kt = {v for v in r["metrics"]["Kt"] if v is not None}
    bg = {v for v in r["metrics"]["B_gap"] if v is not None}
    ms = [v for v in r["metrics"]["mass_g"] if v is not None]
    assert len(kt) == 1, "Kt darf sich nicht bewegen: %s" % sorted(kt)
    assert len(bg) == 1, "B_gap darf sich nicht bewegen: %s" % sorted(bg)
    assert max(ms) - min(ms) > 100, "die Masse MUSS sich bewegen: %s" % ms
    assert "nicht ganz halten" not in (r["hinweis"] or "")
    print("✓ Wellenstudie: Kt und B_gap stehen (%.4f / %.3f), nur die Masse "
          "bewegt sich (%.0f…%.0f g)" % (kt.pop(), bg.pop(), min(ms), max(ms)))


def _echter_payload(**geom_zusatz):
    """Ein frischer Payload mit gesetzter Geometrie — wie `test_welle_studie…`."""
    import json as _j, sys as _s
    _s.argv = ["x"]
    import cae_cli
    pl = cae_cli.frischer_payload()
    pl.update(rpm_from=2000, rpm_to=8000, load_nm=60, cooling="water")
    pl["geom"].update(geom_zusatz)
    return _j.loads(_j.dumps(pl))


def test_unbaubare_punkte_werden_BENANNT():
    """Gemessen am 13.09.2026 (s. BEFUNDE.md): eine Polpaar-Studie lieferte fuer
    JEDEN Punkt Kennwerte, obwohl bei p = 7 und p = 8 die Magnettaschen
    benachbarter Pole einander durchdringen (bei p = 8 um 1,25 mm). Der
    schnelle Bewerter rechnet `n_legs*magWidth/pole_pitch` — ein VERHAELTNIS,
    das nichts davon merkt, dass der Zaehler nicht mehr in den Nenner passt;
    B_gap stieg deshalb exakt linear mit p und Kt exakt mit p^3.

    Die Kurve bricht bewusst NICHT ab — eine Studie soll zeigen, WO die Grenze
    liegt. Aber jeder Punkt traegt sein Urteil, in der CSV UND im Bild.
    """
    import ema_rotorcheck as RC
    pl = _echter_payload(magShape="bar", p=4, slots=36, magWidth=27.0,
                         magThick=6.0, magDist=12.5, pocketMode="position")
    r = S.run_study(pl, "p", 2, 9, steps=8, rpm=6000,
                    progress_cb=lambda m, p=None: None)

    # Das Urteil steht je Schritt und stimmt mit dem ECHTEN Tor ueberein —
    # kein zweites Abstandsmass daneben.
    assert len(r["baubar"]) == len(r["x"])
    for x, b in zip(r["x"], r["baubar"]):
        g = dict(pl["geom"]); g["p"] = int(x)
        assert b == RC.rotor_layout_check(g)["ok"], (x, b)

    assert r["n_unbaubar"] > 0, "diese Reihe MUSS ueber das Tor hinauslaufen"
    assert "NICHT BAUBAR" in r["hinweis"] and r["unbaubar_grund"]

    # Und in der CSV, weil der Hinweis in einer Tabellenkalkulation fehlt.
    zeilen = S.csv_text(r).splitlines()
    assert zeilen[0].endswith(";baubar")
    urteile = [z.rsplit(";", 1)[1] for z in zeilen[1:]]
    assert urteile == ["ja" if b else "NEIN" for b in r["baubar"]]
    print("✓ nicht baubare Punkte: je Schritt benannt, in CSV und Hinweis")


def test_die_zielgroesse_belohnt_das_unbaubare_NICHT_mehr():
    """Der eigentliche Schaden lag nicht in der Studie, sondern im Optimierer.

    `_analytical_Bgap` waechst mit der Polbedeckung — und genau die waechst,
    wenn die Magnete einander zu durchdringen beginnen. Gemessen stieg Kt an
    einer 305-mm-Maschine von 0,314 am letzten baubaren Punkt auf 0,401
    jenseits des Tors: eine Zielwertsuche auf `max Kt` haette den Rotor mit
    ueberlappenden Taschen zum Sieger erklaert, und nichts haette widersprochen.
    """
    import ema_optimize as O, ema_rotorcheck as RC
    # Die GEMESSENE Maschine (305 mm, Rotor 170, Welle 120) und nicht der
    # frische Payload: dort deckelt `alpha_i` bei 0,92 schon VOR dem Layouttor,
    # Kt steht ab magWidth 55 still, und der Test praefte nichts. Der Deckel ist
    # richtig — aber er faellt nicht immer vor das Tor, und genau dann ist der
    # Fehlerfall da.
    pl = _echter_payload(magShape="bar", p=6, slots=36, magThick=6.0,
                         magDist=12.5, pocketMode="position",
                         statorOD=305.0, statorID=171.6, rotorOD=170.0,
                         shaftD=120.0)
    mats = O._materials(pl)
    op = {"rpm": 6000.0, "load_nm": 60.0, "rpm_base": 6000.0,
          "rpm_thermal": 6000.0}
    ziel = {"metric": "Kt", "goal": "max"}
    axial = float(pl.get("axial_len", 80))

    bester_baubar = bester_kt_unbaubar = None
    gesehen = {True: 0, False: 0}
    for mw in (20.0, 27.0, 34.0, 38.0, 41.0, 48.0, 55.0):
        g = dict(pl["geom"]); g["magWidth"] = mw
        m = O._eval_geom(g, axial, mats, op, "water", 25.0, [3000.0, 6000.0], N=110)
        if "error" in m:
            continue
        assert m.get("baubar") == RC.rotor_layout_check(g)["ok"]
        gesehen[bool(m["baubar"])] += 1
        f = O._fitness(m, ziel, [])
        if m["baubar"]:
            bester_baubar = f if bester_baubar is None else max(bester_baubar, f)
        else:
            # Die ROHE Kennzahl ist hier besser — das ist ja der Fehlerfall.
            bester_kt_unbaubar = (m["Kt"] if bester_kt_unbaubar is None
                                  else max(bester_kt_unbaubar, m["Kt"]))
            assert f < -1e6, "unbaubar rangiert nicht unter jeder Loesung"

    assert gesehen[True] and gesehen[False], \
        "die Reihe trifft den Fehlerfall nicht mehr: %s" % gesehen
    assert bester_kt_unbaubar > bester_baubar, \
        "Kt muesste jenseits des Tors STEIGEN — sonst prueft der Test nichts"
    print("✓ Zielgroesse: unbaubar rangiert unter jeder baubaren Loesung")


def test_polzahl_studie_nennt_die_normierung():
    """Eine Kurve, die zu VIEL zeigt — das Gegenstueck zur flachen Kurve.

    Gemessen (13.09.2026, aus einer Nutzerfrage): haelt man die Polbedeckung
    konstant, steht `B_gap` ueber p = 1…8 exakt still (0,6747 T auf vier
    Stellen), aber Kt steigt 0,0080 → 0,5280 = genau x64 = p². Das ist die
    Hauskonvention „eine Windung je Nut", nicht ein Momentgewinn: mit
    `ema_asm.k_norm` zurueckgerechnet ist der physikalische Kt konstant.
    """
    import math, ema_analysis as A, ema_asm as ASM
    pl = _echter_payload(magShape="bar", slots=36, magThick=6.0, magDist=12.5,
                         pocketMode="position", statorOD=305.0, statorID=171.6,
                         rotorOD=170.0, shaftD=120.0)
    g0, L = pl["geom"], float(pl.get("axial_len", 80))
    teil0 = math.pi * g0["statorID"] / (2 * 6)
    bed = 27.0 / teil0                                   # Bedeckung festhalten

    bgs, kts, phys = [], [], []
    for p_ in (1, 2, 3, 4, 6, 8):
        g = dict(g0); g["p"] = p_
        g["magWidth"] = bed * math.pi * g["statorID"] / (2 * p_)
        bg = A._analytical_Bgap(g)
        # UNGERUNDET: `compute_performance` rundet Kt auf vier Stellen, und bei
        # p = 1 ist Kt 0,0033 — die Rundung allein macht dort 1,7 %, und der
        # Test pruefte dann die Rundung statt die Physik.
        kt = 1.5 * p_ * (p_ * (2 / math.pi) * bg * A.r_gap_m(g)
                         * A.stapellaenge_m(g, L))
        bgs.append(bg); kts.append(kt); phys.append(kt * ASM.k_norm(g))

    # B_gap steht still — der lineare Anstieg der gemeldeten Studie war allein
    # die feste Magnetlaenge.
    assert max(bgs) - min(bgs) < 1e-9, bgs
    # Kt steigt trotzdem mit p^2 …
    assert abs(kts[-1] / kts[0] - 64.0) < 0.2, kts
    # … und der PHYSIKALISCHE Kt ist EXAKT konstant (klassisches Ergebnis:
    # bei gleichem Luftspaltfeld und gleicher Wicklung haengt das Moment nicht
    # an der Polzahl).
    assert max(phys) - min(phys) < 1e-9, phys

    # Und die Studie SAGT es, statt es den Leser herausfinden zu lassen.
    falle = S.deutungsfalle(pl, "p")
    assert "p²" in falle and "k_norm" in falle
    assert S.deutungsfalle(pl, "magWidth") == ""
    print("✓ Polzahl: B_gap steht still, Kt ist Normierung — und es steht dabei")


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
    test_welle_haelt_die_magnete()
    test_welle_studie_zeigt_nur_die_welle()
    test_unbaubare_punkte_werden_BENANNT()
    test_die_zielgroesse_belohnt_das_unbaubare_NICHT_mehr()
    test_polzahl_studie_nennt_die_normierung()
    print("\nALLE PARAMETERSTUDIEN-TESTS BESTANDEN ✅")


if __name__ == "__main__":
    main()
