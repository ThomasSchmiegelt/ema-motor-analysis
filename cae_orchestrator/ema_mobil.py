"""Handy-Pfad: Maße eingeben, Halbpol zeichnen, vier Betriebspunkte rechnen.

Ein bewusst schmaler zweiter Bedienweg neben ``ema.html``. Warum eine eigene Seite und
nicht die vorhandene responsiv gemacht: ``ema.html`` hat auf 643 kB **null**
``@media``-Regeln, ein Layout aus Splittern und festen Seitenbereichen, und sein Designer
hört nur auf Maus-Ereignisse. Ein Umbau hätte den funktionierenden Schreibtischpfad
gefährdet. Geteilt wird deshalb nicht Code, sondern das **Datenmodell** (``customLegs``)
und der **Löser**.

Was dieses Modul dem Server hinzufügt:

* ``GET  /m``            die Handyseite
* ``GET  /m/<datei>``    Manifest, Service Worker, Symbole
* ``GET  /m/schema``     der Ausschnitt aus ``/param_schema``, den die App zeigt
* ``POST /m/punkte``     die Stapelrechnung (NDJSON, eine Zeile je fertigem Punkt)
* ``GET  /m/zugang``     Einstiegs-URL + Token + QR — **nur von localhost aus**

Drei Entscheidungen, die beim Bau gemessen und nicht geraten wurden:

1. **``out_px`` muss durchgereicht werden.** ``ema_pipeline.render_preview_frame`` hat
   den harten Boden ``out_px = min(5000, max(1000, N))`` — auf ein Handydisplay gehen
   ~640 px. Deshalb ruft dieses Modul ``_field_frame`` direkt und deckelt bei
   ``OUT_PX_MAX``. Gemessen an der Delta-IPM bei N=180 (Rechenzeit / Antwortgröße
   base64-PNG je Punkt):

   ===========  ==========  =============
   ``out_px``   Zeit        Größe
   ===========  ==========  =============
   640          2,33 s      **459 kB**
   800          2,39 s      640 kB
   1000         2,48 s      889 kB
   ===========  ==========  =============

   Die Rechenzeit hängt fast nur an ``N``, die Übertragung fast nur an ``out_px``.
   Vier Punkte bei der Vorgabe kosten also rund 10 s und 1,8 MB statt 3,6 MB.
2. **Ein ``B_gap``-Vorlauf für alle vier Punkte statt vier.** ``render_preview_frame``
   rechnet je Aufruf einen eigenen groben Lauf für die dq-Stromschätzung. Bei vier Punkten
   derselben Geometrie ist das dreimal dieselbe Zahl.
3. **``N`` gedeckelt.** Gemessen (echte Delta-IPM, 36 Nuten, 3 Polpaare):
   N=140 → 1,23 s · N=200 → 2,84 s · N=300 → 7,60 s. Über 260 wird ein Vierersatz
   unzumutbar lang, deshalb ``N_MAX``.

Zugang: ein gemeinsames Token, kein Benutzerkonto. Es hält Gelegenheitszugriffe im WLAN
draußen, ohne TLS oder Benutzerverwaltung einzuführen. Die **bestehenden** Routen bleiben
unverändert offen — sie jetzt abzusichern wäre eine eigene, größere Entscheidung und würde
``ema.html`` und ``cae_cli.py`` brechen.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import socket
import time

MOBIL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mobil")

# Deckel für den mobilen Pfad. Beide sind Zumutbarkeitsgrenzen, keine technischen:
# der Löser kann mehr, ein Handy über WLAN will es nicht.
N_MAX      = 260     # gemessen: N=300 kostet 7,6 s je Punkt = 30 s je Vierersatz
N_DEFAULT  = 180
OUT_PX_MAX = 1200
OUT_PX_DEF = 640
PUNKTE_MAX = 8       # die App zeigt vier; mehr wäre auf dem Display sinnlos

# Vorgabe der vier Betriebspunkte: eine **Momenten-Drehzahl-Linie**, nicht vier
# Drehzahlen bei gleichem Moment.
#
# Der Grund ist gemessen und wichtig genug, um hier zu stehen: das 2D-Feld bei festem
# Rotorwinkel haengt nur von (i_q, i_d) ab, und die kommen unterhalb der Eckdrehzahl
# ALLEIN aus dem Moment — die Drehzahl geht erst ein, wenn die Spannungsgrenze
# Feldschwaechung erzwingt. Fuer die Beispielmaschine (800 V, EMK 3,5 V bei
# 1000 min-1) liegt die Eckdrehzahl bei rund **52 800 min-1**; bei 1000…20000 min-1
# und konstant 5 Nm liefert ``estimate_dq_currents`` deshalb VIERMAL i_q 125,5 /
# i_d -65,1 — vier identische Feldbilder. Ueber die Last aendert sich dagegen alles
# (i_q 77 bei 0 Nm bis 664 bei 300 Nm, gemessen bei 5000 min-1).
#
# Die Vorgabe faehrt deshalb die uebliche Auslegungslinie ab: viel Moment bei wenig
# Drehzahl, wenig Moment bei viel Drehzahl. Die Drehzahlen sind die der KI-Auslegung
# (ema_design_ai.RANGED_RPM_LIST), die Momente eine abfallende Rampe.
PUNKTE_DEFAULT = [
    {"rpm": 1000.0,  "load_nm": 300.0},
    {"rpm": 5000.0,  "load_nm": 200.0},
    {"rpm": 15000.0, "load_nm": 80.0},
    {"rpm": 20000.0, "load_nm": 40.0},
]
RPM_DEFAULT = [p["rpm"] for p in PUNKTE_DEFAULT]     # rueckwaertskompatibel


def eckdrehzahl(geom: dict, b_gap_t: float) -> float:
    """Die Drehzahl, ab der die Spannungsgrenze Feldschwaechung erzwingt.

    Dieselbe Formel, die ``estimate_dq_currents`` intern benutzt, wenn kein
    ``rpm_base`` uebergeben wird — hier herausgezogen, damit die App dem Nutzer
    sagen kann, WARUM sich unterhalb davon bei gleichem Moment nichts aendert.
    """
    import math
    import ema_analysis
    emf1 = ema_analysis.compute_performance(geom, b_gap_t, 1000.0)["emf_peak_V"]
    if emf1 <= 0:
        return 0.0
    return 1000.0 * 0.4 * (ema_analysis.INVERTER_V_DC / math.sqrt(3)) / emf1


# ── Token ─────────────────────────────────────────────────────────────────────

def _token_pfad() -> str:
    from server import PROJECTS_ROOT
    return os.path.join(PROJECTS_ROOT, "_session", "mobil_token")


def token() -> str:
    """Das gemeinsame Geheimnis; wird beim ersten Zugriff erzeugt und bleibt liegen.

    Datei statt Prozessvariable, damit ein Serverneustart den Startbildschirm-Eintrag
    auf dem Handy nicht entwertet. Zurücksetzen = Datei löschen.
    """
    p = _token_pfad()
    try:
        with open(p, encoding="utf-8") as f:
            t = f.read().strip()
        if t:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(16)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(t)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return t


def token_ok(mitgeschickt: str | None) -> bool:
    """Vergleich in konstanter Zeit — sonst verrät die Antwortzeit das Token Zeichen
    für Zeichen. Kostet nichts und erspart eine peinliche Fußnote."""
    if not mitgeschickt:
        return False
    return hmac.compare_digest(str(mitgeschickt), token())


# ── Adresse im Heimnetz ───────────────────────────────────────────────────────

def lan_adresse() -> str:
    """Die IPv4-Adresse, unter der das Handy den Server erreicht.

    Zwei Fallstricke, beide hier gemessen:

    * **Nicht den Rechnernamen nehmen.** An einer Fritz!Box löst ``<name>.fritz.box``
      auf — aber ausschließlich auf **IPv6**. Flask bindet mit ``host="0.0.0.0"`` nur
      auf IPv4; ein Handy, das den Namen auflöst, läuft ins Leere.
    * **Nicht die erste Adresse nehmen.** Auf dieser Maschine gibt es neben dem WLAN
      noch ``docker0`` (172.17.0.1) und eine Bridge (172.18.0.1). Deshalb wird die
      Adresse über die tatsächlich benutzte Route bestimmt: ein UDP-Socket wird zum
      Standard-Gateway "verbunden" (schickt kein Paket) und seine lokale Adresse
      ausgelesen — das ist genau die, die auch der echte Verkehr trüge.
    """
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("192.168.178.1", 9))     # Fritz!Box-Vorgabe; irgendein Ziel genügt
        return s.getsockname()[0]
    except OSError:
        pass
    finally:
        if s is not None:
            s.close()
    for ziel in ("8.8.8.8", "1.1.1.1"):
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.3)
            s.connect((ziel, 9))
            return s.getsockname()[0]
        except OSError:
            continue
        finally:
            if s is not None:
                s.close()
    return "127.0.0.1"


def einstieg_url(port: int = 5000) -> str:
    return f"http://{lan_adresse()}:{port}/m?t={token()}"


# ── QR-Code (reines Python, keine Abhängigkeit) ───────────────────────────────
#
# Ein QR-Code der Version 4-L (33x33 Module) fasst 78 alphanumerische bzw. 50 Byte
# Zeichen — eine URL wie ``http://192.168.178.49:5000/m?t=<22 Zeichen>`` liegt bei
# ~52 Byte. Statt eine vollständige QR-Bibliothek zu vendorn (Reed-Solomon, Masken,
# Versionswahl) wird ``qrcode``/``segno`` benutzt, WENN vorhanden — und sonst
# ehrlich die URL im Klartext ausgegeben. Ein selbstgebauter, halb richtiger
# QR-Code wäre schlimmer als keiner: er scannt scheinbar und führt ins Leere.

def qr_terminal(text: str) -> str | None:
    """QR-Code als Halbblock-Text fürs Terminal, oder ``None`` wenn keine Bibliothek da."""
    try:
        import segno                                    # type: ignore
        import io
        puf = io.StringIO()
        segno.make(text, error="l").terminal(out=puf, border=2)
        return puf.getvalue()
    except Exception:
        pass
    try:
        import qrcode                                   # type: ignore
        import io
        q = qrcode.QRCode(border=2, error_correction=0)
        q.add_data(text)
        q.make(fit=True)
        puf = io.StringIO()
        q.print_ascii(out=puf, invert=True)
        return puf.getvalue()
    except Exception:
        return None


def zugang_text(port: int = 5000) -> str:
    """Der Block, den ``start.sh`` beim Start ausgibt."""
    url = einstieg_url(port)
    zeilen = ["", "  ── Handy-Bedienung ────────────────────────────────────────", ""]
    qr = qr_terminal(url)
    if qr:
        zeilen += ["    " + z for z in qr.rstrip("\n").split("\n")]
        zeilen.append("")
    zeilen += [f"    {url}", ""]
    if not qr:
        zeilen += ["    (Kein QR im Terminal — 'pip install segno' im venv nachrüsten;",
                   "     die Adresse oben funktioniert unverändert.)", ""]
    zeilen += ["    Handy ins GLEICHE WLAN — nicht ins Gast-WLAN der Fritz!Box,",
               "    das ist gegen das Heimnetz abgeschottet.", ""]
    return "\n".join(zeilen)


# ── Schema-Ausschnitt für die App ─────────────────────────────────────────────
#
# Nur die Felder, die den Querschnitt bestimmen. Bewusst KEINE zweite Tabelle mit
# Grenzen: die kommen aus /param_schema, sonst laufen die beiden Oberflächen
# auseinander (derselbe Fehler, den server.py schon einmal mit einer doppelten
# geom_keys-Tabelle hatte).
FELDER = ["statorOD", "rotorOD", "shaftD", "slots", "p", "slotDepth",
          "conductorsPerSlot", "magGapMm", "axialLen"]

# ``airGap`` steht bewusst NICHT im Schema und kann auch nicht dort stehen: die
# Statorbohrung ist keine unabhaengige Groesse, sondern folgt aus Rotor und Spalt
# (``statorID = rotorOD + 2*airGap``, so macht es auch der Schreibtisch-Designer in
# ``ema.html:dsnDims``). Die App fragt deshalb den Spalt und rechnet die Bohrung aus —
# sonst kann der Nutzer eine Bohrung eingeben, die zum Rotor nicht passt.
FELDER_ABGELEITET = {
    "airGap": {"key": "airGap", "kind": "num", "lo": 0.3, "hi": 5.0, "def": 0.7,
               "desc": "Luftspalt einseitig; die Statorbohrung folgt daraus"},
}
ALLE_FELDER = FELDER + list(FELDER_ABGELEITET)


def basis_geom() -> dict:
    """Eine VOLLSTAENDIGE Geometrie aus den Schemavorgaben.

    Der Loeser braucht mehr Schluessel, als die App zeigt: ``ema_topology.magnet_legs``
    liest auch bei ``magShape:"custom"`` parametrische Werte (gemessen an einem
    ``KeyError: 'magThick'``). Der Schreibtischpfad faellt das nicht auf, weil er die
    gezeichneten Werte ueber eine bereits vollstaendige ``GEOM`` legt
    (``ema.html:5593`` — ``{ ...GEOM, statorOD: ... }``).

    Die Vorgaben kommen aus ``ema_text2ema.SCHEMA`` — derselben Quelle wie die
    Eingabemasken. Keine zweite Vorgabetabelle.
    """
    import ema_text2ema as T2E
    return {k: v["def"] for k, v in T2E.SCHEMA.items()
            if v.get("geom") and "def" in v}


def schema_ausschnitt(voll: dict) -> dict:
    """``voll`` ist die Antwort von ``/param_schema``; hier bleibt nur, was die App zeigt."""
    params = voll.get("params") or voll
    if isinstance(params, dict):
        gefiltert = {k: v for k, v in params.items() if k in FELDER}
    else:                                        # Liste von Einträgen mit "key"
        gefiltert = {e["key"]: e for e in params
                     if isinstance(e, dict) and e.get("key") in FELDER}
    gefiltert.update(FELDER_ABGELEITET)
    return {"felder": ALLE_FELDER, "params": gefiltert,
            "rpm_default": RPM_DEFAULT, "punkte_default": PUNKTE_DEFAULT,
            "grenzen": {"N_MAX": N_MAX, "N_DEFAULT": N_DEFAULT,
                        "OUT_PX_MAX": OUT_PX_MAX, "OUT_PX_DEF": OUT_PX_DEF,
                        "PUNKTE_MAX": PUNKTE_MAX}}


# ── Die Stapelrechnung ────────────────────────────────────────────────────────

def pruefe_anfrage(data: dict) -> tuple[dict, str | None]:
    """Nutzlast prüfen und normalisieren. Weist ab, statt zu klemmen — wie ``cae_cli``.

    Ein stillschweigend geklemmter Wert ist die schlechteste Antwort: der Nutzer sieht
    ein Ergebnis, das nicht zu seiner Eingabe gehört.
    """
    if not isinstance(data, dict):
        return {}, "Rumpf ist kein JSON-Objekt."
    geom = data.get("geom")
    if not isinstance(geom, dict) or not geom:
        return {}, "geom fehlt."
    # Die vom Client geschickte Geometrie IMMER auf eine vollstaendige auffuellen.
    # ``ema_topology.magnet_legs`` liest auch bei ``magShape:"custom"`` parametrische
    # Werte (gemessen: KeyError 'magThick'), und der Handy-Client kennt nur die elf
    # Felder, die er anzeigt. Hier statt im Client, damit JEDER Aufrufer geschuetzt ist
    # — der Schreibtischpfad kommt nicht in die Lage, weil er die gezeichneten Werte
    # ueber eine bereits vollstaendige GEOM legt (``ema.html:5593``).
    geom = {**basis_geom(), **geom}

    punkte = data.get("punkte")
    if not isinstance(punkte, list) or not punkte:
        return {}, "punkte fehlt (Liste aus {rpm, load_nm})."
    if len(punkte) > PUNKTE_MAX:
        return {}, f"höchstens {PUNKTE_MAX} Punkte, {len(punkte)} bekommen."
    norm = []
    for i, p in enumerate(punkte):
        if not isinstance(p, dict):
            return {}, f"Punkt {i + 1} ist kein Objekt."
        try:
            rpm = float(p.get("rpm", 0.0))
            last = float(p.get("load_nm", 5.0))
        except (TypeError, ValueError):
            return {}, f"Punkt {i + 1}: rpm/load_nm nicht numerisch."
        if not (0.0 <= rpm <= 60000.0):
            return {}, f"Punkt {i + 1}: rpm {rpm:g} ausserhalb 0…60000."
        if not (0.0 <= last <= 5000.0):
            return {}, f"Punkt {i + 1}: load_nm {last:g} ausserhalb 0…5000."
        norm.append({"rpm": rpm, "load_nm": last})

    try:
        N = int(data.get("N", N_DEFAULT))
        out_px = int(data.get("out_px", OUT_PX_DEF))
    except (TypeError, ValueError):
        return {}, "N/out_px nicht ganzzahlig."
    if not (60 <= N <= N_MAX):
        return {}, (f"N {N} ausserhalb 60…{N_MAX}. Der Deckel ist eine Zumutbarkeits-"
                    f"grenze: bei N=300 kostet ein Punkt 7,6 s.")
    if not (200 <= out_px <= OUT_PX_MAX):
        return {}, f"out_px {out_px} ausserhalb 200…{OUT_PX_MAX}."

    return {"geom": geom, "punkte": norm, "N": N, "out_px": out_px,
            "magnet": data.get("magnet", "ndfeb_n35"),
            "axial_len": float(data.get("axial_len", 80.0)),
            "field_bmax": float(data.get("field_bmax", 0) or 0),
            "rotor_angle_deg": float(data.get("rotor_angle_deg", 0.0))}, None


def rechne_punkte(anfrage: dict):
    """Generator: liefert je Betriebspunkt EIN fertiges Ergebnis-dict.

    Nacheinander statt gesammelt, damit die erste Kachel nach ~3 s auf dem Handy steht
    und nicht erst nach ~12 s. Die Route macht daraus NDJSON.

    Ausnahmen werden je Punkt gefangen und als ``fehler``-Zeile ausgeliefert — ein
    unbaubarer dritter Punkt darf die ersten beiden nicht wegwerfen.
    """
    import math
    import ema_analysis
    import ema_pipeline as P

    geom   = anfrage["geom"]
    N      = anfrage["N"]
    out_px = anfrage["out_px"]
    ang    = math.radians(anfrage["rotor_angle_deg"])
    mag    = P.MAGNETS.get(anfrage["magnet"], P.MAGNETS["ndfeb_n35"])

    _Br, _mu = ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG
    ema_analysis.Br_NdFeB = mag["Br"]
    ema_analysis.MU_R_MAG = mag["mu_r"]
    try:
        # EIN grober Vorlauf für die dq-Stromschätzung aller Punkte. render_preview_frame
        # macht das je Aufruf neu — bei vier Punkten derselben Geometrie dreimal umsonst.
        t0 = time.time()
        em0 = ema_analysis.run_em_analysis(geom, N=min(N, 250), rotor_angle=0.0)
        b_gap = em0["performance"]["B_gap_T"]
        n_eck = eckdrehzahl(geom, b_gap)
        yield {"art": "start", "b_gap_T": round(b_gap, 4), "n_punkte": len(anfrage["punkte"]),
               "N": N, "out_px": out_px, "vorlauf_s": round(time.time() - t0, 2),
               "rpm_base": round(n_eck),
               # Damit die App erklaeren kann, warum gleiche Momente gleiche Bilder geben.
               "alle_unter_eck": all(p["rpm"] < n_eck for p in anfrage["punkte"]),
               "gleiche_last": len({p["load_nm"] for p in anfrage["punkte"]}) == 1}

        for i, p in enumerate(anfrage["punkte"]):
            t0 = time.time()
            try:
                # KEIN rpm_base uebergeben. ``render_preview_frame`` setzt
                # ``rpm_base=rpm`` — fuer EIN Bild richtig (die Maschine soll dort an
                # ihrer Eckdrehzahl stehen), fuer einen Drehzahlsweep falsch: jeder
                # Punkt laege dann per Definition genau an der Ecke, die
                # Feldschwaechung griffe nie und alle vier Punkte lieferten dieselben
                # Stroeme und dasselbe Bild (gemessen: i_q 116,0 / i_d -54,6 an allen
                # vier Drehzahlen). Ohne das Argument leitet estimate_dq_currents die
                # Eckdrehzahl aus EMK und Spannungsgrenze der Maschine ab — so macht es
                # auch der 3D-Pfad (ema_em3d.py:1302).
                iq, id_ = ema_analysis.estimate_dq_currents(
                    geom, p["rpm"], p["load_nm"], b_gap_t=b_gap)
                png = P._field_frame(geom, ang, N=N, iq=iq, id_=id_, rpm=p["rpm"],
                                     out_px=out_px, saturate=True,
                                     b_ceiling=anfrage["field_bmax"] or None,
                                     magnet_outlines=True)
                yield {"art": "punkt", "i": i, "rpm": p["rpm"], "load_nm": p["load_nm"],
                       "B_gap_T": round(b_gap, 4), "iq": round(iq, 1), "id": round(id_, 1),
                       "N": N, "out_px": out_px, "dauer_s": round(time.time() - t0, 2),
                       "png_b64": png}
            except Exception as e:                       # noqa: BLE001 — je Punkt isolieren
                yield {"art": "fehler", "i": i, "rpm": p["rpm"], "load_nm": p["load_nm"],
                       "fehler": str(e)[:300], "dauer_s": round(time.time() - t0, 2)}
    finally:
        ema_analysis.Br_NdFeB = _Br
        ema_analysis.MU_R_MAG = _mu
        # Der LU-Cache hält je Rotorwinkel einen Eintrag. Alle Punkte hier teilen den
        # Winkel, aber mit saturate=True haengt mu vom Strom ab — die Matrix ist also je
        # Punkt eine andere und der Cache traegt ueber Punkte hinweg nichts. Gemessen:
        # Vorlauf ~0,9 s, danach je Punkt 1,1-1,4 s bei N=180. Aufraeumen wie im
        # Vorschaupfad, damit ein Handylauf keinen GB-Cache stehen laesst.
        ema_analysis.clear_lu_cache()


# ── Halbpol → customLegs ──────────────────────────────────────────────────────

def legs_aus_halbpol(magnete: list, eps_off: float = 0.5, eps_ang: float = 2.0) -> list:
    """Halbpol → voller Pol: an der d-Achse spiegeln, deckungsgleiche Legs entdoppeln.

    **Zeichengetreu aus ``ema.html:5570-5590`` übernommen.** Das ist der einzige Ort, an
    dem Handy und Schreibtisch auseinanderlaufen könnten, ohne dass es auffällt: gleiche
    Zeichnung, andere Legs, andere Maschine, plausibel aussehendes Ergebnis.
    ``test_mobil.py`` nagelt die Gleichheit an einem Festwert fest.

    Eingabe:  ``{r, off, ang, len, thick, pol}``   (pol-lokal, mm — wie ``DESIGN.magnets``)
    Ausgabe:  ``{r_pos, offset, tilt_deg, length, thickness, mag_sign}``  (``customLegs``)
    """
    legs, gesehen = [], set()

    def _add(r, off, ang, laenge, dicke, sign):
        k = f"{r:.1f}|{off:.1f}|{ang:.1f}|{laenge:.1f}"
        if k in gesehen:
            return
        gesehen.add(k)
        legs.append({"r_pos": r, "offset": off, "tilt_deg": ang,
                     "length": laenge, "thickness": dicke, "mag_sign": sign})

    for m in magnete or []:
        r     = float(m.get("r", 0.0))
        off   = float(m.get("off", 0.0))
        ang   = float(m.get("ang", 0.0))
        laeng = float(m.get("len", 0.0))
        dicke = float(m.get("thick", 0.0))
        sign  = int(m.get("pol", 1))
        _add(r, off, ang, laeng, dicke, sign)
        auf_achse = abs(off) < eps_off and abs(ang) < eps_ang
        if not auf_achse:
            _add(r, -off, -ang, laeng, dicke, sign)
    return legs


def barrieren_aus_halbpol(barrieren: list) -> list:
    """Wie ``legs_aus_halbpol``, für die Flusssperren (``ema.html:5591-5595``)."""
    aus = []
    for b in barrieren or []:
        pts = [[float(x), float(y)] for x, y in (b.get("pts") or [])]
        if not pts:
            continue
        w = float(b.get("width", 1.0))
        aus.append({"pts": pts, "width": w})
        aus.append({"pts": [[x, -y] for x, y in pts], "width": w})
    return aus


def geom_aus_entwurf(entwurf: dict) -> dict:
    """Der Entwurf der App → ``geom`` für den Löser.

    Die parametrischen Flusssperren und die Wuchtbohrungen werden ausdrücklich
    abgeschaltet — sie würden sonst zusätzlich zur gezeichneten Geometrie erscheinen
    (dieselbe Begründung wie in ``ema.html:5598-5602``).
    """
    masse = dict(entwurf.get("masse") or {})
    geom = basis_geom()          # vollstaendig; pruefe_anfrage fuellt zusaetzlich auf
    geom.update({k: masse[k] for k in ALLE_FELDER if k in masse})
    # Die Statorbohrung ist abgeleitet, nicht eingegeben.
    if "rotorOD" in geom and "airGap" in geom:
        geom["statorID"] = float(geom["rotorOD"]) + 2.0 * float(geom["airGap"])
    geom.update({
        "magShape": "custom",
        "customLegs":     legs_aus_halbpol(entwurf.get("magnete")),
        "customBarriers": barrieren_aus_halbpol(entwurf.get("barrieren")),
        "genFluxBarrierQ": False, "genFluxBarrierD": False, "genBalanceBolts": False,
    })
    return geom
