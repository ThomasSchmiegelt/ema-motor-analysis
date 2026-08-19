"""Lesen + Prüfen des 2D-Datensatzes (erzeugt von `cae_orchestrator/gen_fdm_dataset.py`).

Ein Datensatzverzeichnis enthält:

    meta.json        Gitter, Basismaschine, Kanalreihenfolge, A_SCALE, Sampling-Box
    manifest.jsonl   eine Zeile je Geometrie (Parameter, α je Quelle, Dateiname)
    rejected.jsonl   verworfene Kandidaten samt Grund (Ausschussanalyse)
    NNNNNN.npz       mat(uint8) · j_magnet/j_stator(float32) · a_magnet/a_stator(float16)

Die **Quelle liegt bewusst in float32**, das Ziel in float16: der Löser verstärkt Rauschen
in der Quelle (die Statorquelle lebt von Auslöschung zwischen benachbarten Nuten), sodass
eine float16-Quelle das Paar (Eingang, Ziel) um bis zu 1,2e-2 inkonsistent machen würde —
ein Drittel des 3-%-Fehlerbudgets. Die Quantisierung des Ziels (~8e-4) wird dagegen nicht
verstärkt. Details im Kommentar in `gen_fdm_dataset._one`.

Je Geometrie stehen **zwei** Trainingsbeispiele darin (Magnetquelle, Statorquelle) — sie
teilen sich das Material, unterscheiden sich in der Quelle.

Das **Trainingsziel ist das Muster** ``A/RMS(A)``, nicht die gespeicherte Ablageform:
`load_sample` normiert beim Laden nach (`encode2d.pattern`). Begründung im Docstring von
`encode2d` — kurz: der Orchestrator kalibriert die Amplitude ohnehin analytisch weg, und
die rohe Ablageform spannt über den Datensatz einen Faktor 1514, an dem das Training
scheitert.

`--verify` löst gespeicherte Samples mit dem echten Löser nach und vergleicht. Das ist
der Test, der zählt: ein stiller Fehler in der Ablage würde sonst erst nach Stunden
Training als „Modell lernt nicht" auffallen.

    python data/dataset.py --root datasets/fdm_512 --verify 5
"""

import argparse
import json
import os
import zipfile

import numpy as np

from domain import _add_orchestrator_to_path  # noqa: F401  (setzt sys.path)

import encode2d                                # noqa: E402
import ema_analysis as ea                      # noqa: E402
import ema_optimize as eo                      # noqa: E402


def geom_of(meta: dict, rec: dict) -> dict:
    """Geometrie eines Records rekonstruieren — **derselbe Pfad wie im Generator**.

    Das Manifest speichert nur die gezogenen Parameter, nicht die fertige Geometrie.
    Statt `statorID = rotorOD + 2·airgap` hier nachzubauen (und damit eine zweite,
    still driftende Kopie von `_apply_params` zu schaffen), wird die Originalfunktion
    aufgerufen.
    """
    geom, _axial = eo._apply_params(meta["base_geom"], meta["base_axial"], rec["params"])
    geom["magShape"] = rec["magShape"]
    return geom


def ring_radius(meta: dict, rec: dict) -> float:
    """Radius des Luftspalt-Auswertekreises in Pixeln (für den ``B_r``-Verlustterm)."""
    return encode2d.ring_radius_px(geom_of(meta, rec), int(meta["grid"]))


def read_meta(root: str) -> dict:
    with open(os.path.join(root, "meta.json")) as f:
        return json.load(f)


def read_manifest(root: str) -> list[dict]:
    recs = []
    with open(os.path.join(root, "manifest.jsonl")) as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def load_sample(root: str, rec: dict, source: str, pattern: bool = True,
                free_space: bool = False):
    """Ein Trainingsbeispiel laden → ``(x[4,n,n] float32, y[n,n] float32)``.

    `source` ist "magnet" oder "stator". Die Kanäle werden hier aus `mat` + der bereits
    normierten Quelle zusammengesetzt — dieselbe Reihenfolge wie `encode2d.encode`.

    ``pattern=True`` (Vorgabe) liefert das **Trainingsziel** ``A/RMS(A)``; die Amplitude
    stammt später aus der analytischen Kalibrierung des Orchestrators, s.
    `encode2d.pattern`. Mit ``pattern=False`` kommt die rohe Ablageform ``A/(α·A_SCALE)``
    — die braucht nur `verify`, das gegen den Löser nachrechnet.
    """
    with np.load(os.path.join(root, rec["file"])) as z:
        mat = z["mat"]
        j_n = z[f"j_{source}"].astype(np.float32)
        y = z[f"a_{source}"].astype(np.float32)
    if pattern:
        y = encode2d.pattern(y)
    nch = encode2d.N_CHANNELS + int(free_space)
    x = np.empty((nch, *mat.shape), dtype=np.float32)
    x[0] = (mat == encode2d.MAT_IRON)
    x[1] = (mat == encode2d.MAT_MAGNET)
    x[2] = (mat == encode2d.MAT_AIR)
    x[3] = j_n
    if free_space:
        x[4] = encode2d.free_space_field(j_n)
    return x, y


