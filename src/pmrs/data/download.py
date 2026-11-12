"""Download and safely extract the MovieLens ``ml-latest-small`` dataset.

Only the official GroupLens URL is used. Any redirect is refused (the owner asked to be
consulted before downloading from a different host). Nothing about the user is sent: the
only request header that identifies the client is a generic name.

Run from the project root::

    uv run python -m pmrs.data.download
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import IO, Any

OFFICIAL_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
OFFICIAL_HOST = "files.grouplens.org"
CLIENT_NAME = "pmrs-dataset-fetch"
DATASET_DIR_NAME = "ml-latest-small"
EXPECTED_FILES = ("links.csv", "movies.csv", "ratings.csv", "tags.csv", "README.txt")
# Maximum size we accept (the real archive is about 1 MB).
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
# Counts stated in the official ml-latest-small README (read 2026-11-12).
README_COUNTS = {"ratings": 100_836, "movies": 9_742, "users": 610, "tags": 3_683}


class DownloadError(Exception):
    """Raised when the download or extraction cannot be done safely."""


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """Stop instead of following a redirect to another location."""

    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise DownloadError(f"Server redirected to {newurl!r}; refusing to follow.")


def sha256_of(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_archive(dest: Path, url: str = OFFICIAL_URL) -> Path:
    """Download the archive to file ``dest``; refuse redirects and other hosts."""
    if urllib.parse.urlparse(url).hostname != OFFICIAL_HOST:
        raise DownloadError(f"Only {OFFICIAL_HOST} is allowed, got {url!r}.")
    if dest.exists():
        raise DownloadError(f"{dest} already exists; refusing to overwrite.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(_RefuseRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": CLIENT_NAME})
    try:
        with opener.open(request, timeout=60) as response:
            _copy_limited(response, dest)
    except urllib.error.URLError as error:
        dest.unlink(missing_ok=True)
        raise DownloadError(f"Download failed: {error}") from error
    return dest


def _copy_limited(source: IO[bytes], dest: Path) -> None:
    total = 0
    with dest.open("wb") as out:
        for block in iter(lambda: source.read(64 * 1024), b""):
            total += len(block)
            if total > MAX_ARCHIVE_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise DownloadError("Archive larger than expected; aborting.")
            out.write(block)


def safe_extract(archive: Path, target: Path) -> list[str]:
    """Extract ``archive`` into the new directory ``target``.

    The single top-level folder inside the archive is stripped. Members that are
    absolute, contain ``..``, or are symbolic links are rejected before writing.
    Returns the extracted file names.
    """
    if target.exists():
        raise DownloadError(f"{target} already exists; refusing to extract into it.")
    with zipfile.ZipFile(archive) as bundle:
        plan: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        for info in bundle.infolist():
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts:
                raise DownloadError(f"Unsafe path in archive: {info.filename!r}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise DownloadError(f"Symbolic link in archive: {info.filename!r}")
            if info.is_dir():
                continue
            parts = name.parts[1:] if len(name.parts) > 1 else name.parts
            if not parts:
                raise DownloadError(f"Unexpected archive entry: {info.filename!r}")
            plan.append((info, PurePosixPath(*parts)))
        target.mkdir(parents=True)
        for info, relative in plan:
            out_path = target.joinpath(*relative.parts)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as src, out_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    return sorted(p.name for p in target.iterdir())


def missing_files(directory: Path) -> list[str]:
    """Return expected dataset files that are absent from ``directory``."""
    return [name for name in EXPECTED_FILES if not (directory / name).is_file()]


def main(raw_dir: Path = Path("data/raw")) -> None:
    """Download, extract, verify the file list and print the archive SHA-256."""
    archive = raw_dir / f"{DATASET_DIR_NAME}.zip"
    target = raw_dir / DATASET_DIR_NAME
    download_archive(archive)
    print(f"Downloaded {archive} ({archive.stat().st_size} bytes)")
    print(f"SHA-256: {sha256_of(archive)}")
    names = safe_extract(archive, target)
    print(f"Extracted to {target}: {names}")
    absent = missing_files(target)
    print("Missing expected files:", absent or "none")


if __name__ == "__main__":
    main()
