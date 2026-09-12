"""**Spritzoel am Wickelkopf mit FluidX3D** (Lattice-Boltzmann, freie Oberflaeche, GPU).

Eigenstaendiger On-Demand-Pfad **neben** dem qualitativen Mantaflow-Pfad
(`ema_oilspray`) und dem quantitativen VOF-Pfad (`ema_cfd`). Er beantwortet
dieselbe Frage wie der erste — bildet sich der Strahl, trifft er, benetzt er,
wie zerfaellt er — nur mit **aufgeloester Duese** und auf der GPU.

Architektur gespiegelt zu `ema_oilspray`: STL-Ausschnitt aus FreeCAD (dieselbe
Funktion, `_export_winding_stl`), Loeser im Unterprozess, Marker-Strom,
Frames -> `anim.mp4`, Kennwert-Charts, Persistenz nach `results["fluidx3d"]`,
automatischer Varianten-Store.

────────────────────────────────────────────────────────────────────────────
DREI GRENZEN, GEMESSEN AM 12.09.2026 — sie stehen hier, weil jede von ihnen
eine Entscheidung dieses Moduls traegt:

1. **Die ganze Maschine geht nicht.** Ein 287-mm-Wuerfel mit 3 GB VRAM ergibt
   0,94 mm je Zelle — die 1-mm-Duese waere 1,06 Zellen breit; derselbe Befund,
   den `ema_oilspray` als „Strahl unter-aufgeloest" meldet. Drei Zellen ueber
   der Bohrung bei voller Maschine hiessen 861^3 = 638 Mio. Zellen ~ 41 GB auf
   einer 24-GB-Karte. Deshalb rechnet dieses Modul grundsaetzlich ein
   **FENSTER** um EINE Duese (`fenster_bestimmen`) — nicht als Sparmassnahme,
   sondern weil die Alternative nicht existiert. `vollmaschine_kosten` rechnet
   diese Zahl je Auslegung aus, statt sie zu behaupten.

2. **Es gibt keinen Dauerstrahl.** `mass` — die Erhaltungsgroesse des
   Freiflaechenloesers — hat keinen Wirtspuffer (`lbm.cpp:149`,
   `allocate_host=false`), und ein `TYPE_E`-Rand traegt keine Masse in die
   Grenzflaeche ein: gemessen 1,94 mm^3 Oel nach 12.000 Schritten gegen 21,8
   eingesetzte. Gerechnet wird deshalb ein **OELSTOSS** — die Strahlsaeule
   steht zum Zeitpunkt 0 da und fliegt los. Der Anlaufvorgang faellt heraus,
   der Aufprall nicht. Das steht in jedem Ergebnis (`note`), damit niemand die
   benetzte Flaeche fuer einen Dauerzustand haelt.

3. **Isotherm.** `SURFACE` und `TEMPERATURE` sind in keinem der 40
   mitgelieferten Faelle kombiniert. Kein Temperaturfeld, kein
   Waermeuebergang — dieselbe Grenze wie `interFoam`. Dieser Pfad ersetzt den
   **qualitativen** Mantaflow-Pfad, NICHT `ema_cfd`, aus dem der HTC kommt.
────────────────────────────────────────────────────────────────────────────

LIZENZ: FluidX3D (ProjectPhysX) — keine kommerzielle, keine militaerische
Nutzung, kein KI-Training auf dem Quelltext, Lizenzhinweis bleibt stehen, und
wer Ergebnisse einer geaenderten Fassung veroeffentlicht, muss die geaenderte
Quelle veroeffentlichen. Das erzeugte `setup.cpp` IST eine solche Aenderung
und sagt das in seinem Kopf. Der Quellbaum bleibt deshalb ausserhalb der
Versionsverwaltung (`.gitignore`), und gearbeitet wird in einer Kopie
(`fluidx3d_runner.vorbereiten`).
"""

import base64
import io
import json
import math
import os
import struct
import time

import fluidx3d_runner

# ── Grenzen / Vorgaben ───────────────────────────────────────────────────────
FENSTER_RANGE  = (16.0, 160.0)   # Kantenlaenge des Rechenfensters [mm]
N_RANGE        = (64, 512)       # Zellen je Kante
BILDER_RANGE   = (4, 120)        # Ausgabeschritte (= Videobilder)
DAUER_RANGE    = (0.5, 60.0)     # simulierte Zeit [ms]
STOSS_RANGE    = (0.05, 20.0)    # Dauer des Oelstosses [ms]
DEFAULT_FENSTER = 48.0
DEFAULT_N       = 208
DEFAULT_BILDER  = 24
DEFAULT_DAUER   = 10.0
DEFAULT_STOSS   = 0.7

FRAMES_SUBDIR = "frames_fx3d"
RUNS_SUBDIR   = "fluidx3d_runs"
WORK_SUBDIR   = "fluidx3d_work"

# Gemessen am Probelauf 12.09.2026: 572 MB GPU-Speicher fuer 208^3 = 8.998.912
# Zellen mit SURFACE + FP16S ⇒ 63,6 B/Zelle. Aufgerundet, weil eine zu kleine
# Schaetzung in einem OOM endet und ein OOM hier ein SIGKILL ist.
BYTES_JE_ZELLE = 64
VRAM_MB_VORGABE = 20000          # nutzbar auf der 24-GB-Karte, mit Luft

# Oel — dieselben Werte, mit denen `ema_oilspray` rechnet.
SI_RHO   = 850.0                 # [kg/m^3]
SI_NU    = 1.0e-5                # [m^2/s], warmes Getriebeoel
SI_SIGMA = 0.030                 # [kg/s^2]
SI_G     = 9.81
CD_NOZZLE = 0.8                  # Ausflusszahl, wie `ema_oilspray`

# Ab wie vielen Zellen je Bohrung der Strahl ueberhaupt ein zusammenhaengendes
# Oel-Netz bilden kann. Dieselbe Schwelle wie `ema_oilspray._jet_cells`.
ZELLEN_JE_BOHRUNG_MIN = 2.0
ZELLEN_JE_BOHRUNG_ZIEL = 3.0


def _klemm(v, lo, hi, vorgabe):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return vorgabe
    if v != v:
        return vorgabe
    return max(lo, min(hi, v))


def strahlgeschwindigkeit(druck_bar, rho=SI_RHO, cd=CD_NOZZLE):
    """Bernoulli mit Ausflusszahl — dieselbe Formel wie `ema_oilspray`, damit
    ein Druck in beiden Pfaden denselben Strahl bedeutet."""
    return cd * math.sqrt(2.0 * float(druck_bar) * 1e5 / rho)


