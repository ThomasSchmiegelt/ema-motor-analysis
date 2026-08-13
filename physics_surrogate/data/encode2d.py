"""Encoder für Stufe 1 — Geometrie/Quelle → Tensor, und zurück.

**Gelernt wird der Löser-Operator, nicht „Geometrie → Feld".** `ema_analysis._solve_fdm`
löst `∇·(ν∇A) = −J` und sieht dabei ausschließlich `mu` und `J` — kein `sc`, kein `geom`,
keine Baulänge. Die minimal vollständige Eingabe ist damit (Material, Quelle); alles
weitere wäre redundant und böte dem Netz nur Scheinkorrelationen an. Insbesondere ist die
**Blechpaketlänge bewusst kein Kanal**: das 2D-Feld ist von ihr unabhängig, sie geht erst
in `compute_performance` ein.

Kanäle (feste Reihenfolge — Training und Inferenz müssen identisch encodieren):

    0  iron      Materialmaske Eisen    (µ = MU_R_IRON)
    1  magnet    Materialmaske Magnet   (µ = MU_R_MAG)
    2  air       Materialmaske Luft     (µ = 1)
    3  J/α       Quellterm, normiert    (α = max|J|)

**Gelernt wird das MUSTER von A, nicht seine Amplitude** (Korrektur vom 31.07.2026, s. u.).
Trainingsziel ist ``A / RMS(A)`` — `pattern()`. Die Amplitude liefert der Orchestrator
selbst, exakt wie beim echten Löser.

Zwei Normierungen, die man auseinanderhalten muss:

* **Ablage** (`encode_target`/`decode_target`, so liegt der Datensatz auf Platte):
  ``A / (α · A_SCALE)`` mit ``α = max|J|``. Das nutzt die Linearität des Lösers — aus
  ``J → J/α`` folgt exakt ``A → A/α``, die Amplitudenstreuung *innerhalb einer Quelle*
  fällt damit exakt heraus. `A_SCALE = 128` ist reine Konditionierung.
* **Trainingsziel** (`pattern`): zusätzlich durch die eigene RMS geteilt.

**Warum die Ablage-Normierung als Trainingsziel nicht reicht (gemessen am Datensatz):**
``A/(α·128)`` spannt über die 10 398 Beispiele einen Faktor **1514** (Magnetquelle
0,06…1,8, Statorquelle 0,7…423). Das ist kein Ablagefehler, sondern Physik: die
Magnetquelle ist eine Dipolschicht auf den Magnetflanken (die Beiträge löschen sich in
der Ferne weitgehend aus), die Statorquelle füllt ganze Nuten kohärent — bei gleichem
``max|J|`` also völlig verschiedene Übertragungsgewinne. Zusätzlich skaliert das
Ankerfeld stark mit der Polzahl (p = 1…22 im Datensatz).
Bei einem sample-relativen Verlust ist der Gradient ∝ ``1/‖t‖``; die kleinen Samples
dominieren um Faktor ~7000 und drücken die Ausgabe global gegen null. Gemessen: das Netz
blieb bei ``rel. L2 = 0,95`` stehen und konnte **nicht einmal 50 Beispiele auswendig
lernen** — genau die Signatur dieser Unwucht.

**Warum das Muster genügt — und die Amplitude gar nicht gebraucht wird:**
`run_em_analysis:1050-1061` skaliert jede Quelle einzeln auf ihren *analytischen*
Luftspalt-Spitzenwert:

    sf_mag = _analytical_Bgap(geom)      / max|Br_magnet|
    sf_arm = _analytical_Barm(geom, |i|) / max|Br_stator|

Die Amplitude, die der Löser liefert, wird dabei **verworfen**; nur das Muster überlebt.
`_build_fv_matrix` sagt dasselbe in seinem eigenen Docstring („A global scale factor …
is irrelevant — the caller calibrates the air-gap peak to the analytical value, so only
the field *pattern* matters"). Das Surrogat muss die Amplitude also weder lernen noch
schätzen; sie kommt aus demselben analytischen Pfad wie heute.

Verworfene Alternativen (gemessen, nicht vermutet): Galerkin-Projektion
``c = ⟨â,J⟩/⟨â,Mâ⟩`` ist mit dem exakten Muster auf 1e-4 genau, aber bei 3 % Formfehler
schon 3…70 % daneben (der Operator verstärkt Rauschen quadratisch). Ein grober
FDM-Vorlauf (N=48…96) engt die Streuung nur auf 67…150× ein, eine
Freiraum-Poisson-Referenz auf 49× — beides zu wenig, beides Rechenzeit für nichts.

**Ein Lastfall braucht keinen i_q/i_d-Kanal.** Er ist die Superposition, die der
Orchestrator ohnehin bildet: Modell einmal auf die Magnetquelle und einmal auf die
Statorquelle anwenden, dann mit `_analytical_Bgap` bzw. `_analytical_Barm` kalibrieren —
exakt der bestehende Ablauf, nur mit vorhergesagtem statt gelöstem A.
"""

