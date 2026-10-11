"""Maschinenart als ausgesprochener Begriff -- damit keine Annahme mehr still gilt.

Das Werkzeug ist als **permanenterregte Synchronmaschine mit Hairpin-Wicklung**
gewachsen. Diese Annahme steht nirgends als Schalter, sondern verteilt in sechs
Modulen: ``_analytical_Bgap`` rechnet aus ``Br_NdFeB`` und ``magThick``,
``compute_performance`` gibt ``Kt = 1.5*p*psi_pm`` heraus (reines Magnetmoment),
``estimate_dq_currents`` teilt durch dieses Kt, ``estimate_saliency`` legt die
Magnetdicke in den d-Pfad, ``ema_rotorcheck`` prueft Magnettaschen, und
``ema_referenz`` fuehrt Baender je **Magnet**anordnung.

Wer dort eine Asynchronmaschine hineinreicht, bekommt keine Fehlermeldung --
er bekommt **PSM-Zahlen mit einem anderen Etikett**. Genau dieser Fehler ist beim
Fahrzyklus schon einmal passiert: die Voreinstellung WLTP rechnete ein Fahrrad
als 1600-kg-Auto, und niemand sah es, weil nichts widersprach.

Dieses Modul ist deshalb kein Datenblatt, sondern ein **Tor**:

* ``art_code(payload_oder_geom)`` -- welche Art ist gemeint (Vorgabe ``pmsm``);
* ``pruefe_stufe(code, stufe)`` -- traegt diese Stufe diese Art ueberhaupt schon?
  Wenn nicht, gibt es einen klaren Fehler und **keine** Ersatzrechnung;
* ``gilt(code, kennzahl)`` -- hat diese Kennzahl fuer diese Art eine Bedeutung?
  Kurzschlussstrom und Entmagnetisierungsreserve sind bei einer Maschine ohne
  Magnete nicht *null*, sondern **nicht anwendbar**. Eine 0 liest sich wie ein
  Messwert; ``n. v.`` liest sich wie das, was es ist.

Die Stufenfolge ist die aus dem Auftrag: erst analytisch mit Paarvergleich, dann
Feldanalyse, dann CAD, dann 3D-Elmer. ``STUFEN`` haelt sie in dieser Reihenfolge,
``ARTEN[...].stufen`` sagt je Art, wie weit sie heute wirklich getragen ist.
"""

from __future__ import annotations

from dataclasses import dataclass

# Reihenfolge = Ausbaufolge. "analytisch" traegt den Paarvergleich, "feld" die
# 2-D-Feldrechnung, "cad" den Aufbau in FreeCAD, "em3d" die 3-D-Gegenrechnung.
STUFEN = ("analytisch", "feld", "cad", "em3d")

STUFEN_LABEL = {
    "analytisch": "analytisch (Paarvergleich, Vorauswahl)",
    "feld":       "Feldanalyse (2-D)",
    "cad":        "CAD-Aufbau",
    "em3d":       "3-D-Feld (Elmer)",
}


class ArtNichtUnterstuetzt(ValueError):
    """Diese Maschinenart traegt diese Stufe (noch) nicht."""


@dataclass(frozen=True)
class Art:
    code: str
    label: str
    erregung: str                 # woher der Luftspaltfluss kommt
    hat_magnete: bool
    hat_laeuferwicklung: bool     # Kaefig oder Erregerwicklung -> Laeuferverluste
    hat_schlupf: bool
    stellbarer_fluss: bool        # Fluss ueber einen eigenen Strom einstellbar
    stufen: tuple = ()            # welche Stufen diese Art HEUTE tragen
    ohne_bedeutung: tuple = ()    # Kennzahlen, die es fuer diese Art nicht gibt
    # WELCHER Loeser die Feldstufe traegt. Die Pipeline rechnet ihr Feld mit der
    # 2-D-FDM (``fdm``) -- reell, linear, magnetostatisch. Ein Kaefiglaeufer ist
    # darin grundsaetzlich nicht abbildbar, seine Feldstufe laeuft ueber Elmers
    # harmonischen Loeser (``elmer2d_harm``, Modul ``ema_em2d_harm``).
    #
    # Ohne diese Unterscheidung waere ``stufen`` mehrdeutig: „feld getragen"
    # haette dann geheissen, die Pipeline duerfe die ASM durch die FDM schicken
    # -- und die haette klaglos ein magnetostatisches Feld ohne Laeuferstroeme
    # ausgegeben. Genau die Art stiller Ersatzrechnung, gegen die dieses Modul
    # gebaut ist.
    feldweg: str = "fdm"
    hinweis: str = ""


