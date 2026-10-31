"""auslegen (Phase 1 ohne Sprachmodell): heilt, was es darf, haelt an, wo der Mensch entscheidet.

Ohne Server und ohne Loeser: der Lauf wird gestellt, die Magnetschlussmessung auch.
"""

import copy

import ema_auslegen as AU
import ema_magnetschluss as MS
from cae_cli import frischer_payload


def _ohne_messung(stufe="ok"):
    MS.urteil = lambda geom, **kw: {"ok": True, "stufe": stufe, "streuanteil": 0.2}


def test_vorbereitet_ohne_lauf():
    _ohne_messung()
    e = AU.auslegen(frischer_payload("radial"), lauf=None, log=lambda t: None)
    assert e["ok"] is None
    namen = [s["schritt"] for s in e["schritte"]]
    assert namen[:3] == ["grenzen", "layout", "fliehkraft"]


def test_drehzahl_wird_nicht_selbst_gesenkt():
    """Reisst die Fliehkraft und hilft kein Blech, wird die Drehzahl GENANNT, nicht gesetzt."""
    _ohne_messung()
    p = frischer_payload("radial")
    p["rpm_to"] = 60000
    p.setdefault("target", {})["n_max"] = 60000
    vorher = copy.deepcopy(p)
    e = AU.auslegen(p, lauf=lambda q: ("/nie", ""), log=lambda t: None)
    assert e["ok"] is False and e["angehalten_bei"] == "fliehkraft"
    assert e["payload"]["rpm_to"] == 60000
    assert p == vorher, "der Payload des Aufrufers bleibt unberuehrt"


def test_layout_wird_geheilt():
    _ohne_messung()
    p = frischer_payload("radial")
    p["geom"]["magWidth"] = 400.0          # passt in keinen Laeufer
    e = AU.auslegen(p, lauf=None, log=lambda t: None)
    lay = [s for s in e["schritte"] if s["schritt"] == "layout"]
    assert lay and lay[0]["ok"] is True and lay[0].get("set"), lay


def test_gescheiterter_lauf_haelt_an():
    _ohne_messung()
    e = AU.auslegen(frischer_payload("radial"), lauf=lambda q: (None, "409 belegt"), log=lambda t: None)
    assert e["ok"] is False and e["angehalten_bei"] == "lauf"
    assert "409" in e["schritte"][-1]["text"]


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
