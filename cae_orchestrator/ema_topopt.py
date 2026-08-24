"""Topologieoptimierung des Rotorblechs auf dem eigenen Rechensatz.

Z88Arion, das naheliegende Werkzeug dafür, **gibt es nicht für Linux** — nur für
Windows, und dort als reines GUI-Programm ohne Stapelbetrieb. Ein Agent kann es nicht
bedienen. Also wird das Verfahren hier selbst gefahren, auf den Lösern, die vorhanden
sind: ``ema_deck`` (CalculiX) und ``ema_z88``.

Was das Verfahren voraussetzt und warum ``ema_deck`` davor steht
---------------------------------------------------------------

Eine Dichteschleife ändert **je Element** den E-Modul. FreeCADs ``.inp``-Schreiber kann
das nicht; unser eigener kann es (``*SOLID SECTION`` je ``ELSET``), Z88 ebenso über
Materialsätze. Und eine Optimierung sind 30–80 Löserläufe: mit dem Polsektor
(~14.000 Elemente, ccx in 0,35 s) sind das Sekunden, mit dem FreeCAD-Vollrotor
(797.275 Elemente, ~40 s Start je Lauf) wären es Stunden bis Tage.

Zwei Verfahren — und welches hier das richtige ist
--------------------------------------------------

**SKO (Soft Kill Option), die Vorgabe.** Spannungsgetrieben:

    E_e  <-  clip( E_e + k · (sigma_vm,e − sigma_ref),  E_min,  E_0 )

Braucht nur die Vergleichsspannung je Element — genau das, was ``Z88O3.TXT`` und die
CalculiX-``.dat`` ohnehin liefern. Elemente werden **weich, nicht gelöscht**: das Netz
bleibt über alle Iterationen identisch, es ändert sich allein der Materialsatz. Das ist
für dieses Bauteil auch fachlich das richtige Verfahren — ein Rotorblech versagt durch
**Fließen an den Stegen**, nicht durch Nachgiebigkeit.

**SIMP/OC, wahlweise.** Minimiert die Nachgiebigkeit unter einer Volumenschranke. Hier
ist die Last **entwurfsabhängig** (weniger Material heißt weniger Fliehkraft), was in
die Empfindlichkeit eingeht:

    E_e = E_0 · rho_e^p ,   f_e = rho_e · f_e0
    dc/drho_e = (2/rho_e) · (W_e − p · U_e)

mit ``W_e = f_e·u_e`` (Arbeit der Last an den Elementknoten) und ``U_e`` der
Formänderungsenergie. Beide Löser geben ``U_e`` nicht aus; es wird aus Spannung und
E-Modul genähert (``U_e ≈ ½ σ_vm² V_e / E_e``). **Das ist eine Näherung und wird als
solche beschriftet** — dieselbe Regel, nach der ``B_gap`` im Bericht als analytisch
verankert ausgewiesen wird.

Was NICHT optimiert werden darf
--------------------------------

Ohne Sperrbereiche rechnet das Verfahren die Flusspfade weg und liefert ein magnetisch
wertloses Ergebnis. Fest bleiben deshalb: der **Wellensitz**, der **Rotoraußenrand**
(dort laufen die Stege, die die Magnete halten) und ein **Saum um jede Magnettasche**.
Die drei Breiten sind Parameter, keine Konstanten — wer den Saum verkleinert, sieht
genau, was das Verfahren dann tut.

Was herauskommt — und was nicht
--------------------------------

Ein Dichtefeld je Element, **kein Bauteil**. Ein Blechschnitt hat Fertigungs-, Fluss-
und Steifigkeitsrandbedingungen, die kein Dichtefeld kennt. ``ableseempfehlung()``
rechnet das Feld deshalb auf die **parametrischen** Rotorgrößen zurück (Stegbreiten,
Taschenabstand) — das ist das, was danach tatsächlich gebaut und gerechnet werden kann.
"""

from __future__ import annotations

import math
import os
import time

import ema_deck as D
import ema_z88 as Z
from ema_topology import leg_records, magnet_legs

