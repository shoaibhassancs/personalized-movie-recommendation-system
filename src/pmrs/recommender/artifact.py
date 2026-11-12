"""Step 12 artifacts: save and load a fitted ``Recommender``.

An artifact is a folder under ``data/processed/artifacts/`` (git-ignored) holding:

* ``recommender.joblib``: the fitted models;
* ``metadata.json``: readable version information (creation time, seed, data hash, split
  target, library versions, settings) plus the model file's size and SHA-256.

TRUSTED ARTIFACTS ONLY. A ``.joblib`` file is a Python pickle, and loading it can run
any code stored in it. Load only artifacts this project built, kept somewhere only you
can write. Never load one that came from a download, an email or an upload. The SHA-256
check catches accidental damage and mix-ups (a changed byte, a cut-off file, files from
two different builds); it cannot make an untrusted file safe, because anyone who can
replace the model file can also replace ``metadata.json``.

Saving never overwrites an existing artifact folder.
"""

import hashlib
import importlib
import json
import warnings
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pmrs.recommender.recommender import (
    SCHEMA_VERSION,
    TRUSTED_ARTIFACT_WARNING,
    ArtifactMetadata,
    Recommender,
    library_versions,
)

DEFAULT_ARTIFACTS_DIR = Path("data/processed/artifacts")
MODEL_FILE = "recommender.joblib"
METADATA_FILE = "metadata.json"
DATA_FILES = ("ratings.csv", "movies.csv", "tags.csv")


class ArtifactError(Exception):
    """The artifact is missing, damaged or from an incompatible build."""


def _joblib() -> Any:
    # joblib ships no type information; importing it dynamically keeps strict mypy
    # honest without a config override. Only dump/load are used.
    return importlib.import_module("joblib")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def data_fingerprint(raw_dir: Path) -> str:
    """One SHA-256 over the three MovieLens CSVs the models are built from."""
    digest = hashlib.sha256()
    for name in DATA_FILES:
        digest.update(f"{name}:{sha256_of(raw_dir / name)}\n".encode())
    return digest.hexdigest()


def save_recommender(recommender: Recommender, directory: Path) -> Path:
    """Write the model and its metadata to a new folder; refuses to overwrite."""
    if directory.exists():
        raise ArtifactError(
            f"{directory} already exists; artifacts are never overwritten"
        )
    directory.mkdir(parents=True)
    model_path = directory / MODEL_FILE
    _joblib().dump(recommender, model_path, compress=3)
    record = {
        **asdict(recommender.metadata),
        "model_file": MODEL_FILE,
        "model_bytes": model_path.stat().st_size,
        "model_sha256": sha256_of(model_path),
    }
    (directory / METADATA_FILE).write_text(json.dumps(record, indent=2, sort_keys=True))
    return directory


def read_metadata(directory: Path) -> dict[str, Any]:
    path = directory / METADATA_FILE
    if not path.is_file():
        raise ArtifactError(f"no {METADATA_FILE} in {directory}")
    record = json.loads(path.read_text())
    if not isinstance(record, dict):
        raise ArtifactError(f"{path} is not a metadata record")
    return record


def load_recommender(directory: Path) -> Recommender:
    """Load a trusted artifact after checking its size, SHA-256 and version.

    WARNING: this unpickles the model file and can run arbitrary code. Only call it on
    artifacts this project built. See the module note.
    """
    record = read_metadata(directory)
    model_path = directory / str(record.get("model_file", MODEL_FILE))
    if not model_path.is_file():
        raise ArtifactError(f"missing model file {model_path}")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ArtifactError(
            f"artifact schema {record.get('schema_version')} is not {SCHEMA_VERSION}"
        )
    if model_path.stat().st_size != record.get("model_bytes"):
        raise ArtifactError("model file size differs from its metadata (damaged?)")
    if sha256_of(model_path) != record.get("model_sha256"):
        raise ArtifactError("model file SHA-256 differs from its metadata (damaged?)")
    saved = record.get("libraries", {})
    now = library_versions()
    changed = {k: (saved.get(k), v) for k, v in now.items() if saved.get(k) != v}
    if changed:
        warnings.warn(
            f"library versions differ from the build (saved, now): {changed}",
            stacklevel=2,
        )
    loaded = _joblib().load(model_path)
    if not isinstance(loaded, Recommender):
        raise ArtifactError("the model file does not hold a Recommender")
    expected = {f: record.get(f) for f in asdict(loaded.metadata)}
    if expected != asdict(loaded.metadata):
        raise ArtifactError("metadata.json does not match the model file")
    return loaded


__all__ = [
    "DEFAULT_ARTIFACTS_DIR",
    "TRUSTED_ARTIFACT_WARNING",
    "ArtifactError",
    "ArtifactMetadata",
    "data_fingerprint",
    "load_recommender",
    "read_metadata",
    "save_recommender",
    "sha256_of",
]
