#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LinkedIn Rich Media Downloader
==============================

Reads LinkedIn's Rich_Media.csv and downloads all reachable files referenced
in the "Media Link" column to a local directory.

Features:
- downloads images and videos
- creates stable, traceable filenames
- detects file extensions via Content-Type
- skips files that already exist
- retries temporary failures
- writes a CSV manifest
- calculates SHA-256 for every successfully downloaded file
- never modifies the original CSV

Usage:
    python linkedin_rich_media_download.py "C:\\path\\to\\Rich_Media.csv"

Optional destination:
    python linkedin_rich_media_download.py "C:\\path\\to\\Rich_Media.csv" "C:\\path\\to\\linkedin-rich-media"

Requirement:
    pip install requests
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import mimetypes
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests


CSV_REQUIRED_COLUMNS = {"Date/Time", "Media Description", "Media Link"}

CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "application/octet-stream": ".bin",
}

DATE_RE = re.compile(
    r"^You uploaded a (?P<kind>.+?) on "
    r"(?P<date>[A-Za-z]+ \d{1,2}, \d{4}) at "
    r"(?P<time>\d{1,2}:\d{2} [AP]M) \(GMT\)$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download all media referenced by LinkedIn Rich_Media.csv"
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to LinkedIn Rich_Media.csv",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        type=Path,
        default=None,
        help="Destination directory (default: ./linkedin-rich-media next to CSV)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of retries per file (default: 3)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Pause between downloads in seconds (default: 0.25)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite already existing files",
    )
    return parser.parse_args()


def read_csv_rows(path: Path):
    """
    LinkedIn exports are usually UTF-8. utf-8-sig also tolerates a BOM.
    If decoding fails, cp1252 is tried as a fallback.
    """
    encodings = ("utf-8-sig", "utf-8", "cp1252")
    last_error = None

    for enc in encodings:
        try:
            with path.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = set(reader.fieldnames or [])
                missing = CSV_REQUIRED_COLUMNS - fieldnames
                if missing:
                    raise ValueError(
                        f"Missing required column(s): {', '.join(sorted(missing))}"
                    )
                return list(reader), enc
        except UnicodeDecodeError as exc:
            last_error = exc

    raise RuntimeError(f"Could not decode CSV: {last_error}")


def parse_linkedin_datetime(raw: str) -> tuple[Optional[datetime], str]:
    """
    Example:
    You uploaded a feed photo on September 24, 2026 at 4:00 PM (GMT)
    """
    raw = (raw or "").strip()
    m = DATE_RE.match(raw)
    if not m:
        return None, "media"

    kind = m.group("kind").strip().lower()
    dt = datetime.strptime(
        f"{m.group('date')} {m.group('time')}",
        "%B %d, %Y %I:%M %p",
    ).replace(tzinfo=timezone.utc)

    return dt, kind


def safe_kind(kind: str) -> str:
    kind = re.sub(r"[^a-zA-Z0-9]+", "-", kind.strip().lower())
    return kind.strip("-") or "media"


def extension_from_content_type(content_type: str, url: str) -> str:
    content_type = (content_type or "").split(";", 1)[0].strip().lower()

    if content_type in CONTENT_TYPE_EXTENSIONS:
        return CONTENT_TYPE_EXTENSIONS[content_type]

    guessed = mimetypes.guess_extension(content_type) if content_type else None
    if guessed:
        return guessed

    clean_url = url.split("?", 1)[0]
    suffix = Path(clean_url).suffix.lower()
    if suffix and len(suffix) <= 8:
        return suffix

    return ".bin"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def find_existing(output_dir: Path, stem: str) -> Optional[Path]:
    candidates = sorted(output_dir.glob(stem + ".*"))
    candidates = [p for p in candidates if p.is_file() and not p.name.endswith(".part")]
    return candidates[0] if candidates else None