# Kennzahlen, die es ohne Permanentmagnet **nicht gibt** -- nicht solche, die
# dann null sind. Der Unterschied entscheidet, ob eine Zahl unterdrueckt oder
# ausgerechnet wird:
#
#   Magnetmasse 0 kg      -> ausgerechnet. Das ist eine Aussage, und zwar die
#                            wichtigste zugunsten der magnetlosen Bauarten.
#   Magnetwirbelstrom 0 W -> ausgerechnet, gleiche Begruendung.
#   Kurzschlussstrom      -> nicht vorhanden. Ohne eingepraegten Fluss gibt es
#                            keinen Kurzschlussstrom bei abgeschaltetem Umrichter;
#                            eine 0 laese sich als „gemessen und unbedenklich"
#                            lesen, und genau das waere falsch.
#   Entmagnetisierung     -> nicht vorhanden, es gibt nichts zu entmagnetisieren.
#   T_rel_pct             -> gegen ``psi_pm`` definiert (Anteil AM MAGNETMOMENT);
#                            ohne psi_pm ist der Bruch nicht gebildet, nicht null.
# Kennzahlen, die ein DREHFELD voraussetzen. Die Gleichstrommaschine hat keins:
# ihr Feld steht still, der Kommutator haelt die Ankerdurchflutung im Raum fest.
# Eine d- und eine q-Achse gibt es dort nicht — und eine 0 in ``xi_LqLd`` laese
# sich als „gemessen, nicht salient" lesen, was etwas ganz anderes ist als
# „diese Groesse ist hier nicht gebildet".
_DREHFELD_KENNZAHLEN = (
    "xi_LqLd", "saliency", "T_rel_pct", "schlupf", "schlupf_pct",
    "i_d_A", "i_q_A", "mag_anteil",
)

# Kennzahlen, die eine GENUTETE Staenderbohrung voraussetzen. ``ema_saettigung``
# rechnet die Zahnflussdichte ueber die Nutteilung -- wo der Staender Schenkel-
# pole traegt und gar keine Nuten hat, ist das eine Formel auf eine Geometrie,
# die es nicht gibt. Gemessen kam an der GSM ``B_zahn = 8,885 T`` heraus, exakt
# derselbe Wert wie an ASM und EESM: die Zahl haengt nur an ``B_gap`` und
# ``slotWidthRatio`` und weiss von der Maschine nichts. Eine Zahl, die neben
# gerechneten Zahlen steht und wie eine aussieht, ist schlimmer als eine Luecke.
_STAENDERNUT_KENNZAHLEN = (
    "B_zahn_T", "saett_pct", "saett_engstelle",
)

_PM_KENNZAHLEN = (
    "Isc_A", "I_sc_A", "T_kurzschluss_Nm",
    "entmag_reserve", "entmag_T_C", "demag_margin",
    "T_rel_pct",
)

