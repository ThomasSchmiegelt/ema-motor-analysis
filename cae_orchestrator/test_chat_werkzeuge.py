"""Tests fuer den erweiterten Chat und die Aehnlichkeitssuche.

Ohne Server, ohne Ollama, ohne Netz — das Sprachmodell wird gestellt. Geprueft
wird genau das, was NICHT vom Modell abhaengt:

  * der Verlauf liegt anhaengend im Projekt und ueberlebt,
  * die Werkzeugschleife erkennt einen Aufruf, fuehrt ihn aus und reicht das
    Ergebnis zurueck — und laesst eine Antwort in Ruhe, die den Aufruf bloss
    ERWAEHNT,
  * ein gescheitertes Werkzeug ist ein Ergebnis und keine Ausnahme,
  * die Deckungspruefung findet die erfundene Zahl und meldet KEINE
    Projektkennung,
  * die Aehnlichkeit ist massstabsunabhaengig und traegt ihre Begruendung.

Lauf: ``python test_chat_werkzeuge.py``
"""

import json
import os
import tempfile

import ema_chat as C
import ema_projekt as PJ


# ── Verlauf im Projekt ───────────────────────────────────────────────────────
def test_verlauf_ist_anhaengend_und_ueberlebt():
    with tempfile.TemporaryDirectory() as d:
        PJ.init(d, "p")
        assert C.verlauf_lesen(d) == []
        C.verlauf_anhaengen(d, "chat", "user", "Wie hoch ist B_gap?")
        C.verlauf_anhaengen(d, "chat", "assistant", "0,63 T [analytisch]",
                            werkzeuge=[], ungedeckt=[])
        C.verlauf_anhaengen(d, "fertigung", "user", "Welche Stegbreite?")
        z = C.verlauf_lesen(d, "chat")
        assert [x["role"] for x in z] == ["user", "assistant"]
        assert z[1]["content"].startswith("0,63")
        # Zwei Fragestraenge stehen nebeneinander — eine Datei je Gespraech.
        g = C.gespraeche(d)
        assert {x["kennung"] for x in g} == {"chat", "fertigung"}
        assert next(x for x in g if x["kennung"] == "chat")["zuege"] == 2
    print("✓ Verlauf: anhaengend, je Gespraech eine Datei, ueberlebt den Prozess")


def test_verlauf_weist_pfade_ab():
    with tempfile.TemporaryDirectory() as d:
        PJ.init(d, "p")
        C.verlauf_anhaengen(d, "../../entkommen", "user", "x")
        # Die Kennung wird entschaerft, nicht befolgt.
        assert not os.path.exists(os.path.join(d, "..", "..", "entkommen.jsonl"))
        assert os.listdir(os.path.join(d, C.GESPRAECHE))
    print("✓ eine Kennung aus der URL kann nicht aus dem Projekt herausfuehren")


# ── Werkzeugschleife ─────────────────────────────────────────────────────────
class _Modell:
    """Ein gestelltes Sprachmodell: gibt der Reihe nach feste Antworten."""

    def __init__(self, antworten):
        self.antworten = list(antworten)
        self.gesehen = []

    def __call__(self, msgs, model=None, timeout=300):
        self.gesehen.append(msgs)
        return self.antworten.pop(0) if self.antworten else "(leer)"


def _mit_modell(antworten, fn):
    alt = C._ollama_chat
    m = _Modell(antworten)
    C._ollama_chat = m
    try:
        return fn(), m
    finally:
        C._ollama_chat = alt


def test_werkzeugaufruf_wird_ausgefuehrt_und_zurueckgereicht():
    with tempfile.TemporaryDirectory() as d:
        PJ.init(d, "p")
        alt = C.werkzeug_ausfuehren
        C.werkzeug_ausfuehren = lambda n, a, p: {"ok": True,
                                                 "text": f"[{n}:{a.strip()}]"}
        try:
            (erg, _), m = _mit_modell(
                ["WERKZEUG: suche Ferrit Remanenz", "Ferrit hat rund 0,4 T."],
                lambda: C._werkzeugschleife("SYS", [], "Wie stark ist Ferrit?",
                                            d, "modell"))
        finally:
            C.werkzeug_ausfuehren = alt
        assert erg == "Ferrit hat rund 0,4 T."
        # Das Ergebnis ist wirklich in die zweite Aufforderung gewandert.
        zweite = m.gesehen[1]
        assert any("[suche:Ferrit Remanenz]" in x["content"] for x in zweite)
        assert any("FREMDTEXT" in x["content"] for x in zweite)
    print("✓ Werkzeugaufruf erkannt, ausgefuehrt, Ergebnis zurueckgereicht")