import numpy as np

from domain import _add_orchestrator_to_path  # noqa: F401  (setzt sys.path)

import ema_analysis as ea       # noqa: E402

CHANNEL_NAMES = ("iron", "magnet", "air", "J")
N_CHANNELS = len(CHANNEL_NAMES)

# Optionaler fünfter Kanal: die Freiraumlösung (µ ≡ 1) derselben Quelle, s.
# `free_space_field`. An/aus über die Konfiguration, weil er Rechenzeit kostet
# (~9 ms bei N=512) und der Datensatz ihn nicht mit ablegt.
CHANNEL_FREE = "A_free"


def channel_names(free_space: bool = False) -> tuple[str, ...]:
    return CHANNEL_NAMES + ((CHANNEL_FREE,) if free_space else ())

# Feste Konditionierungskonstante, NICHT gefittet — s. Modul-Docstring.
A_SCALE = 128.0

# Materialcodes der kompakten uint8-Ablage im Datensatz.
MAT_AIR, MAT_MAGNET, MAT_IRON = 0, 1, 2


def rasterise(geom: dict, n: int, rotor_angle: float = 0.0,
              iq: float = 0.0, id_: float = 0.0):
    """Material + beide Quellterme in EINEM Durchgang.

    Gibt ``(mat, j_mag, j_stat, maps)`` zurück:
      ``mat``    uint8 (n,n) — MAT_AIR / MAT_MAGNET / MAT_IRON
      ``j_mag``  float32 (n,n) — Quelle der Permanentmagnete (curl M)
      ``j_stat`` float32 (n,n) — Quelle der Statorströme (0, wenn iq=id=0)
      ``maps``   der Maps-Dict von `_rasterise` (für die Rasterprüfung)

    Die Aufspaltung ist dieselbe wie in `run_em_analysis:997-1004`: einmal mit und
    einmal ohne Strom rastern, differenzieren. µ hängt nicht vom Strom ab, beide
    Rasterungen teilen es also.
    """
    mu, j_full, _sc, _ctr, maps = ea._rasterise(
        geom, n, rotor_angle=rotor_angle, iq=iq, id_=id_, maps=True)

    if (abs(iq) + abs(id_)) > 0.1:
        _mu0, j_mag, _s, _c = ea._rasterise(geom, n, rotor_angle=rotor_angle,
                                            iq=0.0, id_=0.0)
        j_stat = j_full - j_mag
    else:
        j_mag = j_full
        j_stat = np.zeros_like(j_full)

    mat = np.full(mu.shape, MAT_AIR, dtype=np.uint8)
    mat[maps["magnet"]] = MAT_MAGNET
    mat[maps["iron"]] = MAT_IRON
    return mat, np.asarray(j_mag, np.float32), np.asarray(j_stat, np.float32), maps


def mu_from_mat(mat: np.ndarray) -> np.ndarray:
    """Materialmaske → µ. Die Umkehrung ist EXAKT (µ nimmt genau drei Werte an), was die
    Behauptung „die drei Masken codieren µ vollständig" prüfbar macht — der
    Datensatzgenerator assertiert das im `--dry-run`."""
    mu = np.ones(mat.shape, dtype=np.float32)
    mu[mat == MAT_MAGNET] = ea.MU_R_MAG
    mu[mat == MAT_IRON] = ea.MU_R_IRON
    return mu


def encode(mat: np.ndarray, j: np.ndarray) -> tuple[np.ndarray, float]:
    """(Material, Quelle) → ``(x[4,n,n] float32, alpha)``.

    ``alpha = max|J|`` ist der Normierungsfaktor; er wird zum Zurückskalieren der
    Vorhersage gebraucht (`decode_target`). Bei einer identisch-null-Quelle (kein Strom)
    ist alpha 0 — dann ist auch das Feld null und der Aufrufer sollte gar nicht erst
    vorhersagen; wir geben 1.0 zurück, damit nichts durch 0 geteilt wird.
    """
    alpha = float(np.max(np.abs(j)))
    x = np.empty((N_CHANNELS, *mat.shape), dtype=np.float32)
    x[0] = (mat == MAT_IRON)
    x[1] = (mat == MAT_MAGNET)
    x[2] = (mat == MAT_AIR)
    x[3] = j / alpha if alpha > 0 else 0.0
    return x, (alpha if alpha > 0 else 1.0)


