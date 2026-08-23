"""Tests für die Agent-Kommandozeile (`cae_cli`) — OHNE laufenden Server.

Geprüft wird der Teil, der still falsch sein kann: das Einsortieren und Prüfen von
``--set``-Zuweisungen. Ein Tippfehler, der als neuer Schlüssel im Payload landet, wird
vom Server anstandslos angenommen und ändert an der Rechnung nichts — der Aufrufer
bekommt ein Ergebnis, das nicht zu seiner Bestellung gehört. Genau das fangen diese
Tests ab.

Das Schema wird gestellt (kein HTTP), die Schlüsselnamen entsprechen aber dem echten
``/param_schema``; ``test_schema_vs_payload`` prüft gegen den Server, wenn einer läuft,
und wird sonst übersprungen."""

import json
import os

import cae_cli


# Ausschnitt aus /param_schema — dieselben Felder, dieselbe Bedeutung.
SCHEMA = {
    "slotDepth": {"key": "slotDepth", "kind": "num", "in_geom": True,
                  "lo": 5, "hi": 60, "def": 25, "int": False},
    "p":         {"key": "p", "kind": "num", "in_geom": True,
                  "lo": 1, "hi": 40, "def": 4, "int": True},
    "magShape":  {"key": "magShape", "kind": "enum", "in_geom": True,
                  "options": [{"value": "v"}, {"value": "spm"}, {"value": "delta"}]},
    "axialLen":  {"key": "axialLen", "kind": "num", "in_geom": False,
                  "lo": 30, "hi": 300, "def": 80, "int": False},
    "load_nm":   {"key": "load_nm", "kind": "num", "in_geom": False,
                  "lo": 0, "hi": 2000, "def": 5, "int": False},
    # Feinparameter (adv) — seit der Schemaerweiterung gepruefte Schluessel
    "poleArcFrac":     {"key": "poleArcFrac", "kind": "num", "in_geom": True, "adv": True,
                        "lo": 0.5, "hi": 0.98, "def": 0.83, "int": False},
    "genFluxBarrierQ": {"key": "genFluxBarrierQ", "kind": "bool", "in_geom": True,
                        "adv": True, "def": False},
    "magOrient":       {"key": "magOrient", "kind": "enum", "in_geom": True, "adv": True,
                        "options": [{"value": "transverse"}, {"value": "longitudinal"}]},
}


def _payload():
    return {"project_name": "Basis", "axial_len": 120, "load_nm": 5,
            "vehicle": {"mass_kg": 1600},
            "geom": {"slotDepth": 25, "p": 3, "magShape": "delta",
                     "axialLen": 120, "magLayers": 3}}


def _apply(sets, force=False):
    pl = _payload()
    applied, errors = cae_cli.apply_sets(pl, sets, url="<ungenutzt>", force=force)
    return pl, applied, errors


def _stub_schema():
    cae_cli._SCHEMA_CACHE = dict(SCHEMA)      # param_schema() fragt dann nicht


def test_placement():
    """Schemaparameter landen laut ``in_geom``, alles Übrige dort, wo es schon liegt."""
    _stub_schema()
    pl, applied, errors = _apply(["slotDepth=30", "load_nm=250",
                                  "magLayers=2", "vehicle.mass_kg=1750"])
    assert not errors, errors
    assert pl["geom"]["slotDepth"] == 30            # in_geom
    assert pl["load_nm"] == 250                     # obere Ebene
    assert "slotDepth" not in pl and "load_nm" not in pl["geom"]
    assert pl["geom"]["magLayers"] == 2             # nur im Payload, nicht im Schema
    assert pl["vehicle"]["mass_kg"] == 1750         # Punktpfad
    assert [a["geprueft"] for a in applied] == [True, True, False, False]
    print("✓ placement: in_geom / obere Ebene / Payload-Fund / Punktpfad")


def test_types_and_bounds():
    """Grenzen weisen ab, statt zu klemmen — und ALLE Fehler kommen auf einmal."""
    _stub_schema()
    pl, applied, errors = _apply(["slotDepth=999", "p=8.5", "magShape=banane",
                                  "slotDepth=abc"])
    assert len(errors) == 4, errors
    assert "Obergrenze 60" in errors[0]
    assert "ganze Zahl" in errors[1]
    assert "banane" in errors[2] and "spm" in errors[2]
    assert "Zahl erwartet" in errors[3]
    assert not applied and pl["geom"]["slotDepth"] == 25, "nichts darf gesetzt sein"
    # untere Grenze und der gültige Randfall
    _, _, e_lo = _apply(["slotDepth=4.9"]);  assert "Untergrenze 5" in e_lo[0]
    _, ok, e_ok = _apply(["slotDepth=5", "p=40"]); assert not e_ok and len(ok) == 2
    print("✓ types_and_bounds: Grenzen/Typen weisen ab, Ränder gelten, Sammelmeldung")