def test_erwaehnter_aufruf_loest_NICHTS_aus():
    """Ein Modell, das seinen eigenen Aufruf bloss erklaert, sucht nicht."""
    with tempfile.TemporaryDirectory() as d:
        PJ.init(d, "p")
        gerufen = []
        alt = C.werkzeug_ausfuehren
        C.werkzeug_ausfuehren = lambda n, a, p: (gerufen.append(n) or
                                                 {"ok": True, "text": "x"})
        try:
            text = ("Du koenntest WERKZEUG: suche Ferrit benutzen, wenn du "
                    "eine Quelle brauchst. Ich habe die Zahl aber schon: "
                    "B_gap ist 0,63 T, und das steht im Steckbrief.")
            (erg, benutzt), _ = _mit_modell(
                [text], lambda: C._werkzeugschleife("SYS", [], "?", d, "m"))
        finally:
            C.werkzeug_ausfuehren = alt
        assert erg == text and benutzt == [] and gerufen == []
    print("✓ ein bloss ERWAEHNTER Aufruf loest kein Werkzeug aus")


def test_gescheitertes_werkzeug_ist_ein_ergebnis():
    with tempfile.TemporaryDirectory() as d:
        PJ.init(d, "p")
        alt = C.werkzeug_ausfuehren
        C.werkzeug_ausfuehren = lambda n, a, p: {"ok": False,
                                                 "text": "Nicht erreichbar."}
        try:
            (erg, benutzt), m = _mit_modell(
                ["WERKZEUG: hole https://kaputt.example", "Die Seite ging nicht."],
                lambda: C._werkzeugschleife("SYS", [], "?", d, "m"))
        finally:
            C.werkzeug_ausfuehren = alt
        assert benutzt and benutzt[0]["ok"] is False
        # Das Modell ERFAEHRT den Fehlschlag, statt in eine leere Antwort zu laufen.
        assert any("Nicht erreichbar." in x["content"] for x in m.gesehen[1])
    print("✓ ein gescheitertes Werkzeug wird gemeldet, nicht verschwiegen")


def test_schleife_endet_und_erzwingt_eine_antwort():
    """Ein Modell, das nur noch Werkzeuge ruft, haelt den Chat nicht auf."""
    with tempfile.TemporaryDirectory() as d:
        PJ.init(d, "p")
        alt = C.werkzeug_ausfuehren
        C.werkzeug_ausfuehren = lambda n, a, p: {"ok": True, "text": "x"}
        try:
            # Gibt das Modell nach der Aufforderung endlich eine Antwort, steht sie da.
            (erg, benutzt), _ = _mit_modell(
                ["WERKZEUG: suche a", "WERKZEUG: suche b", "Jetzt die Antwort."],
                lambda: C._werkzeugschleife("SYS", [], "?", d, "m", max_runden=2))
            assert erg == "Jetzt die Antwort." and len(benutzt) == 2

            # Und wenn nicht: die rohe Protokollzeile hinzustellen waere das
            # Schlechteste von beidem — sie sagt dem Menschen nichts und sieht
            # aus wie ein Fehler. Ein oertliches Modell ist im Werkzeugaufruf
            # unzuverlaessig; dann wird das GESAGT.
            (erg2, benutzt2), _ = _mit_modell(
                ["WERKZEUG: suche a", "WERKZEUG: suche b", "WERKZEUG: suche c"],
                lambda: C._werkzeugschleife("SYS", [], "?", d, "m", max_runden=2))
        finally:
            C.werkzeug_ausfuehren = alt
        assert not erg2.lstrip().startswith("WERKZEUG:"), erg2
        assert "komme hier nicht weiter" in erg2 and "nachpruefen lassen" in erg2
        assert benutzt2[-1]["ok"] is False
    print("✓ die Schleife endet nach max_runden — und sagt es, statt Protokoll zu zeigen")


def test_unbekanntes_werkzeug_wird_benannt():
    r = C.werkzeug_ausfuehren("zaubern", "", None)
    assert r["ok"] is False and "zaubern" in r["text"]
    print("✓ ein unbekanntes Werkzeug wird benannt statt still uebergangen")


# ── Deckungspruefung ─────────────────────────────────────────────────────────
def test_deckung_findet_die_erfundene_zahl():
    material = "B_gap_T 0.6301  Kt_Nm_per_A 0.0362  max_safe_rpm 16000"
    ug = C.deckung_pruefen(
        "B_gap ist 0,63 T, Kt 0,036 Nm/A — und der Wirkungsgrad 97,4 %.",
        material)
    # Runden ist gedeckt, erfinden nicht.
    assert ug == ["97,4"], ug
    print("✓ Deckung: gerundete Zahlen gelten, erfundene werden gemeldet")


def test_deckung_meldet_keine_projektkennung():
    """Gemessen an der ersten Antwort, die `aehnlich` benutzt hat."""
    ug = C.deckung_pruefen(
        "Aehnlich sind 20260908_103936 und 20260912_190801.", "nichts davon")
    assert ug == [], ug
    # Die echte Falschaussage faellt trotzdem durch.
    assert C.deckung_pruefen("In 20260908_103936 sind es 4,2 Nm.", "x") == ["4,2"]
    print("✓ Deckung: Projektkennungen sind keine Behauptung ueber die Maschine")