def split_by_geometry(recs: list[dict], val_frac: float = 0.2, seed: int = 0):
    """80/20-Aufteilung **nach Geometrie**, nicht nach Sample.

    Magnet- und Statorquelle derselben Geometrie teilen das Material; landete eines im
    Training und das andere in der Validierung, wäre die Validierung geschönt.
    """
    idx = np.arange(len(recs))
    np.random.default_rng(seed).shuffle(idx)
    cut = int(round(len(recs) * (1.0 - val_frac)))
    return [recs[i] for i in idx[:cut]], [recs[i] for i in idx[cut:]]


def verify(root: str, k: int = 5, rtol: float = 2e-3, seed: int = 0) -> None:
    """Gespeicherte Ziele gegen den echten Löser nachrechnen.

    Trick ohne α: gespeichert sind ``j_n = J/α`` und ``a_n = A/(α·A_SCALE)``. Weil der
    Löser linear in der Quelle ist, gilt ``_solve_fdm(µ, j_n) = A/α``, also muss
    ``_solve_fdm(µ, j_n)/A_SCALE`` genau ``a_n`` sein — unabhängig von α.
    """
    meta = read_meta(root)
    recs = read_manifest(root)
    if not recs:
        raise SystemExit(f"{root}: leeres Manifest")
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(recs), size=min(k, len(recs)), replace=False)

    print(f"Verifikation gegen den Löser — {root}")
    print(f"  {len(recs)} Geometrien, N={meta['grid']}, A_SCALE={meta['a_scale']}\n")
    worst = 0.0
    for i in picks:
        rec = recs[int(i)]
        with np.load(os.path.join(root, rec["file"])) as z:
            mat = z["mat"]
            mu = encode2d.mu_from_mat(mat)
            for src in ("magnet", "stator"):
                j_n = z[f"j_{src}"].astype(np.float32)
                a_ref = z[f"a_{src}"].astype(np.float32)
                if np.max(np.abs(j_n)) == 0:
                    continue                      # keine Quelle (Leerlauf-Statoranteil)
                try:
                    a_got = ea._solve_fdm(mu, j_n) / meta["a_scale"]
                finally:
                    ea.clear_lu_cache()
                scale = max(float(np.max(np.abs(a_ref))), 1e-12)
                err = float(np.max(np.abs(a_got - a_ref))) / scale
                worst = max(worst, err)
                status = "✓" if err < rtol else "✗"
                print(f"  {status} {rec['file']} [{src:6s}] max. rel. Abweichung {err:.2e}")
                assert err < rtol, (
                    f"{rec['file']}/{src}: gespeichertes Ziel weicht um {err:.2e} vom "
                    f"nachgerechneten ab (Grenze {rtol:.0e}) — Ablage ist fehlerhaft")
    print(f"\n✓ {len(picks)} Geometrien nachgerechnet, schlechtester Fehler {worst:.2e} "
          f"(float16-Ablage erlaubt ~1e-3)")


def check(root: str, prune: bool = False) -> list[str]:
    """CRC-32 jeder NPZ prüfen; mit `prune` beschädigte aus dem Manifest entfernen.

    Warum das nötig ist: eine NPZ ist ein ZIP, und ein einzelnes gekipptes Byte fällt
    erst auf, wenn der Trainingsloop nach Stunden zufällig dieses Sample zieht und mit
    `BadZipFile` abbricht. Gefunden am 31.07.2026: 1 von 5199 Dateien im Datensatz
    `fdm_512` war beschädigt (`004418.npz`, `a_magnet.npy`).
    """
    import shutil
    import zipfile

    recs = read_manifest(root)
    bad = []
    for i, rec in enumerate(recs):
        path = os.path.join(root, rec["file"])
        try:
            with zipfile.ZipFile(path) as z:
                if z.testzip() is not None:
                    bad.append(rec["file"])
        except (OSError, zipfile.BadZipFile) as exc:
            bad.append(rec["file"])
            print(f"  {rec['file']}: {exc}")
        if i and i % 1000 == 0:
            print(f"  {i}/{len(recs)} …", flush=True)

    print(f"{len(recs)} Dateien geprüft, {len(bad)} beschädigt")
    for f in bad:
        print(f"   ✗ {f}")
    if bad and prune:
        man = os.path.join(root, "manifest.jsonl")
        shutil.copy2(man, man + ".bak")
        keep = [r for r in recs if r["file"] not in set(bad)]
        with open(man, "w") as f:
            for r in keep:
                f.write(json.dumps(r) + "\n")
        for f_ in bad:
            os.rename(os.path.join(root, f_), os.path.join(root, f_ + ".corrupt"))
        print(f"→ {len(bad)} Einträge entfernt ({len(keep)} bleiben), "
              f"Manifest gesichert als manifest.jsonl.bak")
    elif bad:
        print("→ mit --prune aus dem Manifest entfernen")
    return bad


