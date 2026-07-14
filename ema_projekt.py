"""Projektakte — die eine KI-lesbare Quelle der Wahrheit pro Projekt.

Jedes Projektverzeichnis ``~/cae_projekte/<id>/`` bekommt eine ``project.json``, die
**zuerst** (bei Verzeichnisanlage) angelegt und **laufend** während/nach jedem Lauf
fortgeschrieben wird. Sie bündelt — als *Referenzen*, nicht als schwere Base64-Daten —
alles, was Bericht, Chat, Training, Vergleich und Vorlage brauchen:

    {schema_version, id, label, created, updated,
     status,                 # neu|rechnet|gerechnet|bewertet|berichtet|verworfen
     tags:[], notes:"",      # Status & Tags · Freitext-/Entscheidungsnotizen
     lineage:{parent, origin},          # Abstammung (Vorlage/Klon/Import)
     design:{brief, rationale, source},
     datasheet,              # ema_chat._machine_datasheet (lesbare Spezifikation)
     inputs:{payload},       # eine Kopie des Form-Payloads
     metrics,                # ema_training.build_metrics (flache Kennzahlen)
     assets:{fcstd, step, charts:[{key,title,path}], report},
     evolution:[{ts, action, changed_inputs, key_metrics, note, ref}],
     links:[{id, label, relation, note}],
     rag:{docs:[…]},
     attachments:[{name, added}]}

Entwurfsprinzipien (aus dem Codebase): atomarer JSON-Write (``os.replace``), jeder
Schreibvorgang **soft-fail** (darf nie einen Lauf/Bericht abbrechen), ``setdefault`` für
jeden Schlüssel beim Lesen (Vorwärtskompatibilität), und KEINE parallele Extraktion —
Datenblatt/Kennzahlen/Bilder kommen aus ``ema_chat`` / ``ema_training``.

``load_or_synthesize`` ist das Sicherheitsnetz: fehlt die Akte (Altprojekt), wird sie
in-memory aus ``meta.json`` + ``results.json`` rekonstruiert — keine Pflichtmigration.
"""

from __future__ import annotations

import json
import os
import datetime

MANIFEST_NAME = "project.json"
SCHEMA_VERSION = 1

# Payload-Schlüssel, die im Evolutions-Diff ignoriert werden (zu groß / verrauscht).
_DIFF_SKIP = {"cycle_csv", "customLegs", "customBarriers", "design_label"}

VALID_STATUS = {"neu", "rechnet", "gerechnet", "bewertet", "berichtet", "verworfen"}


# ── helpers ────────────────────────────────────────────────────────────────────

def path_for(project_dir: str) -> str:
    return os.path.join(project_dir, MANIFEST_NAME)


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _empty(pid: str, *, origin: str = "analyse", parent=None, label: str = "") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "id": pid,
        "label": label or pid,
        "created": _now(),
        "updated": _now(),
        "status": "neu",
        "tags": [],
        "notes": "",
        "lineage": {"parent": parent, "origin": origin},
        "design": {"brief": "", "rationale": "", "source": "hand"},
        "datasheet": "",
        "inputs": {"payload": {}},
        "metrics": {},
        "assets": {"fcstd": None, "step": None, "charts": [], "report": None},
        "evolution": [],
        "links": [],
        "rag": {"docs": []},
        "attachments": [],
    }


def _normalize(m: dict, pid: str = "") -> dict:
    """Forward-compatible read: ensure every key exists with the right type."""
    base = _empty(pid or m.get("id", ""))
    for k, v in base.items():
        m.setdefault(k, v)
    # nested dicts
    for sub in ("lineage", "design", "assets", "rag"):
        if not isinstance(m.get(sub), dict):
            m[sub] = base[sub]
        else:
            for kk, vv in base[sub].items():
                m[sub].setdefault(kk, vv)
    if not isinstance(m.get("inputs"), dict):
        m["inputs"] = {"payload": {}}
    m["inputs"].setdefault("payload", {})
    for lst in ("tags", "evolution", "links", "attachments"):
        if not isinstance(m.get(lst), list):
            m[lst] = []
    return m


# ── persistence ────────────────────────────────────────────────────────────────

def _read(project_dir: str) -> dict | None:
    p = path_for(project_dir)
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return _normalize(json.load(f), os.path.basename(project_dir.rstrip("/")))
    except Exception:
        return None


def _write(project_dir: str, manifest: dict) -> bool:
    """Atomic write. Soft-fail (returns False) — never raises into the pipeline."""
    try:
        os.makedirs(project_dir, exist_ok=True)
        manifest["updated"] = _now()
        p = path_for(project_dir)
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def load(project_dir: str) -> dict | None:
    """Read the manifest (normalized) or None if absent/unreadable."""
    return _read(project_dir)


