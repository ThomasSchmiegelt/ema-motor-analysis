"""Tests für den dritten Agentenkopf (Studio), seine Tokenwache und die Beiträge.

Was hier still falsch sein kann und deshalb geprüft wird:

* **Der stehende Auftrag.** Er stand inline in ``server.py`` und galt damit für
  jeden Kopf. Zöge man ihn falsch heraus, bekäme der Studio-Kopf weiter die
  Auslegungsanweisung — und finge an, Fahrzyklen zu rechnen, statt zu schreiben.
* **Die Tokenwache.** Sie darf genau eine Seite schützen und keine andere
  einschränken. Zu viel Wache bricht den PI-Reiter, zu wenig öffnet den
  Studio-Kopf im WLAN.
* **Zwei Abschriften, die auseinanderlaufen.** Die Schnittstücke der Aufnahme und
  die Reel-Vorschläge kommen aus derselben Funktion; die beiden Seiten benutzen
  dieselbe ``agent_gemein.js``. Beides wird nachgemessen, nicht behauptet.
* **Erfundene Zahlen.** Ein Beitrag wird veröffentlicht. Die Prüfung ``keine Zahl
  ohne Deckung im Material`` ist deshalb Code und nicht nur eine Bitte im Prompt.

Ohne pytest — wie die übrigen Testdateien hier: ``venv/bin/python test_studio.py``.
Der Server wird NICHT gebraucht; die Wache wird über den Flask-Testklienten
geprüft, das Sprachmodell über einen eingesetzten Aufruf.
"""

import os
import re
import subprocess
import sys

import ema_agent
import ema_beitrag

HIER = os.path.dirname(os.path.abspath(__file__))


# ── 1. Der dritte Kopf ──────────────────────────────────────────────────────

def test_dritter_kopf():
    assert set(ema_agent.KOEPFE) == {"pi", "hermes", "studio"}, list(ema_agent.KOEPFE)
    k = ema_agent.kopf("studio")
    assert k is ema_agent.STUDIO and k is not ema_agent.LAUF
    assert k.NAME == "studio" and k.LABEL == "Studio"
    # Unbekanntes faellt weiter auf PI zurueck -- der gewachsene Weg.
    assert ema_agent.kopf("quatsch") is ema_agent.LAUF
    assert ema_agent.kopf("") is ema_agent.LAUF
    # Eigener Prozess, eigener Ring: der Studio-Kopf steht NEBEN PI, nicht an
    # seiner Stelle. Waeren es dieselben Objekte, saehe das Handy PIs Lauf.
    assert ema_agent.STUDIO.ring is not ema_agent.LAUF.ring
    print("✓ dritter_kopf: pi · hermes · studio, jeder mit eigenem Lauf")


def test_systemzusatz_je_kopf():
    """Der Auslegungsauftrag gehoert PI und Hermes -- nicht dem Studio-Kopf."""
    akte = {"design": {"brief": "Ein Antrieb fuer ein Lastenrad"}}
    pi = ema_agent.LAUF.systemzusatz("P1", akte, 3)
    st = ema_agent.STUDIO.systemzusatz("P1", akte, 3)

    # Der verschobene Text ist der alte: die vier Saetze, die vorher in
    # server.py standen, muessen bei PI wortwoertlich ankommen.
    for satz in ("zyklus liste", "run em3d", "cae_cli.py welle", "aufgabe",
                 "ENTWURFSMODUS", "sicherheit --from-project"):
        assert satz in pi, f"PI fehlt: {satz}"
        assert satz not in st, f"Studio hat den Auslegungsauftrag geerbt: {satz}"

    # Der Studio-Auftrag sagt, was er ist -- und was er nicht tut.
    for satz in ("steckbrief", "beitrag", "nicht im Beitrag"):
        assert satz in st, f"Studio fehlt: {satz}"
    assert "Ein Antrieb fuer ein Lastenrad" in st, "Der Brief kommt nicht an"

    # Ohne Projekt bleibt beides brauchbar (der haeufigste Fall bei --frisch).
    assert ema_agent.LAUF.systemzusatz("", {}, 0)
    assert "Kein Projekt gebunden" in ema_agent.STUDIO.systemzusatz("", {}, 0)
    print("✓ systemzusatz: Auslegung bei PI, Schreiben bei Studio")


def test_projektakte_gehoert_dem_ersten():
    """Ein zweiter Kopf schreibt die Akte des ersten nicht um.

    Gemessen wird an der Datei: laeuft ein anderer Kopf, darf ihr Inhalt sich
    nicht aendern -- sonst faende der erste beim naechsten Lesen ein fremdes
    Projekt vor und haette keinen Anlass, daran zu zweifeln.
    """
    pfad = os.path.join(ema_agent.WURZEL, "AGENTS.projekt.md")
    vorher = open(pfad, encoding="utf-8").read() if os.path.isfile(pfad) else None
    lief = ema_agent.LAUF.laeuft
    try:
        ema_agent.LAUF.laeuft = True
        ema_agent.LAUF.projekt = "20260101_fremd"
        ema_agent.STUDIO.projekt = ""
        aus = ema_agent.STUDIO.projektakte_schreiben("")
        assert aus == "", "Studio hat die Akte trotz laufendem PI geschrieben"
        jetzt = open(pfad, encoding="utf-8").read() if os.path.isfile(pfad) else None
        assert jetzt == vorher, "Die Akte hat sich geaendert"
        # Und es wird GESAGT, nicht verschwiegen.
        letzte = [e for e in ema_agent.STUDIO.ring if e.get("art") == "gemerkt"]
        assert letzte and "AGENTS.projekt.md" in letzte[-1]["text"], letzte
    finally:
        ema_agent.LAUF.laeuft = lief
        ema_agent.LAUF.projekt = ""
        ema_agent.STUDIO.ring = []
    print("✓ projektakte: der zweite Kopf ueberschreibt den ersten nicht")


# ── 2. Die Tokenwache ───────────────────────────────────────────────────────

