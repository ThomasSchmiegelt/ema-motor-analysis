"""Beitragsentwuerfe fuer Instagram und X -- aus dem, was gerechnet wurde.

Der Studio-Reiter (``ema_studio.html``) und das Verb ``cae_cli.py beitrag``
benutzen dieses Modul; beide bekommen dasselbe, weil es nur EINEN Weg gibt.

Drei Entscheidungen, die den Rest erklaeren:

1. **Das Material kommt aus dem Steckbrief, nicht aus dem Gespraech.**
   ``ema_steckbrief.steckbrief`` weiss, welche Stufe eine Kennzahl geliefert hat
   und was noch fehlt. Ein Beitrag, der aus dem Chatverlauf entsteht, uebernimmt
   dagegen jede Zahl, die der Agent unterwegs einmal geschaetzt hat -- und
   veroeffentlicht sie.
2. **Die Zahlen werden nachgeprueft, nicht nur angemahnt.** Der Prompt sagt
   „keine Zahl, die nicht im Material steht"; ``ungedeckte_zahlen`` misst
   hinterher nach und haengt die Fundstellen an den Entwurf. Eine Bitte an ein
   Sprachmodell ist keine Zusicherung.
3. **Veroeffentlicht wird nichts.** Es gibt keinen Netzweg nach draussen, keine
   Zugangsdaten und keinen Knopf dafuer -- der Entwurf wird abgelegt und
   kopiert. Das ist dieselbe Linie wie im ganzen Repo: nichts spricht ueber
   ``localhost`` hinaus.
"""

from __future__ import annotations

import os
import re
import time

import ema_agent
import ema_steckbrief

# Die Zeichengrenzen der Kanaele. Instagram schneidet die Bildunterschrift bei
# 2200 Zeichen ab, X nimmt 280 je Beitrag. Beides wird hier GEMESSEN und nicht
# dem Modell ueberlassen: ein lokales Modell zaehlt keine Zeichen.
GRENZE = {"instagram": 2200, "x": 280}
X_FADEN_MAX = 3            # laenger ist kein Beitrag mehr, sondern ein Aufsatz
BILDER_VORGABE = 4         # Instagram zeigt bis zu 10; vier sind eine Auswahl

KANAELE = ("instagram", "x")
TOENE = ("sachlich", "begeistert", "trocken")
SPRACHEN = ("de", "en")

# Welche Bilder zuerst. Die Reihenfolge ist nicht Geschmack, sondern was ein
# Aussenstehender ueberhaupt lesen kann: ein Feldbild und ein Querschnitt sagen
# in einem Beitrag mehr als ein Konvergenzdiagramm.
BILD_RANG = ("feld_", "em_field", "cross", "quer", "rotor", "stator",
             "cad", "geometrie", "mesh", "verformung", "temp")


# ── Material ────────────────────────────────────────────────────────────────

def _kennwert_zeile(k: dict) -> str:
    wert = k.get("wert")
    if isinstance(wert, float):
        wert = f"{wert:.4g}"
    einheit = (" " + k["einheit"]) if k.get("einheit") else ""
    quelle = k.get("methode_text") or k.get("methode") or "unbekannt"
    return f"{k['schluessel']} = {wert}{einheit}   (Herkunft: {quelle})"


def _bilder_ordnen(bilder: list) -> list:
    """Nach Aussagekraft ordnen, nicht nach Alter."""
    def rang(b):
        name = b["datei"].lower()
        for i, muster in enumerate(BILD_RANG):
            if muster in name:
                return (i, -b["mtime"])
        return (len(BILD_RANG), -b["mtime"])
    return sorted(bilder, key=rang)


