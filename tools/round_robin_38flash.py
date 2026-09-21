#!/usr/bin/env python3
"""
Round-robin batch translation using gemini-3.8-flash across 28 independent API keys.
Each round: 28 chapters assigned 1-to-1 to 28 keys, then sleeps 3 minutes.
Repeats up to 10 rounds until chapter 300 is reached.
Performs verification, rebuilds website data, and pushes to git.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw_chapters"
BOOK_SLUG = "ta-that-khong-muon-trung-sinh-a"
CHAPTERS_DIR = ROOT / "books" / BOOK_SLUG / "chapters"
GLOSSARY_FILE = ROOT / "glossary.json"
STATUS_FILE = ROOT / "translation_status.json"
KEY_FILE = Path("/home/anng/Documents/data_api.txt")

MAX_CHAPTER = 300
MAX_ROUNDS = 10
COOLDOWN_SECONDS = 180  # 3 minutes
MODEL = "gemini-3.8-flash"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def load_keys() -> List[str]:
    with open(KEY_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def to_slug(title: str) -> str:
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


def get_missing_chapters() -> List[int]:
    pattern = re.compile(r"^chap_(\d+)(?:_.+)?\.txt$")
    existing = set()
    for f in CHAPTERS_DIR.glob("chap_*.txt"):
        m = pattern.match(f.name)
        if m:
            num = int(m.group(1))
            raw_file = RAW_DIR / f"chap_{num:04d}.txt"
            raw_len = len(raw_file.read_text(encoding="utf-8")) if raw_file.exists() else 0
            content = f.read_text(encoding="utf-8").strip()
            
            # Sanity check existing
            if raw_len > 1200 and len(content) < raw_len * 1.8:
                f.unlink(missing_ok=True)
                continue
            last_c = content[-1] if content else ""
            if last_c not in '.!?\"”’\'…\n' and not content.endswith('······') and not content.endswith('...'):
                f.unlink(missing_ok=True)
                continue
            existing.add(num)
    return [n for n in range(1, MAX_CHAPTER + 1) if n not in existing]


def clean_and_verify(text: str, chap_num: int, raw_len: int) -> Tuple[bool, str, str]:
    text = text.replace("\r\n", "\n").replace("\u3000", "").strip()
    lines = text.split("\n")
    if not lines:
        return False, "", "Rỗng"

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

    # Length check
    if raw_len > 1200:
        if len(final_text) < int(raw_len * 1.8):
            return False, final_text, title
    elif len(final_text) < 400:
        return False, final_text, title

    # Ending check
    stripped = final_text.strip()
    last_char = stripped[-1] if stripped else ""
    if last_char not in '.!?\"”’\'…\n' and not stripped.endswith('······') and not stripped.endswith('...'):
        return False, final_text, title

    # Leftover Chinese characters
    if re.search(r"[\u4e00-\u9fff]", final_text):
        return False, final_text, title

    return True, final_text, title


async def translate_chapter_with_key(
    client: httpx.AsyncClient,
    chap_num: int,
    key_idx: int,
    key: str,
    system_inst: str,
    char_str: str,
    term_str: str,
) -> bool:
    raw_path = RAW_DIR / f"chap_{chap_num:04d}.txt"
    if not raw_path.exists():
        print(f"[{chap_num:04d}] Missing raw file: {raw_path}", file=sys.stderr)
        return False

    raw_content = raw_path.read_text(encoding="utf-8")
    raw_len = len(raw_content)

    user_prompt = f"""Dịch ĐẦY ĐỦ TOÀN BỘ chương truyện tiểu thuyết đô thị sau đây sang tiếng Việt.
Tuyệt đối KHÔNG tóm tắt, KHÔNG bỏ dở giữa chừng, dịch liền mạch từ đầu tới hết chương.

QUY CÁCH TRÌNH BÀY:
- Dòng 1: Chương {chap_num}: [Tên chương tiếng Việt]
- Dòng 2: [Dòng trống]
- Dòng 3 trở đi: Toàn bộ nội dung chương, mỗi đoạn văn cách nhau một dòng trống.