def test_tokenwache():
    """Genau eine Seite schuetzen -- und keine andere einschraenken."""
    import server
    import ema_mobil
    tok = ema_mobil.token()
    server.app.config["TESTING"] = True
    c = server.app.test_client()

    # Vom Rechner selbst offen: dort steht der Reiter in ema.html.
    assert c.get("/studio").status_code == 200
    assert c.get("/agent/auswahl?kopf=studio").status_code == 200

    # Von aussen: die Seite verlangt das Token -- und antwortet mit einer SEITE,
    # nicht mit einem JSON, weil der Startbildschirm-Eintrag ohne ``?t=`` startet.
    fremd = {"REMOTE_ADDR": "192.168.178.99"}
    a = c.get("/studio", environ_overrides=fremd)
    assert a.status_code == 401 and b"Token" in a.data
    assert c.get(f"/studio?t={tok}", environ_overrides=fremd).status_code == 200
    assert c.get("/agent/auswahl?kopf=studio",
                 environ_overrides=fremd).status_code == 401
    assert c.get(f"/agent/auswahl?kopf=studio&t={tok}",
                 environ_overrides=fremd).status_code == 200

    # PI und Hermes bleiben unangetastet -- sie waren nie von aussen gemeint,
    # und sie jetzt mit abzusichern waere eine eigene, groessere Entscheidung.
    assert c.get("/agent/auswahl?kopf=pi", environ_overrides=fremd).status_code == 200
    assert c.get("/agent/auswahl", environ_overrides=fremd).status_code == 200

    # Der Zugang selbst ist schaerfer: nur localhost, sonst waere das Token frei
    # abholbar und die Sperre eine Attrappe.
    assert c.get("/studio/zugang").status_code == 200
    assert c.get("/studio/zugang", environ_overrides=fremd).status_code == 403
    print("✓ tokenwache: Studio geschuetzt, PI und Hermes unveraendert offen")


def test_zugang_traegt_qr_oder_sagt_es():
    import ema_mobil
    url = ema_mobil.studio_url(5000)
    assert url.startswith("http://") and "/studio?t=" in url
    m = ema_mobil.qr_matrix(url)
    if m is None:
        print("✓ zugang: kein segno/qrcode im venv — die Seite zeigt die Adresse "
              "im Klartext (ein halb richtiger QR waere schlimmer als keiner)")
        return
    assert len(m) == len(m[0]) >= 21 and set(m[0]) <= {0, 1}
    # Suchmuster oben links: sieben Module Kante. Faellt das aus, ist die Matrix
    # keine QR-Matrix, sondern irgendetwas Quadratisches.
    assert all(m[0][i] == 1 for i in range(7)) and m[1][0] == 1 and m[1][1] == 0
    print(f"✓ zugang: QR {len(m)}x{len(m)} Module fuer {url}")


# ── 3. Eine Bildersuche, eine Gruppierung ───────────────────────────────────

def test_marken_und_schnitt_sind_dieselbe_gruppierung():
    """Die Reel-Vorschlaege duerfen nicht andere Sekunden zeigen als geschnitten
    werden. Deshalb dieselbe Funktion -- hier gegen das Skript nachgemessen."""
    marken = [{"s": 3.0, "uhr": "10:00:03", "art": "start", "text": "Aufnahme"},
              {"s": 20.0, "uhr": "10:00:20", "art": "ergebnis", "text": "rotor-check"},
              {"s": 400.0, "uhr": "10:06:40", "art": "bild", "text": "feld.png"}]
    A = ema_agent.Aufnahme
    stuecke = ema_agent.stuecke_aus_marken(marken, A.VOR_S, A.NACH_S, A.VERSCHMELZEN_S)
    # Die ersten beiden verschmelzen (17 s Abstand < 25 s), die dritte nicht.
    assert len(stuecke) == 2, stuecke
    assert stuecke[0][0] == 0.0 and stuecke[0][1] == 32.0, stuecke[0]

    skript = ema_agent._schnitt_skript("/tmp/x.webm", stuecke)
    for ab, bis, _ in stuecke:
        assert f"-ss {ab:.2f}" in skript and f"-t {bis - ab:.2f}" in skript, skript
    print(f"✓ marken: {len(marken)} Marken -> {len(stuecke)} Stuecke, "
          f"Skript und Vorschlag zeigen dieselben Sekunden")