def aufnahmen(n: int = 6) -> list:
    """Die juengsten Bildschirmaufnahmen samt ihrer Markenliste.

    Gelesen wird ``<video>.marken.tsv`` -- die Datei, die ``Aufnahme`` beim
    Beenden neben das Video legt. Ohne Marken ist eine Aufnahme fuer einen
    Beitrag wertlos: eine Stunde Bildschirm ist kein Reel.
    """
    ordner = ema_agent.VIDEO_ORDNER
    aus = []
    try:
        namen = os.listdir(ordner)
    except OSError:
        return aus
    for name in namen:
        if not name.lower().endswith((".webm", ".mp4")):
            continue
        voll = os.path.join(ordner, name)
        marken = os.path.splitext(voll)[0] + ".marken.tsv"
        try:
            mt = os.path.getmtime(voll)
            groesse = os.path.getsize(voll)
        except OSError:
            continue
        aus.append({"video": voll, "datei": name, "mtime": mt,
                    "mb": round(groesse / 1048576.0, 1),
                    "marken": marken if os.path.isfile(marken) else "",
                    "clips": clips(marken) if os.path.isfile(marken) else []})
    aus.sort(key=lambda a: -a["mtime"])
    return aus[:n]


def marken_lesen(pfad: str) -> list:
    """Die ``.marken.tsv`` zurueck in die Liste, aus der sie geschrieben wurde."""
    aus = []
    try:
        with open(pfad, encoding="utf-8") as f:
            for zeile in f:
                if zeile.startswith("#") or not zeile.strip():
                    continue
                teile = zeile.rstrip("\n").split("\t")
                if len(teile) < 3:
                    continue
                try:
                    s = float(teile[0])
                except ValueError:
                    continue
                aus.append({"s": s, "uhr": teile[1], "art": teile[2],
                            "text": teile[3] if len(teile) > 3 else ""})
    except OSError:
        return []
    return aus


# Die Marke, die die Studio-Seite beim Aufnahmestart schreibt. Sie ist der
# einzige Weg, den Hochkantausschnitt SPAETER noch genau zu treffen: im fertigen
# Video ist die Buehne nur ein Rechteck unter anderen, und wer sie von Hand sucht,
# trifft sie um ein paar Pixel daneben — was bei 1080x1920 sofort zu sehen ist.
_FORMAT_MARKE = re.compile(
    r"Hochformat (\d+)x(\d+) . Buehne (-?\d+),(-?\d+) (\d+)x(\d+) "
    r"im Fenster (\d+)x(\d+) . Aufnahme (\d+)x(\d+)")


def zuschnitt(marken: list) -> str:
    """Der ffmpeg-Filter, der die Aufnahme auf die Buehne zuschneidet -- oder "".

    Nur wenn sich die Aufnahme im selben Verhaeltnis auf das Fenster abbilden
    laesst (in beiden Achsen gleich), stammt sie vom Fenster oder vom Reiter, und
    dann liegt die Buehne an einer berechenbaren Stelle. Wurde der ganze
    BILDSCHIRM aufgenommen, sitzt das Fenster irgendwo darin -- das laesst sich
    hier nicht wissen, und geraten wird nicht.
    """
    for m in marken:
        t = _FORMAT_MARKE.search(m.get("text") or "")
        if not t:
            continue
        sw, sh, bx, by, bw, bh, fw, fh, aw, ah = (int(x) for x in t.groups())
        if not (fw and fh and aw and ah and bw and bh):
            return ""
        kx, ky = aw / fw, ah / fh
        if abs(kx - ky) > 0.02 * max(kx, ky):
            return ""                       # Bildschirmaufnahme: Lage unbekannt
        x, y = round(bx * kx), round(by * ky)
        w, h = round(bw * kx), round(bh * ky)
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > aw or y + h > ah:
            return ""
        # Gerade Kantenlaengen: viele Kodierer nehmen ungerade nicht an.
        w, h = w - w % 2, h - h % 2
        return f"crop={w}:{h}:{x}:{y},scale={sw}:{sh}"
    return ""


# Die Studio-Seite schneidet die Aufnahme seit dem 08.09.2026 schon im Browser
# auf die Buehne zu (Region Capture). Dann gibt es hinterher nichts mehr zu
# schneiden — und das ist etwas ANDERES als „die Lage ist unbekannt", auch wenn
# in beiden Faellen keine ffmpeg-Zeile herauskommt. Wer das nicht unterscheidet,
# liest unter einem perfekt zugeschnittenen Reel „ohne Zuschnitt".
_BEREICH_MARKE = re.compile(r"Bereichsaufnahme")


