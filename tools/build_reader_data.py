#!/usr/bin/env python3
"""Build the multi-book data consumed by the static reader."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BOOKS_DIR = ROOT / "books"
OUTPUT_DIR = ROOT / "site" / "data"
CHAPTER_PATTERN = re.compile(r"^chap_(\d+)(?:_.+)?\.txt$")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_BOOK_FIELDS = ("title", "author")


def chapter_id(path: Path) -> int:
    match = CHAPTER_PATTERN.match(path.name)
    if not match:
        raise ValueError(f"Tên tệp chương không hợp lệ: {path.name}")
    return int(match.group(1))


def split_chapter(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    if not text:
        raise ValueError(f"Chương trống: {path}")

    title, separator, content = text.partition("\n")
    return title.strip(), content.strip() if separator else ""


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_metadata(book_dir: Path) -> dict[str, object]:
    metadata_path = book_dir / "book.json"
    if not metadata_path.is_file():
        raise SystemExit(f"Thiếu metadata: {metadata_path.relative_to(ROOT)}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Metadata không hợp lệ: {metadata_path}: {error}") from error
    if not isinstance(metadata, dict):
        raise SystemExit(f"Metadata phải là một object: {metadata_path}")
    for field in REQUIRED_BOOK_FIELDS:
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise SystemExit(f"Thiếu trường {field!r} trong {metadata_path}")
    genres = metadata.get("genres", [])
    if not isinstance(genres, list) or not all(isinstance(item, str) for item in genres):
        raise SystemExit(f"Trường 'genres' phải là một mảng chuỗi: {metadata_path}")
    return metadata


def build_book(book_dir: Path) -> dict[str, object]:
    slug = book_dir.name
    if not SLUG_PATTERN.fullmatch(slug):
        raise SystemExit(f"Slug không hợp lệ: {slug}")
    metadata = read_metadata(book_dir)
    source_dir = book_dir / "chapters"
    if not source_dir.is_dir():
        raise SystemExit(f"Không tìm thấy thư mục chương: {source_dir.relative_to(ROOT)}")
    files = sorted(source_dir.glob("chap_*.txt"), key=chapter_id)
    if not files:
        raise SystemExit(f"Không tìm thấy chương nào trong: {source_dir.relative_to(ROOT)}")

    chapter_output_dir = OUTPUT_DIR / "books" / slug / "chapters"
    chapter_output_dir.mkdir(parents=True, exist_ok=True)
    chapters: list[dict[str, object]] = []
    seen_ids: set[int] = set()
    for path in files:
        identifier = chapter_id(path)
        if identifier in seen_ids:
            raise SystemExit(f"Trùng số chương: {identifier}")
        seen_ids.add(identifier)

        title, content = split_chapter(path)
        chapter = {
            "id": identifier,
            "title": title,
            "content": content,
            "characterCount": len(content),
        }
        write_json(chapter_output_dir / f"{identifier:04d}.json", chapter)
        chapters.append(
            {
                "id": identifier,
                "title": title,
                "characterCount": len(content),
            }
        )

    book = {
        "slug": slug, "title": metadata["title"], "originalTitle": metadata.get("originalTitle", ""),
        "author": metadata["author"], "genres": metadata.get("genres", []),
        "description": metadata.get("description", ""), "status": metadata.get("status", "Đang cập nhật"),
    }
    manifest = {
        "book": book,
        "chapterCount": len(chapters),
        "chapters": chapters,
    }
    write_json(OUTPUT_DIR / "books" / slug / "manifest.json", manifest)
    return {**book, "chapterCount": len(chapters)}


def main() -> None:
    if not BOOKS_DIR.is_dir():
        raise SystemExit(f"Không tìm thấy thư mục tác phẩm: {BOOKS_DIR}")
    book_dirs = sorted(path for path in BOOKS_DIR.iterdir() if path.is_dir())
    if not book_dirs:
        raise SystemExit("Chưa có tác phẩm nào trong thư mục books/.")
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    books = [build_book(book_dir) for book_dir in book_dirs]
    write_json(OUTPUT_DIR / "catalog.json", {"libraryTitle": "Văn các", "books": books})
    total_chapters = sum(int(book["chapterCount"]) for book in books)
    print(f"Đã tạo catalog {len(books)} tác phẩm, {total_chapters} chương tại {OUTPUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