def test_force_bypasses_checks():
    _stub_schema()
    pl, applied, errors = _apply(["slotDepth=999"], force=True)
    assert not errors and pl["geom"]["slotDepth"] == 999
    print("✓ force: --force hebt die Prüfung auf")


def test_typo_is_refused_with_suggestion():
    """Der eigentliche Zweck: ein erfundener Name darf NICHT im Payload landen."""
    _stub_schema()
    pl, applied, errors = _apply(["slotDepht=30", "quatsch=1", "p"])
    assert not applied and "slotDepht" not in pl["geom"] and "quatsch" not in pl
    assert "slotDepth" in errors[0], errors[0]      # Vorschlag
    assert "quatsch" in errors[1]
    assert "KEY=WERT" in errors[2]
    print("✓ typo: unbekannter Name wird abgewiesen, naher Treffer vorgeschlagen")


def test_axiallen_alias_and_mirror():
    """``axialLen`` heißt im Payload ``axial_len`` — sonst landet der Wert im Nichts."""
    _stub_schema()
    pl, applied, errors = _apply(["axialLen=150"])
    assert not errors, errors
    assert pl["axial_len"] == 150, "die Pipeline liest data['axial_len']"
    assert pl["geom"]["axialLen"] == 150, "der Spiegel muss mitgehen"
    assert "axialLen" not in pl, "kein toter Schlüssel auf der oberen Ebene"
    assert applied[0]["geprueft"] and "axial_len" in applied[0]["notiz"]
    # geprüft wird trotzdem gegen die Schemazeile von axialLen
    _, _, err = _apply(["axialLen=999"])
    assert "axialLen" in err[0] and "300" in err[0], err
    print("✓ alias: axialLen -> axial_len (+ Spiegel in geom), Grenzen greifen weiter")


def test_dotted_path_is_still_checked():
    """Der Punktpfad ist ein Umweg fuer die Ablage, kein Umweg um die Pruefung."""
    _stub_schema()
    pl, applied, errors = _apply(["geom.slotDepth=999"])
    assert errors and "Obergrenze 60" in errors[0], errors
    assert pl["geom"]["slotDepth"] == 25
    pl, applied, errors = _apply(["geom.slotDepth=30"])
    assert not errors and pl["geom"]["slotDepth"] == 30 and applied[0]["geprueft"]
    print("✓ punktpfad: umgeht die Ablage, nicht die Schemapruefung")


def test_value_parsing():
    _stub_schema()
    pl, _, errors = _apply(["magShape=v", "project_name=Test_1",
                            "vehicle.mass_kg=1750.5"])
    assert not errors, errors
    assert pl["geom"]["magShape"] == "v"            # nackter Text bleibt Text
    assert pl["project_name"] == "Test_1"
    assert pl["vehicle"]["mass_kg"] == 1750.5       # JSON-Zahl bleibt Zahl
    print("✓ parsing: JSON zuerst, sonst Text")


def test_run_routes_have_status_paths():
    """Jede Stufe braucht IHRE Statusroute — ``/status`` meldet nur die Pipeline."""
    for stage, entry in cae_cli.RUN_ROUTES.items():
        assert isinstance(entry, tuple) and len(entry) == 2, (stage, entry)
        start, status = entry
        assert start.startswith("/") and status.startswith("/"), (stage, entry)
    assert cae_cli.RUN_ROUTES["cad"][1] == "/cad_preview/status"
    assert cae_cli.RUN_ROUTES["analyse"][1] == "/status"
    print("✓ run_routes: Start- und Statusroute je Stufe getrennt gefuehrt")


