from __future__ import annotations

from pathlib import Path
import re
import pandas as pd


# Mapping from ProQuest/EndNote-style tags to our internal field names
TAGS = {
    "%A": "authors",          # can repeat
    "%T": "title",
    "%D": "year_published",
    "%X": "abstract",         # may span multiple lines
    "%R": "doi",
    "%0": "_start",           # start of a new record
}


def parse_exportlist(input_txt: str | Path,
                     output_csv: str | Path | None = Path("data/parsed_articles.csv")) -> pd.DataFrame:
    """
    Parse a tagged export .txt file (e.g., from ProQuest) into a structured DataFrame.
    Optionally writes a CSV if output_csv is not None.

    Expected tags (examples):
    - %A Author name
    - %T Title
    - %D Year/date
    - %X Abstract
    - %R DOI
    - %0 Journal Article (start of record)
    """
    input_txt = Path(input_txt)
    if not input_txt.exists():
        raise FileNotFoundError(f"Input file not found: {input_txt}")

    # Ensure data folder exists
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    lines = input_txt.read_text(encoding="utf-8", errors="ignore").splitlines()

    records = []
    current = None
    last_field = None

    def finalize_record():
        nonlocal current
        if not current:
            return
        out = {
            "authors": "; ".join(current.get("authors", [])),
            "title": current.get("title", ""),
            "abstract": current.get("abstract", ""),
            "year published": current.get("year_published", ""),
            "DOI": current.get("doi", ""),
        }
        records.append(out)

    for raw in lines:
        line = raw.rstrip()

        # Lines that start with a tag like "%A ", "%T ", "%X "
        if len(line) >= 3 and line.startswith("%") and line[2] == " ":
            tag, value = line[:2], line[3:].strip()

            if tag == "%0":
                # New record
                finalize_record()
                current = {"authors": []}
                last_field = None
                continue

            if current is None:
                current = {"authors": []}

            field = TAGS.get(tag)
            if not field:
                last_field = None
                continue

            if field == "authors":
                current["authors"].append(value)
                last_field = "authors"

            elif field == "year_published":
                # Try to extract a 4-digit year
                m = re.search(r"\b(\d{4})\b", value)
                current["year_published"] = m.group(1) if m else value
                last_field = "year_published"

            else:
                # title, abstract, doi
                if field in current and current[field]:
                    current[field] += " " + value
                else:
                    current[field] = value
                last_field = field

        else:
            # Continuation lines for abstract (or title if needed)
            if current is not None and last_field in {"abstract", "title"}:
                current[last_field] = (current.get(last_field, "") + " " + line).strip()

    # finalize last record
    finalize_record()

    df = pd.DataFrame.from_records(
        records,
        columns=["authors", "title", "abstract", "year published", "DOI"],
    )

    if output_csv is not None:
        output_csv = Path(output_csv)
        output_csv.parent.mkdir(exist_ok=True)
        df.to_csv(output_csv, index=False, encoding="utf-8")
        print(f"Saved parsed data to {output_csv} (rows: {len(df)})")

    return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse tagged export .txt into CSV.")
    parser.add_argument(
        "input_txt",
        help="Path to exportlist.txt (or similar). Example: data/exportlist.txt",
    )
    parser.add_argument(
        "-o", "--output",
        default="data/parsed_articles.csv",
        help="Output CSV path (default: data/parsed_articles.csv)",
    )
    args = parser.parse_args()

    parse_exportlist(args.input_txt, args.output)