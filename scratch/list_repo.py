import os

with open('scratch/repo_structure.txt', 'w', encoding='utf-8') as f:
    for root, dirs, files in os.walk('.'):
        if any(ign in root for ign in ['.git', 'scratch', '__pycache__', '.venv', 'env']):
            continue
        for file in files:
            p = os.path.join(root, file)
            size = os.path.getsize(p)
            f.write(f"{p} ({size} bytes)\n")

print("Done listing repo structure!")