ARTEN = {
    "pmsm": Art(
        code="pmsm",
        label="PSM — permanenterregte Synchronmaschine",
        erregung="permanentmagnet",
        hat_magnete=True,
        hat_laeuferwicklung=False,
        hat_schlupf=False,
        stellbarer_fluss=False,
        stufen=STUFEN,
        ohne_bedeutung=(),
        hinweis="Der gewachsene Weg des Werkzeugs; alles Bestehende gilt unveraendert.",
    ),
    "asm": Art(
        code="asm",
        label="ASM — Asynchronmaschine (Kaefig oder Schleifring)",
        erregung="kaefig",
        hat_magnete=False,
        hat_laeuferwicklung=True,
        hat_schlupf=True,
        stellbarer_fluss=True,
        # "feld" traegt seit ``ema_em2d_harm`` (harmonische 2-D-Rechnung mit
        # Elmers MagnetoDynamics2DHarmonic). NICHT die 2-D-FDM: die ist reell
        # und magnetostatisch, ein Kaefiglaeufer ist darin nicht abbildbar.
        #
        # "em3d" traegt seit ``ema_em3d_harm`` (WhitneyAVHarmonicSolver). Die
        # Probe dafuer ist die Luftspalt-Grundwelle: 0,3047 T in 3-D gegen
        # 0,2870 T in 2-D am selben Betriebspunkt, bei einem Spalt, der im
        # 3-D-Netz gar nicht aufgeloest ist.
        #
        # "cad" traegt seit dem 18.09.2026. Der Kaefig war im Zeichner schon
        # da (Nuten, Staebe, beide Kurzschlussringe aus ``ema_asm.kaefig`` --
        # derselben Quelle wie Widerstand und Feldnetz), nur nie erreichbar:
        # dieses Tor liess ihn nicht durch, ``GEN_MAGNETS`` fragte die Art gar
        # nicht (ein ASM-Laeufer haette Magnettaschen UND Magnete UND einen
        # Kaefig bekommen), und ein nicht auslegbarer Kaefig waere still auf
        # den 2-mm-Fertigungsboden gezeichnet worden. Alle drei sind behoben.
        # Dazu die zweite Laeuferbauform: ``rotorType="schleifring"`` zeichnet
        # eine Drehstromwicklung mit drei Schleifringen und Buersten.
        stufen=("analytisch", "feld", "cad", "em3d"),
        feldweg="elmer2d_harm",
        ohne_bedeutung=_PM_KENNZAHLEN,
        hinweis=("Der Magnetisierungsstrom liegt DAUERND im Stator, und der "
                 "Schlupfverlust faellt im Laeufer an -- der thermisch "
                 "schlechtesten Stelle. Dafuer keine Magnete: keine Masse, "
                 "keine Magnetkosten, keine Entmagnetisierung, kein "
                 "Kurzschlussmoment. Zwei Laeuferbauformen: Kaefig (Vorgabe) "
                 "und Schleifringlaeufer mit Anlasswiderstand."),
    ),
    "synrm": Art(
        code="synrm",
        label="SynRM — Reluktanzmaschine (ohne Magnete)",
        erregung="reluktanz",
        hat_magnete=False,
        hat_laeuferwicklung=False,
        hat_schlupf=False,
        stellbarer_fluss=False,
        # "cad" traegt seit dem 20.09.2026. Der Laeufer ist bis dahin als
        # IPM-Tasche ohne Magnet gezeichnet worden ("in der reluktanzmaschine
        # sind nur die magnete entfernt"); seit ``ema_synrm_cad`` entsteht er
        # aus Auslegungsregeln (Barrierenzahl aus der Nutteilung, Endpunkte bei
        # konstanter Laeufernutteilung, Form nach den Feldlinien, Dicken aus
        # dem Isolationsgrad). Nachgemessen an einem ECHTEN FreeCAD-Bau:
        # 24 Barrieren geschnitten, Rotor gueltig und EIN Solid, und das
        # Volumen trifft die gezeichnete Flaeche auf **0,00 %** -- CAD,
        # Leinwand und FDM-Raster sehen damit denselben Laeufer.
        #
        # "feld" traegt seit dem 20.09.2026 -- aber NICHT auf der Pipeline.
        # Der 2-D-FDM scheidet aus: er eicht seine Amplitude auf
        # ``_analytical_Bgap``, und die liefert fuer eine magnetlose Maschine
        # gemessen dieselben 0,63 T wie fuer die PSM daneben; die Salienz sieht
        # er ueberhaupt nicht, weil ``_analytical_Barm`` nur den BETRAG des
        # Stromzeigers kennt (gemessen d/q ~ 1,0 gegen 1,72 aus dem
        # magnetostatischen Elmer-Lauf). Belegt in BEFUNDE.md, 20.09.2026.
        #
        # Elmer 2-D magnetostatisch (``ema_em2d_stat``) kann es dagegen, und
        # zwar genau richtig: diese Maschine ist magnetostatisch, ihr Moment
        # kommt allein aus der Laeufergeometrie. Also traegt die Art die Stufe
        # und geht einen anderen WEG -- dieselbe Unterscheidung wie bei der
        # ASM. Das Pipelinetor fragt ``pruefe_feldweg(code, "fdm")`` und weist
        # sie weiterhin ab, nennt aber das Werkzeug, das sie traegt.
        # **"em3d" traegt seit dem 20.09.2026** -- und zwar nach einem
        # DURCHGELAUFENEN Loeser, nicht nach einem gebauten Netz. Das Tor stand
        # vorher mit der Begruendung "kein durchgelaufener Loeserlauf" zu, und
        # das war unerledigte Arbeit und keine Begruendung.
        #
        # Gemessen: 103.433 Knoten, **672 Flussbarrieren-Prismen, 0 Magnete**,
        # 54 Statornuten, Lastfeld mit Statorstroemen (3000 1/min, 20 Nm →
        # i_q 170,0 A, i_d −101,6 A). Der Weg ist derselbe wie bei der PSM
        # (magnetostatisch, WhitneyAV) und damit genau richtig fuer eine
        # Maschine, deren Moment allein aus der Laeufergeometrie kommt --
        # Magnete braucht er nicht, nur eine Quelle, und die sind hier die
        # Staenderstroeme.
        #
        # **Der 2-D-Vergleich in diesem Lauf ist NICHT belastbar** und sagt es:
        # er haelt das 3-D-Feld gegen ``run_em_analysis``, und das eicht seine
        # Amplitude auf ``_analytical_Bgap`` -- eine Formel ohne Magnet ist
        # fuer eine magnetlose Maschine keine. ``Kt_2D`` ist dort reines
        # Magnetmoment, also 0 fuer diese Bauart, und wird trotzdem gedruckt.
        # Die belastbare 2-D-Gegenrechnung ist ``feld2d`` (``ema_em2d_stat``,
        # Anisotropie 1,719 mit dem glatten Laeufer als Bezugsfall).
        stufen=("analytisch", "feld", "cad", "em3d"),
        feldweg="elmer2d_stat",
        ohne_bedeutung=_PM_KENNZAHLEN,
        hinweis=("Die Flussbarrieren entstehen in ``ema_synrm_cad`` nach "
                 "Auslegungsregeln (Moghaddam 2007), nicht mehr aus der "
                 "Magnet-Anordnung. Das Moment kommt ausschliesslich aus "
                 "(Ld-Lq); die analytische Kette kennt davon nur eine "
                 "Ersatz-Barrierenhoehe."),
    ),
    "eesm": Art(
        code="eesm",
        label="EESM — fremderregte Synchronmaschine",
        erregung="fremderregt",
        hat_magnete=False,
        hat_laeuferwicklung=True,
        hat_schlupf=False,
        stellbarer_fluss=True,
        # "cad" traegt seit dem 18.09.2026: Schenkelpollaeufer mit Erreger-
        # spulen und zwei Schleifringen, gezeichnet aus ``ema_eesm_cad``,
        # das seinerseits ``polgeometrie``/``erregung`` liest — also den
        # Magnetkreis, der die Maschine rechnet.
        #
        # **"feld" traegt seit dem 20.09.2026 -- aber NICHT auf der Pipeline.**
        # Der Satz, der hier lange stand ("die 2-D-FDM kann eine Gleichstrom-
        # Erregerwicklung so wenig darstellen wie einen Kaefig"), war in seiner
        # ersten Haelfte falsch und in seiner zweiten richtig: eine eingepraegte
        # GLEICHdurchflutung ist magnetostatisch exakt darstellbar -- das ist
        # gerade der Fall, den ein magnetostatischer Loeser kann. Nicht
        # darstellbar ist, was ZEITABHAENGIG ist (Kaefig, kommutierter Anker).
        # Die 2-D-FDM scheidet aus einem anderen Grund aus: sie eicht ihre
        # Amplitude auf ``_analytical_Bgap``, und die kennt keinen Erregerstrom.
        #
        # Gerechnet wird deshalb in ``ema_em2d_stat`` (Elmer 2-D, magneto-
        # statisch), und das ist dieselbe Unterscheidung wie bei der ASM: die
        # Art TRAEGT die Stufe, sie geht nur einen anderen Weg (``feldweg``).
        # Das Pipelinetor fragt ``pruefe_feldweg(code, "fdm")`` und weist sie
        # daher weiterhin ab -- mit dem Namen des Werkzeugs, das sie traegt.
        #
        # Gemessen am frischen Payload (2p = 8, 77.433 Dreiecke, 72 Koerper):
        # Anisotropie des Schenkelpollaeufers **1,738**; Erregung 0 -> 0,000 T,
        # Nennerregung -> 0,3418 T bei 16,1 % Klirranteil, doppelte Erregung
        # -> 0,6837 T, also **exakt 2,000x** -- die Linearitaetsprobe, die ein
        # linearer Loeser bestehen MUSS.
        #
        # **"em3d" traegt seit dem 20.09.2026 -- und zwar erst, seit ein Loeser
        # wirklich durchgelaufen ist.** Der 3-D-Pfad zeichnete den Laeufer bis
        # dahin aus `magnet_legs`, also aus Magneten, die es hier nicht gibt;
        # `ema_em3d.laeufer_profile` baut ihn jetzt aus derselben
        # `ema_laeuferbild.teile()`-Quelle wie Leinwand, Raster und CAD, und
        # `write_sif` gibt den Erregerspulen ihre Gleichstromdichte. Gemessen
        # am frischen Payload: 48.055 Knoten, 61 Laeuferkoerper, 12 Spulen mit
        # +-459 A, Loeser 290 s, Orientierungspruefung 0,12 Grad gegen 3 Grad
        # Toleranz.
        #
        # **Was dieser Weg NICHT gibt, ist die Amplitude**: 0,196 T in der
        # Mittelebene gegen 0,509 T aus dem 2-D-Elmer derselben Erregung. Der
        # 0,7-mm-Luftspalt ist in einem bezahlbaren 3-D-Netz nicht aufloesbar,
        # und `COIL_J_SCALE` ist am STAENDER geeicht. Das steht als Warnung an
        # jedem Lauf -- eine getragene Stufe ist keine Zusicherung ueber jede
        # Zahl, die aus ihr faellt.
        stufen=("analytisch", "feld", "cad", "em3d"),
        feldweg="elmer2d_stat",
        ohne_bedeutung=_PM_KENNZAHLEN,
        hinweis=("Die einzige Art, bei der der Fluss EINGESTELLT wird -- "
                 "zweiter Freiheitsgrad im Betriebspunkt (Erregerstrom), dafuer "
                 "Schleifring- und Erregerverluste."),
    ),
    "gsm": Art(
        code="gsm",
        label="GSM — fremderregte Gleichstrommaschine (Kommutator)",
        erregung="fremderregt",
        hat_magnete=False,
        # Die Wicklung sitzt im LAEUFER (Anker) -- wie bei ASM und EESM faellt
        # der Hauptverlust dort an, an der thermisch schlechtesten Stelle.
        hat_laeuferwicklung=True,
        hat_schlupf=False,
        stellbarer_fluss=True,
        # "analytisch" und "cad" -- und ausdruecklich KEINE Feldstufe. Die
        # 2-D-FDM ist reell, linear und magnetostatisch; ein kommutierter Anker,
        # dessen Durchflutung im Raum stehenbleibt, waehrend das Blech sich
        # dreht, ist darin so wenig darstellbar wie ein Kaefig. Sie hier zu
        # fuehren hiesse, ein magnetostatisches Feld ohne Kommutierung
        # auszugeben und „GSM" darueberzuschreiben.
        stufen=("analytisch", "cad"),
        feldweg="keiner",
        ohne_bedeutung=(_PM_KENNZAHLEN + _DREHFELD_KENNZAHLEN
                        + _STAENDERNUT_KENNZAHLEN),
        hinweis=("Das Feld steht STILL (Schenkelpole am Staender), der "
                 "Kommutator haelt die Ankerdurchflutung im Raum fest. "
                 "E = k*Phi*omega und T = k*Phi*I_a mit DERSELBEN Konstante "
                 "k = p*z/(2*pi*a) -- daraus folgt E*I_a = T*omega exakt. "
                 "Begrenzt wird sie nicht vom Eisen, sondern vom Kommutator: "
                 "Lamellenspannung (Mittel und Spitze) und Umfangs"
                 "geschwindigkeit. Wendepole und Kompensationswicklung sind "
                 "NICHT modelliert."),
    ),
}