def zuschnitt_lage(marken: list) -> str:
    """Woher der Hochkantausschnitt kommt: ``fertig`` · ``berechnet`` ·
    ``unbekannt`` · ``keine`` (die Aufnahme lief gar nicht im Hochformat)."""
    hat_format = False
    for m in marken:
        t = m.get("text") or ""
        if m.get("art") == "format" or "Hochformat" in t:
            hat_format = True
            if _BEREICH_MARKE.search(t):
                return "fertig"
    if zuschnitt(marken):
        return "berechnet"
    return "unbekannt" if hat_format else "keine"


LAGE_TEXT = {
    "fertig":    "kein Zuschnitt noetig — aufgenommen wurde bereits nur die Buehne",
    "berechnet": "schneidet auf das Hochformat zu",
    "unbekannt": ("ohne Zuschnitt — die Aufnahme war der ganze Bildschirm, "
                  "die Lage der Buehne darin ist unbekannt"),
    "keine":     "ohne Zuschnitt — die Aufnahme lief nicht im Hochformat",
}


def clips(marken_tsv: str) -> list:
    """Schnittvorschlaege aus einer Markenliste -- Sekunden, Dauer, ffmpeg-Zeile.

    Zusammengefasst wird mit ``ema_agent.stuecke_aus_marken``: derselben
    Funktion, aus der auch das ``schnitt.sh`` neben der Aufnahme entsteht. Zwei
    Gruppierungen waeren zwei Vorstellungen davon, was ein Stueck ist -- und der
    Vorschlag zeigte dann andere Sekunden, als das Skript schneidet.
    """
    marken = marken_lesen(marken_tsv)
    if not marken:
        return []
    video = re.sub(r"\.marken\.tsv$", "", marken_tsv)
    stuecke = ema_agent.stuecke_aus_marken(
        marken, ema_agent.Aufnahme.VOR_S, ema_agent.Aufnahme.NACH_S,
        ema_agent.Aufnahme.VERSCHMELZEN_S)
    schnitt = zuschnitt(marken)
    lage = zuschnitt_lage(marken)
    vf = f' -vf "{schnitt}"' if schnitt else ""
    aus = []
    for ab, bis, mm in stuecke:
        dauer = max(0.0, bis - ab)
        # Die Marke, die den Zuschnitt traegt, ist keine Szene -- sie steht am
        # Aufnahmestart und beschreibt das Fenster, nicht das Geschehen.
        worum = " · ".join(m["text"] for m in mm
                           if m.get("text") and m.get("art") != "format")
        aus.append({
            "ab": round(ab, 2), "bis": round(bis, 2), "dauer": round(dauer, 1),
            "worum": worum[:200],
            "marken": len(mm), "zuschnitt": schnitt, "zuschnitt_lage": lage,
            "ffmpeg": (f"ffmpeg -ss {ab:.2f} -i {_sh(video)} -t {dauer:.2f}"
                       f"{vf} -c:v libx264 -crf 22 -an clip_{int(ab)}s.mp4"),
        })
    return aus


def _sh(pfad: str) -> str:
    return "'" + str(pfad).replace("'", "'\\''") + "'"


def material(pid: str, *, bilder: list | None = None,
             mit_aufnahmen: bool = True) -> dict:
    """Alles, worueber ein Beitrag reden DARF -- und nichts darueber hinaus."""
    pdir = ema_steckbrief.projekt_pfad(pid)
    if not pdir:
        return {"ok": False, "grund": f"Kein Projekt '{pid}'."}
    sb = ema_steckbrief.steckbrief(pdir)
    if not sb.get("ok", True):
        return {"ok": False, "grund": sb.get("grund", "Steckbrief nicht lesbar")}
    echt = os.path.basename(pdir.rstrip("/"))
    alle = _bilder_ordnen(ema_agent.bilder_im_projekt(echt))
    if bilder:
        gewuenscht = {os.path.basename(b) for b in bilder}
        wahl = [b for b in alle if b["datei"] in gewuenscht]
    else:
        wahl = alle[:BILDER_VORGABE]
    return {"ok": True, "projekt": echt, "ordner": pdir, "steckbrief": sb,
            # Liegt die Maschine ausserhalb der gepruefteren Klasse, gehoert das
            # in den Entwurf -- ein veroeffentlichter Satz ueber eine Zahl aus
            # einer fremden Klasse ist schlimmer als kein Satz. S.
            # ema_referenz.GELTUNG.
            "geltung": sb.get("geltung") or [],
            "text": ema_steckbrief.als_text(sb),
            "kennwerte": sb.get("kennwerte") or [],
            "bilder": wahl, "bilder_alle": alle,
            "aufnahmen": aufnahmen() if mit_aufnahmen else []}