def test_rotor_check_verb_is_registered():
    """Das zehnte Verb muss im Parser stehen — und die Doku muss es kennen.

    ``rotor-check`` kam nach der Doku in den Baum: README, SKILL.md und dieser Test
    kannten es nicht. Ein Verb, das nur ``--help`` kennt, existiert fuer den Agenten
    nicht, denn der liest die Skill-Datei, nicht die Hilfe."""
    parser = cae_cli.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and isinstance(a.choices, dict)]
    assert sub, "kein Unterbefehls-Parser gefunden"
    verbs = set(sub[0].choices)
    assert "rotor-check" in verbs, sorted(verbs)
    assert callable(getattr(cae_cli, "cmd_rotor_check", None)), "cmd_rotor_check fehlt"
    # Die Skill-Datei ist die einzige Quelle, aus der das lokale Modell Verben lernt.
    skill = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                         ".agents", "skills", "cae-orchestrator", "SKILL.md")
    if os.path.exists(skill):
        with open(skill, encoding="utf-8") as f:
            assert "rotor-check" in f.read(), \
                "SKILL.md kennt rotor-check nicht — der Agent sieht das Verb nicht"
    print(f"✓ rotor-check: im Parser registriert ({len(verbs)} Verben) und dokumentiert")


def test_rotor_check_runs_without_server():
    """Ohne ``--set`` darf ``rotor-check`` das Schema NICHT abrufen.

    ``apply_sets`` holt ``/param_schema`` nur, wenn es etwas zu pruefen gibt. Genau
    darauf beruht die Zusage 'laeuft ohne CAD und ohne Server' — sie waere still
    falsch, wenn der Pfad doch HTTP anfasst."""
    from ema_rotorcheck import rotor_layout_check

    def _explodiere(*a, **k):
        raise AssertionError("param_schema() darf hier nicht gerufen werden")

    alt = cae_cli.param_schema
    cae_cli.param_schema = _explodiere
    try:
        pl = _payload()
        applied, errors = cae_cli.apply_sets(pl, [], url="<ungenutzt>")
        assert applied == [] and errors == [], (applied, errors)
    finally:
        cae_cli.param_schema = alt

    # Und der Check selbst rechnet rein lokal.
    geom = {"statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60,
            "slots": 36, "p": 3, "magShape": "delta", "magAngle": 94,
            "magAngle2": 94, "magDepthRel": 0.3, "magWidth": 37, "magThick": 6,
            "magDist": 13.5, "magLayers": 3, "magLayerGap": 13.5,
            "poleArcFrac": 0.83, "magGapMm": 0.1, "airGap": 0.7}
    chk = rotor_layout_check(geom)
    assert set(("ok", "fatal", "layout")) <= set(chk), sorted(chk)
    assert chk["ok"] is True, chk["fatal"]
    # Exit-Code-Vertrag: 0 = OK, 1 = abgelehnt.
    kaputt = rotor_layout_check(dict(geom, magLayerGap=0.0, magDist=0.0))
    assert kaputt["ok"] is False and kaputt["fatal"]
    print("✓ rotor-check: lokal, ohne HTTP, Ablehnung begruendet")


def test_adv_params():
    """Feinparameter werden wie jeder andere Schemaschluessel gepflegt.

    Der Punkt der Erweiterung: ``poleArcFrac`` stand in keinem Payload und fiel als
    Tippfehler durch; ``magLayers`` stand zufaellig drin und ging UNGEPRUEFT durch —
    beides falsch. Jetzt entscheidet das Schema, nicht der Zufall."""
    _stub_schema()
    pl, applied, errors = _apply(["poleArcFrac=0.9", "genFluxBarrierQ=true",
                                  "magOrient=longitudinal"])
    assert not errors, errors
    assert pl["geom"]["poleArcFrac"] == 0.9
    assert pl["geom"]["genFluxBarrierQ"] is True            # echtes Bool, keine "true"
    assert pl["geom"]["magOrient"] == "longitudinal"
    # ein Schluessel, den es vorher im Payload gar nicht gab, wird angelegt statt abgewiesen
    assert "poleArcFrac" not in _payload()["geom"]

    _, _, errors = _apply(["poleArcFrac=1.5"])
    assert errors and "Obergrenze" in errors[0], errors
    _, _, errors = _apply(["magOrient=quer"])
    assert errors and "transverse" in errors[0], errors
    print("✓ adv: Feinparameter gepflegt, Grenzen und Auswahllisten greifen")