VORGABE = "pmsm"

LABELS = {c: a.label for c, a in ARTEN.items()}


def art_code(quelle) -> str:
    """Maschinenart aus Payload **oder** ``geom`` lesen. Unbekannt -> Vorgabe.

    Der Schluessel sitzt in ``geom``, weil die analytischen Funktionen
    (``_analytical_Bgap``, ``estimate_saliency``, ...) nur ``geom`` bekommen --
    laege er oben im Payload, waere er dort unsichtbar und die Art damit genau
    an den Stellen unbekannt, an denen sie entscheidet.
    """
    if not isinstance(quelle, dict):
        return VORGABE
    code = None
    geom = quelle.get("geom")
    if isinstance(geom, dict):
        code = geom.get("machineType")
    if not code:
        code = quelle.get("machineType")
    code = str(code or VORGABE).strip().lower()
    return code if code in ARTEN else VORGABE


def hole(code: str) -> Art:
    """Die Art zu einem Code. Unbekannter Code ist ein Fehler, keine Vorgabe --
    ein Tippfehler soll nicht still als PSM durchgehen."""
    code = str(code or "").strip().lower()
    if code not in ARTEN:
        raise ArtNichtUnterstuetzt(
            f"Unbekannte Maschinenart {code!r}. Bekannt: "
            + ", ".join(f"{c} ({a.label})" for c, a in ARTEN.items()))
    return ARTEN[code]