def encode_target(a: np.ndarray, alpha: float) -> np.ndarray:
    """Rohes A aus `_solve_fdm` → **Ablage**form ``A/(α·A_SCALE)``.

    Das ist die Konvention der NPZ auf Platte, nicht das Trainingsziel — dafür kommt
    `pattern()` obendrauf. Getrennt gehalten, weil `dataset.verify` die Ablage gegen den
    echten Löser nachrechnet und dazu die *unskalierte* Beziehung ``M·a = j/A_SCALE``
    braucht.
    """
    return np.asarray(a, np.float32) / (alpha * A_SCALE)


def decode_target(a_norm: np.ndarray, alpha: float) -> np.ndarray:
    """Umkehrung von `encode_target` — Ablageform → rohes A."""
    return np.asarray(a_norm, np.float32) * (alpha * A_SCALE)


def pattern(a: np.ndarray) -> np.ndarray:
    """**Trainingsziel**: A auf seine eigene RMS normiert.

    Die Amplitude wird bewusst weggeworfen — `run_em_analysis:1050-1061` skaliert jede
    Quelle ohnehin auf ihren analytischen Luftspalt-Spitzenwert
    (`_analytical_Bgap`/`_analytical_Barm`) und verwirft dabei die Amplitude des Lösers.
    Ausführlich im Modul-Docstring; kurz: das Muster ist alles, was die Kette danach
    benutzt, und der Versuch, zusätzlich die Amplitude zu lernen, hat das Training
    nachweislich blockiert (Streuung 1514×).
    """
    a = np.asarray(a, np.float32)
    s = float(a.std())
    return a / s if s > 0 else a


def free_space_field(j: np.ndarray) -> np.ndarray:
    """``(−∇²)⁻¹ j`` mit Dirichlet 0 am Rand — die Lösung für **Luft überall** (µ ≡ 1).

    Optionaler fünfter Eingangskanal (`CHANNEL_FREE`). Nutzen: das gesuchte A ist die
    Lösung einer elliptischen Gleichung, also von der Quelle *global* abhängig; ein
    Faltungsnetz muss diese Fernwirkung sonst mühsam über die Tiefe aufbauen. Dieser
    Kanal liefert sie geschenkt und exakt, sodass das Netz nur noch die Wirkung des
    Eisens (µ = 500, Flussführung) lernen muss — dieselbe Idee wie das Residual-Lernen
    in Stufe 3, nur eine Ebene tiefer.

    Exakt lösbar per Sinustransformation, weil der Operator bei konstantem µ separabel
    ist. Kosten bei N=512 in float32: ~9 ms (gemessen), also im Inferenzbudget.
    """
    from scipy.fft import dstn, idstn
    j = np.asarray(j, np.float32)
    n = j.shape[0]
    k = np.arange(1, n - 1) * np.pi / (n - 1)
    lam = ((2 - 2 * np.cos(k))[:, None] + (2 - 2 * np.cos(k))[None, :]).astype(np.float32)
    out = np.zeros_like(j)
    out[1:-1, 1:-1] = idstn(dstn(j[1:-1, 1:-1], type=1) / lam, type=1)
    s = float(np.abs(out).max())
    return out / s if s > 0 else out


def scale_px_per_mm(geom: dict, n: int) -> float:
    """Rasterskala von `_rasterise:108-110` — px/mm. Hängt nur an `statorOD` und N."""
    return n / (float(geom["statorOD"]) * ea.AIR_DOMAIN_FACTOR)


def ring_radius_px(geom: dict, n: int) -> float:
    """Radius des Auswertekreises von `_sample_airgap`: ``r_si − 1 px`` (`:589`).

    Wird für die differenzierbare Torch-Spiegelung von ``B_r = (1/r)·∂A/∂θ`` gebraucht
    (`train/airgap_torch.py`). Bewusst hier und nicht dort dupliziert: die Formel gehört
    zur Rasterisierung, und eine zweite Kopie würde still von ihr abdriften.
    """
    return float(geom["statorID"]) / 2 * scale_px_per_mm(geom, n) - 1.0


def encode_geom(geom: dict, n: int, rotor_angle: float = 0.0,
                iq: float = 0.0, id_: float = 0.0):
    """Bequemer Pfad für den Dienst: Geometrie → beide Eingangstensoren.

    Gibt ``{"magnet": (x, alpha), "stator": (x, alpha) | None, "mat": mat}`` zurück.
    ``stator`` ist None im Leerlauf (keine Statorquelle ⇒ nichts vorherzusagen).
    """
    mat, j_mag, j_stat, _maps = rasterise(geom, n, rotor_angle, iq, id_)
    out = {"mat": mat, "magnet": encode(mat, j_mag), "stator": None}
    if float(np.max(np.abs(j_stat))) > 0:
        out["stator"] = encode(mat, j_stat)
    return out