def summary(root: str) -> None:
    """Kurzbericht: Umfang, Topologien, Ausschussgründe, Größe."""
    import collections
    meta = read_meta(root)
    recs = read_manifest(root)
    shapes = collections.Counter(r.get("magShape", "?") for r in recs)
    size = sum(os.path.getsize(os.path.join(root, f))
               for f in os.listdir(root) if f.endswith(".npz"))
    print(f"{root}")
    print(f"  {len(recs)} Geometrien → {2 * len(recs)} Trainingsbeispiele, "
          f"N={meta['grid']}, {size / 1e9:.2f} GB")
    print(f"  Topologien: {dict(shapes)}")
    rej_path = os.path.join(root, "rejected.jsonl")
    if os.path.exists(rej_path):
        reasons = collections.Counter()
        n_rej = 0
        with open(rej_path) as f:
            for line in f:
                n_rej += 1
                reasons[json.loads(line)["reason"].split("—")[0].strip()[:60]] += 1
        print(f"  {n_rej} verworfen ({n_rej / max(1, n_rej + len(recs)):.0%} Ausschuss):")
        for reason, cnt in reasons.most_common(5):
            print(f"     {cnt:5d}  {reason}")
    p = [r["params"] for r in recs if "params" in r]
    if p:
        print("  Parameterspanne:")
        for key in sorted(p[0]):
            vals = [x[key] for x in p]
            print(f"     {key:12s} {min(vals):8.3g} … {max(vals):8.3g}")


def torch_dataset(root: str, recs: list[dict], meta: dict | None = None,
                  free_space: bool = False):
    """Torch-Dataset über die Beispiele (Import lokal — der Erzeuger hat kein Torch).

    Liefert ``(x[4,N,N], y[1,N,N], r_ev)``. Der Ringradius kommt mit, weil er je nach
    Luftspalt zwischen den Samples schwankt (`statorID = rotorOD + 2·airgap`) und der
    ``B_r``-Verlustterm ihn pro Sample braucht.
    """
    import torch

    meta = meta or read_meta(root)

    class _Ds(torch.utils.data.Dataset):
        def __init__(self, root, recs):
            self.root = root
            # Ein Eintrag je (Geometrie, Quelle); Statorquelle nur wenn vorhanden.
            self.items = []
            for r in recs:
                r_ev = ring_radius(meta, r)
                self.items.append((r, "magnet", r_ev))
                if float(r.get("alpha_stator", 0)) > 0:
                    self.items.append((r, "stator", r_ev))

        def __len__(self):
            return len(self.items)

        def __getitem__(self, i):
            rec, src, r_ev = self.items[i]
            try:
                x, y = load_sample(self.root, rec, src, free_space=free_space)
            except (zipfile.BadZipFile, OSError, ValueError) as e:
                # Stiller Bitzerfall im Datensatz — bisher zweimal beobachtet
                # (004418.npz am 31.07., 002733.npz am 11.08.2026), beide Male mit
                # unveränderter mtime und ohne ext4-Fehler, also nichts, was das
                # Dateisystem bemerkt. Ein 12-Stunden-Lauf darf daran nicht sterben:
                # ein Beispiel von 8316 auszulassen verzerrt nichts Messbares, ein
                # abgestürzter Lauf kostet Stunden. Der Dateiname wird laut gemeldet,
                # damit er gezielt neu erzeugt werden kann (Manifest trägt alle
                # Parameter, s. `dataset.py --check`).
                print(f"\n  ⚠ {rec['file']} ({src}) nicht lesbar: "
                      f"{type(e).__name__}: {e}\n"
                      f"    Beispiel wird übersprungen. Danach:  "
                      f"dataset.py --check\n", flush=True)
                j = (i + 1) % len(self.items)          # Nachbarbeispiel als Ersatz
                rec, src, r_ev = self.items[j]
                x, y = load_sample(self.root, rec, src, free_space=free_space)
            return (torch.from_numpy(x), torch.from_numpy(y[None]),
                    torch.tensor(r_ev, dtype=torch.float32))

    return _Ds(root, recs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "datasets", "fdm_512"))
    ap.add_argument("--verify", type=int, default=0, metavar="K",
                    help="K zufällige Geometrien gegen den Löser nachrechnen")
    ap.add_argument("--check", action="store_true",
                    help="CRC-32 aller NPZ prüfen (Ablage-Integrität)")
    ap.add_argument("--prune", action="store_true",
                    help="mit --check: beschädigte Dateien aus dem Manifest entfernen")
    args = ap.parse_args()
    root = os.path.normpath(args.root)
    if args.check:
        check(root, args.prune)
        print()
    summary(root)
    if args.verify:
        print()
        verify(root, args.verify)