# ── Die Zahlen nachmessen ───────────────────────────────────────────────────

_ZAHL = re.compile(r"\d+(?:[.,]\d+)?")


def _zahlen(text: str) -> list:
    aus = []
    for t in _ZAHL.findall(text or ""):
        try:
            aus.append((t, float(t.replace(",", "."))))
        except ValueError:
            continue
    return aus


def ungedeckte_zahlen(entwurf: str, material_text: str) -> list:
    """Zahlen im Entwurf, die im Material nicht vorkommen.

    Gerundet wird mitgedacht: steht im Material 0.3412 und im Entwurf 0,34, ist
    das gedeckt -- runden ist erlaubt, erfinden nicht. Hashtags und Jahreszahlen
    bleiben aussen vor, sonst meldet die Pruefung staendig ``#emotor2026``.
    """
    belegt = [w for _, w in _zahlen(material_text)]
    ohne_tags = re.sub(r"#\S+", " ", entwurf or "")
    aus = []
    for roh, wert in _zahlen(ohne_tags):
        if 1900 <= wert <= 2100 and "." not in roh and "," not in roh:
            continue                                   # Jahreszahl
        stellen = len(roh.split(",")[-1].split(".")[-1]) if ("," in roh or "." in roh) else 0
        if any(abs(round(b, stellen) - wert) < 10 ** (-stellen) / 2 or b == wert
               for b in belegt):
            continue
        aus.append(roh)
    return sorted(set(aus), key=aus.index)


# ── Die Entwuerfe ───────────────────────────────────────────────────────────

_TON = {
    "sachlich": "sachlich und praezise, ohne Superlative",
    "begeistert": "begeistert, aber ohne eine einzige erfundene Zahl",
    "trocken": "trocken und knapp, wie eine Laborzeile",
}

_FORM = """Antworte AUSSCHLIESSLICH in diesem Format, ohne Vorrede:

### TEXT
<der Beitrag>
### HASHTAGS
<Hashtags in einer Zeile, mit # und durch Leerzeichen getrennt>
### ALT
<dateiname> :: <Alternativtext, ein Satz>
"""


def _auftrag(kanal: str, mat: dict, ton: str, sprache: str) -> tuple:
    bilder = ", ".join(b["datei"] for b in mat["bilder"]) or "(keine)"
    sprach_satz = ("Schreibe auf Deutsch." if sprache == "de"
                   else "Write in English.")
    if kanal == "x":
        form = (f"Ein Beitrag fuer X. HOECHSTENS {GRENZE['x']} Zeichen "
                f"einschliesslich Hashtags. Passt es nicht, mach einen Faden "
                f"aus hoechstens {X_FADEN_MAX} Beitraegen und trenne sie durch "
                f"eine Zeile mit nur ---. Hoechstens drei Hashtags.")
    else:
        form = (f"Eine Bildunterschrift fuer Instagram. HOECHSTENS "
                f"{GRENZE['instagram']} Zeichen, in kurzen Absaetzen, "
                f"8 bis 15 Hashtags am Ende.")
    system = (
        "Du schreibst ueber eine Elektromaschine, die mit einer eigenen "
        "CAE-Werkzeugkette ausgelegt und GERECHNET wurde. "
        + sprach_satz + " Der Ton ist " + _TON.get(ton, _TON["sachlich"]) + ". "
        "HARTE REGEL: du darfst NUR Zahlen nennen, die woertlich im Material "
        "unten stehen. Keine Schaetzung, keine Hochrechnung, keine Zahl aus "
        "deinem Gedaechtnis -- der Beitrag wird veroeffentlicht. Ist eine "
        "Groesse nicht gerechnet, erwaehne sie nicht. Keine Versprechen ueber "
        "Serienreife, Wirkungsgrade oder Preise. " + form + "\n\n" + _FORM)
    ausserhalb = [e for e in (mat.get("geltung") or [])
                  if e.get("befund") == "ausserhalb"]
    if ausserhalb:
        system += ("\n\nACHTUNG: diese Maschine liegt AUSSERHALB der Klasse, auf "
                   "die die Werkzeugkette geeicht ist (" +
                   "; ".join(e["feld"] + ": " + e["text"] for e in ausserhalb) +
                   "). Schreibe keinen Beitrag, der ihre Zahlen als belastbar "
                   "hinstellt. Entweder du sagst diese Einschraenkung im "
                   "Beitrag deutlich dazu, oder du schreibst ueber das "
                   "Vorhaben statt ueber die Zahlen.")
    nutzer = (f"MATERIAL — Projekt {mat['projekt']}\n\n{mat['text']}\n\n"
              f"KENNWERTE MIT HERKUNFT\n"
              + "\n".join(_kennwert_zeile(k) for k in mat["kennwerte"])
              + f"\n\nBILDER, die zum Beitrag gehoeren: {bilder}\n")
    return system, nutzer