def test_clips_lesen_die_geschriebene_liste(tmp=None):
    """Was ``Aufnahme`` schreibt, muss ``ema_beitrag`` zurueckuebersetzen."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        pfad = os.path.join(d, "lauf.marken.tsv")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("# Videosekunde\tUhrzeit\tArt\tText\n")
            f.write("12.50\t10:00:12\tergebnis\trotor-check bestanden\n")
            f.write("300.00\t10:05:00\tbild\tfeld_quer.png\n")
        clips = ema_beitrag.clips(pfad)
        assert len(clips) == 2, clips
        assert "rotor-check" in clips[0]["worum"]
        assert clips[0]["ffmpeg"].startswith("ffmpeg -ss ")
        assert "lauf.webm" in clips[0]["ffmpeg"] or "lauf" in clips[0]["ffmpeg"]
        assert ema_beitrag.marken_lesen(os.path.join(d, "gibtsnicht.tsv")) == []
    print("✓ clips: die geschriebene Markenliste laesst sich zurueckuebersetzen")


# ── 4. Die Beitraege ────────────────────────────────────────────────────────

def _antwort(text, hashtags="#emotor #cae", alt=""):
    return f"### TEXT\n{text}\n### HASHTAGS\n{hashtags}\n### ALT\n{alt}\n"


# ── Markdown: der Block wird mit `node` gegen feste Beispiele geprueft ──────
#
# Dasselbe Verfahren wie beim JS-Spiegel in test_topology.py: der Block zwischen
# den Marken wird herausgeschnitten, um ein `esc` ergaenzt und ausgefuehrt. Er
# darf deshalb nichts ausser `esc` voraussetzen -- ein Renderer, der am DOM
# haengt, waere nicht pruefbar.

def _markdown_block() -> str:
    h = open(os.path.join(HIER, "ema_studio.html"), encoding="utf-8").read()
    i = h.index("// <<MD-START>>")
    j = h.index("// <<MD-END>>")
    return h[i:j]


def _md(faelle: list) -> list:
    """Jeden Fall durch `markdown()` schicken -- in EINEM node-Aufruf."""
    import json as _json
    import tempfile
    skript = ("const esc = s => String(s).replace(/[&<>]/g, c => "
              "({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));\n"
              + _markdown_block() +
              "\nconst faelle = " + _json.dumps(faelle) + ";\n"
              "console.log(JSON.stringify(faelle.map(markdown)));\n")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "md.js")
        with open(p, "w", encoding="utf-8") as f:
            f.write(skript)
        aus = subprocess.run(["node", p], capture_output=True, text=True)
        assert aus.returncode == 0, aus.stderr
        return _json.loads(aus.stdout)


def test_markdown():
    """Was das Modell wirklich schreibt -- und was daraus werden muss."""
    if not shutil_which("node"):
        print("… node fehlt — Markdown-Pruefung uebersprungen")
        return
    e = _md([
        "**Was der Raum leistet:**",                                   # 0
        "- erste Zeile\n- zweite Zeile",                               # 1
        "1. eins\n2. zwei",                                            # 2
        "## Ergebnis",                                                 # 3
        "Ein `cae_cli.py steckbrief` im Satz.",                        # 4
        "| Groesse | Wert |\n|---|---|\n| B_gap | 0,799 T |",          # 5
        "```\nzeile eins\nzeile zwei\n```",                            # 6
        "> ein Zitat",                                                 # 7
        "Datei em_field_load.png und rotor_check_2.png",               # 8
        "<script>alert(1)</script>",                                   # 9
        "Erster Absatz.\n\nZweiter Absatz.",                           # 10
        "*kursiv* und **fett** zusammen",                              # 11
        "---",                                                         # 12
        "",                                                            # 13
    ])
    assert e[0] == "<p><b>Was der Raum leistet:</b></p>", e[0]
    assert e[1] == "<ul><li>erste Zeile</li><li>zweite Zeile</li></ul>", e[1]
    assert e[2] == "<ol><li>eins</li><li>zwei</li></ol>", e[2]
    assert e[3] == "<h4>Ergebnis</h4>", e[3]           # zwei Stufen tiefer
    assert "<code>cae_cli.py steckbrief</code>" in e[4], e[4]
    # Die Tabelle ist der Grund fuer das Ganze: eine Feldanalyse als Rohtext
    # ist keine Tabelle.
    assert e[5].startswith("<table><thead><tr><th>Groesse</th><th>Wert</th>"), e[5]
    assert "<td>B_gap</td><td>0,799 T</td>" in e[5], e[5]
    assert e[6] == '<pre class="mdcode">zeile eins\nzeile zwei</pre>', e[6]
    assert e[7] == "<blockquote>ein Zitat</blockquote>", e[7]
    # Ein Dateiname mit Unterstrichen darf sich nicht selbst kursiv setzen.
    assert "<i>" not in e[8], e[8]
    # Alles geht durch esc(): gesetzt wird, was das Modell SCHRIEB.
    assert "&lt;script&gt;" in e[9] and "<script>" not in e[9], e[9]
    assert e[10] == "<p>Erster Absatz.</p><p>Zweiter Absatz.</p>", e[10]
    # Weiche Umbrueche des Modells sind KEINE Umbrueche — sonst franst die
    # rechte Kante aus. Zwei Leerzeichen am Zeilenende bleiben einer.
    weich = _md(["Ein Satz, den das Modell\nbei achtzig Zeichen umbrach.",
                 "Erste Zeile  \nZweite Zeile"])
    assert weich[0] == "<p>Ein Satz, den das Modell bei achtzig Zeichen umbrach.</p>", weich[0]
    assert weich[1] == "<p>Erste Zeile<br>Zweite Zeile</p>", weich[1]
    assert e[11] == "<p><i>kursiv</i> und <b>fett</b> zusammen</p>", e[11]
    assert e[12] == "<hr>", e[12]
    assert e[13] == "", e[13]
    print("✓ markdown: Fett, Listen, Ueberschriften, Code, TABELLEN, Zitate — "
          "und nichts davon als HTML des Modells")


def test_markdown_bleibt_stehen():
    """Kein Fall darf die Schleife anhalten -- die Antwort kommt STROEMEND an,
    also wird auch jeder unfertige Zwischenstand gerendert."""
    if not shutil_which("node"):
        return
    roh = ("## Feldanalyse\n\n| Groesse | Wert |\n|---|---|\n| B_gap | 0,8 T |\n"
           "\n```\nunfertig")
    teile = [roh[:n] for n in range(1, len(roh) + 1)]
    aus = _md(teile)
    assert len(aus) == len(teile)
    assert all(isinstance(x, str) for x in aus)
    print(f"✓ markdown: alle {len(teile)} Zwischenstaende einer strömenden "
          f"Antwort werden fertig gesetzt")


def test_ausgerichtete_ausgabe_wird_eingepasst():
    """Spalten bleiben Spalten: eingepasst wird die SCHRIFT, nicht der Text."""
    h = open(os.path.join(HIER, "ema_studio.html"), encoding="utf-8").read()
    assert "function preAnpassen(" in h and "PRE_MIN_PX" in h
    # Auf das 90. Hundertstel, nicht auf die laengste Zeile -- sonst druecke
    # eine einzelne Prosazeile die ganze Tabelle auf Ameisengroesse.
    # Eingepasst wird auf die AUSGERICHTETEN Zeilen (Spaltenluecke), nicht auf
    # die laengste und nicht auf einen Hundertstelwert ueber alles: die
    # `welle`-Ausgabe hat 228 Zeichen Prosa neben 65 Zeichen Tabelle.
    assert "function _sollBreite(" in h and "/\\S {2,}\\S/" in h, \
        "die Spaltenluecke ist nicht das Kriterium"
    assert "k.querySelector('pre')" in h, "die Ergebniskachel wird nicht eingepasst"
    assert "umgebrochen; ungekürzt im abgelegten Text" in h, \
        "zu breite Ausgabe wird verschwiegen"
    assert "m.soll > m.passt" in h, \
        "gemeldet wird nur eine zerbrochene TABELLE, nicht umbrechende Prosa"
    # Und die Zeichenbreite wird GEMESSEN, nicht mit 0,6 em geraten.
    assert "getBoundingClientRect().width / 10 / 100" in h
    pre = h.split("\n  .karte.erg pre{")[1].split("}")[0]
    assert "tabular-nums" in pre, "Ziffern stehen nicht in Tabellenstellung"
    # Kein Hoehendeckel: er schnitt mitten in die Kennwertetabelle — genau die
    # Beschwerde, wegen der das hier steht.
    assert "max-height" not in pre, pre
    print("✓ einpassen: die Schrift folgt der Tabelle, nicht umgekehrt")


def test_hochformat_und_zuschnitt():
    """Die feste Buehne und die Zeile, die daraus ein Reel schneidet.

    Ein Reel ist 1080x1920. Ohne feste Buehne entsteht ein 16:9-Video, aus dem
    der Hochkantausschnitt erst hinterher geschnitten wird -- und dann
    entscheidet sich beim Schneiden, was drin ist.
    """
    h = open(os.path.join(HIER, "ema_studio.html"), encoding="utf-8").read()
    assert "'9:16': [1080, 1920]" in h and "'4:5': [1080, 1350]" in h
    assert "FORMAT_VORGABE = '9:16'" in h, "Reel/Short ist die Vorgabe"
    assert "#buehne.fest{font-size:26px}" in h, "die feste Buehne hat eigene Groessen"
    assert "b.style.transform = 'scale('" in h, "skaliert wird die ganze Buehne"
    # Und die zweispaltige Seite bleibt, was sie ist -- sie ist fuer den
    # Schreibtisch gebaut, nicht fuer ein Reel.
    a = open(os.path.join(HIER, "ema_agent.html"), encoding="utf-8").read()
    assert "FORMATE" not in a and "buehneMessen" not in a

    # Reiter- oder Fensteraufnahme: die Buehne liegt berechenbar, also gibt es
    # eine Zuschnittzeile -- auch bei doppelter Bildpunktdichte.
    def marke(aufnahme):
        return [{"s": 0.0, "uhr": "10:00:00", "art": "format",
                 "text": "Hochformat 1080x1920 · Buehne 460,52 590x1050 "
                         "im Fenster 1512x1102 · Aufnahme " + aufnahme}]
    assert ema_beitrag.zuschnitt(marke("1512x1102")) == "crop=590:1050:460:52,scale=1080:1920"
    assert ema_beitrag.zuschnitt(marke("3024x2204")) == "crop=1180:2100:920:104,scale=1080:1920"
    # Ganzer Bildschirm: das Fenster sitzt irgendwo darin. Geraten wird nicht.
    assert ema_beitrag.zuschnitt(marke("2560x1440")) == ""
    # Und die drei Faelle sind zu unterscheiden: schon zugeschnitten ist etwas
    # anderes als „Lage unbekannt", auch wenn beide keine ffmpeg-Zeile ergeben.
    assert ema_beitrag.zuschnitt_lage(marke("1512x1102")) == "berechnet"
    assert ema_beitrag.zuschnitt_lage(marke("2560x1440")) == "unbekannt"
    bereich = [{"s": 1.0, "uhr": "x", "art": "format",
                "text": "Hochformat 1080x1920 · Bereichsaufnahme der Bühne "
                        "· Aufnahme 527x937"}]
    assert ema_beitrag.zuschnitt_lage(bereich) == "fertig"
    assert ema_beitrag.zuschnitt(bereich) == "", \
        "eine schon zugeschnittene Aufnahme darf nicht ein zweites Mal beschnitten werden"
    assert ema_beitrag.zuschnitt([{"s": 1.0, "uhr": "x", "art": "bild",
                                   "text": "feld.png"}]) == ""
    print("✓ hochformat: 1080x1920 als Vorgabe, Zuschnittzeile aus der Marke")


def test_langer_befehl_wird_nicht_abgeschnitten():
    """Der gelbe Kasten hat rechts hinausgeragt, statt zu scrollen.

    Ursache war ein Flex-Element mit ``min-width:auto``: es durfte nicht
    schmaler werden als sein Inhalt. In einer Aufnahme ist das endgueltig --
    dort scrollt niemand nach, also muss umgebrochen werden.
    """
    h = open(os.path.join(HIER, "ema_studio.html"), encoding="utf-8").read()
    # Die GRUNDregel, nicht die Groessen der festen Buehne (`#buehne.fest .zeile.wz`).
    wz = h.split("\n  .zeile.wz{")[1].split("}")[0]
    assert "min-width:0" in wz, wz
    assert "white-space:pre-wrap" in wz and "overflow-wrap:anywhere" in wz, wz
    assert "white-space:pre;" not in wz and "overflow-x:auto" not in wz, wz
    pre = h.split("\n  .karte.erg pre{")[1].split("}")[0]
    assert "white-space:pre-wrap" in pre and "overflow-wrap:anywhere" in pre, pre
    karte = h.split("\n  .karte.erg{")[1].split("}")[0]
    assert "min-width:0" in karte, karte
    print("✓ codekasten: bricht um statt hinauszulaufen — beides nachgemessen")


def test_ungedeckte_zahlen():
    mat = "B_gap_T = 0.7994 T\nmax_safe_rpm = 12000 1/min\np = 4"
    # Runden ist erlaubt, erfinden nicht.
    assert ema_beitrag.ungedeckte_zahlen("0,80 T bei 12000 min-1", mat) == []
    assert ema_beitrag.ungedeckte_zahlen("0.7994 T", mat) == []
    assert ema_beitrag.ungedeckte_zahlen("340 Nm Spitzenmoment", mat) == ["340"]
    # Hashtags und Jahreszahlen sind keine Messwerte.
    assert ema_beitrag.ungedeckte_zahlen("#emaschine2026 im Jahr 2026", mat) == []
    print("✓ zahlen: gerundet ist gedeckt, erfunden nicht")


def test_x_haelt_seine_280_zeichen():
    lang = "Wort " * 200
    erg, verloren = ema_beitrag._x_teile(lang)
    # Zu lang heisst UMBRECHEN, nicht abschneiden: im ersten echten Lauf fiel
    # sonst ausgerechnet der Satz mit den verletzten Sicherheitskriterien weg.
    assert len(erg) == ema_beitrag.X_FADEN_MAX and verloren, erg
    assert all(len(t) <= ema_beitrag.GRENZE["x"] for t in erg), [len(t) for t in erg]
    assert "Wort Wort" in erg[1], "der zweite Teil traegt die Fortsetzung"
    kurz, verloren = ema_beitrag._x_teile("Ein kurzer Beitrag.")
    assert kurz == ["Ein kurzer Beitrag."] and not verloren
    faden, verloren = ema_beitrag._x_teile("eins\n---\nzwei\n---\ndrei\n---\nvier")
    assert faden == ["eins", "zwei", "drei"] and verloren, faden      # X_FADEN_MAX
    print(f"✓ x: gedeckelt auf {ema_beitrag.GRENZE['x']} Zeichen, "
          f"Faden auf {ema_beitrag.X_FADEN_MAX} Beitraege")


def test_entwurf_ohne_modell():
    """Der ganze Weg -- nur das Sprachmodell wird eingesetzt.

    So laeuft der Test auch ohne Ollama, und die Pruefung misst genau das, was
    dieses Modul tut: Material sammeln, Form halten, Zahlen nachmessen.
    """
    import ema_steckbrief
    pdir = ema_steckbrief.projekt_pfad("last")
    if not pdir:
        print("… entwurf: kein Projekt unter ~/cae_projekte — uebersprungen")
        return
    pid = os.path.basename(pdir.rstrip("/"))

    gesehen = {}
    def llm(system, nutzer):
        gesehen["system"], gesehen["nutzer"] = system, nutzer
        return _antwort("Ein Rotor. 4711 Nm sind es nicht.", alt="x.png :: Ein Bild")

    erg = ema_beitrag.erzeugen(pid, "x", llm=llm, ablage=False)
    assert erg["ok"], erg
    assert "nur Zahlen" in gesehen["system"].replace("NUR", "nur")
    assert len(erg["beitrag"]) <= ema_beitrag.GRENZE["x"]
    assert any("4711" in h for h in erg["hinweise"]), erg["hinweise"]
    assert erg["herkunft"], "Ohne Herkunftsfussnote ist der Entwurf nicht pruefbar"
    text = ema_beitrag.als_text(erg)
    assert "Veroeffentlicht wird hier nichts" in text
    # Ein Kanal, den es nicht gibt, wird abgewiesen -- nicht stillschweigend
    # nach Instagram umgebogen.
    assert not ema_beitrag.erzeugen(pid, "tiktok", llm=llm, ablage=False)["ok"]
    print(f"✓ entwurf: {pid} -> X-Beitrag, erfundene Zahl gemeldet")


def test_verb_ist_angemeldet():
    aus = subprocess.run([sys.executable, os.path.join(HIER, "cae_cli.py"),
                          "beitrag", "--help"], capture_output=True, text=True)
    assert aus.returncode == 0, aus.stderr
    for schalter in ("--from-project", "--bilder", "--ton", "--sprache", "--ohne-ablage"):
        assert schalter in aus.stdout, schalter
    hilfe = subprocess.run([sys.executable, os.path.join(HIER, "cae_cli.py"), "--help"],
                           capture_output=True, text=True).stdout
    assert "beitrag" in hilfe
    print("✓ verb: 'beitrag' ist angemeldet und in der Verbliste")


# ── 5. Eine Datei statt zweier Abschriften ──────────────────────────────────

GETEILT = ("lauschen", "verarbeiten", "verarbeitenStumm", "zugEnde", "anfuegen",
           "folgeUeberwachen", "gleitStart", "runter", "nachUnten", "uhrTick",
           "archivAuf", "archivZeigen", "videoStart", "videoStopp", "rekTaetig",
           "rekWache", "sichernJetzt", "arbeitTick", "freigeben")


def _inline(datei):
    h = open(os.path.join(HIER, datei), encoding="utf-8").read()
    i = h.index("<script>\n") + len("<script>\n")
    return h[i:h.rindex("</script>")]


def test_beide_seiten_teilen_dieselbe_datei():
    for datei in ("ema_agent.html", "ema_studio.html"):
        h = open(os.path.join(HIER, datei), encoding="utf-8").read()
        assert '<script src="/agent_gemein.js"></script>' in h, datei
        eigen = _inline(datei)
        for name in GETEILT:
            assert f"function {name}(" not in eigen, \
                f"{datei} schreibt {name} noch einmal ab"
    gemein = open(os.path.join(HIER, "agent_gemein.js"), encoding="utf-8").read()
    for name in GETEILT:
        assert f"function {name}(" in gemein, f"agent_gemein.js fehlt {name}"
    print(f"✓ geteilt: {len(GETEILT)} Funktionen genau einmal, in agent_gemein.js")


def test_seiten_bringen_mit_was_die_geteilte_datei_ruft():
    """Die geteilte Datei ruft in die Seite zurueck. Fehlt dort eine Funktion,
    faellt das erst im Betrieb auf -- und zwar mitten in einem Lauf."""
    pflicht = ("links", "kachelText", "kachelBild", "zustand", "denkenUm",
               "ordnerZeigen", "gesichertZeigen", "arbeitZeigen")
    for datei in ("ema_agent.html", "ema_studio.html"):
        eigen = _inline(datei)
        for name in pflicht:
            assert f"function {name}(" in eigen, f"{datei} fehlt {name}"
    # Und die Ids, die agent_gemein.js unbedingt braucht. ``p_gesichert`` steht
    # NICHT darunter: der Ablagepfad ist Sache der Seite (die Studioseite haengt
    # ihn an den Sicherungsknopf statt in eine eigene Fusszeile), und die
    # geteilte Datei fasst ihn deshalb nicht mehr an -- sie ruft
    # ``gesichertZeigen``, den beide Seiten haben.
    for datei in ("ema_agent.html", "ema_studio.html"):
        h = open(os.path.join(HIER, datei), encoding="utf-8").read()
        for kennung in ("p_uhr", "p_rek", "b_video", "archiv", "a_liste",
                        "a_titel", "a_wo", "a_hinweis", "a_links"):
            assert f'id="{kennung}"' in h, f"{datei} fehlt #{kennung}"
    geteilt = open(os.path.join(HIER, "agent_gemein.js"), encoding="utf-8").read()
    assert "p_gesichert" not in geteilt, \
        "agent_gemein.js darf kein seitenspezifisches Element anfassen"
    print(f"✓ rueckruf: beide Seiten bringen {len(pflicht)} Zeichenfunktionen mit")


def test_javascript_ist_syntaktisch_heil():
    """`node --check` ueber die geteilte Datei UND jede Seite mit ihr zusammen.

    Zusammen, weil beide klassische Skripte sind: eine zweite Deklaration
    desselben ``let`` im Seitenskript waere ein Fehler, den keine der Dateien
    fuer sich zeigt.
    """
    if not shutil_which("node"):
        print("… node fehlt — JS-Syntaxpruefung uebersprungen")
        return
    import tempfile
    gemein = open(os.path.join(HIER, "agent_gemein.js"), encoding="utf-8").read()
    with tempfile.TemporaryDirectory() as d:
        for datei in ("ema_agent.html", "ema_studio.html"):
            p = os.path.join(d, datei.replace(".html", ".js"))
            with open(p, "w", encoding="utf-8") as f:
                f.write(gemein + "\n" + _inline(datei))
            aus = subprocess.run(["node", "--check", p], capture_output=True, text=True)
            assert aus.returncode == 0, f"{datei}: {aus.stderr}"
    print("✓ javascript: agent_gemein.js + jede Seite fuer sich syntaktisch heil")


def shutil_which(name):
    import shutil
    return shutil.which(name)


def test_html_ist_ausgeglichen():
    """Jedes Element wird geschlossen, und keines zu oft.

    Nicht aus Ordnungsliebe: ein ueberzaehliges ``</div>`` schliesst im Browser
    still den naechsten Kasten darueber mit, und das faellt erst auf, wenn ein
    Bereich an der falschen Stelle endet. In ``ema_agent.html`` standen zwei
    davon, seit es die Seite gibt.
    """
    from html.parser import HTMLParser
    leer = {"meta", "link", "br", "hr", "img", "input", "source", "area",
            "base", "col", "embed", "param", "track", "wbr"}

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stapel, self.fehler = [], []

        def handle_starttag(self, t, a):
            if t not in leer:
                self.stapel.append((t, self.getpos()))

        def handle_endtag(self, t):
            if t in leer:
                return
            if not self.stapel:
                self.fehler.append(f"</{t}> ohne Anfang @{self.getpos()}")
                return
            offen, wo = self.stapel.pop()
            if offen != t:
                self.fehler.append(f"</{t}> schliesst <{offen}> von {wo} @{self.getpos()}")

    for datei in ("ema_agent.html", "ema_studio.html"):
        p = P()
        p.feed(open(os.path.join(HIER, datei), encoding="utf-8").read())
        assert not p.fehler, f"{datei}: {p.fehler[:3]}"
        assert not p.stapel, f"{datei}: nicht geschlossen {[t for t, _ in p.stapel]}"
    print("✓ html: beide Seiten sind ausgeglichen — kein ueberzaehliges </div>")


def test_studio_seite_gehoert_dem_studio_kopf():
    """Ueber den QR kommt die Seite als ``/studio?t=…`` herein -- ohne ``?kopf=``.

    Faellt sie dann auf 'pi' zurueck, treibt das Handy stillschweigend den
    falschen Agenten, und man sieht es an nichts.
    """
    h = open(os.path.join(HIER, "ema_studio.html"), encoding="utf-8").read()
    i, j = h.index('window.KOPF_VORGABE'), h.index('src="/agent_gemein.js"')
    assert i < j, "die Vorgabe muss VOR der geteilten Datei stehen"
    assert '"studio"' in h[i:i + 60], h[i:i + 60]
    gemein = open(os.path.join(HIER, "agent_gemein.js"), encoding="utf-8").read()
    assert "window.KOPF_VORGABE" in gemein
    # Und ema_agent.html setzt sie NICHT -- dort ist 'pi' der gewachsene Rueckfall.
    a = open(os.path.join(HIER, "ema_agent.html"), encoding="utf-8").read()
    assert "KOPF_VORGABE" not in a
    print("✓ kopfvorgabe: die Studio-Seite treibt den Studio-Kopf, auch ohne ?kopf=")


def test_studio_reiter_in_der_oberflaeche():
    h = open(os.path.join(HIER, "ema.html"), encoding="utf-8").read()
    assert "switchTab('studio')" in h and 'id="panel-agent-studio"' in h
    assert "'studio'" in h.split("const TABS =")[1].split("]")[0]
    assert "agent-rahmen-studio" in h
    # Der Rahmen zeigt auf die EIGENE Seite, nicht auf /agent.
    assert "'/studio?kopf=studio'" in h
    print("✓ oberflaeche: Reiter 📱 Studio verdrahtet")


def test_fussleiste_zeigt_wer_was_macht():
    """Zwei Zeilen, kein Pfad, und Lampen statt einer abgeschnittenen Zeile.

    Anlass: „das Eingabefeld unten ist im Studio-Modus noch nicht so schoen, die
    Pfadangaben koennen da weg, dann ist auch etwas mehr Platz fuer die Icons.
    Ich wuerde auch da gerne sehen, wer gerade was macht."
    """
    h = open(os.path.join(HIER, "ema_studio.html"), encoding="utf-8").read()
    eigen = _inline("ema_studio.html")

    # 1) Der Pfad ist aus der Leiste raus -- und nicht verloren.
    assert 'id="p_gesichert"' not in h, "der Ablagepfad steht wieder in der Leiste"
    assert "function pfadAnKnopf(" in eigen and "b_sichern" in eigen, \
        "er sitzt am Sicherungsknopf (title)"
    assert "a.hand" in eigen and "links('sys', '💾 gesichert" in eigen, \
        "und bei einer Sicherung VON HAND im Verlauf, wo er chronologisch hingehoert"

    # 2) Das Haekchen ist in die Arbeitszeile gezogen -- daher der Platz.
    assert 'class="arbeitzeile"' in h and 'class="denkwahl"' in h
    unten = h.split('<div id="unten">')[1].split("</div>\n</div>")[0]
    assert unten.count('<div id="rufhinweis"') == 1
    # Genau zwei tragende Zeilen: Arbeit und Eingabe (der Rufhinweis ist
    # ausgeblendet, bis jemand den Zwischenruf einschaltet).
    assert unten.count('class="arbeitzeile"') == 1
    assert unten.count('class="eingabezeile"') == 1

    # 3) Die Lampen -- gleiche Signatur wie am Schreibtisch, damit beide Seiten
    # gleich zu lesen sind.
    for datei in ("ema_agent.html", "ema_studio.html"):
        e = _inline(datei)
        assert "function lampe(an, symbol, kopf, text, klasse){" in e, datei
    for teil in ("'🤖', 'Agent'", "'⚙', 'Rechnung'", "'🌐', 'Recherche'",
                 "'🧮', 'Löser'", "'🖥', 'GPU'", "'🧠', 'Modell'",
                 "'⚡', 'Tempo'", "'🔧', 'Werkzeug'"):
        assert teil in eigen, f"Lampe fehlt: {teil}"
    # Keine Lampe „Modell denkt" -- Ollama meldet nur, was GELADEN ist.
    assert "denkt" not in eigen.split("function arbeitZeigen")[1][:3000]

    # 4) Die Schwellen kommen weiter aus der geteilten Datei, nicht aus einer
    # zweiten Zahl in der Seite.
    geteilt = open(os.path.join(HIER, "agent_gemein.js"), encoding="utf-8").read()
    assert "STILL_WARNUNG" in geteilt and "STILL_FREIGABE" in geteilt
    for name in ("STILL_WARNUNG", "STILL_FREIGABE"):
        assert f"const {name}" not in eigen and f"let {name}" not in eigen, \
            f"{name} ist in der Seite ein zweites Mal gesetzt"
    assert "freigeben()" in eigen, "die Freigabe ab STILL_FREIGABE bleibt erreichbar"

    # 5) Auf der festen Buehne haben die Lampen ihre eigene Groesse; am Handy
    # bleiben sie EINE wischbare Zeile (umbrechend waeren es gemessen sechs).
    assert "#buehne.fest .lampe{" in h
    assert "@media (max-width: 759px)" in h and "flex-wrap:nowrap" in h

    print("✓ fussleiste: zwei Zeilen, kein Pfad, acht Lampen — wer gerade was macht")


def test_bilder_und_video_im_verlauf():
    """Bilder auf Kachelbreite, Hoehe im Verhaeltnis — und die fertige Aufnahme.

    Anlass: „die Bilder werden im Studio-Tab nicht dargestellt, da sind dann nur
    Linien. Auch waere das fertige Video cool. Das Ganze muss natuerlich auf die
    korrekte Breite skaliert werden, auch ist die Hoehe im richtigen Verhaeltnis
    anzupassen."
    """
    h = open(os.path.join(HIER, "ema_studio.html"), encoding="utf-8").read()
    eigen = _inline("ema_studio.html")
    geteilt = open(os.path.join(HIER, "agent_gemein.js"), encoding="utf-8").read()

    # 1) DIE Ursache der „Linien": #strom ist eine Spalten-Flexbox, und deren
    # Kinder schrumpfen per Vorgabe, sobald der Verlauf laenger wird als die
    # Buehne. Ein <img> mit height:auto hat nichts, was das aufhaelt.
    assert "#strom > *{flex:0 0 auto}" in h, \
        "ohne das staucht der Browser die Bildkacheln zu Strichen"

    # 2) Breite von der Kachel, Hoehe aus dem Verhaeltnis — und beides braucht es.
    assert "width:100%;height:auto;background:#fff" in h.replace("\n", "").replace("  ", ""), \
        "width:100% fehlt (kleines Diagramm bliebe klein) oder height:auto (verzerrt)"
    # Der Deckel auf der Buehne darf nicht in die Breite ziehen.
    fest = h.split("#buehne.fest .karte.erg img,")[1][:220]
    assert "max-height:980px" in fest and "object-fit:contain" in fest, \
        "ohne object-fit zieht der Hoehendeckel ein hochkantes Bild in die Breite"

    # 3) Ein Bild, das nicht kommt, sagt das — sonst ist es von einem
    # gestauchten nicht zu unterscheiden.
    assert "Bild nicht abrufbar" in eigen and ".karte.erg .bildfehler" in h
    for datei in ("ema_agent.html", "ema_studio.html"):
        assert "Bild nicht abrufbar" in _inline(datei), datei

    # 4) Bild- UND Videoadresse gehen durch K(): vom Handy aus tragen sie damit
    # Kopf und Token wie jede andere Adresse.
    assert "K('/agent/bild/" in eigen, "die Bildadresse umgeht K()"
    assert "K('/agent/video/datei/" in eigen, "die Videoadresse umgeht K()"

    # 5) Die fertige Aufnahme ist ein Rueckruf der Seite, kein Sonderweg in der
    # geteilten Datei — und beide Seiten haben ihn.
    assert "nachAufnahmeEnde" in geteilt, "agent_gemein.js ruft ihn nicht"
    for datei in ("ema_agent.html", "ema_studio.html"):
        assert "function nachAufnahmeEnde(" in _inline(datei), datei
    assert "<video controls playsinline" in eigen
    assert ".karte.erg video{" in h and "#buehne.fest .karte.erg video" in h

    # 6) Und der Weg dorthin: die Route liefert die Datei, streng begrenzt.
    srv = open(os.path.join(HIER, "server.py"), encoding="utf-8").read()
    assert '@app.route("/agent/video/datei/<name>")' in srv
    block = srv.split('@app.route("/agent/video/datei/<name>")')[1][:1200]
    assert "_safe_name(name)" in block, "Pfadschutz fehlt"
    assert '(".webm", ".mp4")' in block, "jede Endung waere lieferbar"
    assert "conditional=True" in block, "ohne Bereichsanfragen kein Springen im Video"
    # Und ``beenden`` liefert den Dateinamen, damit die Seite keinen absoluten
    # Pfad zusammensetzen muss.
    ag = open(os.path.join(HIER, "ema_agent.py"), encoding="utf-8").read()
    assert '"datei": os.path.basename(self.pfad or "")' in ag

    # 7) Aufgenommen wird die BUEHNE, nicht der Reiter.
    assert "function aufnahmeOptionen(" in eigen, \
        "ohne preferCurrentTab gibt es nichts, worauf ein Zuschnitt sich bezieht"
    for teil in ("preferCurrentTab: true", "selfBrowserSurface", "surfaceSwitching"):
        assert teil in eigen, teil
    # Zwei Verfahren, und die Reihenfolge ist nicht beliebig: restrictTo nimmt
    # NUR den Teilbaum auf (Verdeckendes ist nicht im Bild), cropTo schneidet das
    # Reiterbild zu. Also erst das schaerfere.
    assert "RestrictionTarget.fromElement(buehne)" in eigen
    assert "CropTarget.fromElement(buehne)" in eigen
    assert eigen.index("restrictTo") < eigen.index("spur.cropTo"), \
        "Element- vor Bereichsaufnahme"
    # Geprueft wird an der SPUR: die Methoden haengen an
    # BrowserCaptureMediaStreamTrack, nicht an MediaStreamTrack.prototype —
    # gemessen ist letzteres undefined, waehrend die Spur sie hat.
    assert "typeof spur.restrictTo === 'function'" in eigen
    assert "typeof spur.cropTo === 'function'" in eigen
    assert "aufnahmeOptionen" in geteilt and "await nachAufnahmeStart" in geteilt, \
        "der Zuschnitt muss VOR dem ersten aufgezeichneten Bild stehen"
    # Und er steht vor REK.start(), nicht davor oder danach irgendwo.
    vor = geteilt.split("REK.start(VIDEO_STUECK_MS)")[0]
    assert "await nachAufnahmeStart(strom)" in vor, \
        "sonst liegen die ersten Sekunden ungeschnitten in der Datei"
    assert "new MediaRecorder" in vor.split("await nachAufnahmeStart")[0], \
        "rekTaetig schreibt seine Marke nur, wenn es schon einen Recorder gibt"
    # Der Browser, der es nicht kann, bekommt einen Satz statt eines stillen
    # Reiter-Mitschnitts. Und der, der es kann, auch — sonst weiss niemand, was
    # gerade aufs Band geht.
    assert "keinen Bereich aufnehmen" in eigen
    assert "aufgenommen wird nur die Bühne" in eigen
    # Beide Verfahren tragen dasselbe Wort in die Marke, damit zuschnitt_lage
    # nicht zwei Muster kennen muss.
    assert "Bereichsaufnahme der Bühne" in eigen
    assert ema_beitrag.zuschnitt_lage([{"s": 0.0, "uhr": "x", "art": "format",
        "text": "Hochformat 1080x1920 · Bereichsaufnahme der Bühne "
                "(Elementaufnahme) · Aufnahme 506x900"}]) == "fertig"

    # 8) Eine Seite, die offen bleibt, waehrend an ihr gearbeitet wird, sagt es.
    # Genau das fehlte: die Bereichsaufnahme war um 10:19 gebaut, der Mitschnitt
    # um 10:27 nahm den ganzen Reiter auf, weil der Reiter seit 09:44 offen war.
    assert "function seiteVeraltet(" in geteilt
    assert "seiteVeraltet(d.seite)" in geteilt, "wird nie gerufen"
    assert "SEITE_GEMELDET" in geteilt, "sonst steht der Hinweis im Sekundentakt da"
    srv2 = open(os.path.join(HIER, "server.py"), encoding="utf-8").read()
    assert 'stand["seite"] = ema_werkzeugstand.stand_oberflaeche()["hash"]' in srv2
    import ema_werkzeugstand
    assert "ema_studio.html" in ema_werkzeugstand.OBERFLAECHE
    # GETRENNT von PHYSIK: ein Knopfumbau darf nicht wie eine Modelaenderung
    # aussehen.
    assert not (set(ema_werkzeugstand.OBERFLAECHE) & set(ema_werkzeugstand.PHYSIK))

    print("✓ bilder/video: volle Kachelbreite, Hoehe im Verhaeltnis, Aufnahme "
          "abspielbar — und aufgenommen wird die Bühne, nicht der Reiter")


if __name__ == "__main__":
    test_dritter_kopf()
    test_systemzusatz_je_kopf()
    test_projektakte_gehoert_dem_ersten()
    test_tokenwache()
    test_zugang_traegt_qr_oder_sagt_es()
    test_marken_und_schnitt_sind_dieselbe_gruppierung()
    test_clips_lesen_die_geschriebene_liste()
    test_markdown()
    test_markdown_bleibt_stehen()
    test_ausgerichtete_ausgabe_wird_eingepasst()
    test_hochformat_und_zuschnitt()
    test_langer_befehl_wird_nicht_abgeschnitten()
    test_ungedeckte_zahlen()
    test_x_haelt_seine_280_zeichen()
    test_entwurf_ohne_modell()
    test_verb_ist_angemeldet()
    test_beide_seiten_teilen_dieselbe_datei()
    test_seiten_bringen_mit_was_die_geteilte_datei_ruft()
    test_javascript_ist_syntaktisch_heil()
    test_html_ist_ausgeglichen()
    test_studio_seite_gehoert_dem_studio_kopf()
    test_studio_reiter_in_der_oberflaeche()
    test_fussleiste_zeigt_wer_was_macht()
    test_bilder_und_video_im_verlauf()
    print("\nALLE STUDIO-TESTS BESTANDEN ✅")
