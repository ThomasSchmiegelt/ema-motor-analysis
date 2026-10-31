"""Erfahrungsdatenbank und Lernprogramm: Hinweis statt Tor, an der Maschine nachgerechnet.

Ohne Server, ohne Loeser; Belege gehen in eine temporaere Datei.
"""

import os
import tempfile

import ema_erfahrung as E
import ema_lernprogramm as LP
from cae_cli import frischer_payload

_TMP = tempfile.mkdtemp()
E.BELEGE = os.path.join(_TMP, "belege.jsonl")


def _gesaettigt():
    p = frischer_payload("radial")
    p["geom"]["slotDepth"] = 36.0            # 9 mm Restjoch an der 280/190-Maschine
    return p


def test_gesunde_maschine_schlaegt_nicht_an():
    r = E.pruefe(frischer_payload("radial"))
    assert r["treffer"] == []


def test_duennes_joch_schlaegt_an_und_hebel_beheben_wirklich():
    r = E.pruefe(_gesaettigt())
    (t,) = r["treffer"]
    assert t["id"] == "statorjoch_saettigt" and t["ist"] > t["grenze"]
    hilft = [h for h in t["hebel"] if h["status"] == "hilft"]
    assert {h["id"] for h in hilft} >= {"rotor_kleiner", "nut_flacher", "stator_groesser"}
    for h in hilft:
        assert h["nachher"]["B_joch"] <= E.ZIEL_AUSNUTZUNG * h["nachher"]["B_sat"] + 1e-3, h


def test_rotor_kleiner_haelt_den_luftspalt():
    t = E.pruefe(_gesaettigt())["treffer"][0]
    h = next(h for h in t["hebel"] if h["id"] == "rotor_kleiner")
    (sid0, sid1), (rod0, rod1) = h["aenderung"]["statorID"], h["aenderung"]["rotorOD"]
    assert abs((sid0 - rod0) - (sid1 - rod1)) < 0.05


def test_fester_parameter_wird_genannt_nicht_gerechnet():
    t = E.pruefe(_gesaettigt(), fest=["statorOD"])["treffer"][0]
    h = next(h for h in t["hebel"] if h["id"] == "stator_groesser")
    assert h["status"] == "fest" and "aenderung" not in h
    assert t["hebel"][-1]["id"] == "stator_groesser", "fest steht hinten"


def test_kein_tor_der_aufrufer_payload_bleibt_unberuehrt():
    p = _gesaettigt()
    vorher = repr(p)
    E.pruefe(p)
    assert repr(p) == vorher


def test_merken_zaehlt_je_hebel():
    os.path.exists(E.BELEGE) and os.remove(E.BELEGE)
    E.pruefe(_gesaettigt(), merken=True, quelle="test")
    z = E.zaehler("statorjoch_saettigt")
    assert z["nut_flacher"]["hilft"] == 1


def test_lernprogramm_schreibt_nur_belege_und_zaehlt():
    os.path.exists(E.BELEGE) and os.remove(E.BELEGE)
    r = LP.lauf(n=40, seed=3, log=lambda t: None, ablage=_TMP, kombinieren=False)
    assert r["gueltig"] == 40 and r["gezogen"] >= 40
    n = sum(sum(c.values()) for c in r["dieser_lauf"].get("statorjoch_saettigt", {}).values())
    assert n == 4 * r["mit_symptom"]
    assert os.path.exists(os.path.join(r["ordner"], "bericht.md"))


def test_trainingsplan_kommt_reihum_an_jede_zelle():
    r = LP.lauf(n=len(LP.trainingsplan()), seed=5, log=lambda t: None, ablage=_TMP, kombinieren=False)
    assert all(v["gueltig"] == 1 for v in r["zellen"].values()), r["zellen"]
    assert len(r["zellen"]) == len(LP.trainingsplan())


def test_preis_ist_das_spitzenmoment_nicht_ein_momentmass():
    """Kleinerer Laeufer bei festen Magneten: Kt bleibt fast stehen, das Spitzenmoment nicht."""
    t = E.pruefe(_gesaettigt())["treffer"][0]
    h = next(h for h in t["hebel"] if h["id"] == "rotor_kleiner")
    assert abs(h["kt_pct"]) < 0.5 and h["moment_pct"] < -1.0, h


def test_kombination_halb_und_halb():
    p = _gesaettigt()
    t = E.pruefe(p)["treffer"][0]
    k = {x["id"]: x for x in E.kombinationen(p, t)}
    sn = k["stator_groesser+nut_flacher"]
    assert sn["status"] == "hilft" and 0.4 < sn["bedarf_b"] < 0.6
    allein = next(h for h in t["hebel"] if h["id"] == "stator_groesser")
    assert sn["aussen_pct"] < allein["aussen_pct"], "die Haelfte Nut spart Aussendurchmesser"


def test_zeitplan_haelt_auswertung_frei():
    r = LP.lauf(minuten=0.05, auswertung_anteil=0.5, seed=1, log=lambda t: None, ablage=_TMP, kombinieren=False)
    assert r["ende"] in ("zeit", "stabil") and r["lern_sekunden"] <= 0.05 * 60 * 0.5 + 2.0
    assert "deutungszeit_min" in r


def test_materialien_rechnen_mit_dem_gewaehlten_blech():
    p = _gesaettigt()
    knie = {}
    for b in ("m250_35a", "m800_65a"):
        p["stator_lam"] = b
        knie[b] = E.pruefe(p)["messung"]["B_sat"]
    assert knie["m250_35a"] < knie["m800_65a"], knie
    plan = LP.trainingsplan("materialien")
    assert {z["stator_lam"] for z in plan} == set(LP.BLECHE)


def test_vorschlag_wird_gespeichert_und_bericht_lernt_nichts():
    wurzel = os.path.join(_TMP, "laeufe")
    r = LP.lauf(n=30, seed=2, log=lambda t: None, ablage=wurzel, kombinieren=False)
    v = LP.naechster_vorschlag(wurzel)
    assert v and v["von"] == r["marke"] and v["bereich"] in LP.BEREICHE and v["gruende"]
    assert "materialien" == v["bereich"], "ein nie gelernter Bereich wird vorgeschlagen"
    with open(os.path.join(r["ordner"], "bericht.md"), encoding="utf-8") as f:
        assert "Vorschlag fuer das naechste Training" in f.read()
    g = LP.lauf(bereich="bericht", ablage=wurzel, log=lambda t: None)
    assert g["gueltig"] == 0 and r["marke"] in g["text"]


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