def download_one(
    session: requests.Session,
    url: str,
    output_dir: Path,
    stem: str,
    timeout: int,
    retries: int,
    overwrite: bool,
) -> dict:
    existing = find_existing(output_dir, stem)
    if existing and not overwrite:
        return {
            "status": "already_exists",
            "local_file": existing.name,
            "content_type": "",
            "http_status": "",
            "sha256": sha256_file(existing),
            "bytes": existing.stat().st_size,
            "error": "",
        }

    last_error = ""
    last_status = ""

    for attempt in range(1, retries + 1):
        temp_path = output_dir / f"{stem}.part"

        try:
            with session.get(
                url,
                stream=True,
                timeout=timeout,
                allow_redirects=True,
            ) as response:
                last_status = response.status_code
                response.raise_for_status()

                content_type = (
                    response.headers.get("Content-Type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )

                if content_type.startswith("text/html"):
                    raise RuntimeError(
                        "Server returned HTML instead of media; URL may have expired."
                    )

                ext = extension_from_content_type(content_type, response.url)
                final_path = output_dir / f"{stem}{ext}"

                if final_path.exists() and not overwrite:
                    return {
                        "status": "already_exists",
                        "local_file": final_path.name,
                        "content_type": content_type,
                        "http_status": response.status_code,
                        "sha256": sha256_file(final_path),
                        "bytes": final_path.stat().st_size,
                        "error": "",
                    }

                h = hashlib.sha256()
                byte_count = 0

                with temp_path.open("wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        h.update(chunk)
                        byte_count += len(chunk)

                if byte_count == 0:
                    raise RuntimeError("Downloaded file is empty.")

                if final_path.exists() and overwrite:
                    final_path.unlink()

                temp_path.replace(final_path)

                return {
                    "status": "downloaded",
                    "local_file": final_path.name,
                    "content_type": content_type,
                    "http_status": response.status_code,
                    "sha256": h.hexdigest(),
                    "bytes": byte_count,
                    "error": "",
                }

        except Exception as exc:
            last_error = str(exc)
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass

            if attempt < retries:
                time.sleep(min(2 ** (attempt - 1), 8))

    return {
        "status": "failed",
        "local_file": "",
        "content_type": "",
        "http_status": last_status,
        "sha256": "",
        "bytes": "",
        "error": last_error,
    }


def main() -> int:
    args = parse_args()

    csv_file = args.csv_file.expanduser().resolve()
    if not csv_file.exists():
        print(f"ERROR: CSV not found: {csv_file}", file=sys.stderr)
        return 2

    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else csv_file.parent / "linkedin-rich-media"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "manifest.csv"

    try:
        rows, encoding = read_csv_rows(csv_file)
    except Exception as exc:
        print(f"ERROR reading CSV: {exc}", file=sys.stderr)
        return 2

    print(f"CSV:       {csv_file}")
    print(f"Encoding:  {encoding}")
    print(f"Rows:      {len(rows)}")
    print(f"Output:    {output_dir}")
    print(f"Manifest:  {manifest_path}")
    print()

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/153.0 Safari/537.36"
        ),
        "Accept": "*/*",
    })

    manifest_fields = [
        "row_number",
        "timestamp_utc",
        "media_type",
        "date_time_raw",
        "media_description",
        "source_url",
        "local_file",
        "content_type",
        "bytes",
        "sha256",
        "status",
        "http_status",
        "error",
    ]

    results = []
    total = len(rows)

    for idx, row in enumerate(rows, start=1):
        raw_dt = (row.get("Date/Time") or "").strip()
        description = row.get("Media Description") or ""
        url = (row.get("Media Link") or "").strip()

        dt, kind = parse_linkedin_datetime(raw_dt)
        kind_slug = safe_kind(kind)

        if dt:
            timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            filename_time = dt.strftime("%Y-%m-%d_%H-%M-%S")
        else:
            timestamp = ""
            filename_time = "unknown-date"

        stem = f"{filename_time}_{kind_slug}_{idx:04d}"

        print(f"[{idx:03d}/{total:03d}] {raw_dt}")

        base = {
            "row_number": idx,
            "timestamp_utc": timestamp,
            "media_type": kind,
            "date_time_raw": raw_dt,
            "media_description": description,
            "source_url": url,
        }

        if not url:
            result = {
                "status": "no_media_link",
                "local_file": "",
                "content_type": "",
                "http_status": "",
                "sha256": "",
                "bytes": "",
                "error": "Media Link is empty.",
            }
            print("            -> no media link")
        else:
            result = download_one(
                session=session,
                url=url,
                output_dir=output_dir,
                stem=stem,
                timeout=args.timeout,
                retries=args.retries,
                overwrite=args.overwrite,
            )
            if result["status"] == "downloaded":
                print(
                    f"            -> {result['local_file']} "
                    f"({result['bytes']} bytes)"
                )
            elif result["status"] == "already_exists":
                print(f"            -> already exists: {result['local_file']}")
            else:
                print(f"            -> FAILED: {result['error']}")

        results.append({**base, **result})

        if args.delay > 0:
            time.sleep(args.delay)

    with manifest_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=manifest_fields)
        writer.writeheader()
        writer.writerows(results)

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print()
    print("Finished.")
    for status in sorted(counts):
        print(f"  {status}: {counts[status]}")
    print(f"Manifest: {manifest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
