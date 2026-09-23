import zipfile
import re
from html import unescape
from pathlib import Path

def clean_html(raw_html):
    # Keep image markers or clean tags
    text = re.sub(r'<br\s*/?>', '\n', raw_html)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'</h\d>', '\n\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    res = []
    for l in lines:
        if l:
            res.append(l)
    return '\n\n'.join(res)

epub_path = 'raw_chapters/tomozaki/Bottom-Tier Character Tomozaki - Volume 01 [Yen Press][Kobo].epub'
with zipfile.ZipFile(epub_path, 'r') as z:
    spine_groups = [
        ("Chương 0: Tôi luôn cảm thấy hụt hẫng khi xem đoạn mở đầu sau khi phá đảo một trò chơi", 
         ["Text/chapter001.xhtml"]),
        ("Chương 1: Dù ai nói ngả nói nghiêng, những game nổi tiếng thường rất hay", 
         ["Text/chapter002.xhtml", "Text/chapter002_a.xhtml", "Text/chapter002_b.xhtml", "Text/chapter002_c.xhtml", "Text/chapter002_d.xhtml"]),
        ("Chương 2: Cảm giác tăng vọt một đống cấp độ sau một trận chiến thật là tuyệt vời", 
         ["Text/chapter003.xhtml", "Text/chapter003_a.xhtml", "Text/chapter003_b.xhtml", "Text/chapter003_c.xhtml", "Text/chapter003_d.xhtml"]),
        ("Chương 3: Cày cuốc một mình mang lại lượng điểm kinh nghiệm bất ngờ", 
         ["Text/chapter004.xhtml", "Text/chapter004_a.xhtml", "Text/chapter004_b.xhtml"]),
        ("Chương 4: Khi một cô gái là người bạn đầu tiên của bạn, cuộc sống lúc nào cũng như một buổi hẹn hò", 
         ["Text/chapter005.xhtml", "Text/chapter005_a.xhtml", "Text/chapter005_b.xhtml", "Text/chapter005_c.xhtml", "Text/chapter005_d.xhtml"]),
        ("Chương 5: Kỹ năng và trang bị mạnh mẽ giúp việc thăng tiến vừa vui vừa dễ dàng", 
         ["Text/chapter006.xhtml", "Text/chapter006_a.xhtml", "Text/chapter006_b.xhtml"]),
        ("Chương 6: Đôi khi bạn vừa chinh phục xong hầm ngục thì lại phát hiện một con trùm siêu mạnh ngay tại làng của mình", 
         ["Text/chapter007.xhtml", "Text/chapter007_a.xhtml", "Text/chapter007_b.xhtml"]),
        ("Chương 7: Tôi luôn mong chờ phần tiếp theo khi phần giới thiệu kết thúc khép lại", 
         ["Text/chapter008.xhtml", "Text/chapter008_a.xhtml"]),
        ("Lời bạt: Lời bạt của tác giả (Tập 1)", 
         ["Text/afterword.xhtml"])
    ]

    out_dir = Path("raw_chapters/tomozaki_extracted/vol1")
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
        # write file
        out_file = out_dir / f"chap_{idx:04d}.txt"
        out_file.write_text(f"{title}\n\n{full_text}", encoding="utf-8")
        print(f"Saved {out_file.name}: {title} ({len(full_text)} chars, {len(full_text.split())} words)")
