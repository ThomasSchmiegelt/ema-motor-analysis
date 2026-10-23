"""Die FEM-Ergebnisse als SCHNITT durch das Netz -- statt als Punktwolke.

Was vorher da war und warum es nicht taugte
--------------------------------------------

``ema_pipeline._render_deform_single`` zeichnete ``ax.scatter(xs, ys, c=um, s=3)``
-- **alle** Knoten des Volumennetzes, auf die xy-Ebene projiziert. Drei Dinge sind
daran falsch, und jedes einzeln genuegt:

1. **Es ist eine Projektion, kein Schnitt.** Ueber die ganze Paketlaenge liegen
   die Knoten uebereinander; was man sieht, ist der Knoten, der zufaellig zuletzt
   gezeichnet wurde. Die Magnettaschen -- die interessante Stelle -- sind von
   Knoten der Stirnflaechen ueberdeckt und als Loecher nicht mehr erkennbar.
2. **Es zeigte die VERSCHIEBUNG.** Die ist bei einem Laeufer ein paar Mikrometer
   gross und sagt ueber das Versagen nichts; entscheidend ist die
   **Vergleichsspannung** am Steg. Sie lag im ``.frd``, wurde geparst
   (``_stress_vm``) -- und in kein Bild gezeichnet.
3. **Es sah aus wie ein Netz und war keines.** Genau diese Verwechslung steht
   schon im Kopf von ``_render_deform_analytical``: die Punktwolke „got mistaken
   for a mesh". Dort wurde sie fuer den analytischen Rueckfall durch eine glatte
   Flaeche ersetzt -- fuer das ECHTE FEM-Ergebnis blieb sie stehen.

Was hier statt dessen gerechnet wird
-------------------------------------

Ein **echter Schnitt** durch das Tetraedernetz bei ``z`` (Vorgabe: Mitte des
Blechpakets). Je Tetraeder, den die Ebene trifft, wird das Schnittpolygon aus den
Kantenschnittpunkten gebildet (drei oder vier Punkte, immer konvex) und der
Feldwert an den Schnittpunkten entlang der Kante **interpoliert**. Das Ergebnis
ist eine geschlossene, lueckenlose Flaeche aus den wirklichen Elementen -- mit
den Magnettaschen als Loechern, weil dort keine Elemente sind.

Gezeichnet werden kann damit, was im Ergebnis steht, und das ist mehr als vorher:
``spannung`` (Vergleichsspannung, die Groesse, auf die das Tor stellt),
``verschiebung`` (wie bisher, nur als Flaeche) und ``sicherheit``
(Fliessgrenze/Spannung -- die Karte, auf der man sieht, WO es knapp wird, ohne
eine Zahl im Kopf zu teilen).

Drei Entscheidungen mit Grund
------------------------------

* **Flaechige Einfaerbung je Element, nicht interpoliert ueber die Elementgrenze.**
  Ein C3D4 ist ein Element KONSTANTER Dehnung -- seine Spannung ist je Element
  eine Zahl, und eine weichgezeichnete Flaeche wuerde eine Auflösung behaupten,
  die das Netz nicht hat. Bei ein paar tausend Schnittpolygonen sieht das
  trotzdem stetig aus, und wer genau hinsieht, sieht das Netz: richtig so.
* **Die Verformung wird UEBERHOEHT gezeichnet, die Farbe nicht skaliert.**
  Dieselbe Trennung wie bisher; die Ueberhoehung steht im Titel.
* **Der Schnitt liegt in der MITTE.** Dort ist der ebene Verzerrungszustand am
  besten erfuellt; an den Stirnflaechen ist das Blech freier und die Spannung
  niedriger. Wer den Rand sehen will, gibt ``z`` an.

Was dieses Modul NICHT tut
---------------------------

Es rechnet nichts. Es bekommt Knoten, Elemente und Werte und zeichnet sie. Der
Schnitt ist deshalb auch keine zweite Auswertung neben ``_parse_frd_full`` oder
``ema_deck.kennzahlen`` -- die Kennzahlen kommen weiter von dort, dieses Modul
sagt nur, WO sie sitzen.

**Und deshalb steht es NICHT in** ``ema_werkzeugstand.PHYSIK``. Es gibt zwar
Zahlen heraus (``wert_p99``, ``wert_max`` je Bild), aber an keiner von ihnen
haengt eine Entscheidung -- das Tor stellt auf die ``.dat``/``.frd``-Werte. Es
mit aufzunehmen hiesse, dass jede geaenderte Farbleiste den Fingerabdruck der
PHYSIK bewegt, und dann ist er binnen einer Woche Rauschen, das niemand mehr
liest. ``ema_magnetlast`` und ``ema_kontakt`` stehen dort sehr wohl: die
bewegen ausgewiesene Zahlen.
"""