# ── Was sich rechnen laesst und was nicht ────────────────────────────────────
def aufloesung(fenster_mm, duese_mm, vram_mb=VRAM_MB_VORGABE, n_fest=None):
    """Zellzahl je Kante fuer ein Fenster — und die ehrliche Auskunft, ob die
    Duese darin aufgeloest ist.

    ``n_fest`` uebersteuert die Zellzahl (Nutzerwahl); der Speicher wird dann
    trotzdem gerechnet und gedeckelt. Returns ein Dict, das 1:1 ins Ergebnis
    wandert."""
    fenster_mm = _klemm(fenster_mm, *FENSTER_RANGE, DEFAULT_FENSTER)
    duese_mm = max(0.1, float(duese_mm or 1.0))
    n_max_speicher = int((vram_mb * 1e6 / BYTES_JE_ZELLE) ** (1.0 / 3.0))
    if n_fest:
        n = int(_klemm(n_fest, *N_RANGE, DEFAULT_N))
    else:
        # so fein, dass ZIEL Zellen ueber der Bohrung liegen
        n = int(math.ceil(fenster_mm * ZELLEN_JE_BOHRUNG_ZIEL / duese_mm))
        n = int(_klemm(n, *N_RANGE, DEFAULT_N))
    n = min(n, n_max_speicher, N_RANGE[1])
    n = max(n, N_RANGE[0])
    n -= n % 2                                   # gerade Zellzahl: Mittelebene liegt sauber
    zelle = fenster_mm / n
    je_bohrung = duese_mm / zelle
    return {
        "n": n, "zelle_mm": zelle, "fenster_mm": fenster_mm,
        "zellen": n ** 3, "speicher_mb": round(n ** 3 * BYTES_JE_ZELLE / 1e6, 1),
        "zellen_je_bohrung": round(je_bohrung, 2),
        "unteraufgeloest": je_bohrung < ZELLEN_JE_BOHRUNG_MIN,
        "n_max_speicher": n_max_speicher,
    }


def vollmaschine_kosten(stator_od_mm, duese_mm, ziel=ZELLEN_JE_BOHRUNG_ZIEL,
                        vram_mb=VRAM_MB_VORGABE):
    """Was die GANZE Maschine mit aufgeloester Duese kosten wuerde. Wird in
    jedes Ergebnis geschrieben — die Aussage „das Fenster ist kein Sparzwang,
    sondern die einzige Moeglichkeit" ist damit gerechnet und nicht behauptet."""
    kante = float(stator_od_mm or 260.0) * 1.1     # Maschine + etwas Luft
    n = int(math.ceil(kante * ziel / max(0.1, float(duese_mm or 1.0))))
    zellen = n ** 3
    gb = zellen * BYTES_JE_ZELLE / 1e9
    return {"kante_mm": round(kante, 1), "n": n, "zellen": zellen,
            "speicher_gb": round(gb, 1), "passt": gb * 1000.0 <= vram_mb}


# ── STL: lesen, drehen, Fenster bestimmen ────────────────────────────────────
def _stl_lesen(pfad):
    """Binaeres STL -> numpy-Feld (n,3,3). FluidX3D liest die Datei selbst; hier
    wird sie nur gelesen, um das Fenster zu SETZEN und die Teile in die
    Fensterlage zu drehen."""
    import numpy as np
    with open(pfad, "rb") as f:
        roh = f.read()
    if len(roh) < 84:
        raise RuntimeError("STL zu kurz: %s" % pfad)
    n = struct.unpack("<I", roh[80:84])[0]
    erwartet = 84 + n * 50
    if len(roh) < erwartet:
        raise RuntimeError("STL unvollstaendig (%d Dreiecke angekuendigt): %s" % (n, pfad))
    daten = np.frombuffer(roh[84:erwartet], dtype=np.uint8).reshape(n, 50)
    ecken = daten[:, 12:48].copy().view(np.float32).reshape(n, 3, 3)
    return ecken


def _stl_schreiben(pfad, tris):
    """numpy-Feld (n,3,3) -> binaeres STL. Die Normalen werden mitgerechnet;
    FluidX3D voxelt ueber Strahlschnitte und braucht sie konsistent."""
    import numpy as np
    tris = np.asarray(tris, dtype=np.float32)
    n = tris.shape[0]
    nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    laenge = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = np.divide(nrm, np.where(laenge > 0, laenge, 1.0)).astype(np.float32)
    satz = np.zeros((n, 50), dtype=np.uint8)
    satz[:, 0:12] = nrm.view(np.uint8).reshape(n, 12)
    satz[:, 12:48] = tris.reshape(n, 9).view(np.uint8).reshape(n, 36)
    with open(pfad, "wb") as f:
        f.write(b"FluidX3D-Fenster, erzeugt von ema_fluidx3d".ljust(80, b" "))
        f.write(struct.pack("<I", n))
        f.write(satz.tobytes())
    return pfad