def _abschnitte(antwort: str) -> dict:
    """Die drei Blockformate auseinandernehmen -- nachsichtig.

    Ein lokales Modell haelt sich nicht immer an das Format. Fehlt ein Block,
    faellt der Entwurf auf das Ganze zurueck, statt leer zu sein.
    """
    teile = re.split(r"^\s*#{2,4}\s*(TEXT|HASHTAGS|ALT)\s*$", antwort or "",
                     flags=re.MULTILINE | re.IGNORECASE)
    if len(teile) < 3:
        return {"text": (antwort or "").strip(), "hashtags": "", "alt": ""}
    aus = {"text": "", "hashtags": "", "alt": ""}
    for i in range(1, len(teile) - 1, 2):
        aus[teile[i].strip().lower()] = teile[i + 1].strip()
    if not aus["text"]:
        aus["text"] = (antwort or "").strip()
    return aus


def _alt_texte(roh: str, bilder: list, projekt: str) -> list:
    """``datei :: Text`` -- und fuer jedes Bild ohne Zeile ein ehrlicher Ersatz."""
    zuordnung = {}
    for zeile in (roh or "").split("\n"):
        if "::" not in zeile:
            continue
        name, _, text = zeile.partition("::")
        zuordnung[os.path.basename(name.strip().strip("-* "))] = text.strip()
    aus = []
    for b in bilder:
        text = zuordnung.get(b["datei"], "")
        if not text:
            text = (f"Berechnungsbild {b['datei']} aus dem Projekt {projekt}")
        aus.append({"datei": b["datei"], "unter": b["unter"], "alt": text,
                    "url": f"/agent/bild/{projekt}/{b['unter']}/{b['datei']}"})
    return aus


def _kuerzen(text: str, grenze: int) -> str:
    """Am Wort abschneiden, nicht mitten hinein -- und es sichtbar sagen."""
    if len(text) <= grenze:
        return text
    schnitt = text[:grenze - 1].rsplit(" ", 1)[0]
    return schnitt + "…"


def _umbrechen(text: str, grenze: int) -> list:
    """Einen zu langen Beitrag auf mehrere verteilen -- an Wort- und moeglichst
    an Absatzgrenzen.

    Gemessen am ersten echten Lauf: das Modell schrieb einen Teil mit 274 von
    280 Zeichen, dessen letzter Satz ausgerechnet die verletzten
    Sicherheitskriterien nannte -- und der wurde abgeschnitten. Ein Beitrag darf
    zu lang sein; abgeschnitten werden darf er erst, wenn auch der Faden voll
    ist. Sonst faellt genau die Einschraenkung weg, wegen der man den Beitrag
    ueberhaupt lesen sollte.
    """
    text = (text or "").strip()
    if len(text) <= grenze:
        return [text] if text else []
    aus, rest = [], text
    while len(rest) > grenze:
        schnitt = rest[:grenze]
        # An einem Absatz trennen, wenn einer in der zweiten Haelfte liegt --
        # sonst am letzten Leerzeichen.
        bruch = schnitt.rfind("\n")
        if bruch < grenze // 2:
            bruch = schnitt.rfind(" ")
        if bruch <= 0:
            bruch = grenze
        aus.append(rest[:bruch].strip())
        rest = rest[bruch:].strip()
    if rest:
        aus.append(rest)
    return aus