from __future__ import annotations

import base64
import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
import numpy as np                                               # noqa: E402
from matplotlib.collections import PolyCollection                # noqa: E402
from matplotlib.lines import Line2D                              # noqa: E402

# Die sechs Kanten eines Tetraeders, in den Ecknummern 0..3.
_KANTEN = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))

# Die Schluessel sind die, mit denen ``ema_pipeline`` die Bilder benennt
# (``struktur_<groesse>_<tag>.png``) und die der Ergebnisreiter als Knopfreihe
# zeigt -- sie muessen deshalb WOERTLICH dieselben sein. ``verschiebung`` steht
# als Zweitname daneben, weil das Feld im ``.frd`` so heisst.
GROESSEN = {
    "spannung":     ("Vergleichsspannung $\\sigma_v$ [MPa]", "inferno"),
    "verformung":   ("Verschiebung $|u|$ [µm]",              "plasma"),
    "verschiebung": ("Verschiebung $|u|$ [µm]",              "plasma"),
    "sicherheit":   ("Sicherheit $R_e/\\sigma_v$ [-]",       "RdYlGn"),
}

# Ein unbekannter Name bekommt KEINE geliehene Beschriftung. Der erste Entwurf
# fiel mit ``.get(groesse, GROESSEN["spannung"])`` still auf die Spannung
# zurueck -- und weil die Pipeline ``verformung`` schreibt und die Tabelle nur
# ``verschiebung`` kannte, stand ueber einer Mikrometer-Skala gemessen
# „Vergleichsspannung [MPa]". Eine falsche Einheit an einer richtigen Zahl ist
# schlimmer als gar keine: man rechnet mit ihr weiter.
UNBEKANNT = ("Wert (Groesse unbenannt)", "viridis")


def _b64(fig, dpi: int = 90) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def z_mitte(knoten: dict) -> float:
    """Mitte des Blechpakets aus den Knoten -- der FreeCAD-Weg legt das Paket
    symmetrisch um z = 0, ``ema_deck`` von 0 bis L. Geraten wird hier nichts."""
    if not knoten:
        return 0.0
    zs = [k[2] for k in knoten.values()]
    return 0.5 * (min(zs) + max(zs))


# ── Der Schnitt ──────────────────────────────────────────────────────────────