def fenster_bestimmen(tris, axial_len_mm, fenster_mm, ring_gap_mm=3.0,
                      duese_mm=1.0, anlauf_mm=0.0):
    """Wo im Motor liegt das Rechenfenster — aus der GEOMETRIE, nicht geraten.

    Der Wickelkopf-Ausschnitt sitzt an einem beliebigen Azimut; gerechnet wird
    aber in einem achsparallelen Kasten mit der Schwerkraft in -y. Also wird
    der Ausschnitt um -theta_c um die Motorachse gedreht, bis er auf der
    +x-Achse liegt; dann ist „radial nach innen" gleich -x und „unten" gleich
    -y, wie im waagerechten Einbau von `ema_oilspray`.

    Der erste Probelauf setzte das Fenster nach Augenmass auf z = 98 mm und
    traf die GERADEN Staebe statt der Krone. Deshalb kommt z hier aus dem
    Ueberhang (|z| > Paketlaenge/2) und nicht aus einer Zahl.

    Returns ein Dict mit ``theta_deg`` (Drehung), ``box_min``/``box_mitte``
    (mm, im gedrehten System), ``r_krone``, ``z_krone``, ``duese`` (Lage der
    Muendung in mm) und ``treffer`` (Zielpunkt auf der Krone)."""
    import numpy as np
    tris = np.asarray(tris, dtype=np.float64)
    p = tris.reshape(-1, 3)
    z_paket = 0.5 * float(axial_len_mm or 100.0)
    ueber = p[p[:, 2] > z_paket]
    if len(ueber) < 10:                            # kein +z-Ueberhang: -z versuchen
        ueber = p[p[:, 2] < -z_paket]
        if len(ueber) >= 10:
            ueber = ueber.copy()
    if len(ueber) < 10:
        ueber = p                                   # gar kein Ueberhang: ganzes Teil
        art = "kein Wickelkopf-Ueberhang gefunden — Fenster auf das ganze Teil gesetzt"
    else:
        art = "Wickelkopf-Ueberhang"
    spiegel = bool(len(ueber) and ueber[:, 2].mean() < 0.0)

    th = np.arctan2(ueber[:, 1], ueber[:, 0])
    # Kreismittel: ueber die Winkel gemittelt, nicht ueber ihre Zahlenwerte —
    # ein Ausschnitt um +-pi haette sonst die Mitte bei 0.
    theta_c = float(np.arctan2(np.sin(th).mean(), np.cos(th).mean()))

    c, s = math.cos(-theta_c), math.sin(-theta_c)
    gedreht = np.column_stack([
        ueber[:, 0] * c - ueber[:, 1] * s,
        ueber[:, 0] * s + ueber[:, 1] * c,
        np.abs(ueber[:, 2]) if spiegel else ueber[:, 2]])
    # nur der Kern des Ausschnitts zaehlt (die Raender laufen aus)
    nah = gedreht[np.abs(gedreht[:, 1]) < 0.35 * fenster_mm]
    if len(nah) < 10:
        nah = gedreht
    r_krone = float(np.hypot(nah[:, 0], nah[:, 1]).max())
    z_spitze = float(nah[:, 2].max())
    z_fuss = max(float(nah[:, 2].min()), z_paket)
    z_krone = 0.5 * (z_fuss + z_spitze)

    r_duese = r_krone + float(ring_gap_mm or 3.0)
    # Hinter der Muendung bleibt Platz fuer den ANLAUF: dort steht die Oelsaeule
    # zum Zeitpunkt 0, in freier Luft ausserhalb des Spritzrings. Ohne diesen
    # Platz begaenne der "Strahl" im Zwischenraum der Leiter — der Ringabstand
    # allein (gemessen 3 mm) reicht dafuer nicht.
    anlauf = max(0.0, float(anlauf_mm or 0.0))
    x_max = r_duese + anlauf + max(2.0, 4.0 * float(duese_mm or 1.0))
    box_min = (x_max - fenster_mm, -0.5 * fenster_mm, z_krone - 0.5 * fenster_mm)
    # Was vom Fenster noch fuer die Maschine uebrig bleibt.
    tiefe = r_krone - box_min[0]
    return {
        "theta_deg": round(math.degrees(theta_c), 3),
        "gespiegelt": spiegel,
        "quelle": art,
        "r_krone_mm": round(r_krone, 2),
        "z_krone_mm": round(z_krone, 2),
        "z_spitze_mm": round(z_spitze, 2),
        "z_paket_mm": round(z_paket, 2),
        "r_duese_mm": round(r_duese, 2),
        "anlauf_mm": round(anlauf, 2),
        "kupfertiefe_mm": round(tiefe, 2),
        "box_min_mm": [round(v, 3) for v in box_min],
        "box_mitte_mm": [round(v + 0.5 * fenster_mm, 3) for v in box_min],
        "duese_mm_pos": [round(r_duese, 2), 0.0, round(z_krone, 2)],
        "treffer_mm": [round(r_krone, 2), 0.0, round(z_krone, 2)],
    }


def stl_ins_fenster(quell_pfade, fenster, ziel_pfad):
    """Dreht die (moeglicherweise mehreren) Bauteil-STL in die Fensterlage und
    schreibt EINE Datei. FluidX3D voxelt ein Netz je Aufruf; mehrere Bauteile
    mit demselben Flag sind eine Menge Dreiecke, kein Unterschied."""
    import numpy as np
    th = math.radians(-fenster["theta_deg"])
    c, s = math.cos(th), math.sin(th)
    alle = []
    for p in quell_pfade:
        t = _stl_lesen(p).astype(np.float64)
        x, y, z = t[..., 0].copy(), t[..., 1].copy(), t[..., 2].copy()
        t[..., 0] = x * c - y * s
        t[..., 1] = x * s + y * c
        if fenster.get("gespiegelt"):
            t[..., 2] = -z
        alle.append(t)
    if not alle:
        raise RuntimeError("keine STL zum Drehen")
    return _stl_schreiben(ziel_pfad, np.concatenate(alle, axis=0))