# ── lifecycle ──────────────────────────────────────────────────────────────────

def init(project_dir: str, pid: str, *, origin: str = "analyse",
         parent=None, label: str = "") -> bool:
    """Create a stub manifest at directory-creation time (status 'neu'). Soft-fail.
    If a manifest already exists it is left untouched (idempotent)."""
    if _read(project_dir) is not None:
        return True
    return _write(project_dir, _empty(pid, origin=origin, parent=parent, label=label))


def update(project_dir: str, **patch) -> bool:
    """Shallow-merge a patch into the manifest (creating a synthesized one if needed),
    bump ``updated`` and write atomically. The 'laufend geschrieben' primitive.

    Nested dicts (lineage/design/assets/rag) and the special ``inputs`` key are merged
    one level deep so e.g. ``update(dir, assets={"report": "bericht.pdf"})`` keeps the
    other asset fields. Soft-fail."""
    try:
        m = _read(project_dir) or load_or_synthesize(project_dir, write_back=False)
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(m.get(k), dict):
                m[k].update(v)
            else:
                m[k] = v
        return _write(project_dir, m)
    except Exception:
        return False


# ── assets / metrics / datasheet (reuse existing extractors) ──────────────────

def _build_assets(project_dir: str, results: dict | None) -> dict:
    """Reference (relative path) inventory of the heavy artefacts — never base64."""
    try:
        import ema_training
        pairs = ema_training.IMAGE_PAIRS
    except Exception:
        pairs = []
    charts = []
    for key, rel, title in pairs:
        if os.path.exists(os.path.join(project_dir, rel)):
            charts.append({"key": key, "title": title, "path": rel})
    def _rel(name):
        return name if os.path.exists(os.path.join(project_dir, name)) else None
    # newest report (mirror server._latest_report policy)
    report = None
    best_mt = -1.0
    for cand in ("bericht.pdf", "bericht_agentisch.pdf"):
        fp = os.path.join(project_dir, cand)
        if os.path.exists(fp) and os.path.getmtime(fp) > best_mt:
            best_mt, report = os.path.getmtime(fp), cand
    return {"fcstd": _rel("motor.FCStd"), "step": _rel("motor.step"),
            "charts": charts, "report": report}


def _build_metrics(results: dict | None) -> dict:
    try:
        import ema_training
        return ema_training.build_metrics(results or {})
    except Exception:
        return {}


def _build_datasheet(meta: dict | None) -> str:
    try:
        from ema_chat import _machine_datasheet
        return _machine_datasheet(meta or {})
    except Exception:
        return ""


def sync_assets(project_dir: str, pid: str, results: dict | None,
                meta: dict | None = None) -> bool:
    """Recompute assets + metrics (+ datasheet if meta given) and persist. Soft-fail."""
    patch = {"assets": _build_assets(project_dir, results),
             "metrics": _build_metrics(results)}
    if meta is not None:
        patch["datasheet"] = _build_datasheet(meta)
    return update(project_dir, **patch)


# ── evolution log ──────────────────────────────────────────────────────────────

def _flatten_payload(payload: dict | None) -> dict:
    """One-level flatten so geom.* keys diff individually (drops heavy/noisy keys)."""
    payload = payload or {}
    flat = {}
    for k, v in payload.items():
        if k in _DIFF_SKIP:
            continue
        if k == "geom" and isinstance(v, dict):
            for gk, gv in v.items():
                if gk in _DIFF_SKIP or isinstance(gv, (list, dict)):
                    continue
                flat[f"geom.{gk}"] = gv
        elif isinstance(v, (list, dict)):
            continue
        else:
            flat[k] = v
    return flat


def _payload_diff(old: dict | None, new: dict | None) -> dict:
    """Changed flat keys (new values) of ``new`` vs ``old``. Capped to stay compact."""
    fo, fn = _flatten_payload(old), _flatten_payload(new)
    changed = {}
    for k in set(fo) | set(fn):
        if fo.get(k) != fn.get(k):
            changed[k] = fn.get(k)
    # keep it small — drop if absurdly large
    return {k: v for k, v in list(changed.items())[:60]}


def append_evolution(project_dir: str, entry: dict) -> bool:
    """Append one slim evolution entry (caller supplies the fields). Soft-fail."""
    try:
        m = _read(project_dir) or load_or_synthesize(project_dir, write_back=False)
        e = {"ts": _now(), "action": "", "changed_inputs": {},
             "key_metrics": {}, "note": "", "ref": None}
        e.update(entry or {})
        m["evolution"].append(e)
        return _write(project_dir, m)
    except Exception:
        return False


