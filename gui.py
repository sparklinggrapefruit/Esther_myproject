"""
Simple Tkinter GUI for your systematic review helper.

Workflow:
1. Click "Upload EndNote .txt file" → select exportlist.txt (or any similar EndNote export).
   - GUI parses %A, %T, %D, %R, %X into a DataFrame:
       columns = authors, title, abstract, year_published, doi
   - Table shows the parsed articles.

2. Edit the "Research theme / question" text if desired.

3. Click "Run relevance scoring".
   - Calls OpenAI for each abstract and gets a score 1–10.
   - Adds a 'relevancy_score' column.
   - Updates the table and progress label.

4. Click "Export scored CSV" to save the results.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from pathlib import Path
import re
import time
from typing import List, Dict, Optional

import pandas as pd
from openai import OpenAI
from config_loader import get_api_key_gui

# -------------------- OpenAI CONFIG -------------------- #

DEFAULT_THEME = (
    "Looking for articles that examined intervention studies which measure physical activity "
    "and that use mobile apps and/or wearable technology either to measure PA and/or deliver "
    "an intervention intended to influence PA levels."
)

MODEL = "gpt-4o-mini"
TEMPERATURE = 0

# Get the API key using the GUI helper
api_key = get_api_key_gui()
if not api_key:
    # User cancelled or didn't provide a key – exit the app
    raise SystemExit("OpenAI API key is required to run this app.")

client = OpenAI(api_key=api_key)



# -------------------- PARSING LOGIC -------------------- #

def parse_endnote_export(path: Path) -> pd.DataFrame:
    """
    Parse an EndNote-style export list (.txt) where:
      - Authors:   %A
      - Title:     %T
      - Year:      %D
      - DOI/URL:   %R
      - Abstract:  %X (may span multiple lines until next % code)

    Returns a DataFrame with columns:
        authors, title, abstract, year_published, doi
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    records: List[Dict[str, object]] = []
    current = {
        "authors": [],
        "title": "",
        "abstract": "",
        "year": "",
        "doi": "",
    }
    in_abstract = False

    def push_current():
        # push only if there's at least some meaningful content
        if (
            current["authors"]
            or current["title"]
            or current["abstract"]
            or current["year"]
            or current["doi"]
        ):
            records.append({
                "authors": "; ".join(current["authors"]),
                "title": current["title"].strip(),
                "abstract": current["abstract"].strip(),
                "year_published": current["year"].strip(),
                "doi": current["doi"].strip(),
            })

    for raw_line in lines:
        line = raw_line.rstrip("\n")

        # Start of a new record
        if line.startswith("%0 "):
            # push previous record if any
            push_current()
            # reset
            current = {
                "authors": [],
                "title": "",
                "abstract": "",
                "year": "",
                "doi": "",
            }
            in_abstract = False
            continue

        if line.startswith("%A "):
            current["authors"].append(line[3:].strip())
            in_abstract = False
        elif line.startswith("%T "):
            current["title"] = line[3:].strip()
            in_abstract = False
        elif line.startswith("%D "):
            current["year"] = line[3:].strip()
            in_abstract = False
        elif line.startswith("%R "):
            current["doi"] = line[3:].strip()
            in_abstract = False
        elif line.startswith("%X "):
            # start of abstract (may continue onto subsequent lines)
            current["abstract"] = line[3:].strip()
            in_abstract = True
        elif line.startswith("%"):
            # some other field - stop capturing abstract
            in_abstract = False
        else:
            # continuation line: if we are in abstract, add to it
            if in_abstract and line.strip():
                if current["abstract"]:
                    current["abstract"] += " " + line.strip()
                else:
                    current["abstract"] = line.strip()

    # push last record
    push_current()

    df = pd.DataFrame(records)
    return df


# -------------------- SCORING LOGIC -------------------- #

