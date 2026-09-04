"""Feldlinienbilder zum Ansehen -- durchsichtig, aufgeschnitten, ein Pol, Laengsschnitt.

Warum es dieses Modul gibt
--------------------------

Die Pipeline rendert laengst ein Feldbild (``charts/em_field.png``, aus
``ema_pipeline._field_frame``). Es ist ein **Berichtsbild**: schwarzer Grund,
volle Flaeche, |B| als deckende Heatmap, die Feldlinien als duenner cyanfarbener
Faden obendrauf. Auf einer Berichtsseite ist das richtig. In der rechten Spalte
des Agentenreiters -- wo die Kacheln nebeneinander gelesen werden und wo eine
Bildschirmaufnahme mitlaeuft -- ist es das nicht: der Kasten ist zu, die Linien
ertrinken in der Farbflaeche, und die interessanten Stellen (Luftspalt,
Taschenstege, Barrieren) sind genau die dunklen.

Hier steht deshalb die andere Haelfte: **die Feldlinie ist die Hauptsache, das
Blech ist Kulisse.** Vier Ansichten, alle als PNG **mit Alphakanal**.

Was "durchsichtig" hier heisst
------------------------------

Nicht ein pauschaler Schleier ueber allem -- das waere nur ein blasseres
Berichtsbild. **Die Deckkraft ist die Flussdichte selbst**: die Farbkarte traegt
eine Alpharampe, also ist Luft (|B| ~ 0) voellig durchsichtig und gesaettigtes
Blech nahezu deckend. Man sieht damit buchstaeblich *durch die Maschine
hindurch* und nur dorthin, wo Fluss ist. Zusaetzlich ist der Bildgrund selbst
durchsichtig, sodass die Kachel auf dem Seitengrund sitzt statt als schwarzer
Block. Beides zusammen -- die Kachel bekommt in ``ema_agent.html`` ein
Schachbrett hinterlegt, sonst laege der Alphakanal auf dem weissen
Vorgabegrund von ``.kachel img`` und die Durchsicht waere nicht zu erkennen.

Die vier Ansichten
------------------

``linien``   Ganzer Querschnitt, Blech als Silhouette, Feldlinien voll.
``schnitt``  Derselbe Schnitt, der Stator ueber einen Sektor **weggenommen** --
             freier Blick auf Luftspalt, Rotor und Taschen. Die Feldlinien im
             weggenommenen Sektor bleiben blass stehen, damit die Schnittkante
             nicht wie eine Feldgrenze aussieht.
``pol``      **Ein** Polsektor gross. Ueber dem ganzen Kreis sind die Linien ein
             Knaeuel; hier sind Stege, Barrieren und Streupfade einzeln zu sehen.
             Die Hoehenlinien werden aus dem SICHTBAREN Ausschnitt bestimmt, nicht
             aus dem ganzen Bild -- sonst liegen im Zoom drei Linien.
``laengs``   Achsschnitt (r-z). **Nur mit 3-D-Ergebnis ein gerechnetes Feld**: die
             2-D-FDM kennt kein z (kein sigma, kein d/dz), ein "Laengsschnitt" aus
             ihr waere gezeichnet, nicht gerechnet. Liegt eine Elmer-VTU im Projekt,
             wird sie in der Ebene y=0 abgetastet und zeigt den Endeffekt; liegt
             keine vor, steht die Geometrie da -- mit genau diesem Satz im Bild.

Zwei Fallen, die hier schon eingebaut sind
------------------------------------------

* **Ausserhalb des Stators wird geblendet.** Das FDM-Gebiet ist mit Luft bis zum
  kuenstlichen Dirichlet-Rand aufgefuellt; A veraendert sich dort weiter, obwohl
  |B| ~ 0 ist. Zeichnet man die A-Hoehenlinien mit, sieht es aus, als trete
  reichlich Fluss aus dem Gehaeuse aus. (Dieselbe Blende steht in
  ``_field_frame`` und ist dort schon begruendet.)
* **Magnetumrisse kommen aus ``ema_pipeline._draw_magnet_outlines``**, nicht aus
  einer zweiten Zeichenroutine. Die Platzierung dort spiegelt
  ``ema_analysis._rasterise``; eine eigene Kopie waere in der ersten
  Topologieaenderung falsch, ohne dass es jemand merkt.
"""

