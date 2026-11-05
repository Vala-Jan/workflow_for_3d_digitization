#!/usr/bin/env python3
"""
dig3d - archiving of 3D digitizations (GOM / ZEISS Scan 1, ZEISS Inspect)

    python dig3d.py          archive the object in input_staging into master
    python dig3d.py verify   check the SHA-256 of all files in master

input_staging must contain exactly one object:
    *.ply    mesh as measured (holes not filled), polygonized in mode "More details"
    *.zixml  the same mesh element exported from ZEISS Inspect (paradata)
    *.json   object metadata (template: tool/config/config.json)

The calibration is taken from tool/config/calibration.json: the newest record dated
on or before the date of scanning. Packages are not versioned: an object that is
already in master is refused until the old package is moved away or deleted.

Requirements: Python 3.9+ and numpy (verify works without numpy).
"""

import hashlib
import json
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

WORKFLOW_VERSION = "1.0.0"  # see "Workflow versions" in README.txt

WORKSPACE = Path(__file__).resolve().parent.parent
STAGING = WORKSPACE / "input_staging"
MASTER = WORKSPACE / "master"
LOGFILE = WORKSPACE / "log" / "dig3d.log"
CALIBRATION_FILE = WORKSPACE / "tool" / "config" / "calibration.json"

# role, input extension, path in the package ({id} = object id)
DATA_FILES = [
    ("mesh", ".ply", "01_MESH/{id}_mesh.ply"),
    ("paradata", ".zixml", "02_PARADATA/{id}_paradata.zixml"),
]
METADATA_FILE = "03_METADATA/{id}_metadata.json"
METADATA_PATTERN = "03_METADATA/*_metadata.json"

# sections of config.json copied into metadata.json, in this order
CONFIG_SECTIONS = ["cultural_heritage_object", "digitization", "calibration"]
REQUIRED = [
    ("cultural_heritage_object", "title"),
    ("cultural_heritage_object", "inventory_number"),
    ("cultural_heritage_object", "institution_owner"),
    ("digitization", "date"),
    ("digitization", "operator_name"),
]
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# the only accepted polygonization mode: as ZEISS Inspect writes it -> as stored in metadata
ALLOWED_MODES = {"Více detailů": "More details", "More details": "More details"}


class PipelineError(Exception):
    pass


# ================================================================ helpers

def log(text):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}"
    print(line)
    LOGFILE.parent.mkdir(parents=True, exist_ok=True)
    with LOGFILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def sha256(file_path):
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(file_path, encoding="utf-8"):
    try:
        return json.loads(Path(file_path).read_text(encoding=encoding))
    except ValueError as e:
        raise PipelineError(f"{Path(file_path).name} is not valid JSON: {e}")


