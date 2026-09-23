import asyncio
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import List

import httpx

ROOT = Path("/mnt/storage/Website/Novel")
KEY_FILE = Path("/home/anng/Documents/data_api.txt")
BOOK_SLUG = "nhan-vat-ha-dang-tomozaki"
CHAPTERS_OUT = ROOT / "books" / BOOK_SLUG / "chapters"

# Using gemini-2.5-flash
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
- Attack Families / Tackfam (Atafami): Atafami (tựa game đối kháng nổi tiếng).
- bottom-tier character: nhân vật hạ đẳng / nhân vật tier thấp.
- top-tier character: nhân vật thượng đẳng / nhân vật tier cao.
- god-tier game: game thần thánh / tuyệt tác game.
- trash game / kusoge: game rác.
- life is a game: cuộc đời là một trò chơi.
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

def split_text_into_chunks(text: str, max_chars: int = 10000) -> List[str]:
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

async def translate_chunk(client: httpx.AsyncClient, chunk: str, key_pool: List[str], is_first: bool, title_hint: str) -> str:
    prompt = f"""Bạn là dịch giả văn học chuyên nghiệp, chuyên dịch Light Novel Nhật Bản sang tiếng Việt.
Hãy dịch đoạn văn sau sang tiếng Việt tự nhiên, cảm xúc, trôi chảy:

{GLOSSARY}

YÊU CẦU:
1. Dịch đầy đủ, trung thực, KHÔNG tóm tắt hay lược bỏ câu thoại.
2. {'Dòng đầu tiên BẮT BUỘC là tiêu đề chương: "Chương 1: Dù ai nói ngả nói nghiêng, những game nổi tiếng thường rất hay"' if is_first else 'Tiếp tục nội dung liền mạch, không lặp lại tiêu đề.'}
3. Chỉ trả về nội dung đã dịch.

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
    
    key_idx = 0
    for attempt in range(12):
        key = key_pool[key_idx % len(key_pool)]
        key_idx += 1
        try:
            resp = await client.post(
                f"{BASE_URL}?key={key}",
                json=body,
                timeout=120.0
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            elif resp.status_code in (429, 503):
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(2)
        except Exception:
            await asyncio.sleep(2)
    return ""

async def main():
    keys = load_keys()
    raw_path = Path("raw_chapters/tomozaki_extracted/vol1/chap_0001.txt")
    content = raw_path.read_text(encoding="utf-8")
    lines = content.split("\n", 1)
    original_title = lines[0].strip()
    body_text = lines[1].strip()

    print(f"Translating Chap 2: {original_title} ({len(body_text)} chars)...")
    chunks = split_text_into_chunks(body_text)
    print(f"Total chunks: {len(chunks)}")

    translated_parts = []
    async with httpx.AsyncClient() as client:
        for i, chunk in enumerate(chunks):
            print(f"Translating chunk {i+1}/{len(chunks)}...")
            res = await translate_chunk(client, chunk, keys, i == 0, original_title)
            if not res:
                print(f"FAILED chunk {i+1}")
                return
            translated_parts.append(res)
            print(f"Done chunk {i+1}/{len(chunks)}")
            await asyncio.sleep(1)

    full = "\n\n".join(translated_parts).strip()
    clean_title = "Chương 1: Dù ai nói ngả nói nghiêng, những game nổi tiếng thường rất hay"
    slug_name = to_slug(clean_title)
    out_file = CHAPTERS_OUT / f"chap_0002_{slug_name}.txt"
    out_file.write_text(f"{clean_title}\n\n{full}", encoding="utf-8")
    print(f"SUCCESS! Saved {out_file.name} ({len(full)} chars)")

if __name__ == '__main__':
    asyncio.run(main())