# Untere Schranke des E-Moduls. Nicht null, sonst wird die Steifigkeitsmatrix singulär.
E_MIN_REL = 1e-3

# SIMP-Strafexponent. 3 ist der Standardwert; darunter bleibt das Ergebnis grau.
SIMP_P = 3.0

# Daempfung der SKO-Aktualisierung. 0,5 ist der uebliche Wert des Fully-Stressed-Design;
# groesser laesst das Verfahren springen, kleiner macht es traege.
SKO_ETA = 0.5


class TopOptFehler(RuntimeError):
    pass


# ── Sperrbereiche ─────────────────────────────────────────────────────────────

def _abstand_rechteck(px: float, py: float, rec: dict) -> float:
    """Abstand des Punktes (px,py) zum gedrehten Taschenrechteck [mm]; 0 innerhalb."""
    dx, dy = px - rec["cx"], py - rec["cy"]
    c, s = math.cos(-rec["rot"]), math.sin(-rec["rot"])
    lx, ly = dx * c - dy * s, dx * s + dy * c          # ins Rechteckssystem drehen
    ax = abs(lx) - rec["length"] / 2.0
    ay = abs(ly) - rec["thick"] / 2.0
    if ax <= 0 and ay <= 0:
        return 0.0
    return math.hypot(max(ax, 0.0), max(ay, 0.0))


def sperrbereiche(netz: D.Netz, geom: dict, bohrung_mm: float = 3.0,
                  rand_mm: float = 2.0, tasche_mm: float = 1.5) -> set:
    """Elementnummern, die **nicht** optimiert werden dürfen.

    Ohne diese drei Zonen entfernt das Verfahren die Flusspfade und den Wellensitz.
    Die Breiten sind bewusst Parameter: wer ``tasche_mm`` verkleinert, sieht, was das
    Verfahren an den Stegen tun *würde* — und kann entscheiden, ob er es zulässt.
    """
    recs = [r for r in leg_records(magnet_legs(geom)[0]) if r["placement"] == "interior"]
    # Im Vollrotor liegen die Taschen in jedem Pol; die Prüfung dreht den Punkt
    # deshalb in den pollokalen Rahmen zurück, statt die Taschen zu vervielfachen.
    schritt = 2 * math.pi / netz.poles

    fest = set()
    for eid in netz.elemente:
        x, y, _z = D.element_mitte(netz, eid)
        r = math.hypot(x, y)
        if r - netz.r_shaft <= bohrung_mm or netz.r_rot - r <= rand_mm:
            fest.add(eid)
            continue
        phi = math.atan2(y, x)
        lokal = phi - round(phi / schritt) * schritt
        lx, ly = r * math.cos(lokal), r * math.sin(lokal)
        if any(_abstand_rechteck(lx, ly, rc) <= tasche_mm for rc in recs):
            fest.add(eid)
    return fest


# ── Dichtefilter gegen Schachbrettmuster ──────────────────────────────────────

