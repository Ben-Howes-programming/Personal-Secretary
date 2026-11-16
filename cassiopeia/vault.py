"""
vault.py
========
Purpose : An organised home for your notes, slides, problem sheets and assessments.
          Files are filed as  vault/<Area>/<Unit>/<Kind>/<file>  and indexed for search.
Location: cassiopeia/vault.py
Used by : cassiopeia/server.py, cassiopeia/brain.py
Note    : The vault folder is ignored by Git. Anything filed under "Assessments" is flagged
          so the assistant applies your assessed-work rule (hints, no final answers).
"""

import re
import time
import zipfile
from pathlib import Path

import config
from database import database as db

AREAS = ["University", "Placements", "Finance", "Projects", "Personal"]
KINDS = ["Notes", "Lecture slides", "Problem sheets", "Assessments", "Past papers", "Feedback", "Other"]
TEXT_TYPES = {".txt", ".md", ".py", ".tex", ".csv", ".json", ".cpp", ".h", ".ipynb"}
MAX_TEXT = 200_000                      # characters of extracted text kept per file

# Words in a file name that point to a kind. First match wins, so order matters.
KIND_HINTS = [("Assessments", r"coursework|assignment|assessment|report|submission"),
              ("Past papers", r"past.?paper|exam"), ("Problem sheets", r"problem|sheet|exercise|tutorial"),
              ("Lecture slides", r"lecture|slides|week.?\d"), ("Feedback", r"feedback|marks?"),
              ("Notes", r"notes?|summary|revision")]


def safe_name(name):
    """Keep letters, digits and a few safe symbols so a file name can never climb out of the vault."""
    name = Path(name or "file").name
    cleaned = re.sub(r"[^A-Za-z0-9._ ()\-]", "_", name).strip(" .")
    return cleaned[:120] or "file"


def suggest(filename, module_names=()):
    """Guess (area, unit, kind) from the file name. You can override all three when uploading."""
    low = filename.lower()
    # "stat mech lecture 4" should match "Statistical mechanics": compare the first four letters of each word
    unit = next((m for m in module_names if m and any(w[:4] in low for w in re.findall(r"[a-z]{4,}", m.lower()))), "")
    code = re.search(r"\b([A-Za-z]{2}\d{5})\b", filename)            # e.g. PH22007
    if not unit and code:
        unit = code.group(1).upper()
    kind = next((k for k, pattern in KIND_HINTS if re.search(pattern, low)), "Notes")
    area = "Placements" if re.search(r"\bcv\b|cover.?letter|placement|application", low) else \
           "Finance" if re.search(r"statement|invoice|isa|tax", low) else "University"
    return area, unit or "General", kind


def extract_text(path):
    """Best-effort plain text for search. Returns '' for types that cannot be read."""
    suffix = path.suffix.lower()
    try:
        if suffix in TEXT_TYPES:
            return path.read_text(errors="ignore")[:MAX_TEXT]
        if suffix == ".pdf":
            from pypdf import PdfReader                 # optional package
            return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)[:MAX_TEXT]
        if suffix == ".docx":                            # a .docx is a zip with the words in one XML file
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("word/document.xml").decode("utf-8", "ignore")
            return re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n"))[:MAX_TEXT]
    except Exception:
        return ""
    return ""


def save(filename, data, area=None, unit=None, kind=None, module_names=()):
    """File an upload and index it. Returns the new index row."""
    name = safe_name(filename)
    guess = suggest(name, module_names)
    area = area if area in AREAS else guess[0]
    kind = kind if kind in KINDS else guess[2]
    unit = safe_name(unit or guess[1])
    folder = Path(config.VAULT_PATH) / area / unit / kind
    folder.mkdir(parents=True, exist_ok=True)
    target, n = folder / name, 1
    while target.exists():                               # never overwrite: add (2), (3), ...
        n += 1
        target = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
    target.write_bytes(data)
    relative = str(target.relative_to(config.VAULT_PATH))
    row_id = db.execute("INSERT INTO cass_vault (path, name, area, unit, kind, size, text, added_ts) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (relative, target.name, area, unit, kind, len(data), extract_text(target), time.time()))
    return get(row_id)


def get(file_id):
    rows = db.query("SELECT id, path, name, area, unit, kind, size, added_ts FROM cass_vault WHERE id = ?", (file_id,))
    return rows[0] if rows else None


def listing():
    return db.query("SELECT id, path, name, area, unit, kind, size, added_ts, length(text) AS text_chars "
                    "FROM cass_vault ORDER BY area, unit, kind, name")


def full_path(row):
    """Absolute path of an indexed file, refusing anything that resolves outside the vault."""
    root = Path(config.VAULT_PATH).resolve()
    path = (root / row["path"]).resolve()
    if root not in path.parents:
        raise ValueError("Path is outside the vault.")
    return path


def search(query, limit=6):
    """Files whose name or text contains every word of the query, with a snippet around the first hit."""
    words = [w for w in re.findall(r"\w+", (query or "").lower()) if len(w) > 1][:6]
    if not words:
        return []
    where = " AND ".join("(lower(text) LIKE ? OR lower(name) LIKE ?)" for _ in words)
    params = [p for w in words for p in (f"%{w}%", f"%{w}%")]
    rows = db.query(f"SELECT id, path, name, area, unit, kind, text FROM cass_vault WHERE {where} LIMIT ?",
                    (*params, limit))
    for row in rows:
        text = row.pop("text") or ""
        at = max(text.lower().find(words[0]), 0)
        row["snippet"] = re.sub(r"\s+", " ", text[max(at - 150, 0):at + 450]).strip()
        row["assessed"] = row["kind"] == "Assessments"
    return rows


def remove(file_id):
    """Take a file out of the index and move it to vault/_removed (nothing is deleted outright)."""
    row = get(file_id)
    if not row:
        return False
    source = full_path(row)
    bin_folder = Path(config.VAULT_PATH) / "_removed"
    bin_folder.mkdir(parents=True, exist_ok=True)
    if source.exists():
        source.rename(bin_folder / f"{int(time.time())}_{source.name}")
    db.execute("DELETE FROM cass_vault WHERE id = ?", (file_id,))
    return True