def write_json(file_path, data):
    Path(file_path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")


def find_metadata(package):
    """Metadata file of a package folder, or None."""
    found = list(package.glob(METADATA_PATTERN))
    return found[0] if len(found) == 1 else None


# ================================================================ 1. input

def load_staging():
    """Return the three input files and the object config (with the right calibration)."""
    names = [p for p in STAGING.iterdir() if p.is_file() and not p.name.startswith(".")]
    files = {}
    for role, ext in [(r, e) for r, e, _ in DATA_FILES] + [("config", ".json")]:
        found = [p for p in names if p.suffix.lower() == ext]
        if len(found) != 1:
            raise PipelineError(f"input_staging must contain exactly one {ext} file "
                                f"(found {len(found)})")
        files[role] = found[0]

    config = read_json(files["config"], encoding="utf-8-sig")
    for section in ("cultural_heritage_object", "digitization"):
        if not isinstance(config.get(section), dict):
            raise PipelineError(f"config.json: '{section}' must be a section {{...}}")
    oid = str(config.get("id") or "").strip()
    missing = [] if oid else ["id"]
    for section, key in REQUIRED:
        value = str(config[section].get(key) or "").strip()
        if not value or value == "YYYY-MM-DD":
            missing.append(f"{section}.{key}")
    if missing:
        raise PipelineError("Missing in config.json: " + ", ".join(missing))
    if not re.match(r"^[A-Za-z0-9_-]+$", oid):
        raise PipelineError(f"id may contain only letters A-Z, digits, '-' and '_' (got '{oid}')")
    scan_date = str(config["digitization"]["date"]).strip()
    if not DATE.match(scan_date):
        raise PipelineError(f"digitization.date must be YYYY-MM-DD (got '{scan_date}')")

    if "calibration" in config:
        log("Note: calibration in config.json is ignored, tool/config/calibration.json is used")
    config["id"] = oid
    config["calibration"] = calibration_for(scan_date)
    return files, config


def calibration_for(scan_date):
    """The newest calibration dated on or before the date of scanning."""
    if not CALIBRATION_FILE.is_file():
        raise PipelineError("tool/config/calibration.json is missing")
    records = read_json(CALIBRATION_FILE)
    if isinstance(records, dict):
        records = [records]
    valid = [r for r in records if DATE.match(str(r.get("date", ""))) and r["date"] <= scan_date]
    if not valid:
        raise PipelineError("No calibration in tool/config/calibration.json is dated on or "
                            f"before the date of scanning ({scan_date})")
    return max(valid, key=lambda r: r["date"])


def check_inventory_number(inventory_number):
    """Refuse an inventory number that is already archived."""
    wanted = inventory_number.strip().lower()
    for meta_path in MASTER.glob("*/" + METADATA_PATTERN):
        meta = read_json(meta_path)
        other = str(meta.get("cultural_heritage_object", {}).get("inventory_number", ""))
        if other.strip().lower() == wanted:
            raise PipelineError(f"Inventory number '{inventory_number}' is already archived "
                                f"under id '{meta['id']}'.")


# ================================================================ 2. mesh

PLY_TYPES = {"char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1",
             "short": "i2", "int16": "i2", "ushort": "u2", "uint16": "u2",
             "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4",
             "float": "f4", "float32": "f4", "double": "f8", "float64": "f8"}


def read_ply(ply):
    """Return (format, unit, vertices n x 3, triangles m x 3)."""
    with open(ply, "rb") as f:
        if f.readline().strip() != b"ply":
            raise PipelineError("The .ply file does not start with 'ply'")
        fmt, unit, element, counts, vprops, flist = None, None, None, {}, [], None
        while True:
            raw = f.readline()
            if not raw:
                raise PipelineError("The .ply header has no end_header")
            line = raw.decode("ascii", "replace").strip()
            words = line.split()
            if not words:
                continue
            if words[0] == "end_header":
                break
            if words[0] == "format":
                fmt = words[1]
            elif words[0] == "comment" and "unit" in line.lower():
                unit = line.split(":")[-1].strip()
            elif words[0] == "element":
                element = words[1]
                counts[element] = int(words[2])
            elif words[0] == "property" and element == "vertex":
                vprops.append(words[1])
            elif words[0] == "property" and element == "face" and words[1] == "list":
                flist = (words[2], words[3])
        body = f.read()

    nv, nf = counts.get("vertex", 0), counts.get("face", 0)
    if fmt == "ascii":
        values = np.array(body.split(), dtype=np.float64)
        vertices = values[:nv * len(vprops)].reshape(nv, len(vprops))[:, :3]
        faces = values[nv * len(vprops):]
        if faces.size != nf * 4:
            raise PipelineError("The .ply must contain triangles only")
        return fmt, unit, vertices, faces.reshape(nf, 4)[:, 1:].astype(np.int64)

    order = "<" if fmt == "binary_little_endian" else ">"
    vdt = np.dtype([(f"p{i}", order + PLY_TYPES[t]) for i, t in enumerate(vprops)])
    v = np.frombuffer(body, dtype=vdt, count=nv)
    vertices = np.column_stack([v["p0"], v["p1"], v["p2"]]).astype(np.float64)
    fdt = np.dtype([("n", order + PLY_TYPES[flist[0]]), ("i", order + PLY_TYPES[flist[1]], (3,))])
    faces = np.frombuffer(body, dtype=fdt, count=nf, offset=nv * vdt.itemsize)
    if np.any(faces["n"] != 3):
        raise PipelineError("The .ply must contain triangles only")
    return fmt, unit, vertices, faces["i"].astype(np.int64)


def count_holes(open_edges):
    """A hole is a closed loop of open edges: count connected groups (union-find)."""
    parent = {}

    def root(v):
        while parent.setdefault(v, v) != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for a, b in open_edges:
        parent[root(a)] = root(b)
    return len({root(v) for v in list(parent)})


def mesh_info(ply):
    fmt, unit, vertices, faces = read_ply(ply)
    nv = len(vertices)
    # every edge once, with the number of triangles sharing it
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    unique, shared = np.unique(edges[:, 0] * nv + edges[:, 1], return_counts=True)
    lengths = np.linalg.norm(vertices[unique // nv] - vertices[unique % nv], axis=1)
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    open_keys = unique[shared == 1]
    return {
        "format": f"PLY {fmt}",
        "unit": unit,
        "vertex_count": nv,
        "face_count": len(faces),
        "bounding_box_size": [round(float(x), 3) for x in vertices.max(0) - vertices.min(0)],
        "edge_length": {"min": round(float(lengths.min()), 4),
                        "mean": round(float(lengths.mean()), 4),
                        "max": round(float(lengths.max()), 4)},
        "surface_area": round(float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() / 2), 2),
        "open_edges": int(open_keys.size),
        "holes": count_holes((int(k // nv), int(k % nv)) for k in open_keys),
        "watertight": bool(open_keys.size == 0 and np.all(shared == 2)),
    }


# ================================================================ 3. paradata

def parse_value(text):
    """'0.0015 mm' -> {'value': 0.0015, 'unit': 'mm'}; '4' -> 4; other text unchanged."""
    text = text.strip()
    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*([A-Za-z]+)?$", text)
    if not m:
        return text
    number = float(m.group(1)) if "." in m.group(1) else int(m.group(1))
    return {"value": number, "unit": m.group(2)} if m.group(2) else number


def parse_parameters(text):
    """'a = 1 mm, b = 2' -> {'a': {...}, 'b': 2}"""
    result = {}
    for part in text.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            result[key.strip().replace(" ", "_")] = parse_value(value)
    return result


def paradata_info(zixml):
    info = {"zeiss_inspect_version": None, "unit": None, "polygonization": {},
            "postprocessing": []}
    section = None
    for _, el in ET.iterparse(zixml):
        if el.tag == "version" and info["zeiss_inspect_version"] is None:
            info["zeiss_inspect_version"] = el.text
        elif el.tag == "length_unit":
            info["unit"] = el.text
        elif el.tag == "comment" and el.text:
            for line in el.text.splitlines():
                line = line.strip()
                if line.endswith(":"):
                    section = line[:-1]
                elif section == "BASIC POLYGONISATION" and "=" in line:
                    info["polygonization"].update(parse_parameters(line))
                elif section == "POSTPROCESSING" and line:
                    m = re.match(r"^(\w+)\s*\((.*)\)$", line)
                    if m:
                        info["postprocessing"].append(
                            {"operation": m.group(1), **parse_parameters(m.group(2))})
                    else:
                        info["postprocessing"].append(line)
        el.clear()  # do not keep the base64 geometry in memory

    if not info["polygonization"]:
        raise PipelineError("The .zixml contains no polygonization parameters - export the "
                            "mesh element from ZEISS Inspect, not the measurement series")
    mode = info["polygonization"].get("mode")
    if mode not in ALLOWED_MODES:
        raise PipelineError(f"Polygonization mode is '{mode}' - only 'More details' (Více "
                            "detailů) is allowed. Set the measurement series to 'More "
                            "details', let it recalculate and polygonize again.")
    info["polygonization"]["mode"] = ALLOWED_MODES[mode]
    return info


# ================================================================ 4. archiving

def ingest():
    if np is None:
        raise PipelineError("numpy is not installed - run: py -m pip install numpy")
    files, config = load_staging()
    oid = config["id"]
    log(f"Processing object {oid} (calibration of {config['calibration']['date']})")

    existing = [p for p in MASTER.glob(oid + "_[0-9][0-9][0-9][0-9]") if p.is_dir()]
    if existing:
        raise PipelineError(f"master/{existing[0].name} already exists. Move or delete the old "
                            "package first, then run again.")
    check_inventory_number(str(config["cultural_heritage_object"]["inventory_number"]))
    name = f"{oid}_{config['digitization']['date'][:4]}"

    paradata = paradata_info(files["paradata"])
    mesh = mesh_info(files["mesh"])
    log(f"Mesh: {mesh['vertex_count']} vertices, {mesh['face_count']} faces, "
        f"mean edge {mesh['edge_length']['mean']} mm, {mesh['holes']} holes")
    if mesh["unit"] and paradata["unit"] and mesh["unit"] != paradata["unit"]:
        log(f"WARNING: unit differs between .ply ({mesh['unit']}) and .zixml ({paradata['unit']})")

    targets = [(role, target.format(id=oid)) for role, _, target in DATA_FILES]
    hashes = {target: sha256(files[role]) for role, target in targets}
    metadata = {"id": oid, "workflow_version": WORKFLOW_VERSION}
    metadata.update({key: config[key] for key in CONFIG_SECTIONS})
    metadata["files"] = [{"path": target, "sha256": hashes[target],
                          "size_bytes": files[role].stat().st_size} for role, target in targets]
    metadata["technical"] = {"mesh": mesh, "paradata": paradata}

    # build the package in a temporary folder, check every copy, then publish it at once
    tmp = MASTER / (".tmp_" + name)
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        for role, target in targets:
            (tmp / target).parent.mkdir(parents=True)
            shutil.copy2(files[role], tmp / target)
            if sha256(tmp / target) != hashes[target]:
                raise PipelineError(f"Copy of {target} failed (SHA-256 mismatch)")
        meta_path = tmp / METADATA_FILE.format(id=oid)
        meta_path.parent.mkdir(parents=True)
        write_json(meta_path, metadata)
        tmp.rename(MASTER / name)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    log(f"Done: master/{name}")
    for file_path in files.values():  # remove only the archived input files
        file_path.unlink()
    log("input_staging cleared")


# ================================================================ 5. verification

def verify():
    errors = 0
    packages = sorted(p for p in MASTER.iterdir() if p.is_dir() and not p.name.startswith("."))
    for package in packages:
        meta_path = find_metadata(package)
        if not meta_path:
            errors += 1
            log(f"ERROR: {package.name}: metadata file is missing")
            continue
        for entry in read_json(meta_path)["files"]:
            file_path = package / entry["path"]
            if not file_path.is_file() or sha256(file_path) != entry["sha256"]:
                errors += 1
                log(f"ERROR: {package.name}/{entry['path']} is missing or corrupted")
    log(f"{len(packages)} package(s) checked: " + ("OK" if errors == 0 else f"{errors} error(s)"))
    return errors


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["verify"]:
            sys.exit(1 if verify() else 0)
        ingest()
    except PipelineError as e:
        log(f"ERROR: {e}")
        sys.exit(1)