def traegt(code: str, stufe: str) -> bool:
    """Traegt diese Art diese Stufe heute?"""
    if stufe not in STUFEN:
        raise ValueError(f"Unbekannte Stufe {stufe!r}; bekannt: {', '.join(STUFEN)}")
    return stufe in hole(code).stufen


# Warum eine Stufe eine bestimmte Art NICHT traegt -- in einem Satz, an der
# Stelle, an der die Absage entsteht. Was hier nicht steht, wird nicht behauptet.
WARUM_NICHT = {
    ("gsm", "em3d"): (
        "Grund: ihre Erregerpole sitzen am STAENDER, und `ema_em3d.slot_rects` "
        "baut dort einen genuteten Drehstromstaender — gebaut wuerde baulich "
        "eine andere Maschine. Der LAEUFER ist seit dem 20.09.2026 netzbar "
        "(gemessen 48.634 Knoten, 54/54 Ankernuten); es fehlt der Staender."),
    ("gsm", "feld"): (
        "Grund: der kommutierte Anker ist ZEITabhaengig, und die 2-D-FDM ist "
        "reell, linear und magnetostatisch."),
}


def pruefe_stufe(code: str, stufe: str) -> Art:
    """Tor vor jeder Rechenstufe. Gibt die Art zurueck oder wirft.

    Der Fehlertext sagt ausdruecklich, **was statt dessen geht** -- sonst steht
    der Anwender (oder der Agent) vor einer Absage ohne Ausweg.
    """
    art = hole(code)
    if stufe in art.stufen:
        return art
    kann = ", ".join(STUFEN_LABEL[s] for s in art.stufen) or "noch nichts"
    # **„Traegt sie nicht" ist die halbe Auskunft.** Wer davorsitzt, will
    # wissen WARUM -- sonst liest sich die Absage wie eine Luecke im Zeitplan,
    # und man wartet auf etwas, das aus einem baulichen Grund nicht kommt.
    warum = WARUM_NICHT.get((code, stufe), "")
    raise ArtNichtUnterstuetzt(
        f"{art.label}: die Stufe „{STUFEN_LABEL.get(stufe, stufe)}“ traegt diese "
        f"Maschinenart noch nicht. Getragen wird bisher: {kann}. "
        + (warum + " " if warum else "")
        + "Es wird hier bewusst NICHT ersatzweise mit PSM-Physik gerechnet.")


