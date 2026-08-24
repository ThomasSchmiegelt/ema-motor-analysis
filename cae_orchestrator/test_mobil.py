"""Tests fuer den Handy-Pfad (``ema_mobil``).

Der wichtigste Test ist ``test_legs_js_gegen_python``: Handy und Schreibtisch zeichnen
in derselben Konvention, rechnen die Zeichnung aber in ZWEI Umsetzungen in
``customLegs`` um — einmal JavaScript in ``ema_mobil.html``, einmal Python in
``ema_mobil.py``, beide zeichengetreu aus ``ema.html:5570-5590``. Laufen die
auseinander, liefert dieselbe Zeichnung stillschweigend zwei verschiedene Maschinen,
und beide Ergebnisse sehen plausibel aus. Genau das faengt der Test ab.

Lauf: ``python test_mobil.py``  (kein Server noetig, kein FreeCAD, kein Elmer)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

import ema_mobil

_fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")
        _fails.append(name)


# Ein Halbpol, der jeden Zweig der Umrechnung trifft:
#   [0] schraeg, versetzt          -> wird gespiegelt
#   [1] auf der d-Achse            -> wird NICHT gespiegelt (off<0.5 und ang<2)
#   [2] deckungsgleich mit [0]     -> muss entdoppelt werden
#   [3] nur knapp neben der Achse  -> wird gespiegelt (off ueber der Schwelle)
HALBPOL = [
    {"r": 45.0, "off":  8.0, "ang":  25.0, "len": 30.0, "thick": 6.0, "pol":  1},
    {"r": 62.0, "off":  0.2, "ang":   1.0, "len": 18.0, "thick": 5.0, "pol": -1},
    {"r": 45.0, "off":  8.0, "ang":  25.0, "len": 30.0, "thick": 9.9, "pol":  1},
    {"r": 70.0, "off":  0.6, "ang":   0.5, "len": 12.0, "thick": 4.0, "pol":  1},
]


def test_legs_festwert():
    """Die Umrechnung gegen einen von Hand nachvollzogenen Festwert."""
    print("1. Halbpol -> customLegs (Festwert)")
    legs = ema_mobil.legs_aus_halbpol(HALBPOL)
    check("Anzahl stimmt (2 + 1 + 0 + 2 = 5)", len(legs) == 5, f"{len(legs)}")
    check("Spiegel-Leg hat negatives offset und negative Neigung",
          any(abs(l["offset"] + 8.0) < 1e-9 and abs(l["tilt_deg"] + 25.0) < 1e-9 for l in legs))
    achs = [l for l in legs if abs(l["r_pos"] - 62.0) < 1e-9]
    check("Leg auf der d-Achse wird NICHT gespiegelt", len(achs) == 1, f"{len(achs)}")
    check("deckungsgleiches Leg entdoppelt (thickness aendert den Schluessel nicht)",
          sum(1 for l in legs if abs(l["r_pos"] - 45.0) < 1e-9 and l["offset"] > 0) == 1)
    knapp = [l for l in legs if abs(l["r_pos"] - 70.0) < 1e-9]
    check("Leg knapp neben der Achse WIRD gespiegelt", len(knapp) == 2, f"{len(knapp)}")
    check("Polung wandert unveraendert mit",
          all(l["mag_sign"] in (1, -1) for l in legs))
    check("Schluesselnamen sind die des Loesers",
          set(legs[0]) == {"r_pos", "offset", "tilt_deg", "length", "thickness", "mag_sign"},
          str(sorted(legs[0])))


_JS_HILFE = """
const magnete = JSON.parse(process.argv[2]);
%s
console.log(JSON.stringify(legsAusHalbpol(magnete)));
"""


def _js_funktion_aus_html() -> str | None:
    """Schneidet ``legsAusHalbpol`` aus der Handyseite heraus."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ema_mobil.html")
    with open(p, encoding="utf-8") as f:
        s = f.read()
    a = s.find("function legsAusHalbpol(")
    if a < 0:
        return None
    # bis zur schliessenden Klammer auf Spaltenanfang
    e = s.find("\n}", a)
    return s[a:e + 2] if e > 0 else None


