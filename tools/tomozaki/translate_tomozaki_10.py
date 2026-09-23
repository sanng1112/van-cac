import asyncio
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import List, Dict

import httpx

ROOT = Path("/mnt/storage/Website/Novel")
KEY_FILE = Path("/home/anng/Documents/data_api.txt")
BOOK_SLUG = "nhan-vat-ha-dang-tomozaki"
CHAPTERS_OUT = ROOT / "books" / BOOK_SLUG / "chapters"
CHAPTERS_OUT.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-2.5-flash"
BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

GLOSSARY = """
Quy chuẩn dịch & Thuật ngữ Light Novel "Nhân Vật Hạ Đẳng Tomozaki" (Bottom-Tier Character Tomozaki / Jaku-Chara Tomozaki-kun):
- Fumiya Tomozaki: Tomozaki Fumiya (biệt danh game: nanashi / Nanashi) - ngôi thứ nhất "tôi", gọi bạn bè là "cậu", xưng hô lễ phép với người trên.
- Aoi Hinami: Hinami Aoi (biệt danh game: NO NAME) - nữ thần hoàn hảo của trường, nói chuyện tự tin, sắc sảo.
- Fuuka Kikuchi: Kikuchi Fuuka - cô gái nhỏ nhắn, yêu thích sách của tác giả Michael Andi.
- Minami Nanami: Nanami Minami (biệt danh Mimimi) - năng động, tinh nghịch, hay chọc Tomozaki.
- Hanabi Natsubayashi: Natsubayashi Hanabi (biệt danh Tama / Tama-chan) - thẳng thắn, bộc trực.
- Takahiro Mizusawa: Mizusawa Takahiro - đẹp trai, ăn nói lưu loát, sành điệu.
- Shuji Nakamura: Nakamura Shuji - nam sinh nổi bật, tính cách hơi hung hăng nhưng thẳng tính.
- Takei: Takei - bạn trong nhóm Nakamura, tính tình ồn ào hài hước.
- Attack Families / Tackfam (Atafami): Atafami (tựa game đối kháng nổi tiếng giả tưởng tương tự Super Smash Bros).
- bottom-tier character: nhân vật hạ đẳng / nhân vật tier thấp.
- top-tier character: nhân vật thượng đẳng / nhân vật tier cao.
- god-tier game: game thần thánh / tuyệt tác game.
- trash game / kusoge: game rác.
- life is a game: cuộc đời là một trò chơi.
- Giữ nguyên các kính ngữ nếu tự nhiên (-san, -kun, -chan) hoặc chuyển ngữ mượt mà hợp bối cảnh học đường Nhật Bản.
"""

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

def split_text_into_chunks(text: str, max_chars: int = 12000) -> List[str]:
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_len = 0
    for p in paragraphs:
        p_len = len(p)
        if current_len + p_len > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [p]
            current_len = p_len
        else:
            current_chunk.append(p)
            current_len += p_len + 2
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    return chunks