from __future__ import annotations

import math
import os

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                       # noqa: E402
from matplotlib.colors import ListedColormap, PowerNorm   # noqa: E402
from matplotlib.lines import Line2D                   # noqa: E402
from matplotlib.patches import Rectangle              # noqa: E402

import ema_analysis                                   # noqa: E402


ANSICHTEN = ("linien", "schnitt", "pol", "laengs")
PRAEFIX   = "feld"

# Hoehenlinien: prozentgleiche Stufen von A, nicht gleiche A-Schritte -- so steht
# hinter jedem Zwischenraum gleich viel Fluss und die Linien draengen sich dort,
# wo magnetisch etwas passiert (Luftspalt, Taschen), statt gleichmaessig ueber
# das Blech verteilt zu sein. 30 bleibt im Vollbild lesbar; im Polzoom sind es
# mehr, weil dort nur ein Achtel des A-Bereichs im Bild liegt.
N_LINIEN_VOLL = 22
N_LINIEN_ZOOM = 24

C_LINIE   = "#41e9ff"      # Feldlinie
C_SCHNITT = "#ffb04a"      # Schnittkante
C_BLECH   = "#9fb4c9"      # Blechsilhouette
C_TEXT    = "#dfe6ee"
C_TEXT2   = "#9fb0c0"


# ── Leinwand ─────────────────────────────────────────────────────────────────

def _leinwand(breite: float = 6.2, hoehe: float = 6.2):
    """Achse ohne jeden Grund -- Figur UND Achse durchsichtig."""
    fig, ax = plt.subplots(figsize=(breite, hoehe))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor("none")
    ax.axis("off")
    return fig, ax


