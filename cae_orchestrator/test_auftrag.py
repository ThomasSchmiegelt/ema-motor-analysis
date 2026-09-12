"""Tests fuer ``AUFTRAG.md`` — die fortschreibbare ABSICHT eines Projekts.

Ohne Server, ohne LLM, ohne FreeCAD. Gegen die vier Eigenschaften, auf denen
der ganze Entwurf ruht (s. ``ema_auftrag``):

  * die Vorlage entsteht bei der Projektanlage — an EINER Stelle,
  * eine vorhandene Datei wird NICHT ueberschrieben (sie kann von Hand
    geschrieben sein; eine Vorlage darueber waere der eine Schreibvorgang, der
    Text vernichtet),
  * ``ergaenzen`` haengt an und laesst Bestehendes Zeichen fuer Zeichen stehen,
  * der Auftrag erreicht Steckbrief und Agentenkopf — sonst ist er geschrieben
    und unerreichbar, und das ist dasselbe wie nicht geschrieben.

Lauf: ``python test_auftrag.py``
"""

import os
import tempfile

import ema_auftrag as AU


def test_vorlage_traegt_ziel_und_schlagworte():
    with tempfile.TemporaryDirectory() as d:
        assert AU.anlegen(d, "Roboterachse", "Ein 75-mm-Antrieb.",
                          ["robotik", "klein"]) is True
        t = AU.lesen(d)
        for _, titel in AU.ABSCHNITTE:
            assert f"## {titel}" in t, titel
        assert "Ein 75-mm-Antrieb." in t
        assert "robotik, klein" in t
        assert os.path.isfile(os.path.join(d, "AUFTRAG.md"))
    print("✓ Vorlage: fuenf Abschnitte, Ziel und Schlagworte stehen drin")


def test_vorhandene_datei_wird_nicht_angefasst():
    with tempfile.TemporaryDirectory() as d:
        eigen = "# Mein eigener Auftrag\n\nvon Hand geschrieben.\n"
        with open(AU.pfad(d), "w", encoding="utf-8") as f:
            f.write(eigen)
        assert AU.anlegen(d, "egal", "anderer Text") is False
        assert AU.lesen(d) == eigen          # Zeichen fuer Zeichen
    print("✓ anlegen ist idempotent — eine vorhandene Datei bleibt unberuehrt")


def test_ergaenzen_haengt_an_und_loescht_nichts():
    with tempfile.TemporaryDirectory() as d:
        AU.anlegen(d, "T", "Das Ziel.")
        vorher = AU.lesen(d)
        assert AU.ergaenzen(d, "entscheidungen",
                            "Ferrit statt NdFeB, weil der Preis bindet.",
                            "Mensch")["ok"]
        assert AU.ergaenzen(d, "entscheidungen", "Und noch eine.", "pi")["ok"]
        t = AU.lesen(d)
        # Beide Eintraege da, in der Reihenfolge, in der sie kamen.
        assert t.index("Ferrit statt NdFeB") < t.index("Und noch eine.")
        # Das Ziel aus der Vorlage steht unveraendert weiter da.
        assert "Das Ziel." in t
        # Alles, was vorher stand, steht noch — bis auf den Platzhalter des
        # einen beschriebenen Abschnitts. Es gibt bewusst kein `ersetzen`.
        assert vorher.count("## Verweise") == t.count("## Verweise") == 1
        assert "(Mensch)" in t and "(pi)" in t
    print("✓ ergaenzen haengt an, loescht nichts, und die Quelle steht dabei")


def test_schluessel_und_ueberschrift_meinen_DENSELBEN_abschnitt():
    with tempfile.TemporaryDirectory() as d:
        AU.anlegen(d, "T", "Z")
        AU.ergaenzen(d, "offen", "ueber den Schluessel")
        AU.ergaenzen(d, "Offene Punkte", "ueber die Ueberschrift")
        t = AU.lesen(d)
        # Genau EIN Abschnitt. Ueber den Schluessel gesucht liefe `offen` an
        # „Offene Punkte" vorbei und legte einen zweiten, gleichnamigen an —
        # und dann steht die Haelfte der offenen Punkte woanders.
        assert t.count("## Offene Punkte") == 1
        assert "ueber den Schluessel" in t and "ueber die Ueberschrift" in t
        assert list(AU.abschnitte(d)) == [t for _, t in AU.ABSCHNITTE]
    print("✓ `offen` und `Offene Punkte` treffen denselben Abschnitt")


def test_unbekannter_abschnitt_wird_angelegt_statt_verworfen():
    with tempfile.TemporaryDirectory() as d:
        AU.anlegen(d, "T", "Z")
        assert AU.ergaenzen(d, "Messprotokoll", "am Pruefstand gemessen")["ok"]
        t = AU.lesen(d)
        assert "## Messprotokoll" in t and "am Pruefstand gemessen" in t
    print("✓ ein unbekannter Abschnitt entsteht — ein verworfener Eintrag waere schlimmer")