def _x_teile(text: str) -> tuple:
    """(Teile, verloren) -- ``verloren`` sagt, ob der Faden nicht ausgereicht hat."""
    roh = [t.strip() for t in re.split(r"^\s*---\s*$", text,
                                       flags=re.MULTILINE) if t.strip()]
    teile = []
    for stueck in (roh or [""]):
        teile.extend(_umbrechen(stueck, GRENZE["x"]) or [""])
    verloren = len(teile) > X_FADEN_MAX
    teile = teile[:X_FADEN_MAX] or [""]
    return [_kuerzen(t, GRENZE["x"]) for t in teile], verloren


def _fussnote(mat: dict) -> str:
    zeilen = [f"Projekt {mat['projekt']} · {time.strftime('%d.%m.%Y')}"]
    for k in mat["kennwerte"][:8]:
        zeilen.append("  " + _kennwert_zeile(k))
    if not mat["kennwerte"]:
        zeilen.append("  (keine Kennwerte gerechnet — der Entwurf darf keine nennen)")
    return "\n".join(zeilen)


def erzeugen(pid: str, kanal: str, *, bilder: list | None = None,
             ton: str = "sachlich", sprache: str = "de",
             ablage: bool = True, llm=None) -> dict:
    """Einen Entwurf bauen. ``llm`` ist der Ausstieg fuer die Pruefung.

    ``llm(system, nutzer) -> str``; ohne Angabe geht es an dasselbe Ollama, das
    auch Bericht und Chat benutzen (``ema_chat``) -- ein zweiter Client waere
    ein zweites Modell, ein zweiter Zeitablauf und eine zweite Fehlerquelle.
    """
    kanal = str(kanal or "").strip().lower()
    if kanal not in KANAELE:
        return {"ok": False, "grund": f"Kanal '{kanal}' gibt es nicht. "
                                      f"Zulaessig: {', '.join(KANAELE)}"}
    mat = material(pid, bilder=bilder)
    if not mat.get("ok"):
        return mat

    system, nutzer = _auftrag(kanal, mat, ton, sprache)
    if llm is None:
        def llm(s, n):
            import ema_chat
            return ema_chat._ollama_chat(
                [{"role": "system", "content": s},
                 {"role": "user", "content": n}])
    try:
        antwort = llm(system, nutzer)
    except Exception as e:                                   # noqa: BLE001
        return {"ok": False, "grund": f"Modell nicht erreichbar: "
                                      f"{type(e).__name__}: {e}"}

    ab = _abschnitte(antwort)
    text, hashtags = ab["text"], ab["hashtags"]
    verloren = False
    if kanal == "x":
        teile, verloren = _x_teile((text + ("\n" + hashtags if hashtags else "")).strip())
        beitrag = "\n---\n".join(teile)
        laengen = [len(t) for t in teile]
    else:
        ganz = (text + ("\n\n" + hashtags if hashtags else "")).strip()
        beitrag = _kuerzen(ganz, GRENZE["instagram"])
        teile, laengen = [beitrag], [len(beitrag)]

    hinweise = []
    offen = ungedeckte_zahlen(beitrag, mat["text"] + "\n" +
                              "\n".join(_kennwert_zeile(k) for k in mat["kennwerte"]))
    if offen:
        hinweise.append("Zahlen ohne Deckung im Material: " + ", ".join(offen)
                        + " — pruefen oder streichen, bevor das veroeffentlicht wird.")
    if verloren:
        hinweise.append(f"Der Entwurf war laenger als {X_FADEN_MAX} Beitraege — "
                        f"der Rest fehlt. Kuerzen und neu erzeugen lassen.")
    if not mat["kennwerte"]:
        hinweise.append("Fuer dieses Projekt liegt kein gerechnetes Ergebnis vor "
                        "— der Entwurf kann nur beschreiben, nicht belegen.")

    erg = {"ok": True, "kanal": kanal, "projekt": mat["projekt"],
           "beitrag": beitrag, "teile": teile, "laengen": laengen,
           "grenze": GRENZE[kanal], "hashtags": hashtags,
           "bilder": _alt_texte(ab["alt"], mat["bilder"], mat["projekt"]),
           "clips": (mat["aufnahmen"][0]["clips"] if mat["aufnahmen"] else []),
           "aufnahme": (mat["aufnahmen"][0]["video"] if mat["aufnahmen"] else ""),
           "herkunft": _fussnote(mat), "hinweise": hinweise, "roh": antwort}

    if ablage:
        erg["ablage"] = _ablegen(mat, erg, ton, sprache)
    return erg


