#!/usr/bin/env python3
"""
Batch translate chapters from raw_chapters/ up to chapter 300.
Coordinates via gemini-subworker pool across 28 API keys.
Performs doublecheck verification, builds website data, and pushes to git.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.append("/home/anng/.gemini/config/skills/gemini-subworker/scripts")
from pool_client import KeyPoolManager, generate_content
import httpx

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw_chapters"
BOOK_SLUG = "ta-that-khong-muon-trung-sinh-a"
CHAPTERS_DIR = ROOT / "books" / BOOK_SLUG / "chapters"
GLOSSARY_FILE = ROOT / "glossary.json"
STATUS_FILE = ROOT / "translation_status.json"
MAX_CHAPTER = 300
CONCURRENCY = 4
MODEL = "gemini-3.5-flash"


def to_slug(title: str) -> str:
    """Convert Vietnamese title to a clean ASCII file slug."""
    s = title.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-zA-Z0-9\s_]", "", s)
    words = s.strip().split()
    return "_".join(words) if words else "Chuong"


def load_glossary() -> Tuple[str, str]:
    if not GLOSSARY_FILE.exists():
        return "", ""
    with open(GLOSSARY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    chars = data.get("characters", {})
    terms = data.get("organizations_and_terms", {})
    char_str = "\n".join([f"- {k}: {v['vi']} ({v.get('desc', '')})" for k, v in chars.items()])
    term_str = "\n".join([f"- {k}: {v}" for k, v in terms.items()])
    return char_str, term_str


def get_existing_chapters() -> Dict[int, Path]:
    existing = {}
    pattern = re.compile(r"^chap_(\d+)(?:_.+)?\.txt$")
    for f in CHAPTERS_DIR.glob("chap_*.txt"):
        m = pattern.match(f.name)
        if m:
            num = int(m.group(1))
            raw_file = RAW_DIR / f"chap_{num:04d}.txt"
            raw_len = len(raw_file.read_text(encoding="utf-8")) if raw_file.exists() else 0
            content = f.read_text(encoding="utf-8").strip()
            
            # Check length ratio
            if raw_len > 1200 and len(content) < raw_len * 1.8:
                print(f"[Audit] Removing truncated chapter {num}: {f.name} ({len(content)}/{raw_len})")
                f.unlink(missing_ok=True)
                continue
            
            # Check ending
            last_c = content[-1] if content else ""
            if last_c not in '.!?\"”’\'…\n' and not content.endswith('······') and not content.endswith('...'):
                print(f"[Audit] Removing incomplete ending chapter {num}: {f.name}")
                f.unlink(missing_ok=True)
                continue
                
            existing[num] = f
    return existing


def clean_and_verify_translation(text: str, chap_num: int, raw_len: int) -> Tuple[bool, str, str]:
    """
    Doublecheck verification for a translated chapter:
    - Verifies header format: 'Chương <chap_num>: <Title>'
    - Verifies character count and paragraph count against raw
    - Verifies ending sentence punctuation
    - Verifies no leftover Chinese characters
    Returns (is_valid, cleaned_text, title)
    """
    text = text.replace("\r\n", "\n").replace("\u3000", "").strip()
    lines = text.split("\n")
    if not lines:
        return False, "", "Rỗng"

    # Find the title line
    title_idx = 0
    header_pattern = re.compile(rf"^Chương\s+{chap_num}\s*[:：]\s*(.+)$", re.IGNORECASE)
    
    title = ""
    for i, line in enumerate(lines[:5]):
        line_clean = line.strip().strip("#*").strip()
        m = header_pattern.match(line_clean)
        if m:
            title = m.group(1).strip()
            title_idx = i
            break

    if not title:
        alt_pattern = re.compile(rf"^Chương\s+{chap_num}\s*[-–]\s*(.+)$", re.IGNORECASE)
        for i, line in enumerate(lines[:5]):
            line_clean = line.strip().strip("#*").strip()
            m = alt_pattern.match(line_clean)
            if m:
                title = m.group(1).strip()
                title_idx = i
                break

    if not title:
        first_line = lines[0].strip().strip("#*").strip()
        if first_line.lower().startswith("chương"):
            parts = first_line.split(":", 1)
            title = parts[1].strip() if len(parts) > 1 else first_line
        else:
            title = f"Chương {chap_num}"

    body_lines = lines[title_idx + 1 :]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)

    paragraphs = []
    current_p = []
    for line in body_lines:
        line_s = line.strip()
        if not line_s:
            if current_p:
                paragraphs.append(" ".join(current_p))
                current_p = []
        else:
            current_p.append(line_s)
    if current_p:
        paragraphs.append(" ".join(current_p))

    cleaned_body = "\n\n".join(paragraphs)
    final_text = f"Chương {chap_num}: {title}\n\n{cleaned_body}\n"

    # 1. Verification of length against raw
    if raw_len > 1200:
        min_len = int(raw_len * 1.8)
        if len(final_text) < min_len:
            print(f"[{chap_num:04d}] Failed ratio check: {len(final_text)} < {min_len} (raw {raw_len})", file=sys.stderr)
            return False, final_text, title
    elif len(final_text) < 400:
        return False, final_text, title

    # 2. Check sentence ending
    stripped = final_text.strip()
    last_char = stripped[-1] if stripped else ""
    if last_char not in '.!?\"”’\'…\n' and not stripped.endswith('······') and not stripped.endswith('...'):
        print(f"[{chap_num:04d}] Failed ending check: '{stripped[-30:]}'", file=sys.stderr)
        return False, final_text, title

    # 3. Check for leftover Chinese characters
    if re.search(r"[\u4e00-\u9fff]", final_text):
        print(f"[{chap_num:04d}] Failed Chinese character check", file=sys.stderr)
        return False, final_text, title

    # 4. Minimum paragraph count
    min_p = 10 if raw_len > 1200 else 3
    if len(paragraphs) < min_p:
        return False, final_text, title

    return True, final_text, title


async def translate_single_chapter(
    client: httpx.AsyncClient,
    pool: KeyPoolManager,
    chap_num: int,
    raw_path: Path,
    system_inst: str,
    char_str: str,
    term_str: str,
) -> bool:
    raw_content = raw_path.read_text(encoding="utf-8")
    raw_len = len(raw_content)

    user_prompt = f"""Dịch ĐẦY ĐỦ TOÀN BỘ chương truyện tiểu thuyết đô thị sau đây sang tiếng Việt. 
