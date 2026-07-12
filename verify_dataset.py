from pathlib import Path
import pandas as pd

folders = [
    "data/raw/dataco",
    "data/raw/inventory",
    "data/raw/amazon_products",
    "data/raw/amazon_reviews",
]

for folder in folders:
    print("=" * 80)
    print(folder)

    for file in Path(folder).iterdir():
        print(f"\nFILE: {file.name}")

        if file.suffix.lower() == ".csv":
            df = pd.read_csv(file, nrows=5)
        elif file.suffix.lower() in [".xlsx", ".xls"]:
            df = pd.read_excel(file, nrows=5)
        else:
            continue

        print("\nColumns:")
        print(df.columns.tolist())

        print("\nShape:")
        print(df.shape)

        print("\nPreview:")
        print(df.head())