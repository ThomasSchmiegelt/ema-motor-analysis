"""Die Bruecke zwischen Agentenkopf und Geometrie-Reiter -- ohne Server.

Was hier still falsch sein koennte und deshalb geprueft wird:

* **Die Marke muss sehen, was ein Agent wirklich aendert.** Der naheliegende Weg
  (``_flatten_payload``) ist fuer die ANZEIGE eines Unterschieds gebaut und
  steigt nur in ``geom`` ab -- eine uebernommene Getriebeauslegung
  (``vehicle.getriebe``) oder eine gezeichnete Geometrie (``customLegs``) faellt
  dort heraus, und die Bruecke haette geschwiegen.
* **Sie darf NICHT auf jedes Schreiben anschlagen.** Eine neue Notiz, ein
  Zeitstempel, eine andere Schluesselreihenfolge sind keine Auslegung. Wer
  darauf anschlaegt, ueberschreibt ein Formular, in dem sich nichts geaendert
  hat -- und das ist schlimmer als gar keine Bruecke.
* **Das Formular des Menschen hat Vorrang.** Automatisch uebernommen wird nur,
  solange niemand selbst getippt hat.

Aufruf: ``venv/bin/python test_bruecke.py``
"""

import copy
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_projekt as PJ

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


GRUND = {"geom": {"statorOD": 280.0, "statorID": 190.0, "p": 3, "slots": 36},
         "load_nm": 100.0, "rpm_to": 12000,
         "vehicle": {"mass_kg": 1600, "gear_ratio": 9.5}}


print("1. Die Marke sieht, was ein Agent aendert")
m0 = PJ.payload_marke(GRUND)
faelle = [
    ("geom.statorOD", lambda p: p["geom"].__setitem__("statorOD", 281.0), True),
    ("geom.p", lambda p: p["geom"].__setitem__("p", 4), True),
    ("load_nm", lambda p: p.__setitem__("load_nm", 120.0), True),
    # Der Fall, an dem der naheliegende Weg scheitert: ``vehicle`` ist ein Dict,
    # und ``_flatten_payload`` steigt nur in ``geom`` ab.
    ("vehicle.gear_ratio", lambda p: p["vehicle"].__setitem__("gear_ratio", 9.5168), True),
    ("vehicle.getriebe", lambda p: p["vehicle"].__setitem__("getriebe", {"i_ist": 9.5}), True),
    # Ebenso: eine gezeichnete Geometrie steht in einer LISTE.
    ("customLegs", lambda p: p["geom"].__setitem__("customLegs", [{"r": 1}]), True),
]
for name, aendern, soll in faelle:
    p = copy.deepcopy(GRUND)
    aendern(p)
    bewegt = PJ.payload_marke(p) != m0
    pruefe(bewegt is soll,
           f"{name} bewegt die Marke" if soll else f"{name} bewegt sie nicht")

print("\n2. Und sie schlaegt NICHT auf alles an")
p = copy.deepcopy(GRUND)
p["cycle_csv"] = "t,v\n" + "\n".join(f"{i},{i}" for i in range(2000))
pruefe(PJ.payload_marke(p) == m0,
       "ein angehaengter Fahrzyklus (hunderte Zeilen Messdaten) ist keine "
       "Auslegung — die Marke bleibt")
p2 = {"vehicle": {"gear_ratio": 9.5, "mass_kg": 1600}, "rpm_to": 12000,
      "load_nm": 100.0, "geom": {"slots": 36, "p": 3, "statorID": 190.0,
                                 "statorOD": 280.0}}
pruefe(PJ.payload_marke(p2) == m0,
       "eine andere Reihenfolge derselben Schluessel auch nicht — sonst meldete "
       "jedes Neuschreiben von meta.json eine Aenderung")
pruefe(PJ.payload_marke({}) == PJ.payload_marke(None),
       "leer und fehlend sind dasselbe")
pruefe(len(m0) == 12 and re.fullmatch(r"[0-9a-f]{12}", m0),
       f"die Marke ist kurz und vergleichbar ({m0})")

