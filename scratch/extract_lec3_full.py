import pymupdf

doc = pymupdf.open('Lec-3.pdf')
with open('scratch/lec3_all_pages.txt', 'w', encoding='utf-8') as f:
    for i, page in enumerate(doc):
        f.write(f"--- PAGE {i+1} ---\n")
        f.write(page.get_text() + "\n")
        images = page.get_images()
        if images:
            f.write(f"[Images on page: {len(images)}]\n")
        f.write("\n")

print("Done writing lec3_all_pages.txt")