def _speichern(fig, pfad: str, px: int = 1400) -> str:
    os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
    dpi = max(100, int(px / fig.get_size_inches()[0]))
    fig.savefig(pfad, dpi=dpi, transparent=True,
                bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    return pfad


def durchsicht_cmap(name: str = "magma", a_max: float = 0.93,
                    gamma: float = 0.72) -> ListedColormap:
    """Farbkarte, deren **Deckkraft mit |B| waechst**.

    Das ist der ganze Trick der Durchsicht: nicht die Flaeche wird blass
    gemacht, sondern die Luft wird unsichtbar. Wo kein Fluss ist, ist auch
    nichts zu sehen -- der Betrachter schaut durch die Maschine auf das, was
    Fluss fuehrt. ``gamma < 1`` zieht die Rampe nach vorn, sonst bliebe der
    ganze Luftspaltbereich (0,2...0,6 T) fast unsichtbar.
    """
    f = plt.get_cmap(name)(np.linspace(0, 1, 256))
    f[:, -1] = (np.linspace(0, 1, 256) ** gamma) * a_max
    cm = ListedColormap(f)
    cm.set_bad((0, 0, 0, 0))
    return cm


# ── Feld holen ───────────────────────────────────────────────────────────────

def feld_rechnen(geom: dict, N: int = 560, rotor_angle: float = 0.0,
                 iq: float = 0.0, id_: float = 0.0,
                 saturate: bool = True) -> dict:
    """EIN FDM-Lauf, aus dem alle Querschnitts-Ansichten gezeichnet werden.

    Bewusst einer: der Loeser ist der teure Teil (Sekunden bis Minuten), das
    Zeichnen kostet nichts. Vier Ansichten aus vier Loesungen waeren viermal so
    teuer und -- schlimmer -- vier leicht verschiedene Felder in einer Bildreihe,
    die nebeneinander gelesen wird.
    """
    em = ema_analysis.run_em_analysis(geom, N=N, rotor_angle=rotor_angle,
                                      iq=iq, id_=id_, saturate=saturate)
    sc, ctr = em["scale"], em["center"]
    B = np.asarray(em["B_mag"], dtype=float)
    A = np.asarray(em["A"], dtype=float)

    # Materialmasken aus DERSELBEN Rasterung, die das Feld erzeugt hat -- damit
    # die Silhouette pixelgenau zur Loesung passt (Nuten, Taschen, Stege inklusive).
    _mu, _J, _sc2, _ctr2, maps = ema_analysis._rasterise(
        geom, N, rotor_angle=rotor_angle, iq=iq, id_=id_, maps=True)

    ceil = float(getattr(ema_analysis, "IRON_B_SAT_DISPLAY", 2.1) or 2.1)
    B = np.minimum(B, ceil)

    ny, nx = B.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    r_mm = np.hypot(xx - ctr, yy - ctr) / sc
    aussen = r_mm > (geom["statorOD"] / 2.0) * 1.02
    B = np.where(aussen, np.nan, B)
    A = np.where(aussen, np.nan, A)

    vmax = float(np.nanpercentile(B, 99.5)) if np.isfinite(B).any() else ceil
    vmax = max(0.3, min(vmax, ceil))

    return {"em": em, "B": B, "A": A, "sc": sc, "ctr": ctr, "N": N,
            "r_mm": r_mm, "winkel": np.arctan2(yy - ctr, xx - ctr),
            "eisen": maps["iron"], "magnet": maps["magnet"],
            "vmax": vmax, "rotor_angle": rotor_angle,
            "iq": iq, "id": id_}


# ── gemeinsame Zeichenbausteine ──────────────────────────────────────────────

def _silhouette(ax, f: dict, blende: np.ndarray | None = None) -> None:
    """Blech und Magnete als schwacher Koerper -- damit die Maschine erkennbar
    bleibt, auch wo gar kein Fluss ist (Nutoeffnung, Barriere, Wellenbohrung)."""
    eisen = f["eisen"].copy()
    mag   = f["magnet"].copy()
    if blende is not None:
        eisen &= ~blende
        mag   &= ~blende
    ax.imshow(np.where(eisen, 1.0, np.nan), origin="lower",
              cmap=ListedColormap([C_BLECH]), vmin=0, vmax=1,
              alpha=0.15, interpolation="nearest", zorder=2)
    ax.imshow(np.where(mag, 1.0, np.nan), origin="lower",
              cmap=ListedColormap(["#ff8a6a"]), vmin=0, vmax=1,
              alpha=0.30, interpolation="nearest", zorder=3)


def _heatmap(ax, f: dict, blende: np.ndarray | None = None, alpha: float = 1.0):
    B = f["B"] if blende is None else np.where(blende, np.nan, f["B"])
    return ax.imshow(np.ma.masked_invalid(B), origin="lower",
                     cmap=durchsicht_cmap(), alpha=alpha,
                     norm=PowerNorm(0.5, vmin=0.0, vmax=f["vmax"]),
                     interpolation="bilinear", zorder=4)


def _linien(ax, A: np.ndarray, n: int, alpha: float = 0.92,
            lw: float = 0.7, farbe: str = C_LINIE, quelle: np.ndarray | None = None):
    """A-Hoehenlinien = Feldlinien. ``quelle`` bestimmt die Stufen (im Zoom der
    sichtbare Ausschnitt, sonst waeren dort drei Linien im Bild)."""
    ref = A if quelle is None else quelle
    if not np.isfinite(ref).any():
        return
    stufen = np.unique(np.nanpercentile(ref, np.linspace(2, 98, n)))
    stufen = stufen[np.isfinite(stufen)]
    if stufen.size < 2:
        return
    ax.contour(A, levels=stufen, colors=farbe, linewidths=lw,
               alpha=alpha, zorder=10)


def _umrisse(ax, geom: dict, f: dict, bis: float = 2 * math.pi,
             ab: float = 0.0) -> None:
    th = np.linspace(ab, bis, 400)
    sc, ctr = f["sc"], f["ctr"]
    for d_mm, col, lw in [(geom["statorOD"], "#e8eef5", 0.9),
                          (geom["statorID"], "#e8eef5", 0.9),
                          (geom["rotorOD"],  "#b9c6d4", 0.8),
                          (geom["shaftD"],   "#7f8f9f", 0.7)]:
        r = (d_mm / 2.0) * sc
        ax.plot(ctr + r * np.cos(th), ctr + r * np.sin(th),
                color=col, lw=lw, alpha=0.8, zorder=12)


def _magnete(ax, geom: dict, f: dict) -> None:
    try:
        from ema_pipeline import _draw_magnet_outlines
        _draw_magnet_outlines(ax, geom, f["sc"], f["ctr"], f["rotor_angle"])
    except Exception:                                     # noqa: BLE001
        pass


def _farbleiste(fig, im, ax) -> None:
    cb = fig.colorbar(im, ax=ax, fraction=0.043, pad=0.02)
    cb.set_label("Flussdichte |B|  (T)   —   Deckkraft = |B|",
                 color=C_TEXT2, fontsize=9)
    cb.ax.tick_params(color="#55626f", labelcolor=C_TEXT2, labelsize=8)
    cb.outline.set_edgecolor("#55626f")
    cb.ax.set_facecolor("none")
    cb.solids.set_alpha(1.0)


def _titel(ax, text: str, klein: str = "") -> None:
    ax.set_title(text + (("\n" + klein) if klein else ""),
                 color=C_TEXT, fontsize=11, pad=6, linespacing=1.5)


def _betriebspunkt(f: dict) -> str:
    if abs(f["iq"]) + abs(f["id"]) < 0.1:
        return "Leerlauf (nur Magnetfluss)"
    return f"Last: i_q={f['iq']:.0f} A · i_d={f['id']:.0f} A"


# ── 1) Durchsicht ────────────────────────────────────────────────────────────

def bild_linien(geom: dict, f: dict, pfad: str) -> str:
    fig, ax = _leinwand()
    _silhouette(ax, f)
    im = _heatmap(ax, f)
    _linien(ax, f["A"], N_LINIEN_VOLL)
    _umrisse(ax, geom, f)
    _magnete(ax, geom, f)
    _farbleiste(fig, im, ax)
    ax.set_aspect("equal")
    _titel(ax, "Magnetfeldlinien — Durchsicht", _betriebspunkt(f))
    leg = ax.legend(handles=[
        Line2D([0], [0], color=C_LINIE, lw=1.2, label="Feldlinie (Höhenlinie von A)"),
        Line2D([0], [0], color=C_BLECH, lw=4, alpha=0.35, label="Blech (durchscheinend)"),
        Line2D([0], [0], color="#ff8a6a", lw=4, alpha=0.5, label="Magnet"),
    ], loc="lower left", fontsize=8.5, framealpha=0.45, facecolor="#0e1116",
        edgecolor="#3a4552", labelcolor=C_TEXT, handlelength=1.6)
    leg.set_zorder(20)
    return _speichern(fig, pfad)


# ── 2) Aufgeschnittener Querschnitt ──────────────────────────────────────────

def bild_schnitt(geom: dict, f: dict, pfad: str,
                 sektor: tuple[float, float] = (25.0, 115.0)) -> str:
    """Stator ueber ``sektor`` (Grad) weggenommen.

    Weggenommen wird nur der **Stator** (r >= statorID/2): der Rotor ist das,
    worauf man schauen will, und der Luftspalt ist die Stelle, an der die
    Feldlinien vom einen ins andere uebertreten. Im Sektor bleiben die Linien
    blass stehen -- eine harte Kante ohne sie liest sich wie eine Feldgrenze,
    und das waere schlicht falsch.
    """
    a0, a1 = math.radians(sektor[0]), math.radians(sektor[1])
    w = np.mod(f["winkel"] - a0, 2 * math.pi)
    im_sektor = w <= np.mod(a1 - a0, 2 * math.pi)
    r_si_mm = geom["statorID"] / 2.0
    weg = im_sektor & (f["r_mm"] >= r_si_mm)          # weggeschnittenes Material

    fig, ax = _leinwand()
    _silhouette(ax, f, blende=weg)
    im = _heatmap(ax, f, blende=weg)
    # Linien: voll ausserhalb des Schnitts, blass im weggenommenen Sektor.
    _linien(ax, np.where(weg, np.nan, f["A"]), N_LINIEN_VOLL, quelle=f["A"])
    _linien(ax, np.where(weg, f["A"], np.nan), N_LINIEN_VOLL, quelle=f["A"],
            alpha=0.22, lw=0.6)

    sc, ctr = f["sc"], f["ctr"]
    r_si = r_si_mm * sc
    r_so = (geom["statorOD"] / 2.0) * sc
    for a in (a0, a1):                                 # die beiden Schnittflaechen
        ax.plot([ctr + r_si * math.cos(a), ctr + r_so * math.cos(a)],
                [ctr + r_si * math.sin(a), ctr + r_so * math.sin(a)],
                color=C_SCHNITT, lw=1.6, zorder=14, solid_capstyle="round")
    th = np.linspace(a0, a1, 200)
    ax.fill(np.concatenate([ctr + r_si * np.cos(th), (ctr + r_so * np.cos(th))[::-1]]),
            np.concatenate([ctr + r_si * np.sin(th), (ctr + r_so * np.sin(th))[::-1]]),
            facecolor="none", edgecolor=C_SCHNITT, hatch="////",
            lw=0.0, alpha=0.30, zorder=13)
    # Umrisse nur ausserhalb des Sektors, sonst zoege der Statorkreis quer durch
    # den offenen Schnitt und machte ihn wieder zu.
    _umrisse(ax, geom, f, ab=a1, bis=a0 + 2 * math.pi)
    _magnete(ax, geom, f)
    _farbleiste(fig, im, ax)
    ax.set_aspect("equal")
    _titel(ax, "Schnittdarstellung — Stator über "
               f"{sektor[1] - sektor[0]:.0f}° weggenommen",
           "Blick auf Luftspalt, Rotor und Taschen · " + _betriebspunkt(f))
    leg = ax.legend(handles=[
        Line2D([0], [0], color=C_SCHNITT, lw=1.6, label="Schnittfläche"),
        Line2D([0], [0], color=C_LINIE, lw=1.2, label="Feldlinie"),
        Line2D([0], [0], color=C_LINIE, lw=1.0, alpha=0.3,
               label="Feldlinie im weggenommenen Material"),
    ], loc="lower left", fontsize=8.5, framealpha=0.45, facecolor="#0e1116",
        edgecolor="#3a4552", labelcolor=C_TEXT, handlelength=1.6)
    leg.set_zorder(20)
    return _speichern(fig, pfad)


# ── 3) Ein Pol, vergroessert ─────────────────────────────────────────────────

def _pol_nach_oben(geom: dict, rotor_angle: float) -> float:
    """Der Polindex, dessen Achse am naechsten an der Senkrechten liegt.

    Damit steht der Ausschnitt aufrecht im Bild, ohne das Feld zu drehen -- eine
    gedrehte Loesung waere ein zweiter Lauf und muesste interpoliert werden.
    """
    poles = max(2, int(geom["p"]) * 2)
    schritt = 2 * math.pi / poles
    k = round((math.pi / 2 - rotor_angle) / schritt)
    return rotor_angle + k * schritt


def bild_pol(geom: dict, f: dict, pfad: str) -> str:
    poles = max(2, int(geom["p"]) * 2)
    achse = _pol_nach_oben(geom, f["rotor_angle"])
    halb  = (math.pi / poles) * 1.25                 # etwas mehr als eine Polteilung
    sc, ctr = f["sc"], f["ctr"]
    r_in  = max(0.0, (geom["shaftD"] / 2.0) * 0.75) * sc
    r_out = ((geom["statorID"] / 2.0)
             + 0.55 * (geom["statorOD"] - geom["statorID"]) / 2.0) * sc

    # QUADRATISCHER Kasten um den Polschwerpunkt, nicht die Huellbox des Sektors:
    # die Huellbox eines schraeg liegenden Sektors ist deutlich groesser als der
    # Sektor selbst, und der Pol sass dann irgendwo am Rand statt in der Mitte.
    r_mit = 0.5 * (r_in + r_out)
    cx = ctr + r_mit * math.cos(achse)
    cy = ctr + r_mit * math.sin(achse)
    seite = 0.5 * max(r_out - r_in, 2.0 * halb * r_out) * 1.14
    x0, x1 = cx - seite, cx + seite
    y0, y1 = cy - seite, cy + seite
    rand = 0.0

    # Hoehenlinien AUS DEM AUSSCHNITT -- der A-Bereich eines Pols ist ein
    # Bruchteil des gesamten; prozentgleiche Stufen ueber das ganze Bild ergaeben
    # im Zoom eine Handvoll Linien.
    i0, i1 = max(0, int(y0)), min(f["N"], int(y1) + 1)
    j0, j1 = max(0, int(x0)), min(f["N"], int(x1) + 1)
    aus = f["A"][i0:i1, j0:j1]

    fig, ax = _leinwand(6.2, 6.2)
    _silhouette(ax, f)
    im = _heatmap(ax, f)
    _linien(ax, f["A"], N_LINIEN_ZOOM, quelle=aus, lw=1.0)
    _umrisse(ax, geom, f)
    _magnete(ax, geom, f)
    _farbleiste(fig, im, ax)
    ax.set_xlim(x0 - rand, x1 + rand)
    ax.set_ylim(y0 - rand, y1 + rand)
    ax.set_aspect("equal")
    _titel(ax, f"Ein Pol von {poles} — Ausschnitt",
           "Taschen, Stege und Streupfade einzeln · " + _betriebspunkt(f))
    return _speichern(fig, pfad)


# ── 4) Laengsschnitt (r-z) ───────────────────────────────────────────────────

def finde_vtu(projekt_dir: str) -> str | None:
    """Juengste Elmer-VTU eines Projekts -- Einzellauf, Sektorlauf oder Ablage."""
    if not projekt_dir or not os.path.isdir(projekt_dir):
        return None
    treffer: list[str] = []
    for wurzel in (os.path.join(projekt_dir, "em3d"),
                   os.path.join(projekt_dir, "em3d_runs")):
        for basis, _dirs, dateien in os.walk(wurzel) if os.path.isdir(wurzel) else []:
            treffer += [os.path.join(basis, d) for d in dateien if d.endswith(".vtu")]
    return max(treffer, key=os.path.getmtime) if treffer else None


def _laengs_geometrie(ax, geom: dict, axial_mm: float, z0: float = 0.0) -> None:
    r_so = geom["statorOD"] / 2.0
    r_si = geom["statorID"] / 2.0
    r_ro = geom["rotorOD"] / 2.0
    r_sh = geom["shaftD"] / 2.0
    z1 = z0 + axial_mm
    for r_a, r_b, farbe, name in [(r_si, r_so, C_BLECH, "Stator"),
                                  (r_sh, r_ro, "#b9c6d4", "Rotor"),
                                  (0.0,  r_sh, "#7f8f9f", "Welle")]:
        for vz in (+1, -1):
            u = vz * r_a if r_a > 0 else -r_b
            h = vz * (r_b - r_a) if r_a > 0 else 2 * r_b
            ax.add_patch(Rectangle((z0, min(u, u + h)), z1 - z0, abs(h),
                                   facecolor=farbe, alpha=0.13,
                                   edgecolor=farbe, lw=0.8, zorder=2))
            if r_a <= 0:
                break
    for vz in (+1, -1):                                   # Luftspalt markieren
        ax.plot([z0, z1], [vz * (r_ro + r_si) / 2] * 2, color="#5c6b7a",
                lw=0.7, ls=(0, (5, 4)), zorder=3)
    ax.annotate("", xy=(z0, -r_so * 1.12), xytext=(z1, -r_so * 1.12),
                arrowprops=dict(arrowstyle="<->", color=C_TEXT2, lw=0.9))
    ax.text((z0 + z1) / 2, -r_so * 1.20, f"Paketlänge {axial_mm:.0f} mm",
            color=C_TEXT2, fontsize=8.5, ha="center", va="top")


def _probe_gueltig(gitter, pkt, bname):
    """B an ``pkt`` (Nx3) interpolieren, ABER mit der Gueltigkeitsmaske.

    ``ema_em3d._probe`` gibt fuer Punkte ausserhalb des Netzes stillschweigend
    Nullen zurueck. In einem Achsschnitt liegt reichlich davon (die Luftbox ist
    ein Quader, das Netz nicht), und ein streamplot ueber Nullvektoren zeichnet
    kein leeres Feld, sondern **Rauschen** -- ein Igel aus kurzen Pfeilen ueber
    dem ganzen Bild. Der vtkProbeFilter fuehrt die Maske selbst mit; sie hier zu
    lesen ist billiger und ehrlicher als eine Schwelle auf |B|.
    """
    import vtk
    from vtk.util import numpy_support as ns
    vpts = vtk.vtkPoints()
    for q in pkt:
        vpts.InsertNextPoint(float(q[0]), float(q[1]), float(q[2]))
    poly = vtk.vtkPolyData(); poly.SetPoints(vpts)
    pf = vtk.vtkProbeFilter()
    pf.SetInputData(poly); pf.SetSourceData(gitter); pf.Update()
    aus = pf.GetOutput().GetPointData()
    arr = aus.GetArray(bname)
    B = (np.zeros((len(pkt), 3)) if arr is None
         else ns.vtk_to_numpy(arr).reshape(-1, 3))
    m = aus.GetArray("vtkValidPointMask")
    gut = (np.ones(len(pkt), bool) if m is None
           else ns.vtk_to_numpy(m).astype(bool))
    return B, gut


def _stapellaenge(vtu: str, rueckfall: float) -> float:
    """Paketlaenge des 3-D-Laufs, wenn sie danebenliegt.

    ``zmax-zmin`` des Netzes ist NICHT die Paketlaenge -- ``ema_em3d`` baut
    axiale Luftkappen an beide Stirnseiten (gemessen 28 mm bei L=80). Neben der
    VTU liegt aber die ``result.json`` des Laufs, und die traegt ``axial_mm``.
    """
    d = os.path.dirname(vtu)
    for kandidat in (os.path.join(d, "result.json"),
                     os.path.join(os.path.dirname(d), "result.json")):
        try:
            import json
            with open(kandidat, encoding="utf-8") as f:
                w = float((json.load(f) or {}).get("axial_mm") or 0.0)
            if w > 0:
                return w
        except Exception:                                 # noqa: BLE001
            continue
    return rueckfall


def bild_laengs(geom: dict, pfad: str, axial_mm: float = 80.0,
                vtu: str | None = None) -> tuple[str, str]:
    """Achsschnitt. Gibt (Pfad, Hinweis) zurueck; der Hinweis sagt, ob ein
    gerechnetes Feld darin steht oder nur die Geometrie."""
    r_so = geom["statorOD"] / 2.0
    fig, ax = _leinwand(7.8, 4.4)
    hinweis = ""
    feld_da = False

    if vtu and os.path.isfile(vtu):
        try:
            import ema_em3d as E3
            gitter = E3._read_grid(vtu)
            bname  = E3._b_array_name(gitter)
            _xn, _xx, _yn, _yx, zmin, zmax = gitter.GetBounds()
            L = _stapellaenge(vtu, axial_mm)
            # Fenster: das Blechpaket plus eine halbe Kappe. Weiter hinaus liegt
            # nur Luftbox -- dort steht nichts, was den Endeffekt zeigt, es macht
            # das Bild aber klein.
            z0 = max(zmin, -0.35 * L)
            z1 = min(zmax, L + 0.35 * L)
            nz, nr = 260, 170
            zs = np.linspace(z0, z1, nz)
            rs = np.linspace(-r_so * 1.02, r_so * 1.02, nr)
            ZZ, RR = np.meshgrid(zs, rs)
            pkt = np.column_stack([RR.ravel(), np.zeros(RR.size), ZZ.ravel()])
            B, gut = _probe_gueltig(gitter, pkt, bname)
            Bm = np.linalg.norm(B, axis=1)
            # Ausserhalb des Netzes UND im Gehaeuseraum jenseits des Stators wird
            # geblendet -- dieselbe Begruendung wie im Querschnitt.
            blende = (~gut) | (np.abs(RR.ravel()) > r_so * 1.02)
            Bm = np.where(blende, np.nan, Bm).reshape(RR.shape)
            vmax = float(np.nanpercentile(Bm, 99.0)) if np.isfinite(Bm).any() else 1.0
            vmax = max(0.3, min(vmax, 2.4))
            im = ax.imshow(np.ma.masked_invalid(Bm), origin="lower",
                           extent=[zs[0], zs[-1], rs[0], rs[-1]],
                           aspect="equal", cmap=durchsicht_cmap(),
                           norm=PowerNorm(0.5, vmin=0.0, vmax=vmax),
                           interpolation="bilinear", zorder=4)
            # Feldlinien: Bz waagerecht, Br senkrecht (die Schnittebene ist y=0,
            # dort ist die radiale Richtung genau x). Schwache Zellen werden
            # maskiert -- ein Stromlinienbild ueber Rauschvektoren ist kein Feld.
            schwach = ~np.isfinite(Bm) | (Bm < 0.02 * vmax)
            U = np.ma.array(B[:, 2].reshape(RR.shape), mask=schwach)
            V = np.ma.array(B[:, 0].reshape(RR.shape), mask=schwach)
            ax.streamplot(zs, rs, U, V, color=C_LINIE, density=1.4,
                          linewidth=0.75, arrowsize=0.8)
            _laengs_geometrie(ax, geom, L, z0=0.0)
            cb = fig.colorbar(im, ax=ax, fraction=0.026, pad=0.015)
            cb.set_label("|B|  (T)   —   Deckkraft = |B|", color=C_TEXT2, fontsize=9)
            cb.ax.tick_params(color="#55626f", labelcolor=C_TEXT2, labelsize=8)
            cb.outline.set_edgecolor("#55626f")
            cb.ax.set_facecolor("none")
            _titel(ax, "Längsschnitt (r–z) — 3-D-Feld aus Elmer",
                   "Endeffekt an den Paketenden · " + os.path.basename(vtu))
            ax.set_xlim(zs[0], zs[-1]); ax.set_ylim(rs[0], rs[-1])
            feld_da = True
            hinweis = f"gerechnetes 3-D-Feld aus {os.path.basename(vtu)}"
        except Exception as e:                            # noqa: BLE001
            hinweis = f"3-D-Feld nicht lesbar ({type(e).__name__}: {e})"
            fig.clear()
            ax = fig.add_subplot(111); ax.axis("off"); ax.set_facecolor("none")

    if not feld_da:
        _laengs_geometrie(ax, geom, axial_mm)
        ax.set_xlim(-0.30 * axial_mm, 1.30 * axial_mm)
        ax.set_ylim(-r_so * 1.38, r_so * 1.22)
        ax.set_aspect("equal")
        _titel(ax, "Längsschnitt (r–z) — Geometrie, KEIN gerechnetes Feld")
        ax.text(0.5 * axial_mm, r_so * 1.02,
                "Die 2-D-FDM kennt kein z — hier stehen keine gerechneten\n"
                "Feldlinien. Für den Endeffekt einen 3-D-Elmer-Lauf fahren\n"
                "(run --stufe em3d), dann steht das Feld an dieser Stelle.",
                color="#ffcf70", fontsize=9, ha="center", va="top",
                linespacing=1.5,
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#1a1712",
                          edgecolor="#4a3f28", alpha=0.85))
        if not hinweis:
            hinweis = "kein 3-D-Ergebnis im Projekt — nur Geometrie"

    ax.set_yticks([]); ax.set_xticks([])
    return _speichern(fig, pfad, px=1600), hinweis