def build_messages(theme: str, title: str, abstract: str):
    """
    Build strict messages so the model returns ONLY an integer 1–10.
    """
    abstract = abstract if isinstance(abstract, str) else ""
    title = title if isinstance(title, str) else ""

    system_msg = (
        "You are an expert in physical activity (PA) research, scoring abstracts for a systematic review. "
        "Score RELEVANCE to the stated theme on a 1–10 integer scale. "
        "Return ONLY the integer (no text, no explanations)."
    )

    user_msg = f"""
Theme:
{theme}

Scoring rubric (return ONLY a single integer 1–10):
10 = Intervention study clearly about physical activity (PA) AND uses a mobile app or wearable tech to measure PA and/or deliver the PA intervention; the abstract provides clear evidence of both.
8–9 = Strong match: intervention on PA with mobile app/wearable clearly present, but details may be limited or mixed; still obviously on-target.
6–7 = Reasonably relevant: PA is targeted and technology is present, but the tech may not be integral to measurement or intervention; or the design is not clearly an intervention.
4–5 = Weak/unclear: mentions PA or mobile/wearable tech but not both; or tech is unrelated to PA; or focus is general health with minimal PA-specific intervention.
2–3 = Barely relevant: tangential reference to PA or to technology, but not used to influence/measure PA; likely not an intervention.
1 = Unrelated to PA intervention and unrelated to mobile/wearable tech for PA measurement or intervention.

Important inclusion points:
- Must involve PA (e.g., steps, MVPA, exercise) AND either:
  (a) use a mobile app/wearable to measure PA, or
  (b) use a mobile app/wearable to deliver an intervention that intends to change PA.

Important exclusions / down-weights:
- Technology unrelated to PA (e.g., general EHRs with no PA measurement/intervention).
- Studies about mental health or surgery, etc., without PA intervention focus.
- Pure observational without intervention AND without mobile/wearable PA measurement.
- Fitness tech mentioned but not used to measure or intervene on PA.

Title: {title or "(no title)"}

Abstract:
{abstract or "(no abstract)"}

Return ONLY a single integer 1–10, nothing else.
""".strip()

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def extract_score(text: str) -> Optional[int]:
    """
    Pull a clean integer 1–10 out of the model's text response.
    """
    if not isinstance(text, str):
        return None
    m = re.search(r"\b(10|[1-9])\b", text.strip())
    if not m:
        return None
    score = int(m.group(1))
    return max(1, min(10, score))


def score_one_article(theme: str, title: str, abstract: str) -> Optional[int]:
    """
    Call the OpenAI API once and return an integer 1–10, or None on failure.
    """
    msgs = build_messages(theme, title, abstract)
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=msgs,
            temperature=TEMPERATURE,
        )
        content = resp.choices[0].message.content
        score = extract_score(content)
        return score
    except Exception as e:
        print(f"Error scoring article: {e}")
        return None


# -------------------- GUI CLASS -------------------- #

class SRAppGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Systematic Review Helper")
        self.root.geometry("1100x700")

        # DataFrame holding articles
        self.df: Optional[pd.DataFrame] = None
        self.current_file: Optional[Path] = None

        # Progress text
        self.progress_var = tk.StringVar(value="Ready.")

        self._build_layout()

    # ---------- Layout ---------- #

    def _build_layout(self):
        # Top frame: file upload + theme
        top = ttk.Frame(self.root, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        # File section
        file_frame = ttk.LabelFrame(top, text="1. Article list", padding=10)
        file_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        upload_btn = ttk.Button(
            file_frame,
            text="Upload EndNote .txt file",
            command=self.on_upload_file,
        )
        upload_btn.pack(anchor="w")

        self.file_label = ttk.Label(
            file_frame, text="No file loaded yet.", foreground="gray"
        )
        self.file_label.pack(anchor="w", pady=(5, 0))

        # Theme section
        theme_frame = ttk.LabelFrame(top, text="2. Research theme / question", padding=10)
        theme_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.theme_text = tk.Text(theme_frame, height=6, wrap="word")
        self.theme_text.pack(fill=tk.BOTH, expand=True)
        self.theme_text.insert("1.0", DEFAULT_THEME)

        # Middle frame: scoring controls
        mid = ttk.Frame(self.root, padding=(10, 0))
        mid.pack(side=tk.TOP, fill=tk.X)

        self.score_btn = ttk.Button(
            mid,
            text="3. Run relevance scoring",
            command=self.on_run_scoring,
            state=tk.DISABLED,  # enabled only after file is parsed
        )
        self.score_btn.pack(side=tk.LEFT)

        export_btn = ttk.Button(
            mid,
            text="Export scored CSV",
            command=self.on_export_csv,
        )
        export_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Progress label
        progress_label = ttk.Label(
            mid,
            textvariable=self.progress_var,
            foreground="blue",
        )
        progress_label.pack(side=tk.RIGHT)

        # Bottom frame: table
        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        columns = ("title", "year", "doi", "score")
        self.tree = ttk.Treeview(
            bottom,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("title", text="Title")
        self.tree.heading("year", text="Year")
        self.tree.heading("doi", text="DOI")
        self.tree.heading("score", text="Relevancy (1–10)")

        self.tree.column("title", width=550, anchor="w")
        self.tree.column("year", width=60, anchor="center")
        self.tree.column("doi", width=260, anchor="w")
        self.tree.column("score", width=110, anchor="center")

        vsb = ttk.Scrollbar(bottom, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

    # ---------- Handlers ---------- #

    def on_upload_file(self):
        file_path = filedialog.askopenfilename(
            title="Select EndNote export .txt file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not file_path:
            return

        path = Path(file_path)
        try:
            self.progress_var.set("Parsing file...")
            self.root.update_idletasks()

            df = parse_endnote_export(path)

            if df.empty:
                messagebox.showwarning(
                    "No records found",
                    "The file was parsed but no valid records were found.\n\n"
                    "Check that it is an EndNote export with %A, %T, %D, %R, %X tags.",
                )
                self.progress_var.set("Ready.")
                return

            self.df = df
            self.current_file = path
            self.file_label.config(text=f"Loaded: {path.name}")
            self.score_btn.config(state=tk.NORMAL)
            self.progress_var.set(f"Parsed {len(df)} articles.")
            self._populate_table()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse file:\n{e}")
            self.progress_var.set("Error while parsing.")

    def _populate_table(self):
        # Clear existing rows
        for row in self.tree.get_children():
            self.tree.delete(row)

        if self.df is None:
            return

        for idx, row in self.df.iterrows():
            title = (row.get("title") or "").strip()
            if len(title) > 150:
                title_display = title[:147] + "..."
            else:
                title_display = title

            year = (row.get("year_published") or "").strip()
            doi = (row.get("doi") or "").strip()
            score = row.get("relevancy_score", "")

            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(title_display, year, doi, score),
            )

    def on_run_scoring(self):
        if self.df is None or self.df.empty:
            messagebox.showwarning("No data", "Please upload and parse an EndNote file first.")
            return

        theme = self.theme_text.get("1.0", "end").strip()
        if not theme:
            theme = DEFAULT_THEME

        n = len(self.df)
        self.progress_var.set(f"Scoring {n} articles...")
        self.root.update_idletasks()

        scores: List[Optional[int]] = []
        failures = 0

        for idx, row in self.df.iterrows():
            title = row.get("title", "")
            abstract = row.get("abstract", "")

            self.progress_var.set(f"Scoring article {idx + 1} / {n} ...")
            self.root.update_idletasks()

            score = score_one_article(theme, title, abstract)
            if score is None:
                failures += 1

            scores.append(score)
            # Update table row as we go
            self.tree.set(str(idx), "score", "" if score is None else str(score))

            # Tiny sleep so the UI doesn't look frozen
            time.sleep(0.1)

        self.df["relevancy_score"] = scores

        if failures:
            self.progress_var.set(
                f"Scoring complete with {failures} failures out of {n} articles."
            )
        else:
            self.progress_var.set("Scoring complete for all articles.")

        messagebox.showinfo(
            "Done",
            f"Relevancy scoring finished.\n\n"
            f"Articles scored: {n}\n"
            f"Failed: {failures}",
        )

    def on_export_csv(self):
        if self.df is None or self.df.empty:
            messagebox.showwarning(
                "No data",
                "There is no data to export yet.\n\nUpload a file and/or run scoring first.",
            )
            return

        save_path = filedialog.asksaveasfilename(
            title="Save scored CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="parsed_articles_scored.csv",
        )
        if not save_path:
            return

        try:
            self.df.to_csv(save_path, index=False, encoding="utf-8")
            messagebox.showinfo("Export complete", f"Saved scored CSV to:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save CSV:\n{e}")


# -------------------- MAIN -------------------- #

def main():
    root = tk.Tk()
    app = SRAppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