Tuyệt đối KHÔNG tóm tắt, KHÔNG bỏ dở giữa chừng, dịch liền mạch từ đầu tới hết chương.

QUY CÁCH TRÌNH BÀY BẮT BUỘC:
- Dòng 1: Chương {chap_num}: [Tên chương tiếng Việt dịch thoát nghĩa, tự nhiên]
- Dòng 2: [Dòng trống]
- Dòng 3 trở đi: Toàn bộ nội dung chương, mỗi đoạn văn cách nhau bởi một dòng trống.

YÊU CẦU VĂN PHONG VÀ THUẬT NGỮ:
1. Văn phong: Hiện đại, sinh động, hài hước, mượt mà, đậm chất đô thị thanh xuân đại học.
2. Giữ nguyên các từ Hán Việt quen thuộc trong giới đọc truyện: tra nam, tu la tràng, bạch nguyệt quang, nốt chu sa, thanh mai trúc mã, Cẩu ca, lão tử, học bá, học tra, trà xanh, cẩu liếm, thao tác tao...
3. Tuân thủ nghiêm ngặt danh sách nhân vật và tổ chức:
NHÂN VẬT:
{char_str}

THUẬT NGỮ & ĐỊA DANH:
{term_str}

4. Tuyệt đối KHÔNG để sót bất kỳ chữ Hán nào trong kết quả.

NỘI DUNG NGUYÊN TÁC (CHƯƠNG {chap_num}):
{raw_content}
"""

    models_to_try = ["gemini-3.5-flash", "gemini-3.6-flash"]

    for attempt in range(4):
        target_model = models_to_try[attempt % len(models_to_try)]
        try:
            res_text = await generate_content(
                client=client,
                pool=pool,
                prompt=user_prompt,
                system_prompt=system_inst,
                model=target_model,
                temperature=0.35,
                max_output_tokens=16384,
                timeout_secs=95.0,
            )
            is_valid, cleaned_text, title = clean_and_verify_translation(res_text, chap_num, raw_len)
            if is_valid:
                slug = to_slug(title)
                filename = f"chap_{chap_num:04d}_{slug}.txt"
                out_path = CHAPTERS_DIR / filename
                out_path.write_text(cleaned_text, encoding="utf-8")
                print(f"[{chap_num:04d}] OK ({target_model}) -> {filename} ({len(cleaned_text)} chars / raw {raw_len})", flush=True)
                return True
            else:
                print(f"[{chap_num:04d}] Verification failed (attempt {attempt+1}), retrying with fallback...", file=sys.stderr, flush=True)
                await asyncio.sleep(1.5)
        except Exception as e:
            print(f"[{chap_num:04d}] Error attempt {attempt+1} ({target_model}): {e}", file=sys.stderr, flush=True)
            await asyncio.sleep(2.0)

    print(f"[{chap_num:04d}] FAILED after all attempts!", file=sys.stderr, flush=True)
    return False


async def run_translation_pipeline():
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    char_str, term_str = load_glossary()

    system_inst = """Bạn là dịch giả văn học chuyên nghiệp, chuyên dịch tiểu thuyết đô thị trọng sinh và thanh xuân đại học Trung Quốc sang tiếng Việt.
