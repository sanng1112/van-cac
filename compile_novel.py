#!/usr/bin/env python3
"""Compile one book from books/<slug>/chapters into a plain-text edition."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BOOKS_DIR = ROOT / "books"
CHAPTER_PATTERN = re.compile(r"^chap_(\d+)(?:_.+)?\.txt$")


def chapter_number(path: Path) -> int:
    match = CHAPTER_PATTERN.match(path.name)
    if not match:
        raise ValueError(f"Tên tệp chương không hợp lệ: {path.name}")
    return int(match.group(1))


def select_slug(requested_slug: str | None) -> str:
    available = sorted(path.name for path in BOOKS_DIR.iterdir() if path.is_dir())
    if not available:
        raise SystemExit("Chưa có tác phẩm nào trong books/.")
    if requested_slug:
        if requested_slug not in available:
            raise SystemExit(f"Không tìm thấy tác phẩm {requested_slug!r}. Có thể dùng: {', '.join(available)}")
        return requested_slug
    if len(available) == 1:
        return available[0]
    raise SystemExit(f"Hãy chỉ định slug tác phẩm. Có thể dùng: {', '.join(available)}")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def compile_book(slug: str, output: Path | None) -> None:
    book_dir = BOOKS_DIR / slug
    metadata = json.loads((book_dir / "book.json").read_text(encoding="utf-8"))
    chapter_dir = book_dir / "chapters"
    files = sorted(chapter_dir.glob("chap_*.txt"), key=chapter_number)
    if not files:
        raise SystemExit(f"Không có chương để gom trong {chapter_dir.relative_to(ROOT)}")

    title = metadata["title"]
    original_title = metadata.get("originalTitle", "")
    author = metadata["author"]
    genres = ", ".join(metadata.get("genres", []))
    header_lines = ["=" * 60, f"TÁC PHẨM: {title.upper()}"]
    if original_title:
        header_lines.append(original_title)
    header_lines.extend([f"TÁC GIẢ: {author.upper()}", f"THỂ LOẠI: {genres.upper()}", "=" * 60, ""])

    toc = ["MỤC LỤC CÁC CHƯƠNG HIỆN CÓ:", ""]
    chapters = []
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            continue
        chapter_title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        toc.append(f"- {chapter_title}")
        chapters.append(f"\n\n{'=' * 50}\n{chapter_title}\n{'=' * 50}\n\n{body}\n")

    output_path = output or ROOT / "compiled" / f"{slug}.txt"
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(header_lines + toc) + "\n" + "".join(chapters), encoding="utf-8")
    status_path = output_path.with_suffix(".status.json")
    status_path.write_text(json.dumps({
        "book": slug,
        "translatedCount": len(files),
        "latestChapter": display_path(files[-1]),
        "compiledFile": display_path(output_path),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Đã gom {len(files)} chương của '{title}' vào {display_path(output_path)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gom các chương của một tác phẩm thành tệp văn bản.")
    parser.add_argument("book", nargs="?", help="Slug tác phẩm trong books/")
    parser.add_argument("--output", type=Path, help="Đường dẫn tệp xuất (mặc định: compiled/<slug>.txt)")
    args = parser.parse_args()
    if not BOOKS_DIR.is_dir():
        raise SystemExit("Không tìm thấy thư mục books/.")
    compile_book(select_slug(args.book), args.output)


if __name__ == "__main__":
    main()
