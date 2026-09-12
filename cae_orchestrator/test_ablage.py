"""Tests fuer den Papierkorb — die EINE Loeschstelle.

Ohne Server, ohne Loeser. Gegen die Eigenschaften, auf denen die Sicherheit
ruht (s. ``ema_ablage``):

  * ohne ``bestaetigt`` passiert NICHTS — und der Aufruf ist dann die Rueckfrage,
  * entsorgt heisst verschoben, und Verschobenes kommt zurueck,
  * ein Pfad ausserhalb wird abgewiesen, und zwar am AUFGELOESTEN Pfad
    (``..`` und Symlinks lassen sich sonst verstecken),
  * jede Entsorgung steht in der einen Zeitleiste,
  * die Modulfunktionen, die frueher ``rmtree`` riefen, gehen jetzt hier durch.

Lauf: ``python test_ablage.py``
"""

import json
import os
import tempfile

import ema_ablage as AB
import ema_projekt as PJ


def _projekt(root, pid="20260101_000000_probe"):
    d = os.path.join(root, pid)
    os.makedirs(d, exist_ok=True)
    PJ.init(d, pid)
    return d


def test_ohne_bestaetigung_passiert_nichts():
    with tempfile.TemporaryDirectory() as root:
        d = _projekt(root)
        ziel = os.path.join(d, "charts")
        os.makedirs(ziel)
        open(os.path.join(ziel, "em_field.png"), "w").write("x" * 2048)

        r = AB.entsorgen(ziel, "Probe")
        assert r["ok"] is False and r["bestaetigung_noetig"] is True
        assert os.path.isdir(ziel), "es wurde etwas angefasst"
        # Der Aufruf IST die Rueckfrage: er sagt, was und wie viel.
        assert r["was"]["dateien"] == 1 and "kB" in r["was"]["groesse"]
        assert "Nichts ist geschehen" in r["text"]
        # Und die Zeitleiste bleibt leer — nichts geschehen heisst nichts gemeldet.
        assert not [e for e in PJ.load(d)["evolution"]
                    if e.get("action") == "entsorgt"]
    print("✓ ohne bestaetigt passiert NICHTS — und der Aufruf ist die Rueckfrage")


def test_entsorgtes_liegt_im_korb_und_kommt_zurueck():
    with tempfile.TemporaryDirectory() as root:
        d = _projekt(root)
        ziel = os.path.join(d, "berichte", "b1")
        os.makedirs(ziel)
        open(os.path.join(ziel, "bericht.pdf"), "w").write("PDF")

        r = AB.entsorgen(ziel, "verworfen", bestaetigt=True)
        assert r["ok"] and not os.path.exists(ziel)
        assert os.path.isfile(os.path.join(r["korb"], "b1", "bericht.pdf"))

        e = AB.inhalt(d)[0]
        assert e["name"] == "b1" and e["herkunft"] == os.path.join("berichte", "b1")
        assert e["da"] is True and e["grund"] == "verworfen"

        w = AB.wiederherstellen(d, r["marke"])
        assert w["ok"] and not w["umbenannt"]
        assert os.path.isfile(os.path.join(ziel, "bericht.pdf"))
        assert AB.inhalt(d)[0]["da"] is False   # aus dem Korb heraus
    print("✓ entsorgt = verschoben; Zurueckholen stellt den Herkunftsort her")


def test_zurueckholen_ueberschreibt_NICHT():
    """Der Rueckweg darf nicht selbst zur Loeschung werden."""
    with tempfile.TemporaryDirectory() as root:
        d = _projekt(root)
        ziel = os.path.join(d, "ansichten")
        os.makedirs(ziel)
        open(os.path.join(ziel, "alt.png"), "w").write("alt")
        r = AB.entsorgen(ziel, bestaetigt=True)

        os.makedirs(ziel)
        open(os.path.join(ziel, "neu.png"), "w").write("neu")
        w = AB.wiederherstellen(d, r["marke"])
        assert w["ok"] and w["umbenannt"] and w["hinweis"]
        # Das Neue ist unangetastet, das Alte liegt daneben.
        assert open(os.path.join(ziel, "neu.png")).read() == "neu"
        assert os.path.isfile(os.path.join(w["pfad"], "alt.png"))
    print("✓ Zurueckholen ueberschreibt nichts — es landet daneben und sagt es")


def test_pfad_ausserhalb_wird_abgewiesen():
    with tempfile.TemporaryDirectory() as root:
        d = _projekt(root)
        fremd = os.path.join(root, "fremd.txt")
        open(fremd, "w").write("nicht anfassen")

        # Direkt daneben
        r = AB.entsorgen(fremd, bestaetigt=True, project_dir=d)
        assert not r["ok"] and "liegt nicht unter" in r["grund"]
        assert os.path.isfile(fremd)

        # Ueber ``..`` versteckt — geprueft wird der AUFGELOESTE Pfad.
        versteckt = os.path.join(d, "charts", "..", "..", "fremd.txt")
        r = AB.entsorgen(versteckt, bestaetigt=True, project_dir=d)
        assert not r["ok"], "ein .. hat die Grenze umgangen"
        assert os.path.isfile(fremd)

        # Ueber einen Symlink versteckt
        link = os.path.join(d, "zeigtraus")
        try:
            os.symlink(fremd, link)
        except (OSError, NotImplementedError):
            pass
        else:
            r = AB.entsorgen(link, bestaetigt=True, project_dir=d)
            assert not r["ok"], "ein Symlink hat die Grenze umgangen"
            assert os.path.isfile(fremd)

        # Und die Wurzel selbst ist tabu.
        assert not AB.entsorgen(d, bestaetigt=True, project_dir=d)["ok"]
        assert os.path.isdir(d)
    print("✓ ausserhalb, ueber .., ueber Symlink und die Wurzel selbst: abgewiesen")