def test_legs_js_gegen_python():
    """DER Test: beide Umsetzungen muessen bitgleich dasselbe liefern."""
    print("2. Halbpol -> customLegs: JavaScript == Python")
    node = shutil.which("node") or shutil.which("nodejs")
    js = _js_funktion_aus_html()
    if js is None:
        check("legsAusHalbpol in ema_mobil.html gefunden", False)
        return
    check("legsAusHalbpol in ema_mobil.html gefunden", True)
    if not node:
        print("  – JS-Vergleich uebersprungen (kein node installiert)")
        return
    with tempfile.TemporaryDirectory() as d:
        skript = os.path.join(d, "l.js")
        with open(skript, "w", encoding="utf-8") as f:
            f.write(_JS_HILFE % js)
        r = subprocess.run([node, skript, json.dumps(HALBPOL)],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            check("node laeuft durch", False, r.stderr[:200])
            return
        aus_js = json.loads(r.stdout)
    aus_py = ema_mobil.legs_aus_halbpol(HALBPOL)
    check("gleiche Anzahl", len(aus_js) == len(aus_py), f"{len(aus_js)} vs {len(aus_py)}")
    check("gleiche Reihenfolge und Werte", aus_js == aus_py,
          f"\n      JS: {json.dumps(aus_js)[:220]}\n      PY: {json.dumps(aus_py)[:220]}")


def test_geom_aus_entwurf():
    print("3. Entwurf -> geom")
    g = ema_mobil.geom_aus_entwurf({
        "masse": {"statorOD": 280, "rotorOD": 188.6, "shaftD": 60, "p": 3, "slots": 36,
                  "unbekannt": 1},
        "magnete": HALBPOL, "barrieren": [{"pts": [[40, 3], [70, 9]], "width": 3.0}]})
    check("magShape ist custom", g["magShape"] == "custom")
    check("nur bekannte Masse wandern mit", "unbekannt" not in g)
    check("customLegs vorhanden", len(g["customLegs"]) == 5)
    check("Barrieren werden gespiegelt", len(g["customBarriers"]) == 2)
    check("gespiegelte Barriere hat negative y", g["customBarriers"][1]["pts"][0][1] == -3)
    # Der Grund steht in ema.html:5598-5602: parametrische Sperren wuerden ZUSAETZLICH
    # zur gezeichneten Geometrie erscheinen.
    check("parametrische Flusssperren und Wuchtbohrungen abgeschaltet",
          g["genFluxBarrierQ"] is False and g["genFluxBarrierD"] is False
          and g["genBalanceBolts"] is False)


def test_pruefung():
    print("4. Nutzlastpruefung (weist ab, statt zu klemmen)")
    gut = {"geom": {"statorOD": 280}, "punkte": [{"rpm": 5000, "load_nm": 5}],
           "N": 180, "out_px": 800}
    a, m = ema_mobil.pruefe_anfrage(gut)
    check("gueltige Anfrage geht durch", m is None, str(m))
    check("Vorgaben normalisiert", a["punkte"][0]["rpm"] == 5000.0)

    for name, roh, teil in [
        ("geom fehlt",          {"punkte": [{"rpm": 1}]},                          "geom"),
        ("punkte fehlt",        {"geom": {"a": 1}},                                "punkte"),
        ("zu viele Punkte",     {"geom": {"a": 1}, "punkte": [{"rpm": 1}] * 9},    "höchstens"),
        ("N zu gross",          dict(gut, N=400),                                  "N 400"),
        ("N zu klein",          dict(gut, N=10),                                   "N 10"),
        ("out_px zu gross",     dict(gut, out_px=4000),                            "out_px"),
        ("Drehzahl negativ",    dict(gut, punkte=[{"rpm": -5, "load_nm": 5}]),     "rpm"),
        ("Last unsinnig",       dict(gut, punkte=[{"rpm": 5000, "load_nm": 1e9}]), "load_nm"),
        ("rpm keine Zahl",      dict(gut, punkte=[{"rpm": "viel", "load_nm": 5}]), "numerisch"),
    ]:
        _, meldung = ema_mobil.pruefe_anfrage(roh)
        check(f"abgewiesen: {name}", bool(meldung) and teil in meldung, f"-> {meldung!r}")


def test_duenne_geom_wird_aufgefuellt():
    """Ein Client, der nur seine elf Felder schickt, muss trotzdem rechnen koennen.

    Gefunden beim End-to-End-Lauf, nicht von den Unit-Tests: ``magnet_legs`` liest
    auch bei ``magShape:"custom"`` parametrische Werte (``KeyError: 'magThick'``).
    Die Handyseite baut ihr ``geom`` selbst und kennt diese Schluessel nicht."""
    print("4b. Duenne Geometrie wird serverseitig vervollstaendigt")
    duenn = {"statorOD": 280, "rotorOD": 188.6, "shaftD": 60, "magShape": "custom",
             "customLegs": [{"r_pos": 55, "offset": 9, "tilt_deg": 25,
                             "length": 35, "thickness": 6, "mag_sign": 1}]}
    a, m = ema_mobil.pruefe_anfrage({"geom": duenn, "punkte": [{"rpm": 5000, "load_nm": 5}]})
    check("Anfrage geht durch", m is None, str(m))
    g = a["geom"]
    check("magThick nachgefuellt", "magThick" in g, sorted(g)[:8])
    fehlend = [k for k in ema_mobil.basis_geom() if k not in g]
    check("kein Basisschluessel fehlt", not fehlend, str(fehlend))
    check("Clientwerte gewinnen", g["statorOD"] == 280 and g["magShape"] == "custom")
    check("customLegs unangetastet", len(g["customLegs"]) == 1)


def test_token():
    print("5. Token")
    t = ema_mobil.token()
    check("Token wird erzeugt und ist nicht trivial", isinstance(t, str) and len(t) >= 16, t[:6])
    check("Token ist stabil ueber Aufrufe", ema_mobil.token() == t)
    check("richtiges Token wird angenommen", ema_mobil.token_ok(t))
    check("falsches Token wird abgelehnt", not ema_mobil.token_ok(t[:-1] + ("x" if t[-1] != "x" else "y")))
    check("leeres Token wird abgelehnt", not ema_mobil.token_ok("") and not ema_mobil.token_ok(None))
    p = ema_mobil._token_pfad()
    check("Datei ist nur fuer den Eigentuemer lesbar",
          (os.stat(p).st_mode & 0o077) == 0, oct(os.stat(p).st_mode))


def test_lan():
    print("6. Adresse im Heimnetz")
    ip = ema_mobil.lan_adresse()
    check("ist eine IPv4", ip.count(".") == 3, ip)
    # Der Grund steht im Docstring: docker0 (172.17) und die Bridge (172.18) duerfen
    # NICHT gewaehlt werden, sonst zeigt der QR-Code ins Nichts.
    check("keine Docker-Adresse", not ip.startswith("172.1"), ip)
    url = ema_mobil.einstieg_url()
    check("Einstiegs-URL traegt Adresse, Port und Token",
          url.startswith("http://" + ip + ":5000/m?t=") and ema_mobil.token() in url, url)


def test_routen():
    print("7. Routen (Flask-Testclient, ohne echten Server)")
    import server
    c = server.app.test_client()
    t = ema_mobil.token()

    r = c.get("/m")
    check("/m ohne Token -> 401", r.status_code == 401, str(r.status_code))
    r = c.get("/m/schema", headers={"X-Mobil-Token": "falsch"})
    check("/m/schema mit falschem Token -> 401", r.status_code == 401, str(r.status_code))
    r = c.get("/m/schema", headers={"X-Mobil-Token": t})
    check("/m/schema mit Token -> 200", r.status_code == 200, str(r.status_code))
    if r.status_code == 200:
        d = r.get_json()
        check("Schema traegt genau die Felder der App",
              d["felder"] == ema_mobil.ALLE_FELDER, str(d.get("felder"))[:150])
        check("der abgeleitete Luftspalt ist dabei",
              "airGap" in d["params"] and "statorID" not in d["params"],
              str(sorted(d["params"]))[:150])
        check("Schema traegt die Grenzen", d["grenzen"]["N_MAX"] == ema_mobil.N_MAX)
        fehlend = [k for k in d["felder"] if k not in d["params"]]
        check("jedes Feld hat einen Schemaeintrag", not fehlend, str(fehlend))

    r = c.get("/m/manifest.webmanifest")
    check("Manifest ohne Token erreichbar (sonst keine App-Installation)",
          r.status_code == 200, str(r.status_code))
    r = c.get("/m/sw.js")
    check("Service Worker wird nicht gecacht ausgeliefert",
          r.status_code == 200 and "no-cache" in r.headers.get("Cache-Control", ""),
          r.headers.get("Cache-Control"))
    r = c.get("/m/../server.py")
    check("kein Verzeichniswechsel", r.status_code in (404, 308), str(r.status_code))

    r = c.post("/m/punkte", json={"geom": {}, "punkte": []})
    check("/m/punkte ohne Token -> 401", r.status_code == 401, str(r.status_code))
    r = c.post("/m/punkte", headers={"X-Mobil-Token": t}, json={"punkte": [{"rpm": 1}]})
    check("/m/punkte ohne geom -> 400", r.status_code == 400, str(r.status_code))

    server._state["status"] = "running"
    try:
        r = c.post("/m/punkte", headers={"X-Mobil-Token": t},
                   json={"geom": {"statorOD": 1}, "punkte": [{"rpm": 1, "load_nm": 1}]})
        check("waehrend eines Schreibtischlaufs -> 409", r.status_code == 409, str(r.status_code))
    finally:
        server._state["status"] = "idle"

    r = c.get("/m/zugang", environ_overrides={"REMOTE_ADDR": "192.168.178.99"})
    check("/m/zugang von fremder Adresse -> 403", r.status_code == 403, str(r.status_code))
    r = c.get("/m/zugang", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    check("/m/zugang lokal -> 200 mit URL", r.status_code == 200 and "url" in r.get_json())


def test_echte_rechnung():
    """Ein echter Punkt durch den Loeser — grob, aber es muss durchlaufen."""
    print("8. Eine echte Punktrechnung (klein, ~1 s)")
    import server
    c = server.app.test_client()
    entwurf = {
        "masse": {"statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60,
                  "slots": 36, "p": 3, "slotDepth": 25, "airGap": 0.7,
                  "conductorsPerSlot": 4, "magGapMm": 0.1, "axialLen": 120},
        "magnete": [{"r": 55.0, "off": 9.0, "ang": 25.0, "len": 35.0, "thick": 6.0, "pol": 1}],
        "barrieren": []}
    rumpf = {"geom": ema_mobil.geom_aus_entwurf(entwurf), "axial_len": 120,
             "magnet": "ndfeb_n50", "punkte": [{"rpm": 5000, "load_nm": 5}],
             "N": 70, "out_px": 320, "rotor_angle_deg": 0}
    r = c.post("/m/punkte", headers={"X-Mobil-Token": ema_mobil.token()}, json=rumpf)
    check("HTTP 200", r.status_code == 200, str(r.status_code))
    if r.status_code != 200:
        return
    check("NDJSON-Inhaltstyp", "x-ndjson" in r.headers.get("Content-Type", ""),
          r.headers.get("Content-Type"))
    zeilen = [json.loads(z) for z in r.get_data(as_text=True).strip().split("\n") if z.strip()]
    check("Startzeile + eine Punktzeile", len(zeilen) == 2, str(len(zeilen)))
    if len(zeilen) != 2:
        print("      " + str(zeilen)[:400]); return
    kopf, punkt = zeilen
    check("Startzeile meldet B_gap", kopf["art"] == "start" and kopf["b_gap_T"] > 0,
          str(kopf)[:160])
    check("Punkt gerechnet, nicht gescheitert", punkt["art"] == "punkt",
          str(punkt.get("fehler"))[:200])
    if punkt["art"] != "punkt":
        return
    for k in ("png_b64", "B_gap_T", "iq", "id", "rpm", "dauer_s"):
        check(f"Punkt traegt {k}", k in punkt)
    kb = len(punkt["png_b64"]) / 1024
    # Gemessen: 268 kB bei 320 px, 459 kB bei 640 px (Vorgabe), 889 kB bei 1000 px.
    # Der Test haelt fest, dass out_px WIRKT — ohne Durchreichen laege der Boden bei
    # 1000 px (ema_pipeline.render_preview_frame) und damit bei ~890 kB je Punkt.
    check("out_px wirkt (320 px deutlich unter dem 1000-px-Boden)", kb < 350, f"{kb:.0f} kB")
    print(f"      gemessen: {punkt['dauer_s']} s, {kb:.0f} kB base64 bei N=70/320 px")


def test_punkte_unterscheiden_sich():
    """Die VORGABE-Punkte muessen vier verschiedene Arbeitspunkte ergeben.

    Und der Grund, warum das ueber die Last laufen MUSS, wird gleich mitgeprueft:
    unterhalb der Eckdrehzahl haengen i_q/i_d allein am Moment. Gemessen an der
    Beispielmaschine liegt die Eckdrehzahl bei ~52 800 min-1 — bei 1000…20000 min-1
    und konstant 5 Nm kommt viermal derselbe Punkt heraus. Der erste Entwurf hatte
    genau diese Vorgabe und lieferte vier identische Bilder."""
    print("9. Vorgabepunkte -> vier verschiedene Arbeitspunkte")
    entwurf = {
        "masse": {"statorOD": 280, "rotorOD": 188.6, "shaftD": 60, "slots": 36, "p": 3,
                  "slotDepth": 25, "airGap": 0.7, "conductorsPerSlot": 4,
                  "magGapMm": 0.1, "axialLen": 120},
        "magnete": [{"r": 55.0, "off": 9.0, "ang": 25.0, "len": 35.0, "thick": 6.0, "pol": 1}],
        "barrieren": []}
    geom = ema_mobil.geom_aus_entwurf(entwurf)

    a, m = ema_mobil.pruefe_anfrage({
        "geom": geom, "magnet": "ndfeb_n50",
        "punkte": [dict(p) for p in ema_mobil.PUNKTE_DEFAULT],
        "N": 60, "out_px": 200})
    check("Vorgabe ist gueltig", m is None, str(m))
    saetze = list(ema_mobil.rechne_punkte(a))
    kopf = saetze[0]
    punkte = [x for x in saetze if x["art"] == "punkt"]
    check("alle vier gerechnet", len(punkte) == 4, str(len(punkte)))
    if len(punkte) != 4:
        return
    check("Startzeile meldet die Eckdrehzahl", kopf.get("rpm_base", 0) > 0, str(kopf.get("rpm_base")))
    iqs = [p["iq"] for p in punkte]
    check("i_q unterscheidet sich ueber die Punkte", len(set(iqs)) > 1, str(iqs))
    check("weniger Moment -> weniger Strom", iqs[-1] < iqs[0], f"{iqs[0]} -> {iqs[-1]}")
    check("die Feldbilder sind verschieden",
          len({p["png_b64"][:400] for p in punkte}) == 4)
    print(f"      Last {[p['load_nm'] for p in punkte]} Nm -> i_q {iqs}")

    # Die Physik dahinter, damit niemand die Vorgabe versehentlich auf feste Last
    # zurueckdreht: gleiche Last unter der Eckdrehzahl == gleicher Punkt.
    b, m2 = ema_mobil.pruefe_anfrage({
        "geom": geom, "magnet": "ndfeb_n50",
        "punkte": [{"rpm": r, "load_nm": 5} for r in (1000, 5000, 15000, 20000)],
        "N": 60, "out_px": 200})
    saetze2 = list(ema_mobil.rechne_punkte(b))
    kopf2 = saetze2[0]
    p2 = [x for x in saetze2 if x["art"] == "punkt"]
    check("Server meldet: alle unter der Eckdrehzahl", kopf2["alle_unter_eck"] is True)
    check("Server meldet: gleiche Last", kopf2["gleiche_last"] is True)
    check("und dann sind die Stroeme tatsaechlich gleich (Physik, kein Fehler)",
          len({x["iq"] for x in p2}) == 1, str([x["iq"] for x in p2]))


if __name__ == "__main__":
    for t in (test_legs_festwert, test_legs_js_gegen_python, test_geom_aus_entwurf,
              test_pruefung, test_duenne_geom_wird_aufgefuellt, test_token, test_lan, test_routen, test_echte_rechnung,
              test_punkte_unterscheiden_sich):
        t()
    print()
    if _fails:
        print(f"FEHLGESCHLAGEN: {len(_fails)}  ->  " + ", ".join(_fails))
        sys.exit(1)
    print("Alle Pruefungen bestanden.")
