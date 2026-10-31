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
    r = LP.lauf(n=40, seed=3, log=lambda t: None)
    assert r["gueltig"] == 40 and r["gezogen"] >= 40
    n = sum(sum(c.values()) for c in r["zaehler"]["statorjoch_saettigt"].values())
    assert n == 4 * r["ausloeser"].get("statorjoch_saettigt", 0)


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