def als_text(erg: dict) -> str:
    """Der Entwurf, wie er in der Datei und im Terminal steht."""
    z = [f"{erg['kanal'].upper()} — Projekt {erg['projekt']}", ""]
    for i, t in enumerate(erg["teile"], 1):
        if len(erg["teile"]) > 1:
            z.append(f"[{i}/{len(erg['teile'])}]  ({len(t)}/{erg['grenze']} Zeichen)")
        z += [t, ""]
    if len(erg["teile"]) == 1:
        z.append(f"({erg['laengen'][0]}/{erg['grenze']} Zeichen)")
        z.append("")
    if erg["bilder"]:
        z.append("Bilder:")
        for b in erg["bilder"]:
            z.append(f"  {b['unter']}/{b['datei']} — ALT: {b['alt']}")
        z.append("")
    if erg["clips"]:
        z.append("Schnittvorschlaege aus der Bildschirmaufnahme:")
        for c in erg["clips"]:
            z.append(f"  {c['ab']:.0f}–{c['bis']:.0f} s ({c['dauer']:.0f} s) "
                     f"{c['worum']}")
            z.append("    " + LAGE_TEXT.get(c.get("zuschnitt_lage"),
                                            LAGE_TEXT["unbekannt"]))
            z.append(f"    {c['ffmpeg']}")
        z.append("")
    for h in erg["hinweise"]:
        z.append(f"ACHTUNG: {h}")
    if erg["hinweise"]:
        z.append("")
    z += ["Herkunft der Zahlen:", erg["herkunft"], "",
          "Veroeffentlicht wird hier nichts — kopieren und selbst posten."]
    return "\n".join(z)


UNTER = "beitraege"


def _ablegen(mat: dict, erg: dict, ton: str, sprache: str) -> dict:
    """In ``beitraege/`` UND in die Projektakte.

    Zweimal, weil beides zwei verschiedene Fragen beantwortet: die Datei ist
    der Entwurf zum Kopieren, die Zeile in ``rechnungen``/``evolution`` ist die
    Antwort auf „was ist mit diesem Projekt eigentlich passiert".
    """
    aus = {}
    try:
        ordner = os.path.join(mat["ordner"], UNTER)
        os.makedirs(ordner, exist_ok=True)
        marke = time.strftime("%Y%m%d_%H%M%S")
        pfad = os.path.join(ordner, f"{marke}_{erg['kanal']}.md")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(als_text(erg) + "\n")
        aus["datei"] = pfad
    except OSError as e:
        return {"ok": False, "grund": f"{type(e).__name__}: {e}"}
    ab = ema_steckbrief.ablegen(
        mat["ordner"], "beitrag", als_text(erg),
        daten={"kanal": erg["kanal"], "ton": ton, "sprache": sprache,
               "laengen": erg["laengen"], "hinweise": erg["hinweise"],
               "bilder": [b["datei"] for b in erg["bilder"]]},
        befehl=f"beitrag {erg['kanal']} --from-project {mat['projekt']}",
        ok=not erg["hinweise"])
    aus["ok"] = bool(ab.get("ok"))
    aus["rechnung"] = ab.get("datei", "")
    return aus
