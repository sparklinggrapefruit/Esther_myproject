"""
Simple Tkinter GUI for your systematic review helper (.exe friendly).

Workflow:
1) App launches -> prompts for OpenAI API key (one-time) and saves it locally next to the .exe
2) Upload EndNote .txt export
3) Enter theme
4) Run relevance scoring (writes scored CSV)
5) Export CSV
"""

from __future__ import annotations

import sys
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from typing import List, Dict, Optional

import pandas as pd

# Local storage next to exe
from config_loader import load_api_key, save_api_key

# Async scoring engine (your module)
from chatgpt_helper import init_openai_client, run_scoring


# -------------------- Paths (exe-friendly) -------------------- #

def app_dir() -> Path:
    """
    Directory containing the .exe (PyInstaller) or this script (dev).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    d = app_dir() / "data"
    d.mkdir(exist_ok=True)
    return d


# -------------------- API Key Prompt (on launch) -------------------- #

def prompt_for_api_key(root: tk.Tk) -> str | None:
    """
    Get API key from storage next to exe; if missing, prompt user once and save it.
    """
    key = load_api_key()
    if key:
        return key

    key = simpledialog.askstring(
        "OpenAI API Key Required",
        "Paste your OpenAI API key to enable relevance scoring.\n\n"
        "• Starts with sk- or sk-proj-\n"
        "• Saved locally next to this app (not uploaded)\n",
        show="*",
        parent=root,
    )
    if not key:
        return None

    key = key.strip()
    save_api_key(key)
    return key


# -------------------- PARSING LOGIC -------------------- #

def parse_endnote_export(path: Path) -> pd.DataFrame:
    """
    Parse EndNote-style export list (.txt) where:
      %A = author (repeat)
      %T = title
      %D = year
      %R = doi/url
      %X = abstract (can span multiple lines)
      %0 = start new record
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    records: List[Dict[str, object]] = []
    current = {"authors": [], "title": "", "abstract": "", "year": "", "doi": ""}
    in_abstract = False

    def push_current():
        if current["authors"] or current["title"] or current["abstract"] or current["year"] or current["doi"]:
            records.append({
                "authors": "; ".join(current["authors"]),
                "title": str(current["title"]).strip(),
                "abstract": str(current["abstract"]).strip(),
                "year_published": str(current["year"]).strip(),
                "doi": str(current["doi"]).strip(),
            })

    for raw_line in lines:
        line = raw_line.rstrip("\n")

        if line.startswith("%0 "):
            push_current()
            current = {"authors": [], "title": "", "abstract": "", "year": "", "doi": ""}
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
            current["abstract"] = line[3:].strip()
            in_abstract = True
        elif line.startswith("%"):
            in_abstract = False
        else:
            if in_abstract and line.strip():
                current["abstract"] = (str(current["abstract"]) + " " + line.strip()).strip()

    push_current()
    return pd.DataFrame(records)


# -------------------- GUI CLASS -------------------- #

class SRAppGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Systematic Review Helper")
        self.root.geometry("1100x700")

        self.df: Optional[pd.DataFrame] = None
        self.current_file: Optional[Path] = None
        self.progress_var = tk.StringVar(value="Ready.")

        # Thread state
        self._scoring_thread: threading.Thread | None = None
        self._cancel_requested: bool = False

        self._build_layout()
        self._build_menu()

    # ---------- UI Helpers ---------- #

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        settings = tk.Menu(menubar, tearoff=0)
        settings.add_command(label="Change API Key", command=self.on_change_api_key)
        menubar.add_cascade(label="Settings", menu=settings)
        self.root.config(menu=menubar)

    def _build_layout(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        file_frame = ttk.LabelFrame(top, text="1. Article list", padding=10)
        file_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        upload_btn = ttk.Button(
            file_frame,
            text="Upload EndNote .txt file",
            command=self.on_upload_file,
        )
        upload_btn.pack(anchor="w")

        self.file_label = ttk.Label(file_frame, text="No file loaded yet.", foreground="gray")
        self.file_label.pack(anchor="w", pady=(5, 0))

        theme_frame = ttk.LabelFrame(top, text="2. Research theme / question", padding=10)
        theme_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.theme_text = tk.Text(theme_frame, height=6, wrap="word")
        self.theme_text.pack(fill=tk.BOTH, expand=True)

        mid = ttk.Frame(self.root, padding=(10, 0))
        mid.pack(side=tk.TOP, fill=tk.X)

        self.score_btn = ttk.Button(
            mid,
            text="3. Run relevance scoring",
            command=self.on_run_scoring,
            state=tk.DISABLED,
        )
        self.score_btn.pack(side=tk.LEFT)

        self.cancel_btn = ttk.Button(
            mid,
            text="Cancel scoring",
            command=self.on_cancel_scoring,
            state=tk.DISABLED,
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=(10, 0))

        export_btn = ttk.Button(mid, text="Export scored CSV", command=self.on_export_csv)
        export_btn.pack(side=tk.LEFT, padx=(10, 0))

        progress_label = ttk.Label(mid, textvariable=self.progress_var, foreground="blue")
        progress_label.pack(side=tk.RIGHT)

        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        columns = ("title", "year", "doi", "score")
        self.tree = ttk.Treeview(bottom, columns=columns, show="headings", selectmode="browse")
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

    def _set_ui_scoring_state(self, running: bool):
        if running:
            self.score_btn.config(state=tk.DISABLED)
            self.cancel_btn.config(state=tk.NORMAL)
        else:
            can_score = self.df is not None and not self.df.empty
            self.score_btn.config(state=tk.NORMAL if can_score else tk.DISABLED)
            self.cancel_btn.config(state=tk.DISABLED)

    def _populate_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        if self.df is None:
            return

        for idx, row in self.df.iterrows():
            title = (row.get("title") or "").strip()
            title_display = title[:147] + "..." if len(title) > 150 else title
            year = (row.get("year_published") or "").strip()
            doi = (row.get("doi") or "").strip()
            score = row.get("relevancy_score", "")

            self.tree.insert("", "end", iid=str(idx), values=(title_display, year, doi, score))

    # ---------- Handlers ---------- #

    def on_change_api_key(self):
        key = simpledialog.askstring(
            "Change OpenAI API Key",
            "Paste your new OpenAI API key:",
            show="*",
            parent=self.root,
        )
        if not key:
            return

        key = key.strip()
        try:
            save_api_key(key)
            init_openai_client(key)
            messagebox.showinfo("Updated", "API key updated and saved locally.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not update API key:\n{e}")

    def on_cancel_scoring(self):
        self._cancel_requested = True
        self.progress_var.set("Cancel requested… finishing current requests.")
        self.root.update_idletasks()

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
                    "Parsed file but no valid records found.\n\n"
                    "Check that it is an EndNote export with %A, %T, %D, %R, %X tags.",
                )
                self.progress_var.set("Ready.")
                return

            self.df = df
            self.current_file = path
            self.file_label.config(text=f"Loaded: {path.name}")
            self.progress_var.set(f"Parsed {len(df)} articles.")
            self._populate_table()
            self.score_btn.config(state=tk.NORMAL)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse file:\n{e}")
            self.progress_var.set("Error while parsing.")

    def on_run_scoring(self):
        if self.df is None or self.df.empty:
            messagebox.showwarning("No data", "Please upload and parse an EndNote file first.")
            return

        theme = self.theme_text.get("1.0", "end").strip()
        if not theme:
            messagebox.showwarning("Missing theme", "Please enter a research theme/question before scoring.")
            return

        # Prevent starting twice
        if self._scoring_thread and self._scoring_thread.is_alive():
            messagebox.showinfo("Scoring already running", "Scoring is already in progress.")
            return

        # Save input CSV where scorer expects it
        input_csv = data_dir() / "parsed_articles.csv"
        output_csv = data_dir() / "parsed_articles_scored.csv"
        self.df.to_csv(input_csv, index=False, encoding="utf-8")

        self._cancel_requested = False
        self._set_ui_scoring_state(True)
        self.progress_var.set("Scoring… (running in background)")
        self.root.update_idletasks()

        def worker():
            try:
                # This keeps the GUI responsive.
                # Note: true mid-run cancel requires chatgpt_helper to support it.
                run_scoring(theme, input_csv, output_csv)

                # Load results
                scored = pd.read_csv(output_csv)

                def on_success():
                    self.df = scored
                    self._populate_table()
                    self.progress_var.set("Scoring complete.")
                    self._set_ui_scoring_state(False)
                    messagebox.showinfo("Done", f"Saved scored CSV to:\n{output_csv}")

                self.root.after(0, on_success)

            except Exception as e:
                err = f"{e}\n\n{traceback.format_exc()}"

                def on_fail():
                    self.progress_var.set("Scoring failed.")
                    self._set_ui_scoring_state(False)
                    messagebox.showerror("Error", f"Scoring failed:\n{err}")

                self.root.after(0, on_fail)

        self._scoring_thread = threading.Thread(target=worker, daemon=True)
        self._scoring_thread.start()

    def on_export_csv(self):
        if self.df is None or self.df.empty:
            messagebox.showwarning("No data", "No data to export yet.")
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

    # Prompt immediately on launch
    key = prompt_for_api_key(root)
    if not key:
        messagebox.showinfo("Exit", "No API key provided. Exiting.")
        root.destroy()
        return

    # Initialize the OpenAI client used by chatgpt_helper.py
    try:
        init_openai_client(key)
    except Exception as e:
        messagebox.showerror("OpenAI Error", f"Could not initialize API client:\n{e}")
        root.destroy()
        return

    app = SRAppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