FELDWEG_WERKZEUG = {
    "fdm":          "die Pipeline (run)",
    "elmer2d_harm": "cae_cli.py feld2d  (Elmer 2-D, harmonisch)",
    "elmer2d_stat": "cae_cli.py feld2d  (Elmer 2-D, magnetostatisch)",
}


# Dasselbe fuer die 3-D-Stufe: die Pipeline rechnet dort ``ema_em3d``
# (magnetostatisch, WhitneyAVSolver, Magnete als Quelle), der Kaefiglaeufer
# dagegen ``ema_em3d_harm`` (harmonisch, Kurzschlussring als leitender Koerper).
# Beides heisst "em3d", ist aber nicht derselbe Weg -- und ohne diese
# Unterscheidung liefe die ASM in die Magnetostatik und bekaeme ein Feld ohne
# Laeuferstroeme, also PSM-Physik unter fremdem Namen.
EM3D_WEG = {"pmsm": "elmer3d_stat", "asm": "elmer3d_harm"}
EM3D_WERKZEUG = {
    "elmer3d_stat": "die Pipeline (run em3d)",
    "elmer3d_harm": "cae_cli.py feld3d  (Elmer 3-D, harmonisch)",
}


def pruefe_em3d_weg(code: str, weg: str) -> Art:
    """Traegt diese Art die 3-D-Stufe **auf diesem Loeser**?

    Der Gegenpart zu ``pruefe_feldweg``, aus demselben Grund: ``traegt(code,
    "em3d")`` sagt nur, dass es fuer diese Art ueberhaupt eine 3-D-Stufe gibt.
    """
    art = pruefe_stufe(code, "em3d")
    hat = EM3D_WEG.get(code, "elmer3d_stat")
    if hat != weg:
        raise ArtNichtUnterstuetzt(
            f"{art.label}: die 3-D-Stufe laeuft nicht ueber "
            f"'{EM3D_WERKZEUG.get(weg, weg)}', sondern ueber "
            f"'{EM3D_WERKZEUG.get(hat, hat)}'.")
    return art


