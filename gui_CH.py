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
import threading
import asyncio
from typing import List, Dict, Optional, Tuple

import pandas as pd
from chatgpt_helper import process_batch_async

# -------------------- CONFIG -------------------- #

DEFAULT_THEME = (
    "Looking for articles that examined intervention studies which measure physical activity "
    "and that use mobile apps and/or wearable technology either to measure PA and/or deliver "
    "an intervention intended to influence PA levels."
)


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


# -------------------- ASYNC SCORING WRAPPER -------------------- #

async def process_batch_with_updates(articles: List[Tuple[int, str, str]], 
                                     theme: str,
                                     update_callback) -> List[Tuple[int, Optional[int]]]:
    """
    Process articles with progressive updates via callback.
    """
    from chatgpt_helper import score_one_async, MAX_CONCURRENT_REQUESTS, SLEEP_BETWEEN_CALLS_SEC
    import asyncio
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    async def score_with_update(idx: int, title: str, abstract: str) -> Tuple[int, Optional[int]]:
        score = await score_one_async(title, abstract, semaphore, theme)
        await asyncio.sleep(SLEEP_BETWEEN_CALLS_SEC)
        
        # Call update callback immediately after scoring
        if update_callback:
            update_callback(idx, score)
        
        return (idx, score)
    
    tasks = [score_with_update(idx, title, abstract) for idx, title, abstract in articles]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    processed: List[Tuple[int, Optional[int]]] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"❌ Error processing article {i}: {result}")
            processed.append((i, None))
        else:
            processed.append(result)
    
    return processed

def run_async_scoring(articles: List[Tuple[int, str, str]], theme: str, update_callback=None) -> List[Tuple[int, Optional[int]]]:
    """
    Run async scoring in a new event loop (for background thread).
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(process_batch_with_updates(articles, theme, update_callback))
        return result
    finally:
        loop.close()


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

        # Disable button during scoring
        self.score_btn.config(state=tk.DISABLED)
        
        # Run scoring in background thread
        thread = threading.Thread(target=self._score_articles_async, args=(theme,), daemon=True)
        thread.start()

    def _score_articles_async(self, theme: str):
        """Run async scoring in background thread."""
        n = len(self.df)
        self.root.after(0, lambda: self.progress_var.set(f"Scoring {n} articles asynchronously..."))

        # Prepare articles list
        articles: List[Tuple[int, str, str]] = []
        for idx, row in self.df.iterrows():
            title = row.get("title", "")
            abstract = row.get("abstract", "")
            articles.append((idx, title, abstract))

        # Callback for progressive updates
        def update_score(idx: int, score: Optional[int]):
            self.root.after(0, self._update_single_score, idx, score)

        # Run async scoring with callback
        results = run_async_scoring(articles, theme, update_callback=update_score)

        # Process results
        results.sort(key=lambda x: x[0])
        scores = [score for idx, score in results]
        failures = sum(1 for s in scores if s is None)

        self.df["relevancy_score"] = scores

        # Finalize
        self.root.after(0, self._scoring_complete, n, failures)

    def _update_single_score(self, idx: int, score: Optional[int]):
        """Update a single score in the table as it completes (must be called from main thread)."""
        self.tree.set(str(idx), "score", "" if score is None else str(score))
        # Auto-scroll to show the most recently scored item
        self.tree.see(str(idx))

    def _scoring_complete(self, total: int, failures: int):
        """Finalize scoring (must be called from main thread)."""
        self.score_btn.config(state=tk.NORMAL)
        
        if failures:
            self.progress_var.set(
                f"Scoring complete with {failures} failures out of {total} articles."
            )
        else:
            self.progress_var.set("Scoring complete for all articles.")

        messagebox.showinfo(
            "Done",
            f"Relevancy scoring finished.\n\n"
            f"Articles scored: {total}\n"
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