def schnittpolygone(knoten: dict, elemente: dict, z: float,
                    wert_knoten: dict | None = None,
                    wert_element: dict | None = None,
                    verschiebung: dict | None = None,
                    exagg: float = 0.0,
                    skal: float = 1.0,
                    nur_elemente: set | None = None) -> tuple[list, list]:
    """Tetraedernetz bei ``z`` schneiden -> ``(polygone, werte)``.

    ``wert_knoten``   Feldwert je Knoten (wird entlang der Kante interpoliert)
    ``wert_element``  Feldwert je Element (gilt fuer das ganze Polygon) --
                      ``ema_deck``/Z88/Aster liefern Gausspunktwerte je Element,
                      das ``.frd`` dagegen knotengemittelte. Beides geht hier
                      hinein, ohne dass eines in das andere umgerechnet wird:
                      eine Umrechnung waere eine zweite Glaettung, und genau
                      deren Vermeidung ist der Grund fuer ``*EL PRINT``.
    ``verschiebung``  Verschiebungsvektor je Knoten [mm]; mit ``exagg`` > 0 wird
                      das Polygon ueberhoeht gezeichnet.
    ``skal``          rpm²-Faktor: beide Lasten wachsen mit ω², und die FEM ist
                      linear -- Spannung UND Verschiebung skalieren exakt.
    ``nur_elemente``  nur diese Elemente schneiden. Gebraucht beim
                      Mehrkoerperlauf (``ema_kontakt``): dort sind die Magnete
                      eigene Koerper, und Blech und Magnet gehoeren nicht auf
                      EINE Farbskala -- der Magnet traegt 26 MPa, wo das Blech
                      760 traegt, und auf der gemeinsamen Skala waere er
                      schwarz wie Luft. Zwei Durchgaenge, zwei Skalen.

    Polygone mit weniger als drei Punkten werden weggelassen (die Ebene streift
    eine Kante); sie traegt keine Flaeche und faerbte nur eine Linie ein.

    **Ein EBENES Netz wird nicht geschnitten, es IST der Schnitt.** Beim ebenen
    Mehrkoerperlauf (``ema_kontakt.baue_eben``) liegen alle Knoten auf z = 0 --
    eine Schnittebene bei z = 0 streift dort jedes Element und die Funktion
    gaebe nichts zurueck. Erkannt wird es an der Elementlaenge (drei Knoten =
    Dreieck, vier = Tetraeder) und nicht an einer Flagge: die muesste sonst
    durch jeden Aufrufer gereicht werden, und die Laenge ist eindeutig.
    """
    if elemente and all(len(ids) in (3, 6) for ids in elemente.values()):
        return _polygone_eben(knoten, elemente, wert_knoten, wert_element,
                              verschiebung, exagg, skal, nur_elemente)
    polys: list = []
    werte: list = []
    for eid, ids in elemente.items():
        if nur_elemente is not None and eid not in nur_elemente:
            continue
        ecken = ids[:4]
        try:
            p = [knoten[i] for i in ecken]
        except KeyError:
            continue
        d = [q[2] - z for q in p]
        if min(d) > 0.0 or max(d) < 0.0:
            continue                                   # Ebene trifft nicht
        pts: list = []
        for a, b in _KANTEN:
            da, db = d[a], d[b]
            if (da > 0.0 and db > 0.0) or (da < 0.0 and db < 0.0):
                continue
            if abs(da - db) < 1e-12:
                continue                               # Kante liegt IN der Ebene
            t = da / (da - db)
            if t < -1e-9 or t > 1.0 + 1e-9:
                continue
            x = p[a][0] + t * (p[b][0] - p[a][0])
            y = p[a][1] + t * (p[b][1] - p[a][1])
            if exagg and verschiebung is not None:
                ua = verschiebung.get(ecken[a])
                ub = verschiebung.get(ecken[b])
                if ua is not None and ub is not None:
                    dx = (ua[0] + t * (ub[0] - ua[0])) * skal * exagg
                    dy = (ua[1] + t * (ub[1] - ua[1])) * skal * exagg
                    x += dx
                    y += dy
            if wert_knoten is not None:
                wa = wert_knoten.get(ecken[a])
                wb = wert_knoten.get(ecken[b])
                w = None if (wa is None or wb is None) else wa + t * (wb - wa)
            else:
                w = None
            pts.append((x, y, w))
        if len(pts) < 3:
            continue
        cx = sum(q[0] for q in pts) / len(pts)
        cy = sum(q[1] for q in pts) / len(pts)
        pts.sort(key=lambda q: math.atan2(q[1] - cy, q[0] - cx))
        if wert_element is not None:
            w = wert_element.get(eid)
        else:
            gueltig = [q[2] for q in pts if q[2] is not None]
            w = (sum(gueltig) / len(gueltig)) if gueltig else None
        if w is None:
            continue
        polys.append([(q[0], q[1]) for q in pts])
        werte.append(w * skal if wert_element is not None or wert_knoten is not None
                     else w)
    return polys, werte


# ── Das Bild ─────────────────────────────────────────────────────────────────