# ─────────────────────────────────────────────────────────────────────────────
# Der Fall als C++ — FluidX3D hat keine Eingabedatei, jeder Fall IST Quelltext
# ─────────────────────────────────────────────────────────────────────────────
_SETUP_VORLAGE = r'''#include "setup.hpp"
#include <fstream>

// ─────────────────────────────────────────────────────────────────────────────
// ALTERED SOURCE VERSION of FluidX3D (ProjectPhysX).
// Original: https://github.com/ProjectPhysX/FluidX3D — licence notice retained,
// see LICENSE.md and HERKUNFT.txt next to this tree.
//
// Diese Datei ist ERZEUGT (cae_orchestrator/ema_fluidx3d.py). Von Hand
// geaenderte Fassungen werden beim naechsten Lauf ueberschrieben.
// Erzeugt: @@ZEIT@@
// ─────────────────────────────────────────────────────────────────────────────

static void marke(const string& s) { std::cout << "\nFX3D_STAGE:" << s << "\n" << std::flush; }

void main_setup() { // Spritzoel-Fenster; benoetigt: FP16S, VOLUME_FORCE, EQUILIBRIUM_BOUNDARIES, SURFACE
	// ── erzeugte Groessen ───────────────────────────────────────────────────
	const uint  N1       = @@N1@@u;          // Zellen je Kante
	const float CELL_MM  = @@CELL_MM@@f;     // mm je Zelle
	const float BOX_MM   = @@BOX_MM@@f;      // Kantenlaenge des Fensters [mm]
	const float BOX_MIN_X= @@BOX_MIN_X@@f;   // Fensterecke im (gedrehten) Motorsystem [mm]
	const float BOX_MIN_Y= @@BOX_MIN_Y@@f;
	const float BOX_MIN_Z= @@BOX_MIN_Z@@f;
	const float SI_RHO   = @@SI_RHO@@f;
	const float SI_NU    = @@SI_NU@@f;
	const float SI_SIGMA = @@SI_SIGMA@@f;
	const float SI_G     = @@SI_G@@f;
	const float SI_U     = @@SI_U@@f;        // Strahlgeschwindigkeit [m/s]
	const float D_NOZ_MM = @@D_NOZ_MM@@f;    // Duesenbohrung [mm]
	const float X_NOZ    = @@X_NOZ@@f;       // Muendung, x in Zellen
	const float Z_NOZ    = @@Z_NOZ@@f;       // Muendung, z in Zellen
	const float SAEULE   = @@SAEULE@@f;      // Laenge des Oelstosses in Zellen
	const float TILT     = @@TILT@@f;        // Strahlneigung gegen die Radiale [rad]
	const ulong N_BILDER = @@N_BILDER@@ull;
	const ulong SCHRITTE = @@SCHRITTE@@ull;  // Zeitschritte je Bild
	const string STL     = "@@STL@@";
	const string AUS     = "@@AUS@@";

	const float LBM_U = 0.08f;               // Strahl in LBM-Einheiten (Stabilitaetswahl)
	units.set_m_kg_s(1.0f/(0.001f*CELL_MM), LBM_U, 1.0f, 1.0f, SI_U, SI_RHO);
	const float lbm_nu    = units.nu(SI_NU);
	const float lbm_f     = units.f(SI_RHO, SI_G);
	const float lbm_sigma = units.sigma(SI_SIGMA);

	marke("Gitter " + to_string(N1) + "^3, " + to_string(CELL_MM, 4u) + " mm/Zelle, "
	      + to_string(D_NOZ_MM/CELL_MM, 2u) + " Zellen je Bohrung");

	// Schwerkraft quer zur Motorachse (waagerechter Einbau wie ema_oilspray):
	// die Motorachse ist z, "unten" ist -y.
	LBM lbm(N1, N1, N1, lbm_nu, 0.0f, -lbm_f, 0.0f, lbm_sigma);

	// ── Kupfer hineinlegen (mm -> Zellen), NICHT einpassen ──────────────────
	// read_stl skaliert und verschiebt nur; was ausserhalb des Gitters liegt,
	// faellt beim Voxeln weg. Genau das ist hier gewollt: die STL ist der ganze
	// Wickelkopf, gerechnet wird ein Fenster daraus.
	const float3 versatz = float3(-BOX_MIN_X/CELL_MM, -BOX_MIN_Y/CELL_MM, -BOX_MIN_Z/CELL_MM);
	Mesh* netz = read_stl(get_exe_path()+STL, 1.0f/CELL_MM, float3x3(1.0f), versatz);
	lbm.voxelize_mesh_on_device(netz, TYPE_S);
	marke("Kupfer gevoxelt");

	// ── Raender offen + Oelstoss setzen ─────────────────────────────────────
	const float r_loch = 0.5f*D_NOZ_MM/CELL_MM;
	const float ct = cos(TILT), st = sin(TILT);   // Strahlrichtung d = (-ct, 0, +st)
	const uint Nx=lbm.get_Nx(), Ny=lbm.get_Ny(), Nz=lbm.get_Nz();
	parallel_for(lbm.get_N(), [&](ulong n) { uint x=0u, y=0u, z=0u; lbm.coordinates(n, x, y, z);
		if(x==0u||x==Nx-1u||y==0u||y==Ny-1u||z==0u||z==Nz-1u) { lbm.flags[n] = TYPE_E; return; }
		if(lbm.flags[n]&TYPE_S) return;           // Kupfer bleibt Kupfer
		// Die Saeule liegt HINTER der Muendung, in freier Luft ausserhalb des
		// Spritzrings, und fliegt nach innen. Sie im Zwischenraum der Leiter
		// beginnen zu lassen waere kein Strahl, sondern ein vorgefuellter Spalt
		// (gemessen: 13 Zellen lagen schon zum Zeitpunkt 0 am Kupfer).
		const float px = (float)x - X_NOZ, py = (float)y - 0.5f*(float)Ny, pz = (float)z - Z_NOZ;
		const float s  = px*ct - pz*st;           // Lauflaenge nach AUSSEN ab der Muendung
		if(s<0.0f || s>SAEULE) return;
		const float qx = px - s*ct, qz = pz + s*st;
		if(sqrt(qx*qx + py*py + qz*qz) >= r_loch) return;
		lbm.flags[n] = TYPE_F;
		lbm.phi[n]   = 1.0f;
		lbm.u.x[n]   = -LBM_U*ct;
		lbm.u.z[n]   =  LBM_U*st;
	});

	lbm.run(0u);
	lbm.flags.read_from_device();

	// ── Festkoerpermaske des Schnitts (einmal) ──────────────────────────────
	// Schnittebene z = Nz/2: sie traegt die Strahlachse UND die Schwerkraft.
	const uint zs = Nz/2u;
	{
		std::ofstream f(AUS+"/fest.bin", std::ios::binary);
		for(uint y=0u; y<Ny; y++) for(uint x=0u; x<Nx; x++) {
			const char c = (lbm.flags[lbm.index(x,y,zs)]&TYPE_S) ? (char)255 : (char)0;
			f.write(&c, 1);
		}
	}
	ulong n_fest = 0ull;
	for(ulong n=0ull; n<lbm.get_N(); n++) if(lbm.flags[n]&TYPE_S) n_fest++;
	if(n_fest==0ull) {
		marke("FEHLER: im Fenster liegt kein Kupfer — Fensterlage pruefen");
		std::ofstream f(AUS+"/kennwerte.json");
		f << "{\"fehler\":\"kein Festkoerper im Fenster\",\"reihe\":[]}";
		return;
	}
	marke("Fenster: " + to_string(n_fest) + " Festkoerperzellen von " + to_string(lbm.get_N()));

	// ── Lauf in Abschnitten; je Abschnitt ein Schnitt + Kennwerte ───────────
	std::ofstream kw(AUS+"/kennwerte.json");
	kw << "{\"reihe\":[";
	const double mm3 = (double)CELL_MM*(double)CELL_MM*(double)CELL_MM;
	Clock uhr;
	double oel0 = -1.0;
	char* puffer = new char[(size_t)Nx*(size_t)Ny];
	for(ulong k=0ull; k<=N_BILDER; k++) {
		if(k>0ull) lbm.run(SCHRITTE);
		lbm.phi.read_from_device();
		lbm.flags.read_from_device();
		// Schnitt
		for(uint y=0u; y<Ny; y++) for(uint x=0u; x<Nx; x++) {
			const ulong n = lbm.index(x,y,zs);
			puffer[(size_t)y*(size_t)Nx+(size_t)x] = (lbm.flags[n]&TYPE_S) ? (char)255
				: (char)fmin(254.0f, fmax(0.0f, 254.0f*lbm.phi[n]));
		}
		string nr = to_string((uint)k);            // vierstellig auffuellen: `alignr`
		while(nr.length()<4u) nr = "0"+nr;         // fuellt mit Leerzeichen, nicht mit Nullen
		std::ofstream sf(AUS+"/schnitt_"+nr+".bin", std::ios::binary);
		sf.write(puffer, (std::streamsize)((size_t)Nx*(size_t)Ny));
		sf.close();
		// Kennwerte
		double oel = 0.0; ulong nass = 0ull, haft = 0ull;
		for(ulong n=0ull; n<lbm.get_N(); n++) {
			if(lbm.flags[n]&TYPE_S) continue;
			const float p = lbm.phi[n];
			if(p<=0.0f) continue;
			oel += (double)p;
			if(p<=0.5f) continue;
			nass++;
			uint x=0u, y=0u, z=0u; lbm.coordinates(n, x, y, z);
			if(x==0u||x==Nx-1u||y==0u||y==Ny-1u||z==0u||z==Nz-1u) continue;
			if((lbm.flags[lbm.index(x-1u,y,z)]&TYPE_S)||(lbm.flags[lbm.index(x+1u,y,z)]&TYPE_S)
			 ||(lbm.flags[lbm.index(x,y-1u,z)]&TYPE_S)||(lbm.flags[lbm.index(x,y+1u,z)]&TYPE_S)
			 ||(lbm.flags[lbm.index(x,y,z-1u)]&TYPE_S)||(lbm.flags[lbm.index(x,y,z+1u)]&TYPE_S)) haft++;
		}
		if(oel0<0.0) oel0 = oel;
		kw << (k>0ull ? "," : "") << "{\"bild\":" << k
		   << ",\"t_ms\":" << 1000.0f*units.si_t(k*SCHRITTE)
		   << ",\"oel_mm3\":" << oel*mm3
		   << ",\"nass\":" << nass << ",\"am_kupfer\":" << haft << "}";
		kw << std::flush;
		std::cout << "\nFX3D_STEP:" << k << "/" << N_BILDER << "\n" << std::flush;
	}
	delete[] puffer;
	const double sek = uhr.stop();
	const double lups = (double)lbm.get_N()*(double)(N_BILDER*SCHRITTE)/sek/1.0E6;
	kw << "],\"n1\":" << N1 << ",\"zelle_mm\":" << CELL_MM
	   << ",\"zellen\":" << lbm.get_N() << ",\"fest\":" << n_fest
	   << ",\"schritte\":" << (N_BILDER*SCHRITTE)
	   << ",\"sekunden\":" << sek << ",\"mlups\":" << lups
	   << ",\"t_ende_ms\":" << 1000.0f*units.si_t(N_BILDER*SCHRITTE)
	   << ",\"oel_start_mm3\":" << oel0*mm3
	   << ",\"re\":" << units.si_Re(0.001f*D_NOZ_MM, SI_U, SI_NU)
	   << ",\"we\":" << units.si_We(0.001f*D_NOZ_MM, SI_U, SI_RHO, SI_SIGMA)
	   << ",\"zellen_je_bohrung\":" << D_NOZ_MM/CELL_MM << "}";
	kw.close();
	marke("fertig: " + to_string((float)sek, 1u) + " s, " + to_string((float)lups, 0u) + " MLUPS");
	std::cout << "\nFX3D_DONE\n" << std::flush;
}
'''