YÊU CẦU:
1. Văn phong sinh động, dí dỏm, tưng tửng, hiện đại.
2. Giữ lại từ Hán Việt quen thuộc: tra nam, tu la tràng, bạch nguyệt quang, nốt chu sa, thanh mai trúc mã, Cẩu ca, lão tử, cẩu liếm, học bá, học tra, trà xanh...
3. Tuân thủ nhân vật:
{char_str}
4. Tuân thủ thuật ngữ:
{term_str}
5. Không để sót chữ Hán nào.

NỘI DUNG NGUYÊN TÁC (CHƯƠNG {chap_num}):
{raw_content}
"""

    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_inst}]},
        "generationConfig": {
            "temperature": 0.35,
            "maxOutputTokens": 16384,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    models = ["gemini-3.8-flash", "gemini-3.6-flash"]

    for model_name in models:
        url = f"{BASE_URL}/{model_name}:generateContent?key={key}"
        try:
            resp = await client.post(url, json=payload, timeout=120.0)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    cand = candidates[0]
                    if cand.get("finishReason") == "MAX_TOKENS":
                        print(f"[{chap_num:04d}] Key #{key_idx+1} ({model_name}): Cut off by MAX_TOKENS", file=sys.stderr)
                        continue
                    parts = cand.get("content", {}).get("parts", [])
                    res_text = "".join(p.get("text", "") for p in parts).strip()
                    
                    is_valid, cleaned_text, title = clean_and_verify(res_text, chap_num, raw_len)
                    if is_valid:
                        slug = to_slug(title)
                        filename = f"chap_{chap_num:04d}_{slug}.txt"
                        out_path = CHAPTERS_DIR / filename
                        out_path.write_text(cleaned_text, encoding="utf-8")
                        print(f"[{chap_num:04d}] OK (Key #{key_idx+1}, {model_name}) -> {filename} ({len(cleaned_text)} chars / raw {raw_len})")
                        return True
                    else:
                        print(f"[{chap_num:04d}] Key #{key_idx+1} ({model_name}): Verification check failed", file=sys.stderr)
                        continue
            elif resp.status_code in (503, 429):
                print(f"[{chap_num:04d}] Key #{key_idx+1} {model_name} HTTP {resp.status_code}, falling back...", file=sys.stderr)
                await asyncio.sleep(1.0)
                continue
            else:
                print(f"[{chap_num:04d}] Key #{key_idx+1} Error HTTP {resp.status_code}: {resp.text[:120]}", file=sys.stderr)
        except Exception as e:
            print(f"[{chap_num:04d}] Key #{key_idx+1} ({model_name}) Exception: {e}", file=sys.stderr)
            await asyncio.sleep(1.0)

    return False


async def run_round(round_num: int, keys: List[str], missing_chapters: List[int], system_inst: str, char_str: str, term_str: str) -> int:
    batch_size = min(len(keys), len(missing_chapters))
    batch_chapters = missing_chapters[:batch_size]

    print(f"\n=======================================================")
    print(f"=== ROUND {round_num}/{MAX_ROUNDS}: Processing {batch_size} chapters with {batch_size} independent keys ===")
    print(f"=== Chapters: {batch_chapters[:8]} ... {batch_chapters[-3:]} ===")
    print(f"=======================================================")

    limits = httpx.Limits(max_keepalive_connections=35, max_connections=40)
    async with httpx.AsyncClient(limits=limits) as client:
        async def single_worker(idx: int, chap_num: int, key: str):
            # Stagger launch by 1.5s
            await asyncio.sleep(idx * 1.5)
            return await translate_chapter_with_key(
                client=client,
                chap_num=chap_num,
                key_idx=idx,
                key=key,
                system_inst=system_inst,
                char_str=char_str,
                term_str=term_str,
            )

        tasks = [single_worker(i, c, keys[i]) for i, c in enumerate(batch_chapters)]
        results = await asyncio.gather(*tasks)

    successes = sum(1 for r in results if r)
    print(f"\n[Round {round_num}] Result: {successes}/{batch_size} chapters completed successfully.")
    return successes


def run_post_processing():
    print("\n--- Running Final Post-Processing ---")
    print("1. Compiling novel edition...")
    subprocess.run(
        [sys.executable, str(ROOT / "compile_novel.py"), BOOK_SLUG, "--output", str(ROOT / "Ta_That_Khong_Muon_Trung_Sinh_A_Tieng_Viet.txt")],
        check=False,
    )

    print("2. Building reader website data...")
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_reader_data.py")], check=False)

    pattern = re.compile(r"^chap_(\d+)(?:_.+)?\.txt$")
    existing_files = list(CHAPTERS_DIR.glob("chap_*.txt"))
    nums = [int(pattern.match(f.name).group(1)) for f in existing_files if pattern.match(f.name)]
    sorted_nums = sorted(nums)
    latest_num = sorted_nums[-1] if sorted_nums else 0

    latest_file_rel = ""
    for f in existing_files:
        m = pattern.match(f.name)
        if m and int(m.group(1)) == latest_num:
            latest_file_rel = str(f.relative_to(ROOT))
            break

    status_data = {
        "total_story_chapters": 1075,
        "translated_count": len(sorted_nums),
        "latest_chapter": latest_file_rel,
        "compiled_file": "Ta_That_Khong_Muon_Trung_Sinh_A_Tieng_Viet.txt",
    }
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status_data, f, ensure_ascii=False, indent=2)
    print(f"3. Updated {STATUS_FILE.name}: {len(sorted_nums)} chapters translated (latest: {latest_num}).")

    print("4. Committing and pushing to git...")
    subprocess.run(["git", "add", "books/", "glossary.json", "translation_status.json", "Ta_That_Khong_Muon_Trung_Sinh_A_Tieng_Viet.txt"], check=False)
    commit_res = subprocess.run(["git", "commit", "-m", f"Translate up to chapter {latest_num} with gemini-3.8-flash and update reader"], capture_output=True, text=True)
    print(commit_res.stdout.strip())
    push_res = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
    print(push_res.stdout.strip())
    print("Post-processing and git push finished!")


async def main():
    keys = load_keys()
    print(f"Loaded {len(keys)} independent API keys from {KEY_FILE}.")
    char_str, term_str = load_glossary()

    system_inst = """Bạn là dịch giả văn học chuyên nghiệp, chuyên dịch tiểu thuyết đô thị trọng sinh và thanh xuân đại học Trung Quốc sang tiếng Việt.
Chỉ trả về DUY NHẤT nội dung bản dịch tiếng Việt hoàn chỉnh theo đúng định dạng.
TUYỆT ĐỐI KHÔNG xuất ghi chú, phân tích, suy nghĩ ngầm hay bất kỳ ký tự tiếng Trung nào."""

    for round_idx in range(1, MAX_ROUNDS + 1):
        missing = get_missing_chapters()
        print(f"\n[Status] Current missing chapters (<= {MAX_CHAPTER}): {len(missing)}")
        if not missing:
            print("Congratulations! All chapters up to 300 have been translated!")
            break

        await run_round(round_idx, keys, missing, system_inst, char_str, term_str)

        # Check if done
        remaining = get_missing_chapters()
        if not remaining:
            print("All chapters completed!")
            break

        if round_idx < MAX_ROUNDS:
            print(f"\n>>> Cooling down for {COOLDOWN_SECONDS}s (3 minutes) before round {round_idx + 1}... <<<")
            for remaining_sec in range(COOLDOWN_SECONDS, 0, -30):
                print(f"... Cooldown: {remaining_sec}s remaining ...")
                await asyncio.sleep(min(30, remaining_sec))

    run_post_processing()


if __name__ == "__main__":
    asyncio.run(main())