async def translate_chunk(client: httpx.AsyncClient, chunk: str, key: str, is_first: bool, title_hint: str) -> str:
    prompt = f"""Bạn là dịch giả văn học chuyên nghiệp hàng đầu, chuyên dịch Light Novel Nhật Bản sang tiếng Việt.
Hãy dịch đoạn văn sau sang tiếng Việt với văn phong tự nhiên, trôi chảy, giàu cảm xúc, đúng phong cách học đường hài hước lãng mạn (Romcom) và đời thường của Nhật Bản.

{GLOSSARY}

YÊU CẦU QUAN TRỌNG:
1. Bản dịch phải hoàn chỉnh, trung thực 100% với nội dung gốc, KHÔNG được tóm tắt hay lược bỏ bất kỳ câu thoại/đoạn văn nào.
2. {'Nếu đây là phần đầu chương, dòng đầu tiên BẮT BUỘC là tiêu đề chương tiếng Việt (Ví dụ: "Chương X: Tiêu đề...").' if is_first else 'Đây là phần tiếp theo của chương, KHÔNG lặp lại tiêu đề, tiếp tục nội dung một cách liền mạch.'}
3. Chỉ trả về nội dung đã dịch, KHÔNG thêm bất kỳ lời bình luận, lời chào hay ghi chú nào của người dịch.

ĐOẠN CẦN DỊCH:
{chunk}
"""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 8192
        }
    }
    
    for attempt in range(4):
        try:
            resp = await client.post(
                f"{BASE_URL}?key={key}",
                json=body,
                timeout=120.0
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return text
            elif resp.status_code == 429:
                await asyncio.sleep(5 * (attempt + 1))
            else:
                print(f"API Error {resp.status_code}: {resp.text[:100]}")
                await asyncio.sleep(3)
        except Exception as e:
            print(f"Request exception: {e}")
            await asyncio.sleep(3)
    return ""

async def translate_chapter(client: httpx.AsyncClient, chap_id: int, raw_path: Path, key: str) -> bool:
    content = raw_path.read_text(encoding="utf-8")
    lines = content.split("\n", 1)
    original_title = lines[0].strip()
    body_text = lines[1].strip() if len(lines) > 1 else ""

    print(f"-> [Bắt đầu Chap {chap_id:04d}] {original_title} (Dung lượng gốc: {len(body_text)} ký tự)...")

    chunks = split_text_into_chunks(body_text)
    translated_parts = []
    
    for idx, chunk in enumerate(chunks):
        trans = await translate_chunk(client, chunk, key, idx == 0, original_title)
        if not trans:
            print(f"FAILED on chunk {idx+1}/{len(chunks)} of chap {chap_id}")
            return False
        translated_parts.append(trans)
        await asyncio.sleep(1) # small pause between chunks

    full_translation = "\n\n".join(translated_parts).strip()
    first_line, _, rest = full_translation.partition("\n")
    clean_title = first_line.strip()
    if not clean_title.lower().startswith("chương") and not clean_title.lower().startswith("lời bạt"):
        clean_title = f"Chương {chap_id}: {original_title}"
        full_translation = f"{clean_title}\n\n{full_translation}"

    slug_name = to_slug(clean_title)
    out_file = CHAPTERS_OUT / f"chap_{chap_id:04d}_{slug_name}.txt"
    out_file.write_text(full_translation, encoding="utf-8")
    print(f"-> [HOÀN TẤT Chap {chap_id:04d}] Đã lưu: {out_file.name} ({len(full_translation)} ký tự)")
    return True

async def main():
    keys = load_keys()
    print(f"Loaded {len(keys)} API keys.")

    # 10 chapters:
    # 0 to 8: Vol 1 (9 parts)
    # 9: Vol 2 Chap 1 (1 part) -> Total 10 chapters
    tasks_input = [
        (1, Path("raw_chapters/tomozaki_extracted/vol1/chap_0000.txt")),
        (2, Path("raw_chapters/tomozaki_extracted/vol1/chap_0001.txt")),
        (3, Path("raw_chapters/tomozaki_extracted/vol1/chap_0002.txt")),
        (4, Path("raw_chapters/tomozaki_extracted/vol1/chap_0003.txt")),
        (5, Path("raw_chapters/tomozaki_extracted/vol1/chap_0004.txt")),
        (6, Path("raw_chapters/tomozaki_extracted/vol1/chap_0005.txt")),
        (7, Path("raw_chapters/tomozaki_extracted/vol1/chap_0006.txt")),
        (8, Path("raw_chapters/tomozaki_extracted/vol1/chap_0007.txt")),
        (9, Path("raw_chapters/tomozaki_extracted/vol1/chap_0008.txt")),
        (10, Path("raw_chapters/tomozaki_extracted/vol2/chap_0000.txt")),
    ]

    async with httpx.AsyncClient() as client:
        # Run 10 chapters concurrently across 10 keys
        tasks = []
        for i, (chap_id, path) in enumerate(tasks_input):
            key = keys[i % len(keys)]
            tasks.append(translate_chapter(client, chap_id, path, key))
        results = await asyncio.gather(*tasks)
        print("All 10 chapters translation finished. Success count:", sum(1 for r in results if r))

if __name__ == '__main__':
    asyncio.run(main())
