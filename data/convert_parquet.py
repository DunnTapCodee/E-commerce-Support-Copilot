from pathlib import Path
import pandas as pd

data_dir = (
    Path(__file__).resolve().parent
    / "raw"
    / "Vietnamese-Customer-Support-QA"
    / "data"
)

for split in ("train", "test"):
    parquet_file = data_dir / f"{split}-00000-of-00001.parquet"
    csv_file = data_dir / f"{split}.csv"

    df = pd.read_parquet(parquet_file)
    df.to_csv(csv_file, index=False, encoding="utf-8-sig")
    print(f"Created {csv_file.name}: {len(df)} rows")