def setup_code(cfg):
    """Setzt die Vorlage. Ersetzt wird mit ``@@NAME@@`` statt ``str.format``,
    weil C++ voller geschweifter Klammern ist — jede einzelne muesste sonst
    verdoppelt werden, und ein vergessenes Paar faellt erst beim Uebersetzen
    auf."""
    out = _SETUP_VORLAGE
    for k, v in cfg.items():
        out = out.replace("@@%s@@" % k, str(v))
    uebrig = [t for t in ("@@",) if t in out]
    if uebrig:
        rest = out[out.index("@@"):][:40]
        raise RuntimeError("Vorlage nicht vollstaendig gesetzt: %s" % rest)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Bilder, Video, Kennwert-Diagramme
# ─────────────────────────────────────────────────────────────────────────────
def _b64_png(fig):
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def bilder_rendern(schnitte, fest_pfad, n1, cell_mm, reihe, frames_dir,
                   titel="", progress_cb=None):
    """Aus den Schnittdateien die Videobilder rendern (Kupfer grau, Oel bernstein
    nach Fuellstand). Der Schnitt liegt in der Ebene z = N/2 — sie traegt die
    Strahlachse UND die Schwerkraft, ist also die einzige, in der man Flug,
    Aufprall und Ablauf zugleich sieht."""
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(frames_dir, exist_ok=True)
    for fn in os.listdir(frames_dir):
        if fn.startswith("frame_") or fn == "anim.mp4":
            try:
                os.remove(os.path.join(frames_dir, fn))
            except OSError:
                pass
    fest = None
    if fest_pfad and os.path.exists(fest_pfad):
        fest = np.frombuffer(open(fest_pfad, "rb").read(), dtype=np.uint8)
        fest = fest[:n1 * n1].reshape(n1, n1) > 0
    kante = n1 * cell_mm
    n = 0
    for i, p in enumerate(schnitte):
        roh = np.frombuffer(open(p, "rb").read(), dtype=np.uint8)
        if roh.size < n1 * n1:
            continue
        feld = roh[:n1 * n1].reshape(n1, n1).astype(np.float32)
        s = fest if fest is not None else (feld >= 255)
        phi = np.where(s, np.nan, feld / 254.0)
        fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=100)
        ax.set_facecolor("#0d0f12")
        ax.imshow(np.where(s, 1.0, np.nan), origin="lower", cmap="Greys_r",
                  vmin=0.0, vmax=1.6, extent=[0, kante, 0, kante],
                  interpolation="nearest")
        ax.imshow(np.where(np.isfinite(phi) & (phi > 0.02), phi, np.nan),
                  origin="lower", cmap="autumn", vmin=0.0, vmax=1.0,
                  extent=[0, kante, 0, kante], interpolation="nearest")
        z = reihe[i] if i < len(reihe) else {}
        ax.set_title("%s\nt = %.2f ms · %.2f mm³ Öl · %d Zellen am Kupfer"
                     % (titel, z.get("t_ms", 0.0), z.get("oel_mm3", 0.0),
                        int(z.get("am_kupfer", 0))), fontsize=8)
        ax.set_xlabel("radial [mm]  (Düse rechts, Krone links)", fontsize=7)
        ax.set_ylabel("↓ Schwerkraft [mm]", fontsize=7)
        ax.tick_params(labelsize=6)
        fig.tight_layout()
        fig.savefig(os.path.join(frames_dir, "frame_%04d.png" % i))
        plt.close(fig)
        n += 1
        if progress_cb and (i % 5 == 0):
            progress_cb("🖼 Bild %d/%d" % (i + 1, len(schnitte)), None)
    return n