print("\n3. Der Stand eines Projekts — billig und ohne zu rechnen")
with tempfile.TemporaryDirectory() as tmp:
    pdir = os.path.join(tmp, "20260101_000000_bruecke")
    os.makedirs(pdir)
    PJ.init(pdir, "20260101_000000_bruecke", origin="manual")
    with open(os.path.join(pdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"payload": GRUND}, f)
    PJ.update(pdir, inputs={"payload": GRUND})
    st = PJ.stand(pdir)
    pruefe(st["ok"] and st["payload_marke"] == m0,
           "der Stand traegt dieselbe Marke wie der Payload")
    # Gemessen und beinahe uebersehen: die Marke muss aus **meta.json** kommen.
    # `/agent/vorgabe` und `getriebe --uebernehmen` schreiben NUR dorthin —
    # `inputs.payload` in der Akte fuehrt allein `record_run` fort. Aus der Akte
    # gelesen waere die Bruecke fuer genau die Uebergaben blind, fuer die es sie
    # gibt.
    nur_meta = copy.deepcopy(GRUND)
    nur_meta["geom"]["statorOD"] = 999.0
    with open(os.path.join(pdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"payload": nur_meta}, f)
    pruefe(PJ.stand(pdir)["payload_marke"] != m0,
           "ein Schreibvorgang, der NUR meta.json anfasst, bewegt die Marke — "
           "genau so uebergeben Designer und Getriebeauslegung")
    with open(os.path.join(pdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"payload": GRUND}, f)
    pruefe(st["n_evolution"] == 0 and st["letzte"] is None,
           "ein frisches Projekt hat keine Stufe — und meldet das als 'keine', "
           "nicht als leere")

    # Jetzt aendert „der Agent" etwas — genau so, wie es cae_cli tut.
    neu = copy.deepcopy(GRUND)
    neu["geom"]["statorOD"] = 300.0
    neu["vehicle"]["gear_ratio"] = 4.2
    with open(os.path.join(pdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"payload": neu}, f)
    PJ.record_run(pdir, "20260101_000000_bruecke", {"payload": neu}, {},
                  action="cli:run", note="Agentenlauf")
    st2 = PJ.stand(pdir)
    pruefe(st2["payload_marke"] != st["payload_marke"],
           f"nach der Aenderung ist die Marke eine andere "
           f"({st['payload_marke']} -> {st2['payload_marke']}) — genau daran "
           f"erkennt der Reiter, dass er nachziehen muss")
    pruefe(st2["n_evolution"] == 1 and st2["letzte"]["action"] == "cli:run",
           "und die Stufe steht mit ihrem Anlass da")
    pruefe("geom.statorOD" in (st2["letzte"]["geaendert"] or []),
           f"der Befund nennt die geaenderten Felder: "
           f"{st2['letzte']['geaendert']}")

    # Eine reine NOTIZ darf die Bruecke nicht ausloesen.
    PJ.append_evolution(pdir, {"action": "notiz", "note": "nur ein Gedanke"})
    st3 = PJ.stand(pdir)
    pruefe(st3["payload_marke"] == st2["payload_marke"],
           "eine Notiz bewegt die Marke NICHT — sonst ueberschriebe die Bruecke "
           "ein Formular, weil jemand etwas aufgeschrieben hat")
    pruefe(st3["n_evolution"] == 2,
           "sie steht trotzdem in der Akte")