def test_jede_entsorgung_steht_in_der_zeitleiste():
    with tempfile.TemporaryDirectory() as root:
        d = _projekt(root)
        f = os.path.join(d, "weg.json")
        open(f, "w").write("{}")
        AB.entsorgen(f, "nicht mehr gebraucht", bestaetigt=True)
        ev = [e for e in PJ.load(d)["evolution"] if e.get("action") == "entsorgt"]
        assert ev and "weg.json" in ev[0]["note"]
        assert "nicht mehr gebraucht" in ev[0]["note"]
    print("✓ jede Entsorgung steht in der EINEN Zeitleiste (evolution)")


def test_ganzes_projekt_geht_in_den_bestandskorb():
    with tempfile.TemporaryDirectory() as root:
        d = _projekt(root)
        open(os.path.join(d, "results.json"), "w").write("{}")

        r = AB.projekt_entsorgen(d, root)
        assert not r["ok"] and r["bestaetigung_noetig"] and os.path.isdir(d)

        r = AB.projekt_entsorgen(d, root, "Fehlversuch", bestaetigt=True)
        assert r["ok"] and not os.path.exists(d)
        assert os.path.isfile(os.path.join(r["korb"], os.path.basename(d),
                                           "results.json"))
        # Die Projektwurzel selbst ist unantastbar.
        assert not AB.projekt_entsorgen(root, root, bestaetigt=True)["ok"]
        assert os.path.isdir(root)
    print("✓ ein ganzes Projekt geht nach _papierkorb/ — die Wurzel nie")


def test_endgueltig_braucht_ein_zweites_ja():
    with tempfile.TemporaryDirectory() as root:
        d = _projekt(root)
        f = os.path.join(d, "weg.json")
        open(f, "w").write("{}")
        AB.entsorgen(f, bestaetigt=True, project_dir=d)

        r = AB.endgueltig(d)
        assert not r["ok"] and r["bestaetigung_noetig"] and r["eintraege"] == 1
        assert AB.inhalt(d)[0]["da"] is True, "trotz fehlender Bestaetigung weg"

        r = AB.endgueltig(d, bestaetigt=True)
        assert r["ok"] and r["geloescht"] == 1
        assert AB.inhalt(d)[0]["da"] is False
    print("✓ endgueltig braucht ein zweites, ausdrueckliches Ja")


def test_journal_ist_anhaengend():
    with tempfile.TemporaryDirectory() as root:
        d = _projekt(root)
        for i in range(3):
            f = os.path.join(d, f"w{i}.json")
            open(f, "w").write("{}")
            AB.entsorgen(f, f"Nr {i}", bestaetigt=True)
        p = os.path.join(AB.korb_wurzel(d), AB.JOURNAL)
        zeilen = [json.loads(z) for z in open(p, encoding="utf-8") if z.strip()]
        assert len(zeilen) == 3
        assert [z["name"] for z in zeilen] == ["w0.json", "w1.json", "w2.json"]
        # Ausgegeben wird neueste zuerst.
        assert [e["name"] for e in AB.inhalt(d)] == ["w2.json", "w1.json", "w0.json"]
    print("✓ das Journal ist anhaengend, die Liste kommt neueste zuerst")


def test_die_modulfunktionen_gehen_durch_den_korb():
    """Die Stellen, die frueher ``rmtree``/``os.remove`` riefen."""
    import ema_ansichten, ema_bericht
    with tempfile.TemporaryDirectory() as root:
        d = _projekt(root)

        # Ansicht: das Bild UND seine Einstellungen reisen mit.
        import base64
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQAB"
            "DQottAAAAABJRU5ErkJggg==")
        r = ema_ansichten.sichern(d, "data:image/png;base64,"
                                  + base64.b64encode(png).decode(),
                                  name="probe", einstellungen={"skala": "0…2 T"})
        datei = r["datei"]
        assert ema_ansichten.loeschen(d, datei) is True
        assert ema_ansichten.pfad(d, datei) is None
        korb = AB.inhalt(d)[0]["im_korb"]
        assert os.path.isfile(korb)
        assert os.path.isfile(korb[:-4] + ".json"), \
            "die Einstellungen sind nicht mitgereist"

        # Bericht
        kennung = ema_bericht.anlegen(d, "Probe")
        assert ema_bericht.loeschen(d, kennung) is True
        assert not any(x["kennung"] == kennung for x in ema_bericht.liste(d))
        assert any(e["name"] == kennung for e in AB.inhalt(d))
    print("✓ Ansichten und Berichte gehen durch den Korb statt durch rmtree")


def main():
    test_ohne_bestaetigung_passiert_nichts()
    test_entsorgtes_liegt_im_korb_und_kommt_zurueck()
    test_zurueckholen_ueberschreibt_NICHT()
    test_pfad_ausserhalb_wird_abgewiesen()
    test_jede_entsorgung_steht_in_der_zeitleiste()
    test_ganzes_projekt_geht_in_den_bestandskorb()
    test_endgueltig_braucht_ein_zweites_ja()
    test_journal_ist_anhaengend()
    test_die_modulfunktionen_gehen_durch_den_korb()
    print("\nALLE PAPIERKORB-TESTS BESTANDEN ✅")


if __name__ == "__main__":
    main()
