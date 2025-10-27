from __future__ import annotations
from pathlib import Path
import pandas as pd

# Map of tags we care about
TAGS = {
    "%A": "authors",          # can repeat
    "%T": "title",
    "%D": "year_published",
    "%X": "abstract",         # may span multiple lines (continuations)
    "%R": "doi",
    "%0": "_start",           # marks start of a new record
}

def parse_exportlist(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    records = []
    current = None
    last_field = None  # the field that continuation lines should append to

    def finalize():
        if not current:
            return
        # Normalize output
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

        
        if len(line) >= 3 and line.startswith("%") and line[2] == " ":
            tag = line[:2]
            value = line[3:].strip()

            if tag == "%0":
                # new record
                finalize()
                current = {"authors": []}
                last_field = None
                continue

            # ensure we have a record dict
            if current is None:
                current = {"authors": []}

            field = TAGS.get(tag)
            if not field:
                last_field = None
                continue

            if field == "authors":
                current["authors"].append(value)
                last_field = "authors"  # (rarely used for continuations)
            elif field == "year_published":
                # keep the first 4-digit year if present
                # some %D lines include extra text
                import re
                m = re.search(r"\b(\d{4})\b", value)
                current["year_published"] = m.group(1) if m else value
                last_field = "year_published"
            else:
                # title, abstract, doi
                # allow later continuations to append
                if field in current and current[field]:
                    current[field] += " " + value
                else:
                    current[field] = value
                last_field = field

        else:
            # continuation line (no leading % tag)
            if current is not None and last_field in {"abstract", "title"}:
                current[last_field] = (current.get(last_field, "") + " " + line).strip()
            else:
                # ignore stray dates/notes/etc.
                pass

    # last record
    finalize()

    return pd.DataFrame.from_records(
        records, columns=["authors", "title", "abstract", "year published", "DOI"]
    )

if __name__ == "__main__":
    src = Path(__file__).parent / "exportlist.txt"   # make sure the file name matches
    df = parse_exportlist(src)

    # quick peek
    print(df.head(3).to_string(index=False))

    # save for later steps (ChatGPT scoring, etc.)
    out_csv = Path(__file__).parent / "parsed_articles.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\nSaved {len(df)} rows to {out_csv}")