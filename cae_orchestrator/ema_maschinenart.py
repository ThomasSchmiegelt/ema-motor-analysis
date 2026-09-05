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

from dataclasses import dataclass, field

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
        label="ASM — Asynchronmaschine (Kaefiglaeufer)",
        erregung="kaefig",
        hat_magnete=False,
        hat_laeuferwicklung=True,
        hat_schlupf=True,
        stellbarer_fluss=True,
        # "feld" traegt seit ``ema_em2d_harm`` (harmonische 2-D-Rechnung mit
        # Elmers MagnetoDynamics2DHarmonic). NICHT die 2-D-FDM: die ist reell
        # und magnetostatisch, ein Kaefiglaeufer ist darin nicht abbildbar.
        stufen=("analytisch", "feld"),
        feldweg="elmer2d_harm",
        ohne_bedeutung=_PM_KENNZAHLEN,
        hinweis=("Der Magnetisierungsstrom liegt DAUERND im Stator, und der "
                 "Schlupfverlust faellt im Laeufer an -- der thermisch "
                 "schlechtesten Stelle. Dafuer keine Magnete: keine Masse, "
                 "keine Magnetkosten, keine Entmagnetisierung, kein "
                 "Kurzschlussmoment."),
    ),
    "synrm": Art(
        code="synrm",
        label="SynRM — Reluktanzmaschine (ohne Magnete)",
        erregung="reluktanz",
        hat_magnete=False,
        hat_laeuferwicklung=False,
        hat_schlupf=False,
        stellbarer_fluss=False,
        stufen=("analytisch",),
        ohne_bedeutung=_PM_KENNZAHLEN,
        hinweis=("Steht der PMa-SynRM-Anordnung geometrisch am naechsten "
                 "(``_build_pmasynrm`` ohne Magnete), das Moment kommt aber "
                 "ausschliesslich aus (Ld-Lq)."),
    ),
    "eesm": Art(
        code="eesm",
        label="EESM — fremderregte Synchronmaschine",
        erregung="fremderregt",
        hat_magnete=False,
        hat_laeuferwicklung=True,
        hat_schlupf=False,
        stellbarer_fluss=True,
        stufen=("analytisch",),
        ohne_bedeutung=_PM_KENNZAHLEN,
        hinweis=("Die einzige Art, bei der der Fluss EINGESTELLT wird -- "
                 "zweiter Freiheitsgrad im Betriebspunkt (Erregerstrom), dafuer "
                 "Schleifring- und Erregerverluste."),
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


def pruefe_stufe(code: str, stufe: str) -> Art:
    """Tor vor jeder Rechenstufe. Gibt die Art zurueck oder wirft.

    Der Fehlertext sagt ausdruecklich, **was statt dessen geht** -- sonst steht
    der Anwender (oder der Agent) vor einer Absage ohne Ausweg.
    """
    art = hole(code)
    if stufe in art.stufen:
        return art
    kann = ", ".join(STUFEN_LABEL[s] for s in art.stufen) or "noch nichts"
    raise ArtNichtUnterstuetzt(
        f"{art.label}: die Stufe „{STUFEN_LABEL.get(stufe, stufe)}“ traegt diese "
        f"Maschinenart noch nicht. Getragen wird bisher: {kann}. "
        f"Es wird hier bewusst NICHT ersatzweise mit PSM-Physik gerechnet.")


FELDWEG_WERKZEUG = {
    "fdm":          "die Pipeline (run)",
    "elmer2d_harm": "cae_cli.py feld2d  (Elmer 2-D, harmonisch)",
}


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
