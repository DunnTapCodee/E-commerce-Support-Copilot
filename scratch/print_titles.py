import json

with open('scratch/lecture_summary.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

with open('scratch/all_titles.txt', 'w', encoding='utf-8') as out:
    for lec in ['Lec-1.pdf', 'Lec-2.pdf', 'Lec-3.pdf']:
        out.write(f"=== {lec} ===\n")
        for item in data[lec]:
            out.write(f"P{item['page']}: {item['title']} | {item['preview'][:100]}\n")
        out.write("\n")

print("Written all_titles.txt")