def kennwert_charts(metrics, charts_dir):
    """Ölmenge und Benetzung über die Zeit → base64 + Dateien (Muster
    `ema_oilspray._metric_charts`)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(charts_dir, exist_ok=True)
    reihe = (metrics or {}).get("reihe") or []
    if not reihe:
        return {}
    t = [r.get("t_ms", 0.0) for r in reihe]
    oel = [r.get("oel_mm3", 0.0) for r in reihe]
    haft = [r.get("am_kupfer", 0) for r in reihe]
    nass = [r.get("nass", 0) for r in reihe]
    imgs = {}

    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    ax.plot(t, haft, color="#c0392b", lw=2, label="am Kupfer")
    ax.plot(t, nass, color="#c0392b", lw=1, ls="--", alpha=0.6, label="gesamt nass")
    ax.set_xlabel("Zeit [ms]"); ax.set_ylabel("Zellen mit Füllstand > 0,5")
    ax.set_title("Benetzung über die Zeit (geometrischer Proxy)")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    imgs["fx3d_benetzung"] = _b64_png(fig)

    fig2, ax2 = plt.subplots(figsize=(6.2, 3.2))
    ax2.plot(t, oel, color="#2471a3", lw=2)
    ax2.set_xlabel("Zeit [ms]"); ax2.set_ylabel("Öl im Fenster [mm³]")
    ax2.set_title("Massenerhaltung des Freiflächenlösers "
                  "(Abfall = Öl verlässt das Fenster)")
    ax2.grid(alpha=0.3)
    if oel and oel[0] > 0:
        ax2.axhline(oel[0], color="#7f8c8d", ls=":", lw=1)
    imgs["fx3d_masse"] = _b64_png(fig2)

    for key, b64 in imgs.items():
        try:
            with open(os.path.join(charts_dir, key + ".png"), "wb") as f:
                f.write(base64.b64decode(b64))
        except OSError:
            pass
    return imgs


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────
def run_fluidx3d(payload, project_dir, progress_cb=None, cancel_cb=None):
    """Führt den LBM-Spritzöl-Lauf aus und persistiert das Ergebnis.

    ``payload`` — normaler Analyse-Payload (geom + axial_len). Die
    Spritz-Einstellungen werden aus ``payload["oil"]`` GEERBT (Druck,
    Düsen-Ø, Ringabstand, Ausschnitt) und nur die LBM-eigenen unter
    ``payload["fx3d"]`` ergänzt — dasselbe Verhältnis, das der 🌊-Tab zum
    💧-Tab hat: EIN Satz Spritzöl-Einstellungen, drei Löser darauf.
    """
    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    geom = payload.get("geom") or {}
    axial_len = float(payload.get("axial_len", geom.get("axialLen", 100.0)) or 100.0)
    oil = payload.get("oil") or {}
    fx = payload.get("fx3d") or {}

    # aus dem 💧-Satz geerbt
    druck    = max(0.1, min(3.0, float(oil.get("pressure_bar", 3.0) or 3.0)))
    duese_mm = max(0.5, min(3.0, float(oil.get("nozzle_d_mm", 1.0) or 1.0)))
    ring_gap = max(0.5, min(30.0, float(oil.get("ring_gap_mm", 3.0) or 3.0)))
    section  = int(_klemm(oil.get("section_slots", 3), 1, 12, 3))
    tilt_deg = max(-60.0, min(60.0, float(oil.get("jet_tilt_deg", 0.0) or 0.0)))
    # LBM-eigen
    fenster  = _klemm(fx.get("fenster_mm", DEFAULT_FENSTER), *FENSTER_RANGE, DEFAULT_FENSTER)
    n_fest   = fx.get("n")
    bilder   = int(_klemm(fx.get("bilder", DEFAULT_BILDER), *BILDER_RANGE, DEFAULT_BILDER))
    dauer_ms = _klemm(fx.get("dauer_ms", DEFAULT_DAUER), *DAUER_RANGE, DEFAULT_DAUER)
    stoss_ms = _klemm(fx.get("stoss_ms", DEFAULT_STOSS), *STOSS_RANGE, DEFAULT_STOSS)
    fps      = int(_klemm(fx.get("fps", 12), 2, 60, 12))

    si_u = strahlgeschwindigkeit(druck)
    aufl = aufloesung(fenster, duese_mm, n_fest=n_fest)
    voll = vollmaschine_kosten(geom.get("statorOD", 260.0), duese_mm)

    work = os.path.join(project_dir, WORK_SUBDIR)
    aus  = os.path.join(work, "aus")
    frames_dir = os.path.join(project_dir, FRAMES_SUBDIR)
    charts_dir = os.path.join(project_dir, "charts")
    for d in (work, aus, frames_dir, charts_dir):
        os.makedirs(d, exist_ok=True)
    for fn in os.listdir(aus):                    # Reste eines früheren Laufs
        try:
            os.remove(os.path.join(aus, fn))
        except OSError:
            pass

    _log("🌀 FluidX3D (Lattice-Boltzmann, freie Oberfläche, GPU)", 2)
    if aufl["unteraufgeloest"]:
        _log("⚠ Strahl unter-aufgelöst: %.2f Zellen je Bohrung (< %.1f). Fenster "
             "verkleinern oder Zellzahl erhöhen." % (aufl["zellen_je_bohrung"],
                                                     ZELLEN_JE_BOHRUNG_MIN), None)

    # 1) Wickelkopf als STL (dieselbe FreeCAD-Stufe wie der 💧-Pfad)
    import ema_oilspray
    parts, stl_log = ema_oilspray._export_winding_stl(
        geom, axial_len, work, section, _log, include_core=False)
    if not parts:
        raise RuntimeError("Wickelkopf-STL-Export fehlgeschlagen: %s" % stl_log)
    quellen = [p for k, p in sorted(parts.items()) if k == "winding"] or sorted(parts.values())
    _log("✓ Wickelkopf exportiert (%d Nuten)" % section, 10)

    # 2) Fenster aus der Geometrie bestimmen und die STL hineindrehen
    import numpy as np
    tris = np.concatenate([_stl_lesen(p) for p in quellen], axis=0)
    # Laenge der Oelsaeule = was die Duese in `stoss_ms` ausstoesst. Sie braucht
    # Platz HINTER der Muendung; bleibt danach zu wenig Fenster fuer die
    # Maschine uebrig, wird der Stoss gekuerzt und das GESAGT — lieber ein
    # kuerzerer Stoss als ein Fenster, in dem der Wickelkopf nicht mehr steht.
    saeule_mm = stoss_ms * 1e-3 * si_u * 1000.0
    max_anlauf = 0.45 * fenster - ring_gap
    gekuerzt = None
    if saeule_mm > max_anlauf:
        gekuerzt = (stoss_ms, max(0.0, max_anlauf))
        saeule_mm = max(0.0, max_anlauf)
        stoss_ms = saeule_mm / max(1e-9, si_u * 1000.0) * 1e3
        _log("⚠ Ölstoß auf %.2f ms gekürzt — sonst bliebe vom %.0f-mm-Fenster kein "
             "Platz mehr für den Wickelkopf." % (stoss_ms, fenster), None)
    fen = fenster_bestimmen(tris, axial_len, fenster, ring_gap, duese_mm,
                            anlauf_mm=saeule_mm)
    _log("🎯 Fenster: %.1f mm um die Krone bei r=%.1f mm, z=%.1f mm (Ausschnitt %+.1f° "
         "gedreht) — %.1f mm Anlauf, %.1f mm Kupfer im Bild"
         % (fenster, fen["r_krone_mm"], fen["z_krone_mm"], -fen["theta_deg"],
            fen["anlauf_mm"], fen["kupfertiefe_mm"]), 12)

    heim, wie = fluidx3d_runner.vorbereiten(progress_cb=_log)
    stl_dir = os.path.join(heim, "stl")
    os.makedirs(stl_dir, exist_ok=True)
    stl_name = "fenster_%s.stl" % time.strftime("%Y%m%d_%H%M%S")
    stl_ins_fenster(quellen, fen, os.path.join(stl_dir, stl_name))

    if cancel_cb and cancel_cb():
        raise RuntimeError("abgebrochen")

    # 3) Fall als C++ erzeugen und übersetzen
    bx, by, bz = fen["box_min_mm"]
    zelle = aufl["zelle_mm"]
    # Zeitschritte: aus der gewünschten Realzeit. 1 Zelle = zelle mm, der Strahl
    # legt LBM_U = 0,08 Zellen je Schritt zurück ⇒ Schritte = t·v/(0,08·Zelle).
    schritte_ges = max(bilder, int(dauer_ms * 1e-3 * si_u * 1000.0 / (0.08 * zelle)))
    je_bild = max(1, schritte_ges // bilder)
    saeule = saeule_mm / zelle
    cfg = {
        "ZEIT": time.strftime("%Y-%m-%d %H:%M:%S"),
        "N1": aufl["n"], "CELL_MM": "%.6f" % zelle, "BOX_MM": "%.4f" % fenster,
        "BOX_MIN_X": "%.4f" % bx, "BOX_MIN_Y": "%.4f" % by, "BOX_MIN_Z": "%.4f" % bz,
        "SI_RHO": "%.4f" % SI_RHO, "SI_NU": "%.8f" % SI_NU,
        "SI_SIGMA": "%.6f" % SI_SIGMA, "SI_G": "%.4f" % SI_G, "SI_U": "%.4f" % si_u,
        "D_NOZ_MM": "%.4f" % duese_mm,
        "X_NOZ": "%.4f" % ((fen["r_duese_mm"] - bx) / zelle),
        "Z_NOZ": "%.4f" % ((fen["z_krone_mm"] - bz) / zelle),
        "SAEULE": "%.4f" % saeule, "TILT": "%.6f" % math.radians(tilt_deg),
        "N_BILDER": bilder, "SCHRITTE": je_bild,
        "STL": "../stl/" + stl_name, "AUS": aus,
    }
    code = setup_code(cfg)
    with open(os.path.join(work, "setup_erzeugt.cpp"), "w", encoding="utf-8") as f:
        f.write(code)
    ue = fluidx3d_runner.uebersetzen(heim, code, progress_cb=_log)
    if not ue.get("ok"):
        raise RuntimeError(ue.get("error") or "Übersetzung fehlgeschlagen")

    if cancel_cb and cancel_cb():
        raise RuntimeError("abgebrochen")

    # 4) Lauf
    _log("🌀 %d³ Zellen (%.3f mm/Zelle, %.2f Zellen je Bohrung), %d Bilder à %d "
         "Schritte, Strahl %.1f m/s bei %.1f bar"
         % (aufl["n"], zelle, aufl["zellen_je_bohrung"], bilder, je_bild, si_u, druck), 18)
    lf = fluidx3d_runner.laufen(heim, aus, timeout=7200, progress_cb=_log)
    if lf.get("aborted"):
        raise RuntimeError("abgebrochen")
    metrics = lf.get("metrics") or {}
    if metrics.get("fehler"):
        raise RuntimeError("FluidX3D: %s (Fensterlage prüfen: r=%.1f mm, z=%.1f mm)"
                           % (metrics["fehler"], fen["r_krone_mm"], fen["z_krone_mm"]))
    if not lf.get("ok") and not (metrics.get("reihe")):
        raise RuntimeError("FluidX3D-Lauf fehlgeschlagen: %s\n%s"
                           % (lf.get("error"), (lf.get("stdout") or "")[-800:]))

    # 5) Bilder, Video, Diagramme
    reihe = metrics.get("reihe") or []
    _log("🖼 Schnittbilder rendern …", 88)
    n_bilder = bilder_rendern(lf.get("schnitte") or [], lf.get("fest"), aufl["n"],
                              zelle, reihe, frames_dir,
                              titel="Spritzöl am Wickelkopf (FluidX3D LBM)",
                              progress_cb=_log)
    _log("🎬 Video kodieren (ffmpeg) …", 94)
    import ema_em3d
    video = ema_em3d._encode_video(frames_dir, fps=fps)
    images = kennwert_charts(metrics, charts_dir)

    letzte = reihe[-1] if reihe else {}
    erste = reihe[0] if reihe else {}
    oel0, oel1 = erste.get("oel_mm3", 0.0), letzte.get("oel_mm3", 0.0)
    result = {
        "source": "fluidx3d_lbm",
        "config": {"fenster_mm": fenster, "n": aufl["n"], "zelle_mm": round(zelle, 4),
                   "bilder": bilder, "schritte_je_bild": je_bild,
                   "dauer_ms": dauer_ms, "stoss_ms": stoss_ms, "fps": fps,
                   "pressure_bar": druck, "nozzle_d_mm": duese_mm,
                   "ring_gap_mm": ring_gap, "section_slots": section,
                   "jet_tilt_deg": tilt_deg, "jet_speed_mps": round(si_u, 2),
                   "stoss_gekuerzt": bool(gekuerzt)},
        "fenster": fen,
        "aufloesung": aufl,
        "vollmaschine": voll,
        "metrics": {k: v for k, v in metrics.items() if k != "reihe"},
        "series": reihe,
        "bilanz": {
            "oel_start_mm3": round(oel0, 3), "oel_ende_mm3": round(oel1, 3),
            "masse_abweichung_pct": (round(100.0 * (oel1 - oel0) / oel0, 2)
                                     if oel0 else None),
            "am_kupfer_max": max([r.get("am_kupfer", 0) for r in reihe] or [0]),
            "getroffen": bool(max([r.get("am_kupfer", 0) for r in reihe] or [0]) > 0),
        },
        "images": images,
        "video": bool(video),
        "n_frames": n_bilder,
        "note": ("Lattice-Boltzmann mit freier Oberfläche (FluidX3D, GPU), "
                 "ISOTHERM — kein Temperaturfeld und kein Wärmeübergang; die "
                 "Kennwerte sind geometrische Benetzungs-Proxys wie im 💧-Pfad. "
                 "Gerechnet wird ein FENSTER um EINE Düse (die ganze Maschine "
                 "mit aufgelöster Bohrung bräuchte %.0f GB) und ein endlicher "
                 "ÖLSTOSS (%.2f ms), kein Dauerstrahl — der Freiflächenlöser "
                 "kann von aussen keine Masse nachgespeist bekommen."
                 % (voll["speicher_gb"], stoss_ms)),
        "arbeitskopie": heim,
        "lizenz": ("FluidX3D (ProjectPhysX): nicht kommerziell, nicht militärisch, "
                   "kein KI-Training auf dem Quelltext; geänderte Fassungen sind bei "
                   "Veröffentlichung von Ergebnissen offenzulegen."),
    }
    if aufl["unteraufgeloest"]:
        result["warnung"] = ("Strahl unter-aufgelöst: %.2f Zellen je Bohrung."
                             % aufl["zellen_je_bohrung"])
    _persist(project_dir, result)
    try:
        rid = _autosave_variant(project_dir, result, frames_dir)
        if rid:
            result["saved_id"] = rid
            _log("💾 Variante automatisch gespeichert (%s)." % rid, None)
    except Exception as e:                                   # noqa: BLE001
        _log("⚠ Auto-Speichern der Variante fehlgeschlagen: %s" % e, None)
    _log("✓ FluidX3D-Lauf fertig (%s, %.0f MLUPS)."
         % ("Strahl trifft" if result["bilanz"]["getroffen"] else "KEIN Treffer",
            metrics.get("mlups", 0.0)), 100)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Persistenz + Varianten-Store (wortgleich zum 💧-Pfad, damit die Bedienung
# dieselbe ist — ein zweites Ablageschema wäre die nächste Fehlerquelle)
# ─────────────────────────────────────────────────────────────────────────────
def _persist(project_dir, result):
    """Schlanke Zusammenfassung (ohne base64-Bilder) nach ``results.json``
    mergen. Fehlt die Datei, wird sie ANGELEGT — sonst wäre ein Lauf ohne
    vorherige Analyse nach dem Neuladen weg."""
    rj = os.path.join(project_dir, "results.json")
    try:
        data = {}
        if os.path.exists(rj):
            with open(rj) as f:
                data = json.load(f)
        lean = {k: v for k, v in result.items() if k != "images"}
        lean["image_files"] = {k: "charts/%s.png" % k for k in result.get("images", {})}
        data["fluidx3d"] = lean
        tmp = rj + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, rj)
    except (OSError, ValueError):
        pass


def load_saved(project_dir):
    rj = os.path.join(project_dir, "results.json")
    if not os.path.exists(rj):
        return None
    try:
        with open(rj) as f:
            saved = json.load(f).get("fluidx3d")
    except (OSError, ValueError):
        return None
    if not saved:
        return None
    images = {}
    for key, rel in (saved.get("image_files") or {}).items():
        p = os.path.join(project_dir, rel)
        if os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    images[key] = base64.b64encode(f.read()).decode()
            except OSError:
                pass
    out = dict(saved)
    out["images"] = images
    out["video"] = os.path.exists(os.path.join(project_dir, FRAMES_SUBDIR, "anim.mp4"))
    return out


def _runs_root(project_dir):
    return os.path.join(project_dir, RUNS_SUBDIR)


def _autosave_variant(project_dir, result, frames_dir):
    import shutil as _sh
    rid = time.strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(_runs_root(project_dir), rid)
    os.makedirs(dest, exist_ok=True)
    src_mp4 = os.path.join(frames_dir, "anim.mp4")
    has_video = os.path.exists(src_mp4)
    if has_video:
        try:
            _sh.copy(src_mp4, os.path.join(dest, "anim.mp4"))
        except OSError:
            has_video = False
    charts_dir = os.path.join(project_dir, "charts")
    image_files = {}
    for key in (result.get("images") or {}):
        src = os.path.join(charts_dir, key + ".png")
        if os.path.exists(src):
            try:
                _sh.copy(src, os.path.join(dest, key + ".png"))
                image_files[key] = key + ".png"
            except OSError:
                pass
    run = {k: v for k, v in result.items() if k != "images"}
    run.update({"image_files": image_files, "video": has_video, "id": rid,
                "timestamp": time.strftime("%Y-%m-%d %H:%M")})
    try:
        with open(os.path.join(dest, "run.json"), "w") as f:
            json.dump(run, f, ensure_ascii=False)
    except OSError:
        pass
    return rid


def list_saved_runs(project_dir):
    root = _runs_root(project_dir)
    out = []
    if not os.path.isdir(root):
        return out
    for rid in sorted(os.listdir(root), reverse=True):
        d = os.path.join(root, rid)
        rp = os.path.join(d, "run.json")
        if not os.path.isdir(d) or not os.path.exists(rp):
            continue
        try:
            with open(rp) as f:
                run = json.load(f)
        except (OSError, ValueError):
            continue
        cfg = run.get("config") or {}
        met = run.get("metrics") or {}
        bil = run.get("bilanz") or {}
        out.append({
            "id": rid, "timestamp": run.get("timestamp", rid),
            "video": bool(run.get("video")) and os.path.exists(os.path.join(d, "anim.mp4")),
            "n": cfg.get("n"), "zelle_mm": cfg.get("zelle_mm"),
            "fenster_mm": cfg.get("fenster_mm"), "dauer_ms": cfg.get("dauer_ms"),
            "pressure_bar": cfg.get("pressure_bar"), "nozzle_d_mm": cfg.get("nozzle_d_mm"),
            "mlups": met.get("mlups"), "sekunden": met.get("sekunden"),
            "getroffen": bil.get("getroffen"), "am_kupfer_max": bil.get("am_kupfer_max"),
        })
    return out


def load_saved_run(project_dir, rid):
    d = os.path.join(_runs_root(project_dir), rid)
    rp = os.path.join(d, "run.json")
    if not os.path.exists(rp):
        return None
    try:
        with open(rp) as f:
            run = json.load(f)
    except (OSError, ValueError):
        return None
    images = {}
    for key, rel in (run.get("image_files") or {}).items():
        p = os.path.join(d, rel)
        if os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    images[key] = base64.b64encode(f.read()).decode()
            except OSError:
                pass
    out = dict(run)
    out["images"] = images
    out["video"] = bool(run.get("video")) and os.path.exists(os.path.join(d, "anim.mp4"))
    return out


def saved_run_video(project_dir, rid):
    p = os.path.join(_runs_root(project_dir), rid, "anim.mp4")
    return p if os.path.exists(p) else None


def delete_saved_run(project_dir, rid, *, bestaetigt=True):
    """Einen gespeicherten Lauf entsorgen — ueber den Papierkorb.

    Ein gespeicherter Lauf ist Stunden bis Tage Rechenzeit samt Video und
    Feld; ``rmtree(ignore_errors=True)`` warf ihn weg und meldete nicht
    einmal, ob es geklappt hat.
    """
    d = os.path.join(_runs_root(project_dir), rid)
    if not os.path.isdir(d):
        return False
    import ema_ablage
    r = ema_ablage.entsorgen(d, "gespeicherter Lauf verworfen",
                             bestaetigt=bestaetigt, project_dir=project_dir)
    return bool(r.get("ok"))