# ── Aehnlichkeit ─────────────────────────────────────────────────────────────
def _projekt(wurzel, pid, payload, metrics=None):
    d = os.path.join(wurzel, pid)
    os.makedirs(d, exist_ok=True)
    PJ.init(d, pid)
    PJ.update(d, inputs={"payload": payload}, metrics=metrics or {})
    return d


_BASIS = {"cooling": "water", "magnet": "ndfeb_n35", "rotor_lam": "m270_35a",
          "axial_len": 100.0,
          "geom": {"machineType": "pmsm", "magShape": "v", "p": 3, "slots": 36,
                   "statorOD": 280.0, "statorID": 170.0, "rotorOD": 168.6,
                   "shaftD": 60.0, "magWidth": 25.0, "magThick": 5.0,
                   "slotDepth": 25.0, "magDepthRel": 0.6}}


def _skaliert(f):
    """Dieselbe Maschine, Faktor f groesser — alle LAENGEN, nichts sonst."""
    p = json.loads(json.dumps(_BASIS))
    for k in ("statorOD", "statorID", "rotorOD", "shaftD", "magWidth",
              "magThick", "slotDepth"):
        p["geom"][k] *= f
    p["axial_len"] *= f
    return p


def test_aehnlichkeit_ist_massstabsunabhaengig():
    """Eine 75-mm- und eine 300-mm-Maschine koennen dieselbe Auslegung sein."""
    with tempfile.TemporaryDirectory() as w:
        mein = _projekt(w, "20260101_000000_basis", _BASIS)
        _projekt(w, "20260101_000001_gross", _skaliert(2.5))
        anders = json.loads(json.dumps(_BASIS))
        anders["geom"].update({"magShape": "spoke", "p": 8, "slots": 12})
        anders["cooling"] = "natural"
        _projekt(w, "20260101_000002_anders", anders)

        tr = {e["id"]: e for e in PJ.aehnlich(mein, n=5, wurzel=w)}
        assert len(tr) == 2
        gross, fremd = tr["20260101_000001_gross"], tr["20260101_000002_anders"]
        assert gross["aehnlichkeit"] > fremd["aehnlichkeit"] + 0.2, (gross, fremd)
        # Und die Begruendung gehoert zum Treffer.
        assert any("Magnetanordnung" in g for g in gross["gleich"])
        assert any("Magnetanordnung" in a for a in fremd["anders"])
        assert any("Kuehlung" in a for a in fremd["anders"])
    print("✓ Aehnlichkeit: massstabsunabhaengig, mit Begruendung je Treffer")


def test_dublette_ist_keine_aehnlichkeit_sondern_identitaet():
    with tempfile.TemporaryDirectory() as w:
        mein = _projekt(w, "20260101_000000_a", _BASIS)
        _projekt(w, "20260101_000001_b", json.loads(json.dumps(_BASIS)))
        _projekt(w, "20260101_000002_c", _skaliert(1.4))
        tr = PJ.aehnlich(mein, n=5, wurzel=w)
        assert tr[0]["id"] == "20260101_000001_b" and tr[0]["dublette"] is True
        assert tr[1]["dublette"] is False
    print("✓ eine Dublette steht oben und heisst so — das ist eine andere Auskunft")


def test_ablagen_und_das_eigene_projekt_bleiben_draussen():
    with tempfile.TemporaryDirectory() as w:
        mein = _projekt(w, "20260101_000000_a", _BASIS)
        _projekt(w, "_papierkorb", _BASIS)      # fuehrender _ = Ablage
        _projekt(w, "20260101_000009_b", _BASIS)
        ids = [e["id"] for e in PJ.aehnlich(mein, n=9, wurzel=w)]
        assert ids == ["20260101_000009_b"], ids
    print("✓ Ablagen (fuehrender _) und das eigene Projekt zaehlen nicht mit")


def test_ohne_payload_keine_behauptung():
    with tempfile.TemporaryDirectory() as w:
        leer = os.path.join(w, "20260101_000000_leer")
        os.makedirs(leer)
        PJ.init(leer, "leer")
        assert PJ.aehnlich(leer, n=5, wurzel=w) == []
    print("✓ ohne Payload wird nichts behauptet — leere Liste statt Rauschen")


def main():
    test_verlauf_ist_anhaengend_und_ueberlebt()
    test_verlauf_weist_pfade_ab()
    test_werkzeugaufruf_wird_ausgefuehrt_und_zurueckgereicht()
    test_erwaehnter_aufruf_loest_NICHTS_aus()
    test_gescheitertes_werkzeug_ist_ein_ergebnis()
    test_schleife_endet_und_erzwingt_eine_antwort()
    test_unbekanntes_werkzeug_wird_benannt()
    test_deckung_findet_die_erfundene_zahl()
    test_deckung_meldet_keine_projektkennung()
    test_aehnlichkeit_ist_massstabsunabhaengig()
    test_dublette_ist_keine_aehnlichkeit_sondern_identitaet()
    test_ablagen_und_das_eigene_projekt_bleiben_draussen()
    test_ohne_payload_keine_behauptung()
    print("\nALLE CHAT-/AEHNLICHKEITS-TESTS BESTANDEN ✅")


if __name__ == "__main__":
    main()