print("\n4. Abzweige und der Weg zurueck")
with tempfile.TemporaryDirectory() as tmp:
    pdir = os.path.join(tmp, "20260101_000000_zweig")
    os.makedirs(pdir)
    PJ.init(pdir, "20260101_000000_zweig", origin="manual")

    def stand_setzen(payload, action="cli:run"):
        with open(os.path.join(pdir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({"payload": payload}, f)
        PJ.record_run(pdir, "20260101_000000_zweig", {"payload": payload}, {},
                      action=action)

    a = copy.deepcopy(GRUND)                      # Stand A — der Knotenpunkt
    stand_setzen(a, "analyse")
    pruefe(len(PJ.knoten_liste(pdir)) == 1,
           "jeder gerechnete Lauf legt von selbst einen Rueckkehrpunkt an — "
           "sonst waere ausgerechnet der Stand, dessen Kennwerte man "
           "vergleicht, nicht wiederherstellbar")
    gesetzt = PJ.knoten_setzen(pdir, label="vor dem Versuch mit 8 Polen",
                               payload=a)
    pruefe(gesetzt["ok"], "und von Hand laesst sich einer setzen")
    knoten_a = gesetzt["marke"]

    # Dem Abzweig folgen: zwei Schritte, die sich als Sackgasse erweisen.
    b = copy.deepcopy(a); b["geom"]["p"] = 4; b["geom"]["slots"] = 48
    stand_setzen(b)
    c = copy.deepcopy(b); c["geom"]["statorOD"] = 340.0; c["load_nm"] = 210.0
    stand_setzen(c)
    pruefe(PJ.stand(pdir)["n_evolution"] == 3,
           "drei Stufen liegen in der Akte")
    # DAS ist der Punkt: aus der Akte allein liesse sich A nicht zurueckholen.
    ev = (PJ._read(pdir) or {}).get("evolution") or []
    pruefe(all("payload" not in e for e in ev),
           "keine Stufe traegt den vollen Payload — genau deshalb braucht es "
           "die Schnappschuesse")

    zur = PJ.zurueck(pdir, knoten_a)
    pruefe(zur["ok"], f"zurueck auf '{zur.get('label')}'")
    jetzt = json.load(open(os.path.join(pdir, "meta.json"),
                           encoding="utf-8"))["payload"]
    pruefe(PJ.payload_marke(jetzt) == PJ.payload_marke(a)
           and jetzt["geom"]["p"] == 3 and jetzt["geom"]["statorOD"] == 280.0,
           "meta.json traegt wieder den Stand des Knotens — und zwar VOLLSTAENDIG, "
           "nicht nur die Felder, die zufaellig im Diff standen")
    pruefe(PJ.payload_marke((PJ._read(pdir) or {}).get("inputs", {})
                            .get("payload")) == PJ.payload_marke(a),
           "die Akte ebenso — sonst laesen Formular und Steckbrief zwei "
           "verschiedene Staende")
    n_ev = PJ.stand(pdir)["n_evolution"]
    pruefe(n_ev == 4 and (PJ._read(pdir)["evolution"][-1]["action"]
                          == f"zurueck:{knoten_a}"),
           f"die Rueckkehr ist selbst eine Stufe ({n_ev}) — die Stufen "
           f"dazwischen bleiben STEHEN: dass dieser Zweig probiert wurde und "
           f"nicht traegt, ist selbst eine Auskunft")
    marken = [k["marke"] for k in PJ.knoten_liste(pdir)]
    pruefe(any(k["action"] == "verlassen" for k in PJ.knoten_liste(pdir)),
           "und der VERLASSENE Stand ist gesichert — sonst waere der Rueckweg "
           "der einzige Schritt, den man nicht rueckgaengig machen kann")
    # Also auch wieder vorwaerts.
    verlassen = next(k["marke"] for k in PJ.knoten_liste(pdir)
                     if k["action"] == "verlassen")
    pruefe(PJ.zurueck(pdir, verlassen)["ok"]
           and json.load(open(os.path.join(pdir, "meta.json"),
                              encoding="utf-8"))["payload"]["geom"]["p"] == 4,
           "der Weg zurueck geht in beide Richtungen")
    pruefe(not PJ.zurueck(pdir, "gibtsnicht")["ok"]
           and PJ.knoten_holen(pdir, "../../etc/passwd") is None,
           "eine unbekannte Marke wird abgewiesen, ein Pfad erst recht")
    pruefe(all("payload" not in k for k in PJ.knoten_liste(pdir)),
           "die Liste laedt die Payloads NICHT mit — sie steht in der "
           "Oberflaeche, nicht im Speicher")


print("\n5. Die Seite: beide Richtungen, und das Formular hat Vorrang")
_hier = os.path.dirname(os.path.abspath(__file__))
_html = open(os.path.join(_hier, "ema.html"), encoding="utf-8").read()
_srv = open(os.path.join(_hier, "server.py"), encoding="utf-8").read()
pruefe('@app.route("/project/<pid>/stand")' in _srv,
       "der Server liefert den Stand ueber eine eigene, billige Route")
pruefe("koepfe" in _srv.split('def project_stand')[1][:1500],
       "und sagt dazu, WELCHER Agentenkopf an diesem Projekt haengt — ein "
       "blosses 'etwas hat sich geaendert' ist die halbe Auskunft")
pruefe('id="brk-bar"' in _html and "brueckeStart" in _html
       and "brueckeStopp" in _html,
       "der Geometrie-Reiter traegt die Bruecke und schaltet sie mit dem "
       "Reiter an und aus (im Hintergrund im Sekundentakt zu fragen waere Unfug)")
pruefe("brueckeHolen" in _html and "brueckeGeben" in _html,
       "beide Richtungen: holen (Agent -> Formular) und geben "
       "(Formular -> /agent/vorgabe)")
pruefe("_brkBeruehrt" in _html
       and "auto.checked && !_brkBeruehrt" in _html,
       "automatisch uebernommen wird NUR, solange das Formular unberuehrt ist "
       "— wer gerade tippt, bekommt keinen fremden Wert unter der Hand")
pruefe("brueckeNeuesProjekt" in _html
       and "brueckeNeuesProjekt" in _html.split("function pjSetActive")[1][:2000],
       "ein Projektwechsel setzt die Marke zurueck — die alte haette am neuen "
       "Projekt keine Bedeutung und meldete sofort eine Aenderung, die keine ist")
pruefe('@app.route("/project/<pid>/knoten"' in _srv
       and '@app.route("/project/<pid>/zurueck"' in _srv
       and "knotenSetzen" in _html and "knotenZurueck" in _html,
       "Abzweig setzen und zurueckgehen gibt es als Route UND als Knopf")
pruefe("gelöscht wird nichts" in _html,
       "und der Rueckfrage steht dabei, dass nichts geloescht wird")


print("\n" + "=" * 62)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