def record_run(project_dir: str, pid: str, meta: dict, results: dict, *,
               action: str = "analyse", note: str = "", ref=None) -> bool:
    """End-of-run integration: append an evolution entry (diffing inputs vs the
    previously stored payload), refresh datasheet/metrics/assets/design/inputs and set
    status='gerechnet'. THE single call from the pipeline save block. Soft-fail."""
    try:
        m = _read(project_dir) or load_or_synthesize(project_dir, write_back=False)
        new_payload = (meta or {}).get("payload") or {}
        changed = _payload_diff(m.get("inputs", {}).get("payload"), new_payload)
        metrics = _build_metrics(results)
        m["evolution"].append({
            "ts": _now(), "action": action, "changed_inputs": changed,
            "key_metrics": metrics, "note": note or "", "ref": ref,
        })
        m["label"] = (meta or {}).get("label") or m.get("label") or pid
        m["status"] = "gerechnet"
        m["datasheet"] = _build_datasheet(meta)
        m["metrics"] = metrics
        m["inputs"]["payload"] = new_payload
        m["design"] = {
            "brief":     (meta or {}).get("design_brief", "")     or m["design"].get("brief", ""),
            "rationale": (meta or {}).get("design_rationale", "") or m["design"].get("rationale", ""),
            "source":    (meta or {}).get("design_source", "")    or m["design"].get("source", "hand"),
        }
        m["assets"] = _build_assets(project_dir, results)
        return _write(project_dir, m)
    except Exception:
        return False


# ── comparison links (persistent) ─────────────────────────────────────────────

def add_link(project_dir: str, other_id: str, *, label: str = "",
             relation: str = "vergleich", note: str = "") -> bool:
    """Add a one-way link to another project (dedup by id). Soft-fail."""
    try:
        m = _read(project_dir) or load_or_synthesize(project_dir, write_back=False)
        m["links"] = [l for l in m["links"] if l.get("id") != other_id]
        m["links"].append({"id": other_id, "label": label or other_id,
                           "relation": relation, "note": note})
        return _write(project_dir, m)
    except Exception:
        return False


def remove_link(project_dir: str, other_id: str) -> bool:
    try:
        m = _read(project_dir) or load_or_synthesize(project_dir, write_back=False)
        m["links"] = [l for l in m["links"] if l.get("id") != other_id]
        return _write(project_dir, m)
    except Exception:
        return False


def resolved_links(project_dir: str, projects_root: str) -> list[dict]:
    """Links whose target directory still exists (self-healing — drops dead ids)."""
    m = _read(project_dir) or load_or_synthesize(project_dir, write_back=False)
    out = []
    for l in m.get("links", []):
        if os.path.isdir(os.path.join(projects_root, str(l.get("id", "")))):
            out.append(l)
    return out


# ── attachments / rag inventory (filesystem-scan based) ────────────────────────

def scan_attachments(project_dir: str) -> list[dict]:
    d = os.path.join(project_dir, "attachments")
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        fp = os.path.join(d, name)
        if os.path.isfile(fp):
            out.append({"name": name,
                        "added": datetime.datetime.fromtimestamp(
                            os.path.getmtime(fp)).isoformat(timespec="seconds")})
    return out


# ── backward-compatible accessor ──────────────────────────────────────────────

def _read_json(project_dir: str, name: str) -> dict:
    try:
        with open(os.path.join(project_dir, name)) as f:
            return json.load(f)
    except Exception:
        return {}


def load_or_synthesize(project_dir: str, write_back: bool = True) -> dict:
    """Return the manifest, synthesizing one from meta.json + results.json for legacy
    projects (and optionally writing it back). Always returns a normalized dict so all
    consumers can treat old and new projects identically."""
    existing = _read(project_dir)
    if existing is not None:
        return existing

    pid = os.path.basename(project_dir.rstrip("/"))
    meta = _read_json(project_dir, "meta.json")
    results = _read_json(project_dir, "results.json")

    m = _empty(pid, origin="analyse")
    m["label"] = meta.get("label") or pid
    m["created"] = meta.get("created") or m["created"]
    m["status"] = "gerechnet" if results else "neu"
    m["design"] = {"brief": meta.get("design_brief", ""),
                   "rationale": meta.get("design_rationale", ""),
                   "source": meta.get("design_source", "hand")}
    m["datasheet"] = _build_datasheet(meta)
    m["inputs"]["payload"] = meta.get("payload") or {}
    m["metrics"] = _build_metrics(results)
    m["assets"] = _build_assets(project_dir, results)
    m["attachments"] = scan_attachments(project_dir)
    # per-project RAG inventory, if a store already exists
    try:
        rag_idx = _read_json(os.path.join(project_dir, "rag"), "index.json")
        m["rag"]["docs"] = rag_idx.get("documents", []) or []
    except Exception:
        pass

    if write_back:
        _write(project_dir, m)
    return m