def feldbild(knoten: dict, elemente: dict, geom: dict,
             groesse: str = "spannung",
             wert_knoten: dict | None = None,
             wert_element: dict | None = None,
             verschiebung: dict | None = None,
             z: float | None = None,
             skal: float = 1.0,
             exagg: float = 0.0,
             vmin: float | None = None, vmax: float | None = None,
             yield_mpa: float = 0.0,
             titel: str = "", untertitel: str = "",
             px: int = 2400,
             netz_zeigen: bool = False,
             vorab: tuple | None = None) -> tuple[str, dict]:
    """Ein Schnittbild. Rueckgabe ``(png_base64, kennzahlen)``.

    ``groesse`` waehlt nur Beschriftung und Farbskala -- die Werte kommen von
    aussen. ``sicherheit`` rechnet aus den Spannungswerten ``R_e/sigma``; das ist
    die einzige Umrechnung hier, und sie ist eine Division.

    ``vorab`` ist ein schon geschnittenes ``(polygone, werte)`` bei ``skal = 1``.
    Der Schnitt haengt nur am NETZ, und das ist ueber alle Drehzahlen dasselbe --
    Spannung und Verschiebung wachsen mit ω², die Geometrie nicht. Ihn je Bild
    neu zu rechnen waere bei einem 68.000-Element-Netz die teuerste Stelle der
    ganzen Darstellung, und sie waere umsonst. (Fuer die VERFORMTE Darstellung
    gilt das nicht: dort wandern die Polygone mit, dort wird neu geschnitten.)
    """
    label, cmap = GROESSEN.get(groesse, UNBEKANNT)
    zz = z_mitte(knoten) if z is None else float(z)
    if vorab is not None:
        polys, roh = vorab
        werte = [w * skal for w in roh]
    else:
        polys, werte = schnittpolygone(knoten, elemente, zz,
                                       wert_knoten=wert_knoten,
                                       wert_element=wert_element,
                                       verschiebung=verschiebung,
                                       exagg=exagg, skal=skal)
    kenn = {"z_schnitt_mm": round(zz, 3), "n_polygone": len(polys),
            "exagg": round(exagg, 1), "skal": round(skal, 5)}
    if not polys:
        kenn["fehler"] = ("Die Schnittebene trifft kein Element -- das Netz hat "
                          "bei dieser z-Lage keine Tetraeder (oder die "
                          "Elementtabelle fehlt).")
        return "", kenn

    v = np.asarray(werte, dtype=float)
    if groesse == "sicherheit":
        if yield_mpa <= 0:
            kenn["fehler"] = "ohne Fliessgrenze keine Sicherheitskarte"
            return "", kenn
        with np.errstate(divide="ignore", invalid="ignore"):
            v = np.where(v > 1e-9, yield_mpa / v, np.nan)
        v = np.clip(v, 0.0, 5.0)
    kenn.update({"wert_max": round(float(np.nanmax(v)), 4),
                 "wert_min": round(float(np.nanmin(v)), 4),
                 "wert_p99": round(float(np.nanpercentile(v, 99)), 4),
                 "wert_median": round(float(np.nanmedian(v)), 4)})

    lo = vmin if vmin is not None else (0.0 if groesse != "sicherheit" else 0.0)
    hi = vmax if vmax is not None else float(np.nanpercentile(v, 99.5))
    if groesse == "sicherheit":
        hi = vmax if vmax is not None else 3.0
    if not (hi > lo):
        hi = lo + 1e-6

    r_rot = float(geom.get("rotorOD", 0.0)) / 2.0
    ext = max(r_rot * 1.08, max(max(abs(x) for x, _y in q) for q in polys) * 1.05)

    fig_in = max(5.0, px / 600.0)
    fig, ax = plt.subplots(figsize=(fig_in, fig_in), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")
    pc = PolyCollection(polys, array=v, cmap=cmap,
                        edgecolors=("#00000030" if netz_zeigen else "none"),
                        linewidths=(0.15 if netz_zeigen else 0.0))
    pc.set_clim(lo, hi)
    ax.add_collection(pc)

    th = np.linspace(0, 2 * math.pi, 361)
    for r_mm, col, lw in ((r_rot, "#8899aa", 0.9),
                          (float(geom.get("shaftD", 0.0)) / 2.0, "#8899aa", 0.7)):
        if r_mm > 0:
            ax.plot(r_mm * np.cos(th), r_mm * np.sin(th), col, lw=lw, alpha=0.55)
    ax.set_xlim(-ext, ext)
    ax.set_ylim(-ext, ext)
    ax.set_aspect("equal")
    ax.axis("off")

    cb = fig.colorbar(pc, ax=ax, fraction=0.046, pad=0.02)
    cb.set_label(label, color="#ddd", fontsize=10)
    cb.ax.tick_params(color="#666", labelcolor="#bbb", labelsize=8)
    cb.outline.set_edgecolor("#444")
    if groesse == "sicherheit" and yield_mpa > 0:
        cb.ax.axhline(1.0, color="#ff3b30", lw=1.6)
        # IN die Farbleiste, nicht daneben: rechts davon liegen schon die
        # Zahlen und die Achsenbeschriftung, und drei Texte an derselben Stelle
        # sind unleserlich (gemessen am ersten Lauf).
        cb.ax.text(0.5, 1.0, "SF 1", ha="center", va="center", fontsize=7,
                   color="#ffffff", transform=cb.ax.get_yaxis_transform(),
                   bbox={"facecolor": "#ff3b30", "edgecolor": "none",
                         "pad": 1.0, "alpha": 0.85})

    if titel:
        fig.suptitle(titel, color="white", fontsize=11, y=0.985)
    unten = untertitel or (
        f"Schnitt bei z = {zz:.1f} mm (Mitte des Blechpakets) · "
        f"{len(polys):,} Schnittflaechen aus dem Rechennetz".replace(",", "."))
    ax.text(0.5, -0.035, unten, transform=ax.transAxes, ha="center", va="top",
            color="#7f8c99", fontsize=8)
    fig.tight_layout()
    dpi = max(90, int(px / fig_in))
    return _b64(fig, dpi=dpi), kenn


# ── Mehrkoerper: Blech UND Magnete, zwei Skalen ──────────────────────────────

def _polygone_eben(knoten: dict, elemente: dict,
                   wert_knoten: dict | None,
                   wert_element: dict | None,
                   verschiebung: dict | None,
                   exagg: float, skal: float,
                   nur_elemente: set | None) -> tuple[list, list]:
    """Jedes Dreieck IST sein Polygon -- der ebene Fall, ohne Schnitt.

    Gibt dieselbe Form zurueck wie ``schnittpolygone`` (``(polygone, werte)``),
    damit ``feldbild``/``feldbild_mehrkoerper`` in beiden Dimensionen dieselbe
    Zeichenroutine benutzen. Nur die drei ECKEN zaehlen; ein Netz 2. Ordnung
    traegt zusaetzlich Mittenknoten, und die gehoeren nicht in den Umriss.
    """
    polys: list = []
    werte: list = []
    for eid, ids in elemente.items():
        if nur_elemente is not None and eid not in nur_elemente:
            continue
        ecken = ids[:3]
        try:
            p = [knoten[i] for i in ecken]
        except KeyError:
            continue
        pts = []
        for k, q in zip(ecken, p):
            x, y = q[0], q[1]
            if exagg and verschiebung is not None:
                u = verschiebung.get(k)
                if u is not None:
                    x += u[0] * skal * exagg
                    y += u[1] * skal * exagg
            pts.append((x, y))
        if wert_element is not None:
            w = wert_element.get(eid)
            if w is None:
                continue
            werte.append(w * skal)
        elif wert_knoten is not None:
            try:
                w = sum(wert_knoten[i] for i in ecken) / 3.0
            except KeyError:
                continue
            werte.append(w * skal)
        else:
            werte.append(0.0)
        polys.append(pts)
    return polys, werte


def feldbild_mehrkoerper(knoten: dict, elemente: dict, ist_eisen: dict,
                         geom: dict,
                         vm_eisen: dict, zug_magnet: dict,
                         z: float | None = None, skal: float = 1.0,
                         vmax_eisen: float | None = None,
                         vmax_magnet: float | None = None,
                         yield_mpa: float = 0.0, zug_grenze: float = 0.0,
                         titel: str = "", px: int = 2400) -> tuple[str, dict]:
    """Der Schnitt durch den MEHRKOERPER-Rotor: Blech und Magnete zugleich.

    **Zwei Farbskalen, und das ist kein Schmuck.** Gemessen am Beispiellauf
    traegt das Blech 248 MPa (P99), der Magnet 8,4 MPa Hauptzugspannung -- auf
    einer gemeinsamen Skala waere der Magnet schwarz und von Luft nicht zu
    unterscheiden, also genau so unsichtbar wie in dem Modell, das ihn gar nicht
    kannte. Dazu kommt, dass die beiden verschiedene GROESSEN sind: beim Blech
    zaehlt die Vergleichsspannung gegen die Fliessgrenze, beim sproeden Magneten
    die groesste HauptZUGspannung gegen seine Zugfestigkeit.

    ``vm_eisen``/``zug_magnet``: Werte JE ELEMENT (der Kontaktlauf gibt
    Gausspunktwerte ueber ``*EL PRINT`` aus, keine knotengemittelten).
    """
    zz = z_mitte(knoten) if z is None else float(z)
    e_fe = {e for e in elemente if ist_eisen.get(e, True)}
    e_mg = {e for e in elemente if not ist_eisen.get(e, True)}
    pf, wf = schnittpolygone(knoten, elemente, zz, wert_element=vm_eisen,
                             skal=skal, nur_elemente=e_fe)
    pm, wm = schnittpolygone(knoten, elemente, zz, wert_element=zug_magnet,
                             skal=skal, nur_elemente=e_mg)
    kenn = {"z_schnitt_mm": round(zz, 3), "n_polygone_eisen": len(pf),
            "n_polygone_magnet": len(pm), "skal": round(skal, 5)}
    if not pf:
        kenn["fehler"] = "Die Schnittebene trifft kein Blechelement"
        return "", kenn
    vf = np.asarray(wf, dtype=float)
    hi_f = vmax_eisen if vmax_eisen else float(np.percentile(vf, 99.5))
    kenn["eisen_p99"] = round(float(np.percentile(vf, 99)), 2)
    kenn["eisen_max"] = round(float(vf.max()), 2)

    r_rot = float(geom.get("rotorOD", 0.0)) / 2.0
    ext = max(r_rot * 1.08,
              max(max(abs(x) for x, _y in q) for q in pf) * 1.05)
    # Feste Achsen statt `tight_layout`: ZWEI Farbleisten nebeneinander bringt
    # die automatische Anordnung nicht unter (gemessen: „Tight layout not
    # applied", Beschriftungen ineinander). Hier ist die Aufteilung
    # ausgeschrieben, und dann sitzt sie.
    fig_in = max(5.0, px / 600.0)
    fig = plt.figure(figsize=(fig_in * 1.3, fig_in), facecolor="#0d0d0d")
    ax = fig.add_axes([0.01, 0.07, 0.72, 0.85])
    ax.set_facecolor("#0d0d0d")
    pc = PolyCollection(pf, array=vf, cmap=GROESSEN["spannung"][1],
                        edgecolors="none")
    pc.set_clim(0.0, max(hi_f, 1e-6))
    ax.add_collection(pc)

    pcm = None
    if pm:
        vmg = np.asarray(wm, dtype=float)
        hi_m = vmax_magnet if vmax_magnet else max(
            float(np.percentile(vmg, 99.5)), 1e-6)
        kenn["magnet_p99"] = round(float(np.percentile(vmg, 99)), 2)
        kenn["magnet_max"] = round(float(vmg.max()), 2)
        pcm = PolyCollection(pm, array=vmg, cmap="winter", edgecolors="none")
        pcm.set_clim(0.0, hi_m)
        ax.add_collection(pcm)

    th = np.linspace(0, 2 * math.pi, 361)
    for r_mm in (r_rot, float(geom.get("shaftD", 0.0)) / 2.0):
        if r_mm > 0:
            ax.plot(r_mm * np.cos(th), r_mm * np.sin(th), "#8899aa",
                    lw=0.9, alpha=0.55)
    ax.set_xlim(-ext, ext)
    ax.set_ylim(-ext, ext)
    ax.set_aspect("equal")
    ax.axis("off")

    def _leiste(mappable, x, label, grenze, hi):
        cax = fig.add_axes([x, 0.13, 0.021, 0.72])
        cb = fig.colorbar(mappable, cax=cax)
        cb.set_label(label, color="#ddd", fontsize=9)
        cb.ax.tick_params(color="#666", labelcolor="#bbb", labelsize=8)
        cb.outline.set_edgecolor("#444")
        if grenze > 0 and hi >= grenze:
            cb.ax.axhline(grenze, color="#ff3b30", lw=1.6)

    _leiste(pc, 0.775, "Blech: $\\sigma_v$ [MPa]", yield_mpa, hi_f)
    if pcm is not None:
        _leiste(pcm, 0.905, "Magnet: groesste Hauptzugspannung [MPa]",
                zug_grenze, hi_m)

    if titel:
        fig.suptitle(titel, color="white", fontsize=11, y=0.975)
    fig.text(0.37, 0.025,
             f"Schnitt bei z = {zz:.1f} mm · {len(pf):,} Blech- und {len(pm):,} "
             f"Magnetflaechen aus dem Rechennetz\nzwei Groessen, zwei Skalen: "
             f"das zaehe Blech FLIESST, der sproede Magnet REISST"
             .replace(",", "."),
             ha="center", va="bottom", color="#7f8c99", fontsize=8)
    return _b64(fig, dpi=max(90, int(px / fig_in))), kenn


# ── Das Lastbild: WO die Magnetfliehkraft angreift ───────────────────────────

def lastbild(geom: dict, waende: list, axial_mm: float, rpm: float,
             steg: dict | None = None, px: int = 2000) -> tuple[str, dict]:
    """Der Querschnitt mit den belasteten Taschenwaenden und ihren Kraftpfeilen.

    Dieses Bild gibt es, weil „die Magnetlast ist jetzt drin" eine Behauptung
    ist, solange niemand sieht, WO sie angreift und wie gross sie ist. Es
    zeichnet nicht die Rechnung nach, sondern genau die Liste, die in den Loeser
    gegangen ist (``ema_magnetlast.waende``) -- eine Wand, die hier fehlt, fehlt
    auch im Modell.
    """
    import ema_magnetlast as ml
    from ema_topology import leg_center, magnet_legs

    r_rot = float(geom.get("rotorOD", 0.0)) / 2.0
    r_sh = float(geom.get("shaftD", 0.0)) / 2.0
    poles = max(2, int(geom.get("p", 3)) * 2)
    gap = ml.klebespalt_mm(geom)

    fig_in = max(5.0, px / 600.0)
    fig, ax = plt.subplots(figsize=(fig_in, fig_in), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")
    th = np.linspace(0, 2 * math.pi, 361)
    ax.fill(r_rot * np.cos(th), r_rot * np.sin(th), "#2b3240", zorder=0)
    ax.fill(r_sh * np.cos(th), r_sh * np.sin(th), "#0d0d0d", zorder=1)
    ax.plot(r_rot * np.cos(th), r_rot * np.sin(th), "#8899aa", lw=1.0, zorder=2)
    if r_sh > 0:
        ax.plot(r_sh * np.cos(th), r_sh * np.sin(th), "#8899aa", lw=0.8, zorder=2)

    # Die Taschen als Langloch -- dieselbe Form, die geschnitten wird.
    legs, _meta = magnet_legs(geom)
    for lg in legs:
        if lg.placement != "interior" or lg.length <= 0 or lg.thickness <= 0:
            continue
        hl = lg.length / 2.0 + gap
        ht = lg.thickness / 2.0 + gap
        cx0, cy0 = leg_center(lg)
        for pol in range(poles):
            pa = pol * 2.0 * math.pi / poles
            ca, sa = math.cos(pa), math.sin(pa)
            cx = cx0 * ca - cy0 * sa
            cy = cx0 * sa + cy0 * ca
            t = lg.tilt + pa
            ux, uy = math.cos(t), math.sin(t)
            vx, vy = -uy, ux
            bogen = np.linspace(-math.pi / 2, math.pi / 2, 24)
            pts = []
            for b in bogen:                              # Kappe bei +hl_geo
                e = lg.length / 2.0
                pts.append((cx + (e + ht * math.cos(b)) * ux + ht * math.sin(b) * vx,
                            cy + (e + ht * math.cos(b)) * uy + ht * math.sin(b) * vy))
            for b in bogen:                              # Kappe bei -hl_geo
                e = -lg.length / 2.0
                pts.append((cx + (e - ht * math.cos(b)) * ux - ht * math.sin(b) * vx,
                            cy + (e - ht * math.cos(b)) * uy - ht * math.sin(b) * vy))
            ax.fill([q[0] for q in pts], [q[1] for q in pts],
                    "#0d0d0d", zorder=3)
            ax.plot([q[0] for q in pts] + [pts[0][0]],
                    [q[1] for q in pts] + [pts[0][1]],
                    "#55606f", lw=0.5, zorder=4)
            _ = hl

    # Die Waende und ihre Kraefte.
    f_max = max((w["F_N"] for w in waende), default=1.0) or 1.0
    pfeil_max = 0.18 * max(r_rot, 1.0)
    farbe = {"flanke": "#ff9f0a", "kappe": "#32d74b"}
    for w in waende:
        if w["art"] == "flanke":
            ax.plot([w["px"] - w["halb"] * w["tx"], w["px"] + w["halb"] * w["tx"]],
                    [w["py"] - w["halb"] * w["ty"], w["py"] + w["halb"] * w["ty"]],
                    color=farbe["flanke"], lw=2.0, zorder=5, solid_capstyle="round")
        else:
            b = np.linspace(-math.pi / 2, math.pi / 2, 20)
            nx, ny = w["nx"], w["ny"]
            tx, ty = -ny, nx
            ax.plot([w["px"] + w["radius"] * (math.cos(q) * nx + math.sin(q) * tx)
                     for q in b],
                    [w["py"] + w["radius"] * (math.cos(q) * ny + math.sin(q) * ty)
                     for q in b],
                    color=farbe["kappe"], lw=2.0, zorder=5)
        lng = pfeil_max * (w["F_N"] / f_max) ** 0.5
        ax.annotate("", xy=(w["px"] + w["nx"] * lng, w["py"] + w["ny"] * lng),
                    xytext=(w["px"], w["py"]), zorder=6,
                    arrowprops={"arrowstyle": "-|>", "color": farbe[w["art"]],
                                "lw": 1.3, "shrinkA": 0, "shrinkB": 0})

    s = ml.summe(waende, poles=poles)
    ext = r_rot * 1.22
    ax.set_xlim(-ext, ext)
    ax.set_ylim(-ext, ext)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.suptitle(
        f"Magnetfliehkraft auf die Taschenwaende  |  {rpm:,.0f} U/min  |  "
        f"{s['kraft_je_magnet_kN']:.1f} kN je Magnet  |  "
        f"{s['kraft_je_pol_kN']:.1f} kN je Pol".replace(",", "."),
        color="white", fontsize=11, y=0.98)
    # KEIN Legendenkasten. Der Laeufer ist ein Kreis in einem Quadrat, und
    # ``bbox_inches="tight"`` beschneidet das Bild hinterher auf seinen Inhalt
    # -- jede Ankerstelle, die vorher frei aussah, liegt danach am Motiv:
    # gemessen sass der Kasten nacheinander auf dem untersten Pol, auf dem
    # obersten und im Titel. Die beiden Farben stehen deshalb FARBIG in der
    # Fusszeile, wo ohnehin Platz ist und wo nichts verrutschen kann.
    # Rechts- und linksbuendig an der Mitte, nicht auf zwei feste Mitten: wie
    # breit die beiden Beschriftungen werden, haengt an Schrift und Aufloesung
    # -- zentriert gesetzt stiessen sie gemessen aneinander
    # („…Normalkomponente)Endkappe…").
    ax.text(0.49, -0.035, "▬ Flanke (Normalkomponente)", transform=ax.transAxes,
            ha="right", va="top", color=farbe["flanke"], fontsize=8.5)
    ax.text(0.51, -0.035, "▬ Endkappe (Laengskomponente)", transform=ax.transAxes,
            ha="left", va="top", color=farbe["kappe"], fontsize=8.5)
    unten = (f"ihre Vektorsumme IST die Fliehkraft des Magneten\n"
             f"{s['n_magnete']} Magnete, {s['magnet_kg']:.3f} kg, "
             f"{s['n_waende']} Waende · Pfeillaenge ~ sqrt(F) · "
             f"Druck bis {s['druck_max_MPa']:.1f} MPa")
    if steg and steg.get("sigma_steg_MPa"):
        unten += (f"\nRichtwert Steg: {steg['sigma_steg_MPa']:.0f} MPa bei "
                  f"{steg['s_rand_mm']:.2f} mm Randsteg "
                  f"(Ring {steg.get('sigma_ring_MPa') or 0:.0f} MPa, "
                  f"ueberlagert {steg.get('sigma_ueberlagert_MPa') or 0:.0f} MPa)")
    ax.text(0.5, -0.075, unten, transform=ax.transAxes, ha="center", va="top",
            color="#7f8c99", fontsize=8)
    fig.tight_layout()
    dpi = max(90, int(px / fig_in))
    return _b64(fig, dpi=dpi), s