def _nachbarn(netz: D.Netz, radius_mm: float) -> dict:
    """``{element: [(nachbar, gewicht), …]}`` — Kegelfilter über die Elementmitten.

    Ohne Filter entstehen Schachbrettmuster: abwechselnd volle und leere Elemente, die
    numerisch steif aussehen und mechanisch nichts bedeuten. Der Radius wird in mm
    angegeben, damit er unabhängig von der Netzfeinheit dieselbe Bedeutung hat.
    """
    mitten = {eid: D.element_mitte(netz, eid) for eid in netz.elemente}
    # Gitter-Eimer, sonst ist die Nachbarsuche quadratisch in der Elementzahl.
    z = radius_mm
    eimer = {}
    for eid, (x, y, zz) in mitten.items():
        eimer.setdefault((int(x // z), int(y // z), int(zz // z)), []).append(eid)

    aus = {}
    for eid, (x, y, zz) in mitten.items():
        gx, gy, gz = int(x // z), int(y // z), int(zz // z)
        liste = []
        for ax in (-1, 0, 1):
            for ay in (-1, 0, 1):
                for az in (-1, 0, 1):
                    for kand in eimer.get((gx + ax, gy + ay, gz + az), ()):
                        d = math.dist(mitten[kand], (x, y, zz))
                        if d < radius_mm:
                            liste.append((kand, radius_mm - d))
        aus[eid] = liste
    return aus


def _filtere(werte: dict, nachbarn: dict) -> dict:
    """Gewichtetes Mitteln über die Nachbarschaft."""
    aus = {}
    for eid, liste in nachbarn.items():
        s = sum(g for _n, g in liste)
        aus[eid] = (sum(werte[n] * g for n, g in liste) / s) if s > 0 else werte[eid]
    return aus


# ── Ein Löserlauf ─────────────────────────────────────────────────────────────

def _lauf(netz: D.Netz, mat: dict, rpm: float, ordner: str, rho: dict | None,
          simp_p: float, loeser: str, kerne: int) -> dict:
    """Einen Rechenlauf fahren; gibt ``{element: (sxx,…)}`` in .dat-Spaltenordnung."""
    if loeser == "ccx":
        p = D.schreibe_inp(netz, mat, rpm, os.path.join(ordner, "iter.inp"),
                           rho_je_element=rho, simp_p=simp_p)
        r = D.loese_ccx(p, kerne=kerne)
        if r["solver_status"] != "OK":
            raise TopOptFehler(f"CalculiX: {r.get('meldung', r['solver_status'])}")
        return D.lies_dat_spannungen(r["dat"])
    if loeser == "z88":
        Z.schreibe_satz(netz, mat, rpm, ordner, rho_je_element=rho, simp_p=simp_p,
                        kerne=kerne)
        r = Z.loese(ordner, netz=netz)
        if r["solver_status"] != "OK":
            raise TopOptFehler(f"Z88: {r.get('meldung', r['solver_status'])}")
        return Z.spannungen_je_element(os.path.join(ordner, "z88o3.txt"))
    raise ValueError(f"unbekannter Löser {loeser!r} — 'ccx' oder 'z88'")


# ── SKO ───────────────────────────────────────────────────────────────────────

def sko(netz: D.Netz, geom: dict, mat: dict, rpm: float, ordner: str,
        iterationen: int = 30, sigma_ref: float | None = None,
        sf_target: float = 1.3, vol_ziel: float | None = None,
        rate: float = 0.25, filter_mm: float | None = None,
        loeser: str = "ccx", kerne: int = 4,
        sperr: set | None = None, melde=None) -> dict:
    """Soft Kill Option — spannungsgetrieben, das für ein Rotorblech passende Verfahren.

    ``sigma_ref`` ist die **zulässige** Vergleichsspannung, gegen die das Verfahren
    läuft. Ohne Angabe wird sie aus dem Werkstoff gebildet:
    ``yield_mpa / sf_target``, mit ``sf_target = 1.3`` — **derselben Sicherheit, auf die
    ``ema_pipeline`` sein Festigkeitstor stellt**. Damit optimiert das Verfahren gegen
    genau die Schranke, an der die Auslegung sonst auch gemessen wird.

    Der erste Entwurf hat ``sigma_ref`` stattdessen auf den *Median des ersten Laufs*
    gesetzt. Das ist eine Einwegratsche: alles unterhalb wird weicher, nichts kommt
    zurück, und der Volumenanteil sinkt linear weiter, ohne je zu konvergieren
    (gemessen: 12 Iterationen, ``max_aenderung`` konstant bei 0,06). Gegen eine feste
    zulässige Spannung dagegen steigt die Beanspruchung des verbleibenden Materials,
    während es weniger wird — und das Verfahren kommt zum Stehen.

    ``vol_ziel`` bricht zusätzlich ab, sobald der Volumenanteil darunter fällt.
    ``rate`` ist die **Schrittgrenze**: um höchstens diesen Faktor darf sich die Dichte
    eines Elements je Iteration ändern.
    """
    os.makedirs(ordner, exist_ok=True)
    e0     = float(mat["E"])
    fest   = sperrbereiche(netz, geom) if sperr is None else sperr
    frei   = [eid for eid in netz.elemente if eid not in fest]
    if not frei:
        raise TopOptFehler("die Sperrbereiche decken das ganze Bauteil ab — "
                           "bohrung_mm / rand_mm / tasche_mm verkleinern")
    radius = filter_mm if filter_mm is not None else 2.0 * _kantenlaenge(netz)
    nb     = _nachbarn(netz, radius)
    vol    = {eid: abs(D._tetvol(netz, netz.elemente[eid])) for eid in netz.elemente}
    rho    = {eid: 1.0 for eid in netz.elemente}
    verlauf = []
    if sigma_ref is None:
        sigma_ref = float(mat.get("yield_mpa", 340.0)) / max(sf_target, 1e-6)

    for it in range(iterationen):
        t0 = time.time()
        sp = _lauf(netz, mat, rpm, ordner, rho if it else None, 1.0, loeser, kerne)
        vm = {eid: D.von_mises(*s) for eid, s in sp.items() if eid in netz.elemente}
        if not vm:
            raise TopOptFehler("der Löser hat keine Spannungen geliefert")

        # MULTIPLIKATIV, nicht additiv: rho_neu = rho · (sigma/sigma_ref)^eta, mit
        # Schrittgrenze. Der erste Entwurf hat die Spannung mit sigma/rho auf das
        # Vollmaterial zurueckgerechnet und additiv geregelt — das explodiert bei
        # kleinen Dichten (rho=0.001 macht aus jeder Restspannung das Tausendfache),
        # und die Dichten sind zwischen 0,001 und 1 hin- und hergesprungen: gemessen
        # max_aenderung ~0,9 ueber 40 Iterationen, Volumenanteil zwischen 0,147 und
        # 0,205. Die multiplikative Form kann das nicht, weil sie rho nur um einen
        # begrenzten FAKTOR aendert.
        vm_g = _filtere(vm, nb)

        neu = {}
        for eid, r in rho.items():
            if eid in fest:
                neu[eid] = 1.0
                continue
            # Bei E ~ rho traegt ein weiches Element von Haus aus weniger Spannung.
            # Ziel ist deshalb sigma_e = sigma_ref · rho_e (voll ausgenutztes Material).
            soll = max(sigma_ref * r, 1e-9)
            faktor = (max(vm_g.get(eid, soll), 1e-9) / soll) ** SKO_ETA
            faktor = min(1.0 + rate, max(1.0 - rate, faktor))
            neu[eid] = min(1.0, max(E_MIN_REL, r * faktor))

        aenderung = max(abs(neu[e] - rho[e]) for e in rho)
        rho = neu
        anteil = (sum(rho[e] * vol[e] for e in frei) / sum(vol[e] for e in frei))
        verlauf.append({"iteration": it, "sigma_ref_MPa": round(sigma_ref, 2),
                        "stress_peak_MPa": round(max(vm.values()), 2),
                        "stress_p99_MPa": round(sorted(vm.values())[int(0.99*len(vm))], 2),
                        "volumenanteil": round(anteil, 4),
                        "max_aenderung": round(aenderung, 5),
                        "sekunden": round(time.time() - t0, 2)})
        if melde:
            melde(verlauf[-1])
        if aenderung < 2e-3:
            break
        if vol_ziel is not None and anteil <= vol_ziel:
            break

    return {"verfahren": "SKO", "dichte": rho, "simp_p": 1.0, "e0": e0,
            "verlauf": verlauf, "sperrbereiche": sorted(fest),
            "sigma_ref_MPa": sigma_ref, "filter_mm": radius, "loeser": loeser}


# ── SIMP / OC ─────────────────────────────────────────────────────────────────

def simp(netz: D.Netz, geom: dict, mat: dict, rpm: float, ordner: str,
         vol_ziel: float = 0.6, iterationen: int = 40, p: float = SIMP_P,
         schrittweite: float = 0.2, filter_mm: float | None = None,
         loeser: str = "ccx", kerne: int = 4,
         sperr: set | None = None, melde=None) -> dict:
    """SIMP mit OC-Aktualisierung und **entwurfsabhängiger** Fliehkraft.

    ``vol_ziel`` ist der Volumenanteil, der im **optimierbaren** Bereich übrig bleiben
    soll — die Sperrbereiche zählen nicht mit, sonst wäre die Schranke je nach
    Saumbreite etwas anderes.

    Die Formänderungsenergie ist genähert (``U_e ≈ ½ σ_vm² V_e / E_e``); die Löser
    geben sie nicht aus. Das Verfahren ist damit brauchbar, aber die
    Empfindlichkeiten sind **nicht exakt** — wer eine belastbare Nachgiebigkeit
    braucht, nimmt SKO und liest die Spannung ab.
    """
    os.makedirs(ordner, exist_ok=True)
    e0     = float(mat["E"])
    fest   = sperrbereiche(netz, geom) if sperr is None else sperr
    frei   = [eid for eid in netz.elemente if eid not in fest]
    if not frei:
        raise TopOptFehler("die Sperrbereiche decken das ganze Bauteil ab — "
                           "bohrung_mm / rand_mm / tasche_mm verkleinern")
    radius = filter_mm if filter_mm is not None else 2.0 * _kantenlaenge(netz)
    nb     = _nachbarn(netz, radius)
    vol    = {eid: abs(D._tetvol(netz, netz.elemente[eid])) for eid in netz.elemente}

    rho = {eid: (1.0 if eid in fest else vol_ziel) for eid in netz.elemente}
    verlauf = []

    for it in range(iterationen):
        t0 = time.time()
        sp = _lauf(netz, mat, rpm, ordner, rho, p, loeser, kerne)
        vm = {eid: D.von_mises(*s) for eid, s in sp.items() if eid in netz.elemente}
        if not vm:
            raise TopOptFehler("der Löser hat keine Spannungen geliefert")

        # U_e ~ 1/2 sigma^2 V / E  (isotrope Naeherung, s. Modulkopf)
        u_e = {eid: 0.5 * vm[eid] ** 2 * vol[eid]
               / max(e0 * rho[eid] ** p, e0 * E_MIN_REL) for eid in vm}
        # Nachgiebigkeit als Summe der Formaenderungsenergie x 2
        c = 2.0 * sum(u_e.values())

        # Entwurfsabhaengige Last: dc/drho = (2/rho)(W_e - p U_e). W_e wird ueber den
        # Massenanteil genaehert, weil die Knotenarbeit je Element den Verschiebungs-
        # vektor braeuchte; bei rho-proportionaler Last ist W_e ~ 2 U_e rho^(1-p).
        emp = {}
        for eid in frei:
            r = max(rho[eid], 1e-6)
            emp[eid] = -(p - 1.0) * 2.0 * u_e.get(eid, 0.0) / r
        emp = _filtere({**{e: 0.0 for e in netz.elemente}, **emp}, nb)

        rho = _oc_schritt(rho, emp, vol, frei, vol_ziel, schrittweite)

        anteil = (sum(rho[e] * vol[e] for e in frei) / sum(vol[e] for e in frei))
        verlauf.append({"iteration": it, "nachgiebigkeit": round(c, 3),
                        "stress_peak_MPa": round(max(vm.values()), 2),
                        "volumenanteil": round(anteil, 4),
                        "sekunden": round(time.time() - t0, 2)})
        if melde:
            melde(verlauf[-1])
        if it > 3 and abs(verlauf[-1]["nachgiebigkeit"]
                          - verlauf[-2]["nachgiebigkeit"]) < 1e-4 * abs(c):
            break

    return {"verfahren": "SIMP/OC", "dichte": rho, "simp_p": p, "e0": e0,
            "verlauf": verlauf, "sperrbereiche": sorted(fest),
            "vol_ziel": vol_ziel, "filter_mm": radius, "loeser": loeser}


def _oc_schritt(rho, emp, vol, frei, vol_ziel, schrittweite,
                rho_min=1e-3, toleranz=1e-4):
    """Optimality-Criteria-Aktualisierung mit Bisektion auf den Lagrange-Faktor."""
    ziel = vol_ziel * sum(vol[e] for e in frei)
    lo, hi = 1e-12, 1e12
    neu = dict(rho)
    for _ in range(80):
        lam = 0.5 * (lo + hi)
        for eid in frei:
            b = max(0.0, -emp.get(eid, 0.0) / (lam * vol[eid]))
            wert = rho[eid] * math.sqrt(b) if b > 0 else rho_min
            neu[eid] = min(1.0, rho[eid] + schrittweite,
                           max(rho_min, rho[eid] - schrittweite, wert))
        ist = sum(neu[e] * vol[e] for e in frei)
        if abs(ist - ziel) <= toleranz * ziel:
            break
        if ist > ziel:
            lo = lam
        else:
            hi = lam
    return neu


def _kantenlaenge(netz: D.Netz) -> float:
    """Typische Elementkante [mm] — aus dem mittleren Elementvolumen geschätzt."""
    n = min(500, netz.n_elemente)
    ids = list(netz.elemente)[:n]
    v = sum(abs(D._tetvol(netz, netz.elemente[e])) for e in ids) / n
    return (6.0 * max(v, 1e-12)) ** (1.0 / 3.0)


# ── Ableseempfehlung: vom Dichtefeld zurück auf die Parametrik ────────────────

def ableseempfehlung(netz: D.Netz, geom: dict, ergebnis: dict,
                     schwelle: float = 0.5) -> dict:
    """Aus dem Dichtefeld die Größen ableiten, die man wirklich bauen kann.

    Ein Dichtefeld ist kein Blechschnitt. Was sich daraus **verantwortbar** ablesen
    lässt, sind Radialbereiche: wo das Verfahren Material behalten will und wo nicht.
    Das wird auf ``rotorOD``/``shaftD`` bezogen zurückgegeben, damit die Empfehlung in
    denselben Parametern steht, in denen die Pipeline rechnet.
    """
    dichte = ergebnis["dichte"]
    fest = set(ergebnis.get("sperrbereiche", ()))

    n_ringe = 20
    ringe = [[] for _ in range(n_ringe)]
    for eid, d in dichte.items():
        if eid in fest or eid not in netz.elemente:
            continue
        x, y, _z = D.element_mitte(netz, eid)
        rel = (math.hypot(x, y) - netz.r_shaft) / max(netz.r_rot - netz.r_shaft, 1e-9)
        ringe[min(n_ringe - 1, max(0, int(rel * n_ringe)))].append(d)

    profil = []
    for k, werte in enumerate(ringe):
        if not werte:
            continue
        r_mm = netz.r_shaft + (k + 0.5) / n_ringe * (netz.r_rot - netz.r_shaft)
        profil.append({"r_mm": round(r_mm, 2),
                       "dichte_mittel": round(sum(werte) / len(werte), 3),
                       "anteil_ueber_schwelle":
                           round(sum(1 for w in werte if w >= schwelle) / len(werte), 3)})

    duenn = [p for p in profil if p["dichte_mittel"] < schwelle]
    aus = {"radialprofil": profil, "schwelle": schwelle,
           "hinweis": "Dichtefeld, kein Bauteil — Fertigung, Flusspfade und "
                      "Steifigkeit stehen nicht darin."}
    if duenn:
        aus["entlastet_von_mm"] = min(p["r_mm"] for p in duenn)
        aus["entlastet_bis_mm"] = max(p["r_mm"] for p in duenn)
        aus["empfehlung"] = (
            f"Zwischen r = {aus['entlastet_von_mm']:.1f} mm und "
            f"{aus['entlastet_bis_mm']:.1f} mm traegt das Eisen wenig. Dort waere eine "
            f"zusaetzliche Flussbarriere oder eine groessere Tasche vertretbar — "
            f"NACH einer EM-Rechnung, nicht davor.")
    else:
        aus["empfehlung"] = ("Kein Radialbereich faellt unter die Schwelle: das Eisen "
                            "ist bei dieser Drehzahl durchweg beteiligt.")
    return aus