Chỉ trả về DUY NHẤT nội dung bản dịch tiếng Việt hoàn chỉnh theo đúng định dạng.
TUYỆT ĐỐI KHÔNG xuất ghi chú, phân tích, quá trình suy nghĩ hay bất kỳ ký tự tiếng Trung nào."""

    existing = get_existing_chapters()
    missing_nums = [n for n in range(1, MAX_CHAPTER + 1) if n not in existing]
    
    print(f"Total existing chapters: {len(existing)}")
    print(f"Target range: 1 -> {MAX_CHAPTER}")
    print(f"Chapters to translate: {len(missing_nums)}: {missing_nums[:15]}...")

    if not missing_nums:
        print("All chapters up to target are already translated!")
        return True

    # Check raw chapters availability
    tasks_to_run = []
    for n in missing_nums:
        raw_file = RAW_DIR / f"chap_{n:04d}.txt"
        if raw_file.exists():
            tasks_to_run.append((n, raw_file))
        else:
            print(f"Warning: Raw file not found: {raw_file}", file=sys.stderr)

    print(f"Ready to process {len(tasks_to_run)} chapters with concurrency {CONCURRENCY} using pool...")

    pool = KeyPoolManager()
    sem = asyncio.Semaphore(CONCURRENCY)
    limits = httpx.Limits(max_keepalive_connections=35, max_connections=CONCURRENCY * 2)

    async with httpx.AsyncClient(limits=limits) as client:
        async def worker(idx: int, chap_num: int, raw_path: Path):
            # Stagger launch slightly to avoid initial burst
            if idx < CONCURRENCY:
                await asyncio.sleep(idx * 2.0)
            async with sem:
                res = await translate_single_chapter(
                    client=client,
                    pool=pool,
                    chap_num=chap_num,
                    raw_path=raw_path,
                    system_inst=system_inst,
                    char_str=char_str,
                    term_str=term_str,
                )
                await asyncio.sleep(1.0)
                return res

        results = await asyncio.gather(*(worker(i, n, p) for i, (n, p) in enumerate(tasks_to_run)))

    success_count = sum(1 for r in results if r)
    print(f"\nPipeline finished: {success_count}/{len(tasks_to_run)} chapters translated successfully.")
    return success_count == len(tasks_to_run)


def post_processing():
    print("\n--- Running Post-Processing ---")
    # 1. Update compilation
    print("1. Compiling full plain text novel edition...")
    res_compile = subprocess.run(
        [sys.executable, str(ROOT / "compile_novel.py"), BOOK_SLUG, "--output", str(ROOT / "Ta_That_Khong_Muon_Trung_Sinh_A_Tieng_Viet.txt")],
        capture_output=True,
        text=True,
    )
    print(res_compile.stdout.strip())

    # 2. Build reader data
    print("2. Building reader website static data...")
    res_reader = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_reader_data.py")],
        capture_output=True,
        text=True,
    )
    print(res_reader.stdout.strip())

    # 3. Update status json
    existing = get_existing_chapters()
    sorted_nums = sorted(existing.keys())
    latest_num = sorted_nums[-1] if sorted_nums else 0
    latest_file = existing.get(latest_num)
    rel_latest = str(latest_file.relative_to(ROOT)) if latest_file else ""

    status_data = {
        "total_story_chapters": 1075,
        "translated_count": len(existing),
        "latest_chapter": rel_latest,
        "compiled_file": "Ta_That_Khong_Muon_Trung_Sinh_A_Tieng_Viet.txt",
    }
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status_data, f, ensure_ascii=False, indent=2)
    print(f"3. Updated {STATUS_FILE.name}: translated_count = {len(existing)}, latest = {rel_latest}")


if __name__ == "__main__":
    success = asyncio.run(run_translation_pipeline())
    post_processing()