def test_leerer_text_wird_abgewiesen():
    with tempfile.TemporaryDirectory() as d:
        AU.anlegen(d, "T", "Z")
        r = AU.ergaenzen(d, "ziel", "   ")
        assert r["ok"] is False and r["grund"]
        assert AU.lesen(d).count("- **") == 0
    print("✓ leerer Text wird abgewiesen statt eine leere Zeile anzuhaengen")


def test_ergaenzen_steht_in_der_EINEN_zeitleiste():
    """Kein zweites Journal — die Zeitleiste ist ``project.json``s ``evolution``."""
    import ema_projekt
    with tempfile.TemporaryDirectory() as d:
        ema_projekt.init(d, "testprojekt")
        AU.anlegen(d, "T", "Z")
        AU.ergaenzen(d, "entscheidungen", "Ferrit gewaehlt.")
        ev = ema_projekt.load(d)["evolution"]
        assert [e for e in ev if e.get("action") == "auftrag"], ev
        assert "Ferrit gewaehlt." in ev[-1]["note"]
    print("✓ jede Ergaenzung steht in der einen Zeitleiste (evolution)")


def test_als_markdown_deckelt_und_sagt_es():
    with tempfile.TemporaryDirectory() as d:
        AU.anlegen(d, "T", "x" * 9000)
        t = AU.als_markdown(d, max_zeichen=500)
        assert len(t) < 700
        assert "gekuerzt" in t
        # Und ohne Auftrag ist es LEER, nicht „keine Angabe" — der Kopf soll
        # dann gar keinen Abschnitt bekommen.
        with tempfile.TemporaryDirectory() as leer:
            assert AU.als_markdown(leer) == ""
    print("✓ als_markdown deckelt fuer die Aufforderung und sagt es")


def test_projektanlage_legt_ihn_an():
    """EINE Stelle: ``create_project_dir`` — damit /project/new, clone, import,
    CAD-Vorschau und der Pipelinelauf dieselbe Ablage bekommen."""
    from ema_pipeline import create_project_dir
    with tempfile.TemporaryDirectory() as root:
        d, pid = create_project_dir(root, "probe", origin="manual",
                                    brief="Ein Antrieb fuer eine Winde.",
                                    tags=["winde"])
        assert os.path.isfile(os.path.join(d, "AUFTRAG.md"))
        t = AU.lesen(d)
        assert "Ein Antrieb fuer eine Winde." in t and "winde" in t
        # Ohne Beschreibung entsteht er trotzdem — mit dem Platzhalter, der
        # sagt, dass die Absicht noch fehlt.
        d2, _ = create_project_dir(root, "ohne")
        assert "_noch nicht festgehalten_" in AU.lesen(d2)
    print("✓ die Projektanlage legt AUFTRAG.md an — an genau einer Stelle")


def test_auftrag_erreicht_den_steckbrief():
    """Geschrieben und unerreichbar ist dasselbe wie nicht geschrieben."""
    import ema_steckbrief as SB
    from ema_pipeline import create_project_dir
    with tempfile.TemporaryDirectory() as root:
        d, _ = create_project_dir(root, "probe", brief="Winde, 3 kW.")
        AU.ergaenzen(d, "entscheidungen", "Ferrit, weil der Preis bindet.")
        sb = SB.steckbrief(d, mit_laeufen=False)
        assert sb["ok"]
        adat = sb["auftragsdatei"]
        assert "Ziel" in adat and "Winde, 3 kW." in adat["Ziel"]
        assert "Ferrit, weil der Preis bindet." in adat["Entscheidungen"]
        # Platzhalter sind LEER und nicht Inhalt — sonst haelt der Leser die
        # Vorlage fuer eine Aussage.
        assert "Verweise" not in adat
        for text in (SB.als_text(sb), SB.als_markdown(sb)):
            assert "Ferrit, weil der Preis bindet." in text
    print("✓ der Auftrag steht im Steckbrief — in Text UND Markdown")


def main():
    test_vorlage_traegt_ziel_und_schlagworte()
    test_vorhandene_datei_wird_nicht_angefasst()
    test_ergaenzen_haengt_an_und_loescht_nichts()
    test_schluessel_und_ueberschrift_meinen_DENSELBEN_abschnitt()
    test_unbekannter_abschnitt_wird_angelegt_statt_verworfen()
    test_leerer_text_wird_abgewiesen()
    test_ergaenzen_steht_in_der_EINEN_zeitleiste()
    test_als_markdown_deckelt_und_sagt_es()
    test_projektanlage_legt_ihn_an()
    test_auftrag_erreicht_den_steckbrief()
    print("\nALLE AUFTRAGS-TESTS BESTANDEN ✅")


if __name__ == "__main__":
    main()
