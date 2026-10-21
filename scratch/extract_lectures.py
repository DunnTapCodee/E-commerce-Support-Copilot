import pymupdf
import json

summary = {}

for fname in ['Lec-1.pdf', 'Lec-2.pdf', 'Lec-3.pdf']:
    doc = pymupdf.open(fname)
    summary[fname] = []
    for i in range(len(doc)):
        text = doc[i].get_text()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        title = lines[0] if lines else "Empty"
        content_preview = " // ".join(lines[:6])
        summary[fname].append({
            "page": i + 1,
            "title": title,
            "preview": content_preview,
            "full_text": text
        })

with open("scratch/lecture_summary.json", "w", encoding="utf-8") as f:
    json.dump({k: [{"page": x["page"], "title": x["title"], "preview": x["preview"]} for x in v] for k, v in summary.items()}, f, ensure_ascii=False, indent=2)

# Also dump detailed search on Lec-3
with open("scratch/lec3_details.txt", "w", encoding="utf-8") as f:
    for item in summary['Lec-3.pdf']:
        f.write(f"=== Page {item['page']}: {item['title']} ===\n")
        f.write(item['full_text'] + "\n\n")

# And dump detailed search on Lec-1 and Lec-2
with open("scratch/lec1_lec2_details.txt", "w", encoding="utf-8") as f:
    f.write("=== LEC 1 ===\n")
    for item in summary['Lec-1.pdf']:
        f.write(f"=== Page {item['page']}: {item['title']} ===\n")
        f.write(item['full_text'] + "\n\n")
    f.write("\n=== LEC 2 ===\n")
    for item in summary['Lec-2.pdf']:
        f.write(f"=== Page {item['page']}: {item['title']} ===\n")
        f.write(item['full_text'] + "\n\n")

print("Done extracting lectures!")