def pruefe_feldweg(code: str, weg: str) -> Art:
    """Traegt diese Art die Feldstufe **auf diesem Loeser**?

    ``pruefe_stufe(code, "feld")`` sagt nur, dass es fuer diese Art ueberhaupt
    eine Feldstufe gibt. Welcher Loeser sie traegt, sagt ``Art.feldweg`` -- und
    wer die ASM in die FDM schickt, bekommt hier einen Fehler mit der Adresse
    des richtigen Werkzeugs statt ein magnetostatisches Feld ohne Laeuferstroeme.
    """
    art = pruefe_stufe(code, "feld")
    if art.feldweg != weg:
        raise ArtNichtUnterstuetzt(
            f"{art.label}: die Feldstufe laeuft nicht ueber "
            f"'{FELDWEG_WERKZEUG.get(weg, weg)}', sondern ueber "
            f"'{FELDWEG_WERKZEUG.get(art.feldweg, art.feldweg)}'.")
    return art


# Welches Modul eine Art wirklich RECHNET. Die Zuordnung steht hier, weil hier
# die Arten stehen -- eine zweite Liste im Server oder im Paarvergleich waere
# die Stelle, an der eine neue Art an einem von drei Orten vergessen wird.
# ``pmsm`` hat keinen Eintrag: sie IST der Pfad, den ``ema_analysis`` rechnet.
MODULNAME = {
    "asm":   "ema_asm",
    "synrm": "ema_synrm",
    "eesm":  "ema_eesm",
    "gsm":   "ema_gsm",
}


def rechenmodul(code: str):
    """Das Modul, das diese Art rechnet -- oder ``None`` fuer die PSM.

    Spaet importiert: ``ema_asm`` und die uebrigen ziehen ``ema_pipeline``
    nach, und das zoege beim Import dieser Registrierung die halbe Kette mit.
    """
    name = MODULNAME.get(art_code({"machineType": code}) if isinstance(code, dict)
                         else code)
    if not name:
        return None
    try:
        return __import__(name)
    except Exception:                                        # noqa: BLE001
        return None


def gilt(code: str, kennzahl: str) -> bool:
    """Hat diese Kennzahl fuer diese Art ueberhaupt eine Bedeutung?"""
    return kennzahl not in hole(code).ohne_bedeutung


def ohne_bedeutung(code: str) -> tuple:
    return hole(code).ohne_bedeutung


def filtern(code: str, werte: dict, marke: str = "n. v.") -> dict:
    """Kennzahlen ohne Bedeutung fuer diese Art **beschriften**, nicht nullen.

    ``marke`` steht fuer „nicht verfuegbar/nicht anwendbar". Wer die Zahl
    weiterrechnen will, muss vorher ``gilt()`` fragen -- und genau das ist der
    Zweck: eine 0 haette man arglos weiterverwendet.
    """
    art = hole(code)
    return {k: (marke if k in art.ohne_bedeutung else v) for k, v in werte.items()}


def uebersicht() -> str:
    """Kurze Tafel fuer CLI und Agenten-Skill."""
    zeilen = ["Maschinenarten (Vorgabe: pmsm)", ""]
    for c, a in ARTEN.items():
        kann = ", ".join(a.stufen) or "—"
        zeilen.append(f"  {c:<6} {a.label}")
        zeilen.append(f"         Erregung: {a.erregung} · getragene Stufen: {kann}")
        if a.hinweis:
            zeilen.append(f"         {a.hinweis}")
    return "\n".join(zeilen)