def test_bool_kind_is_strict():
    """``genFluxBarrierQ=1`` wird abgewiesen — absichtlich.

    Die Pipeline liest den Schalter mit ``bool(...)``, und dort ist jede nichtleere
    Zeichenkette wahr. Waere 1/"ja"/"an" erlaubt, wirkte ein Tippfehler still."""
    _stub_schema()
    for schlecht in ["genFluxBarrierQ=1", "genFluxBarrierQ=0", "genFluxBarrierQ=ja"]:
        _, _, errors = _apply([schlecht])
        assert errors and "true oder false" in errors[0], (schlecht, errors)
    for gut, soll in [("genFluxBarrierQ=true", True), ("genFluxBarrierQ=false", False)]:
        pl, _, errors = _apply([gut])
        assert not errors, errors
        assert pl["geom"]["genFluxBarrierQ"] is soll
    print("✓ bool: nur true/false, kein 1/0/ja — sonst wirkt ein Tippfehler still")


def test_schema_has_no_second_geom_table():
    """``in_geom`` kommt aus dem Schema selbst, nicht aus einer Liste in server.py.

    Solange beide Seiten dieselbe Menge fuehrten, konnte ein neuer Schluessel im Schema
    bekannt und beim Payload-Bau unbekannt sein — der Wert landete dann still eine
    Ebene zu hoch. Prueft die Quelle, nicht die Route (laeuft ohne Server)."""
    import ema_text2ema as T2E
    alt = {"statorOD", "statorID", "rotorOD", "shaftD", "shaftBoreD", "slots",
           "slotDepth", "p", "magShape", "magAngle", "magDepthRel", "magWidth",
           "magThick", "magDist", "nAx", "nCirc"}
    basis = {k for k, v in T2E.SCHEMA.items() if v.get("geom") and not v.get("adv")}
    assert basis == alt, f"Basis-geom hat sich verschoben: {basis ^ alt}"
    assert all("geom" in v for v in T2E.SCHEMA.values() if v.get("adv")), \
        "jeder Feinparameter braucht eine ausdrueckliche Ebene"
    # Text->Auslegung darf von der Erweiterung nichts merken
    assert len(T2E._validate({})) == len(alt) + 10, "adv darf nicht in den Entwurf sickern"
    print(f"✓ ebenen: in_geom aus EINER Quelle, {sum(1 for v in T2E.SCHEMA.values() if v.get('adv'))} "
          f"Feinparameter halten Text->Auslegung heraus")


def test_schema_vs_payload():
    """Gegen den laufenden Server: jeder Schemaschlüssel muss im Payload ankommen.

    Das ist der Test, der die _ALIAS-Tabelle ehrlich hält — driftet ``/param_schema``
    gegen das Payload-Vokabular, schlägt er an, statt dass Werte still verschwinden."""
    cae_cli._SCHEMA_CACHE = None          # sonst gewinnt das Stub-Schema der Tests davor
    try:
        schema = cae_cli.param_schema(cae_cli.DEFAULT_URL)
    except SystemExit:
        print("– schema_vs_payload: uebersprungen (kein Server auf :5000)")
        return
    except Exception:
        print("– schema_vs_payload: uebersprungen (kein Server auf :5000)")
        return
    root = cae_cli.PROJECTS_ROOT
    metas = [os.path.join(root, d, "meta.json") for d in os.listdir(root)
             if os.path.exists(os.path.join(root, d, "meta.json"))]
    if not metas:
        print("– schema_vs_payload: uebersprungen (kein Projekt mit meta.json)")
        return
    with open(max(metas, key=os.path.getmtime), encoding="utf-8") as f:
        pl = json.load(f)["payload"]
    fehlend = []
    for key, spec in schema.items():
        name = cae_cli._ALIAS.get(key, key)
        where = pl.get("geom", {}) if (spec.get("in_geom") and name == key) else pl
        if name not in where:
            fehlend.append(f"{key} -> erwartet in {'geom' if where is not pl else 'payload'}")
    assert not fehlend, ("Schema und Payload driften: " + "; ".join(fehlend)
                         + " — _ALIAS in cae_cli.py nachziehen")
    print(f"✓ schema_vs_payload: alle {len(schema)} Schemaschluessel im Payload gefunden")


if __name__ == "__main__":
    test_placement()
    test_types_and_bounds()
    test_force_bypasses_checks()
    test_typo_is_refused_with_suggestion()
    test_axiallen_alias_and_mirror()
    test_dotted_path_is_still_checked()
    test_value_parsing()
    test_run_routes_have_status_paths()
    test_rotor_check_verb_is_registered()
    test_rotor_check_runs_without_server()
    test_adv_params()
    test_bool_kind_is_strict()
    test_schema_has_no_second_geom_table()
    test_schema_vs_payload()
    print("\nALLE CAE-CLI-TESTS BESTANDEN ✅")
