from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from parser import parse_exportlist
from chatgpt_helper import run_scoring, THEME as DEFAULT_THEME


class SysRevGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SysRev – Systematic Review Assistant")
        self.root.geometry("800x600")

        self.file_path_var = tk.StringVar(value="")
        self.theme_var = tk.StringVar(value=DEFAULT_THEME)

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 8}

        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)

        # 1) File selection
        ttk.Label(main, text="1) Select exported .txt file").grid(
            row=0, column=0, sticky="w", **pad
        )

        file_row = ttk.Frame(main)
        file_row.grid(row=1, column=0, sticky="ew", **pad)
        file_row.columnconfigure(1, weight=1)

        ttk.Button(file_row, text="Browse…", command=self.choose_file).grid(
            row=0, column=0, sticky="w"
        )
        self.file_entry = ttk.Entry(file_row, textvariable=self.file_path_var)
        self.file_entry.grid(row=0, column=1, sticky="ew", padx=8)

        # 2) Theme / research question
        ttk.Label(main, text="2) Research theme / inclusion criteria").grid(
            row=2, column=0, sticky="w", **pad
        )

        self.theme_text = tk.Text(main, height=5, wrap="word")
        self.theme_text.grid(row=3, column=0, sticky="nsew", **pad)
        self.theme_text.insert("1.0", self.theme_var.get())

        # Buttons
        btn_row = ttk.Frame(main)
        btn_row.grid(row=4, column=0, sticky="w", **pad)

        ttk.Button(btn_row, text="Run Parse + Score", command=self.run_pipeline).grid(
            row=0, column=0, padx=0
        )

        ttk.Button(btn_row, text="Quit", command=self.root.destroy).grid(
            row=0, column=1, padx=10
        )

        # Log output
        ttk.Label(main, text="Log").grid(row=5, column=0, sticky="w", **pad)
        self.log = tk.Text(main, height=15, wrap="word")
        self.log.grid(row=6, column=0, sticky="nsew", **pad)

        main.rowconfigure(3, weight=1)
        main.rowconfigure(6, weight=2)
        main.columnconfigure(0, weight=1)

    def choose_file(self):
        fp = filedialog.askopenfilename(
            title="Select export .txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=str(Path("data").absolute())
        )
        if fp:
            self.file_path_var.set(fp)

    def run_pipeline(self):
        txt_path = self.file_path_var.get().strip()
        if not txt_path:
            messagebox.showwarning("No file", "Please choose an export .txt file first.")
            return

        txt_path = Path(txt_path)
        if not txt_path.exists():
            messagebox.showerror("File not found", f"Could not find:\n{txt_path}")
            return

        theme = self.theme_text.get("1.0", "end").strip()
        if not theme:
            messagebox.showwarning("No theme", "Please enter a research theme.")
            return

        self._log(f"Parsing file:\n{txt_path}")
        try:
            df = parse_exportlist(txt_path, Path("data/parsed_articles.csv"))
        except Exception as e:
            messagebox.showerror("Parse error", str(e))
            self._log(f"Parse error: {e}")
            return

        self._log(f"Parsed {len(df)} articles into data/parsed_articles.csv")

        # scoring may take some time; GUI will freeze briefly – acceptable for now
        self._log("Starting scoring with ChatGPT… this may take a bit.")
        self.root.update_idletasks()

        try:
            run_scoring(theme, Path("data/parsed_articles.csv"), Path("data/parsed_articles_scored.csv"))
        except Exception as e:
            messagebox.showerror("Scoring error", str(e))
            self._log(f"Scoring error: {e}")
            return

        self._log("Scoring complete. Output saved to data/parsed_articles_scored.csv")
        messagebox.showinfo(
            "Done",
            "Parsing + scoring finished.\n\n"
            "Results saved as data/parsed_articles_scored.csv",
        )

    def _log(self, msg: str):
        self.log.insert("end", msg + "\n")
        self.log.see("end")


def main():
    root = tk.Tk()
    app = SysRevGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()