# ── Ablauf ───────────────────────────────────────────────────────────────────

def feldbilder(geom: dict, ziel_dir: str, *,
               ansichten=ANSICHTEN, N: int = 560, rotor_angle: float = 0.0,
               iq: float = 0.0, id_: float = 0.0, axial_mm: float = 80.0,
               projekt_dir: str = "", vtu: str | None = None,
               sektor: tuple[float, float] = (25.0, 115.0),
               praefix: str = PRAEFIX, saturate: bool = True) -> list[dict]:
    """Rendert die gewuenschten Ansichten nach ``ziel_dir`` und meldet, was entstand.

    ``ziel_dir`` ist im Regelfall ``<projekt>/charts`` -- die rechte Spalte des
    Agentenreiters findet neue Bilder ueber die Aenderungszeit in genau diesem
    Ordner, also braucht es keinen eigenen Meldeweg fuer beide Koepfe.
    """
    ansichten = [a for a in ansichten if a in ANSICHTEN]
    if not ansichten:
        raise ValueError("keine gueltige Ansicht: " + ", ".join(ANSICHTEN))

    aus: list[dict] = []
    quer = [a for a in ansichten if a != "laengs"]
    f = None
    if quer:
        f = feld_rechnen(geom, N=N, rotor_angle=rotor_angle, iq=iq, id_=id_,
                         saturate=saturate)

    for a in ansichten:
        pfad = os.path.join(ziel_dir, f"{praefix}_{a}.png")
        hinweis = ""
        if a == "linien":
            bild_linien(geom, f, pfad)
        elif a == "schnitt":
            bild_schnitt(geom, f, pfad, sektor=sektor)
        elif a == "pol":
            bild_pol(geom, f, pfad)
        else:
            v = vtu if vtu is not None else finde_vtu(projekt_dir)
            _p, hinweis = bild_laengs(geom, pfad, axial_mm=axial_mm, vtu=v)
        aus.append({"ansicht": a, "datei": os.path.basename(pfad),
                    "pfad": pfad, "hinweis": hinweis})

    if f is not None:
        perf = f["em"].get("performance") or {}
        for e in aus:
            e["B_gap_T"] = round(float(perf.get("B_gap_T", 0.0)), 4)
            e["N"] = N
    return aus
