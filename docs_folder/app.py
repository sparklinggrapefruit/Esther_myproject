from __future__ import annotations
from pathlib import Path
import pandas as pd

TAGS_MAP = {
    "%A": "authors",          # can appear multiple times
    "%T": "title",
    "%D": "year_published",
    "%X": "abstract",
    "%R": "doi",
    "%0": "_record_start",    # marks a new record
}

def parse_exportlist(file_path: str | Path) -> pd.DataFrame:
    file_path = Path(file_path)
    lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    records = []
    current = None
    last_field = None  # track which field should receive continuation lines

    def finalize_record():
        """Push a copy of current into records with normalized fields."""
        if not current:
            return
        # Normalize authors to a single string; handle missing keys gracefully
        authors_list = current.get("authors", [])
        current_out = {
            "authors": "; ".join(authors_list) if authors_list else "",
            "title": current.get("title", ""),
            "abstract": current.get("abstract", ""),
            "year published": current.get("year_published", ""),
            "DOI": current.get("doi", ""),
        }
        records.append(current_out)

    for raw in lines:
        line = raw.strip()
        if not line:
            # blank line: treat as separator but keep current record open
            last_field = None
            continue

        if len(line) >= 3 and line[:2] == "%" and line[2] == " ":
            tag = line[:2]
            value = line[3:].strip()

            # new record?
            if tag == "%0":
                # finalize the previous record
                finalize_record()
                current = {"authors": []}
                last_field = None
                continue

            # make sure we have a record dict to write into
            if current is None:
                current = {"authors": []}

            mapped = TAGS_MAP.get(tag)
            if not mapped:
                # Unhandled tag → ignore and reset continuation
                last_field = None
                continue

            if mapped == "authors":
                current["authors"].append(value)
                last_field = "authors"  # (continuations into authors are rare; safe to allow)
            elif mapped == "_record_start":
                # handled above
                last_field = None
            else:
                # single-value fields; append if continuing later
                if mapped in current and current[mapped]:
                    current[mapped] += " " + value
                else:
                    current[mapped] = value
                last_field = mapped
        else:
            # Continuation line (no leading %). Append to the last field if sensible.
            if current is not None and last_field in {"abstract", "title"}:
                current[last_field] = (current.get(last_field, "") + " " + line).strip()
            else:
                # Often these are stray dates (e.g., 2024-02-15) or notes; ignore.
                pass

    # finalize last record
    finalize_record()

    df = pd.DataFrame.from_records(records, columns=["authors", "title", "abstract", "year published", "DOI"])
    return df


if __name__ == "__main__":
    # Adjust path if your file lives elsewhere; from your screenshot it's in docs_folder
    src = Path(__file__).parent / "exportlist.txt"
    df = parse_exportlist(src)

    # Preview a few rows
    print(df.head(3).to_string(index=False))

    # Save for your app / ChatGPT helper to load later
    out_csv = Path(__file__).parent / "parsed_articles.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\nSaved {len(df)} rows to {out_csv}")