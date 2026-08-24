"""Z88Aurora V5 als zweiter, umschaltbarer Strukturlöser.

Z88 liegt fertig unter ``/opt/z88aurora`` (V5, 2019, ``thomas:thomas``, weltlesbar —
kein sudo nötig). Genutzt wird ausschließlich der **Stapelpfad**: ``z88r`` liest den
offenen Z88-Satz und schreibt Textdateien. Keine Oberfläche, kein ``z88inp``.

Was beim Bau gemessen und **nicht** aus der Dokumentation übernommen werden konnte
--------------------------------------------------------------------------------

Das Theorie-Handbuch beschreibt ``Z88I1/I2/I5.TXT`` wörtlich, die übrigen drei Dateien
gar nicht. Sie wurden aus dem Binary und aus Fehlversuchen erschlossen:

* ``Z88MAN.TXT`` ist **keine** Zahlenzeile, sondern eine Schlüsselwortdatei im Stil von
  ``z88.dyn`` — ``GLOBAL/SOLVER/STRESS``-Blöcke zwischen ``DYNAMIC START/END``.
  Mit einer Zahlenzeile bricht ``z88r`` mit „Z88MAN.TXT ist falsch" ab.
* Die **Materialdatei** ist trotz der Meldung „Material-CSV-Datei" *nicht* kommagetrennt
  und *nicht* das ``#AURORA_V4_MATERIAL``-Format aus ``/opt/z88aurora/data/material/``
  (dessen Schlüsselwörter kennt ``z88r`` nicht). Gemessen:

  =========================  ==========================
  Inhalt                     was ``z88r`` daraus liest
  =========================  ==========================
  ``210000.0,0.3``           E=210000, **nue=0**
  ``210000.0 0.3``           E=210000, **nue=0.3**  ✔
  ``210000.0;0.3``           E=210000, **nue=0**
  =========================  ==========================

  Also: **zwei Zahlen, durch Leerzeichen getrennt.** Ein Komma ergibt still nue=0 —
  ein Fehler, der nicht auffällt, weil der Löser sauber durchläuft.
* ``Z88ELP.TXT`` trägt 13 Werte je Satz (``von bis QPARA IYY EYY IZZ EZZ IT WT IFBETI
  XCP YCP ZCP RKAP``), ``Z88INT.TXT`` vier (``von bis INTORD INTOS``). Für Tetraeder
  sind die Elementparameter bedeutungslos, müssen aber dastehen.
* Der Aufruf braucht **zwei** Flaggen: ``z88r -c -parao`` (``-c`` = lineare Rechnung,
  ``-t`` = nur Prüflauf). Mit nur einer bricht er ab.
* ``z88r`` findet sein eigenes MKL nicht: ``libiomp5`` und drei ``libmkl_*`` liegen im
  selben Ordner, stehen aber nicht im RPATH. ``LD_LIBRARY_PATH`` darauf zu setzen ist
  der ganze Trick.

Zwei fachliche Grenzen, die den Aufbau bestimmen
------------------------------------------------

1. **Z88 kennt keine Fliehkraft.** Im ganzen Stapelpfad gibt es keine Rotationslast —
   das ``ROMEGA``/``OMEGA`` in ``z88r`` ist der SOR-Relaxationsfaktor. Die Fliehkraft
   kommt deshalb als **Knotenkräfte** aus ``ema_deck.zentrifugal_lasten`` in
   ``Z88I2.TXT``.
2. **Z88 kennt keine zyklische Symmetrie**, und die Schnittebenen eines Pols liegen
   nicht auf Koordinatenachsen — Z88 kann nur achsweise Freiheitsgrade fesseln. Der
   Polsektor bleibt darum CalculiX vorbehalten; Z88 rechnet den **vollen** Rotor
   (``ema_deck.baue(..., sektoren=0)``). Für den Vergleich ist das ohnehin richtig:
   beide Löser bekommen dann denselben Satz.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess

import ema_deck as _deck

Z88_ROOT = "/opt/z88aurora/bin/ubuntu64"

# z88r-Löserflaggen. „always works" laut Handbuch: SICCG/SORCG. PARDISO ist deutlich
# schneller, aber nur bis ~150.000 Freiheitsgrade empfohlen und fordert Speicher
# dynamisch nach — deshalb wird oberhalb automatisch auf SICCG gewechselt (s. loese).
LOESER = ("parao", "siccg", "sorcg", "choly")
DOF_GRENZE_PARDISO = 150_000

# Materialstufen für die Topologieoptimierung: je Stufe EINE Materialdatei.
N_MATERIALSTUFEN = 24


class Z88Fehler(RuntimeError):
    pass


def verfuegbar() -> tuple[bool, str]:
    """(ok, Begründung) — ohne etwas auszuführen."""
    r = os.path.join(Z88_ROOT, "z88r")
    if not os.path.isfile(r):
        return False, f"z88r nicht gefunden unter {Z88_ROOT}"
    if not os.access(r, os.X_OK):
        return False, "z88r ist nicht ausführbar"
    fehlt = [b for b in ("libiomp5.so", "libmkl_core.so",
                         "libmkl_intel_ilp64.so", "libmkl_intel_thread.so")
             if not os.path.isfile(os.path.join(Z88_ROOT, b))]
    if fehlt:
        return False, "MKL-Bibliotheken fehlen: " + ", ".join(fehlt)
    return True, "Z88Aurora V5 einsatzbereit"


def _umgebung() -> dict:
    """Umgebung für z88r — das eigene MKL steht nicht im RPATH."""
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = Z88_ROOT + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    return env


# ── Satz schreiben ────────────────────────────────────────────────────────────

def schreibe_satz(netz: _deck.Netz, mat: dict, rpm: float, pfad: str,
                  e_je_element: dict | None = None, kerne: int = 4) -> str:
    """Vollständigen Z88-Satz in ``pfad`` schreiben; gibt ``pfad`` zurück.

    ``e_je_element`` ordnet Elementnummern einen eigenen E-Modul zu (Topologie-
    optimierung). Die Werte werden über ``ema_deck._materialstufen`` in höchstens
    ``N_MATERIALSTUFEN`` Gruppen gebündelt — je Gruppe entsteht eine Materialdatei,
    und ``Z88MAT.TXT`` bekommt eine Zeile je Element, die darauf zeigt.
    """
    if netz.sektoren:
        raise Z88Fehler(
            "Z88 kann keinen Polsektor rechnen — es kennt weder zyklische Symmetrie "
            "noch schiefe Symmetrieebenen. ema_deck.baue(..., sektoren=0) benutzen.")
    os.makedirs(pfad, exist_ok=True)

    _schreibe_i1(netz, os.path.join(pfad, "z88i1.txt"))
    _schreibe_i2(netz, mat, rpm, os.path.join(pfad, "z88i2.txt"))
    with open(os.path.join(pfad, "z88i5.txt"), "w") as f:
        f.write("0\n")                                   # keine Flächenlasten

    _schreibe_material(netz, mat, pfad, e_je_element)

    typ = _deck.Z88_TYP[netz.ordnung]
    with open(os.path.join(pfad, "z88elp.txt"), "w") as f:
        f.write("1\n")
        f.write(f"1 {netz.n_elemente} " + " ".join(["0"] * 12) + "\n")
    with open(os.path.join(pfad, "z88int.txt"), "w") as f:
        # INTORD = Integrationsordnung der Steifigkeit, INTOS = die der Spannungen.
        # Für die Tetraeder 16/17 sind 4 bzw. 3 die Werte, mit denen z88r durchläuft.
        f.write("1\n")
        f.write(f"1 {netz.n_elemente} 4 3\n")

    _schreibe_man(os.path.join(pfad, "z88man.txt"), kerne)
    _schreibe_dyn(netz, os.path.join(pfad, "z88.dyn"))
    return pfad


def _schreibe_i1(netz: _deck.Netz, datei: str) -> None:
    """Strukturdaten. Kopfzeile: ``IDIM NKP NE NFG KFLAG`` (Theorie-Hb., 1. Eingabegruppe)."""
    typ = _deck.Z88_TYP[netz.ordnung]
    z = [f"3 {netz.n_knoten} {netz.n_elemente} {3 * netz.n_knoten} 0"]
    for i in sorted(netz.knoten):
        x, y, zz = netz.knoten[i]
        z.append(f"{i} 3 {x:.9g} {y:.9g} {zz:.9g}")
    for eid in sorted(netz.elemente):
        z.append(f"{eid} {typ}")
        z.append(" ".join(str(n) for n in netz.elemente[eid]))
    with open(datei, "w") as f:
        f.write("\n".join(z) + "\n")


def _schreibe_i2(netz: _deck.Netz, mat: dict, rpm: float, datei: str) -> None:
    """Randbedingungen: ``Knoten FG Art Wert`` — Art 1 = Kraft, Art 2 = Verschiebung.

    Fliehkraft als konsistente Knotenkräfte, ebener Verzerrungszustand über beide
    Stirnflächen, dazu die drei Starrkörperfesseln aus ``ema_deck``.
    """
    lasten = _deck.zentrifugal_lasten(netz, float(mat["density"]), rpm)
    z = []
    for kn in sorted(set(netz.nset_stirn_a) | set(netz.nset_stirn_b)):
        z.append(f"{kn} 3 2 0")
    for kn, fg in _deck._ebene_fesseln(netz):
        z.append(f"{kn} {fg} 2 0")
    for kn in sorted(lasten):
        fx, fy, _fz = lasten[kn]
        if abs(fx) > 1e-12:
            z.append(f"{kn} 1 1 {fx:.9g}")
        if abs(fy) > 1e-12:
            z.append(f"{kn} 2 1 {fy:.9g}")
    with open(datei, "w") as f:
        f.write(f"{len(z)}\n" + "\n".join(z) + "\n")


def _schreibe_material(netz: _deck.Netz, mat: dict, pfad: str,
                       e_je_element: dict | None) -> None:
    """``Z88MAT.TXT`` + je Stufe eine Materialdatei ``E nue`` (Leerzeichen!)."""
    nu     = float(mat["nu"])
    stufen = _deck._materialstufen(netz, float(mat["E"]), e_je_element,
                                   n_stufen=N_MATERIALSTUFEN)
    zeilen = []
    if len(stufen) == 1:
        e_wert, _elems = stufen[0]
        name = "z88werkstoff_0.txt"
        with open(os.path.join(pfad, name), "w") as f:
            f.write(f"{e_wert:.9g} {nu:.9g}\n")
        zeilen.append(f"1 {netz.n_elemente} {name} 1")
    else:
        stufe_je_element = {}
        for k, (e_wert, elems) in enumerate(stufen):
            name = f"z88werkstoff_{k}.txt"
            with open(os.path.join(pfad, name), "w") as f:
                f.write(f"{max(e_wert, 1e-3):.9g} {nu:.9g}\n")
            for eid in elems:
                stufe_je_element[eid] = name
        # Aufeinanderfolgende Elemente derselben Stufe zu einem von/bis-Bereich raffen.
        lauf_von, lauf_name = None, None
        for eid in sorted(netz.elemente):
            name = stufe_je_element[eid]
            if name != lauf_name:
                if lauf_name is not None:
                    zeilen.append(f"{lauf_von} {eid - 1} {lauf_name} 1")
                lauf_von, lauf_name = eid, name
        zeilen.append(f"{lauf_von} {max(netz.elemente)} {lauf_name} 1")

    with open(os.path.join(pfad, "z88mat.txt"), "w") as f:
        f.write(f"{len(zeilen)}\n" + "\n".join(zeilen) + "\n")


def _schreibe_man(datei: str, kerne: int) -> None:
    """Löversteuerung. Struktur aus dem ``z88r``-Binary erschlossen, s. Modulkopf.

    ``ISFLAG 1`` = Vergleichsspannung nach Gestaltänderungsenergie (von Mises).
    """
    with open(datei, "w") as f:
        f.write(
            "DYNAMIC START\n"
            "GLOBAL START\n  IBFLAG   0\n  IPFLAG   0\n  IHFLAG   0\nGLOBAL END\n"
            "SOLVER START\n"
            f"  MAXIT    50000\n  RALPHA   1.0E-004\n  ROMEGA   1.2\n"
            f"  ICORE    {max(1, int(kerne))}\n  OOCFLAG  0\n  DUMPMAX  100\n"
            "SOLVER END\n"
            "STRESS START\n  KDFLAG   0\n  ISFLAG   1\nSTRESS END\n"
            "DYNAMIC END\n")


def _schreibe_dyn(netz: _deck.Netz, datei: str) -> None:
    """Speichergrenzen aus der echten Netzgröße, nicht die Vorgabe 1.300.000/900.000."""
    maxe = max(1000, int(netz.n_elemente * 1.2))
    maxk = max(1000, int(netz.n_knoten * 1.2))
    with open(datei, "w") as f:
        f.write("DYNAMIC START\n"
                "LANGUAGE\n"
                "ENGLISH\n"
                "QUIET\n"
                "  COMMON START\n"
                f"    MAXE            {maxe}\n"
                f"    MAXK            {maxk}\n"
                "  COMMON END\n"
                "DYNAMIC END\n")


# ── Rechnen ───────────────────────────────────────────────────────────────────

def loese(pfad: str, netz: _deck.Netz | None = None, solver: str = "auto",
          timeout: int = 3600) -> dict:
    """``z88r`` im Satzverzeichnis fahren. Gibt einen Zustandsbericht zurück.

    ``solver="auto"`` wählt PARDISO unterhalb von ``DOF_GRENZE_PARDISO``
    Freiheitsgraden und sonst SICCG — PARDISO fordert Speicher dynamisch nach und
    bricht bei großen Strukturen ab (Handbuch, Tabelle 6).
    """
    ok, warum = verfuegbar()
    if not ok:
        return {"solver_status": "Z88_FEHLT", "meldung": warum}

    if solver == "auto":
        dof = 3 * netz.n_knoten if netz else 0
        solver = "parao" if 0 < dof <= DOF_GRENZE_PARDISO else "siccg"
    if solver not in LOESER:
        raise ValueError(f"unbekannter Löser {solver!r}, erlaubt: {LOESER}")

    for alt in ("z88o0.txt", "z88o1.txt", "z88o2.txt", "z88o3.txt", "z88o4.txt"):
        try:
            os.remove(os.path.join(pfad, alt))       # keine Altstände vortäuschen
        except OSError:
            pass

    # ZWEI Läufe, und das ist keine Vorsicht, sondern Pflicht: der Prüflauf ``-t``
    # SCHREIBT ``Z88R.DYN`` („Z88R.DYN build by Z88R Testmode"), also die Speicher-
    # grenzen MAXGS/MAXKOI/MAXK/MAXE/MAXNFG, die der Rechenlauf ``-c`` dann liest.
    # Ohne ihn bricht z88r mit „cannot open Z88R.DYN" ab.
    ausgabe = ""
    try:
        for flagge in ("-t", "-c"):
            r = subprocess.run([os.path.join(Z88_ROOT, "z88r"), flagge, f"-{solver}"],
                               cwd=pfad, env=_umgebung(), capture_output=True,
                               text=True, timeout=timeout)
            ausgabe += (r.stdout or "") + (r.stderr or "")
            if "###" in ausgabe and flagge == "-t":
                break
    except subprocess.TimeoutExpired:
        return {"solver_status": "ZEITUEBERSCHREITUNG", "solver": solver,
                "meldung": f"z88r -{solver} über {timeout} s"}
    o3 = os.path.join(pfad, "z88o3.txt")
    if not os.path.isfile(o3) or os.path.getsize(o3) < 200:
        fehler = [z.strip() for z in ausgabe.splitlines() if z.strip().startswith("###")]
        return {"solver_status": "KEINE_SPANNUNGEN", "solver": solver,
                "returncode": r.returncode,
                "meldung": " | ".join(fehler[:3]) or ausgabe.strip()[-300:]}
    return {"solver_status": "OK", "solver": solver, "returncode": r.returncode,
            "pfad": pfad}


# ── Ergebnisse lesen ──────────────────────────────────────────────────────────

def lies_spannungen(pfad: str) -> dict:
    """``Z88O3.TXT`` → ``{elementnummer: [(sxx,syy,szz,txy,tyz,tzx,sigv), …]}``.

    Eine Liste je Element, weil ``z88r`` für die Tetraeder 16/17 in den **Gausspunkten**
    rechnet (``KDFLAG`` ändert daran für diese Typen nichts) — je Element also mehrere
    Zeilen. Je Gausspunkt ein Tupel
    ``(x, y, z, sxx, syy, szz, txy, tyz, tzx, sigv)``: die ersten drei Spalten sind
    der **Ort** des Gausspunkts, den z88r mitschreibt — damit braucht die Auswertung
    keinen Elementschwerpunkt zu schätzen.

    Der Elementkopf wird sprachunabhängig erkannt. ``z88r`` schreibt „Element # =" oder
    „element # =", je nachdem, was im ``LANGUAGE``-Block von ``z88.dyn`` steht — ein
    Leser, der nur die deutsche Form kennt, findet an einem englischen Lauf
    stillschweigend null Elemente.
    """
    je_element, aktuell = {}, None
    for L in open(pfad, errors="ignore"):
        t = L.strip()
        if t[:8].lower().startswith("element") and "=" in t:
            try:
                aktuell = int(t.split("=")[1].split()[0])
                je_element[aktuell] = []
            except (ValueError, IndexError):
                aktuell = None
            continue
        if aktuell is None or not t or t[0] not in "+-0123456789":
            continue
        w = t.split()
        if len(w) < 10:
            continue
        try:
            zahlen = [float(x) for x in w]
        except ValueError:
            continue
        # Zeilenform: XX YY ZZ SIGXX SIGYY SIGZZ TAUXY TAUYZ TAUZX SIGV
        je_element[aktuell].append(tuple(zahlen[:10]))
    return {k: v for k, v in je_element.items() if v}


def lies_verschiebungen(pfad: str) -> dict:
    """``Z88O2.TXT`` → ``{knoten: (ux, uy, uz)}`` [mm]."""
    u, gestartet = {}, False
    for L in open(pfad, errors="ignore"):
        t = L.strip()
        if t.startswith("Knoten") or t.startswith("node"):
            gestartet = True
            continue
        if not gestartet or not t:
            continue
        w = t.split()
        if len(w) < 4:
            continue
        try:
            u[int(w[0])] = (float(w[1]), float(w[2]), float(w[3]))
        except ValueError:
            continue
    return u


def lies_knotenkraefte(pfad: str) -> dict:
    """``Z88O4.TXT`` → ``{knoten: (fx, fy, fz)}`` [N] — die Reaktionen.

    Damit wird geprüft, dass die drei Starrkörperfesseln fast keine Kraft tragen; sonst
    wäre das Modell ein anderes als der frei rotierende Ring der analytischen Formel.
    """
    return lies_verschiebungen(pfad)                  # gleiche Spaltenform


def spannungen_je_element(pfad: str) -> dict:
    """``Z88O3.TXT`` → ``{element: (sxx, syy, szz, sxy, sxz, syz)}``.

    Die Gausspunkte eines Elements werden gemittelt (bei Typ 17 sind sie ohnehin
    gleich, weil die Spannung über das lineare Tetraeder konstant ist), und die
    Spalten werden auf **die Reihenfolge der CalculiX-``.dat``** gebracht.

    Das ist die eine Stelle, an der sich die beiden Löser vertauschen ließen:
    Z88 schreibt ``TAUXY TAUYZ TAUZX``, CalculiX ``sxy sxz syz``. Wer das Paar
    verwechselt, bekommt eine Vergleichsspannung, die plausibel aussieht und falsch
    ist. ``ema_deck.kennzahlen`` darf deshalb beide Löser nur über diese Funktion
    sehen.
    """
    aus = {}
    for eid, gp in lies_spannungen(pfad).items():
        k = float(len(gp))
        sxx = sum(g[3] for g in gp) / k
        syy = sum(g[4] for g in gp) / k
        szz = sum(g[5] for g in gp) / k
        txy = sum(g[6] for g in gp) / k
        tyz = sum(g[7] for g in gp) / k
        tzx = sum(g[8] for g in gp) / k
        aus[eid] = (sxx, syy, szz, txy, tzx, tyz)      # -> sxx syy szz sxy sxz syz
    return aus


def kennzahlen_aus_lauf(netz, pfad: str, yield_mpa: float = 0.0) -> dict:
    """Bequemer Abschluss: Z88-Lauf → dieselben Kennzahlen wie beim CalculiX-Pfad."""
    k = _deck.kennzahlen(netz, spannungen_je_element(os.path.join(pfad, "z88o3.txt")),
                         yield_mpa)
    u = lies_verschiebungen(os.path.join(pfad, "z88o2.txt"))
    if u:
        weit = max(math.sqrt(a * a + b * b + c * c) for a, b, c in u.values())
        k["max_displacement_mm"] = round(weit, 4)
        k["max_displacement_um"] = round(weit * 1e3, 3)
    return k
