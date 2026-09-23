import zipfile
import re
from html import unescape
from pathlib import Path

def clean_html(raw_html):
    text = re.sub(r'<br\s*/?>', '\n', raw_html)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'</h\d>', '\n\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    res = [l for l in lines if l]
    return '\n\n'.join(res)

epub_path = 'raw_chapters/tomozaki/Bottom-Tier Character Tomozaki - Volume 02 [Yen Press][Kobo].epub'
with zipfile.ZipFile(epub_path, 'r') as z:
    spine_groups = [
        ("Chương 1: Những nhân vật trở thành bạn sau một sự kiện khó nhằn thường có chỉ số rất cao", 
         ["Text/part0010.xhtml", "Text/part0011.xhtml", "Text/part0012.xhtml", "Text/part0013.xhtml", "Text/part0014.xhtml"]),
        ("Chương 2: Khi chỉ có một nhân vật cấp thấp trong đội, cấp độ của cậu ta sẽ tăng vọt", 
         ["Text/part0015.xhtml"])
    ]

    out_dir = Path("raw_chapters/tomozaki_extracted/vol2")
    out_dir.mkdir(parents=True, exist_ok=True)

    for idx, (title, files) in enumerate(spine_groups):
        texts = []
        for f in files:
            path = f"OEBPS/{f}"
            if path in z.namelist():
                content = clean_html(z.read(path).decode('utf-8', errors='ignore'))
                if content:
                    texts.append(content)
        full_text = "\n\n".join(texts)
        out_file = out_dir / f"chap_{idx:04d}.txt"
        out_file.write_text(f"{title}\n\n{full_text}", encoding="utf-8")
        print(f"Saved {out_file.name}: {title} ({len(full_text)} chars, {len(full_text.split())} words)")
