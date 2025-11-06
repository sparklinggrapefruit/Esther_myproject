import sys, os, threading, time, re
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
import pandas as pd
from tkinter import Tk, Text, StringVar, IntVar, END, DISABLED, NORMAL
from tkinter import filedialog, messagebox
from tkinter import ttk

from openai import OpenAI
from keys import open_ai_api_key

# ============ CONFIG ============
MODEL = "gpt-4o-mini"
TEMPERATURE = 0
MAX_RETRIES = 3
SLEEP_BETWEEN_CALLS_SEC = 0.2  # be gentle with rate limits

client = OpenAI(api_key=open_ai_api_key)

# ============ PARSER (same logic you used) ============
TAGS = {
    "%A": "authors",          # repeats
    "%T": "title",
    "%D": "year_published",
    "%X": "abstract",         # multi-line continuation allowed
    "%R": "doi",
    "%0": "_start",
}

def parse_exportlist(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    records, current, last_field = [], None, None

    def finalize():
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
        if len(line) >= 3 and line.startswith("%") and line[2] == " ":
            tag, value = line[:2], line[3:].strip()

            if tag == "%0":
                finalize()
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
                m = re.search(r"\b(\d{4})\b", value)
                current["year_published"] = m.group(1) if m else value
                last_field = "year_published"
            else:
                if field in current and current[field]:
                    current[field] += " " + value
                else:
                    current[field] = value
                last_field = field
        else:
            if current is not None and last_field in {"abstract", "title"}:
                current[last_field] = (current.get(last_field, "") + " " + line).strip()

    finalize()
    return pd.DataFrame.from_records(records, columns=["authors", "title", "abstract", "year published", "DOI"])

# ============ GPT SCORING ============
def build_messages(theme: str, title: str, abstract: str):
    abstract = abstract if isinstance(abstract, str) else ""
    system_msg = (
        "You are an expert reviewer scoring abstracts for a systematic review. "
        "Score RELEVANCE to the stated theme on a 1-10 integer scale. "
        "Return ONLY the integer (no text, no explanations)."
    )
    user_msg = f"""
Theme:
{theme}

Scoring rubric (return ONLY a single integer 1-10):
10 = Intervention study clearly about physical activity (PA) AND uses a mobile app or wearable tech to measure PA and/or deliver the PA intervention.
8–9 = Strong match: PA intervention with mobile app/wearable clearly present.
6–7 = Reasonably relevant: PA is targeted and technology is present, but tech may not be integral; or design not clearly an intervention.
4–5 = Weak/unclear: mentions PA or mobile/wearable tech but not both; or tech unrelated to PA.
2–3 = Barely relevant: tangential reference to PA or to technology for PA.
1 = Unrelated to PA intervention and unrelated to mobile/wearable tech for PA measurement/intervention.

Title: {title or "(no title)"}

Abstract:
{abstract or "(no abstract)"}

Return ONLY a single integer 1-10, nothing else.
""".strip()

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

def extract_score(text: str):
    if not isinstance(text, str):
        return None
    m = re.search(r"\b(10|[1-9])\b", text.strip())
    if not m:
        return None
    score = int(m.group(1))
    return max(1, min(10, score))

def score_one(theme: str, title: str, abstract: str):
    msgs = build_messages(theme, title, abstract)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=msgs,
                temperature=TEMPERATURE,
            )
            content = resp.choices[0].message.content
            score = extract_score(content)
            if score is not None:
                return score
        except Exception:
            pass
        time.sleep(0.5 * attempt)
    return None

# ============ GUI APP ============
class SysRevGUI:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("SysRev – Abstract Scorer")
        self.root.geometry("780x620")

        # State vars
        self.file_path_var = StringVar(value="")
        self.theme_var = StringVar(value="Looking for intervention studies that measure physical activity and use mobile apps and/or wearable tech to measure PA or deliver an intervention to change PA levels.")
        self.limit_rows_var = IntVar(value=0)  # 0 = no limit
        self.df = None

        # Layout
        pad = {"padx": 10, "pady": 8}

        frm = ttk.Frame(root)
        frm.pack(fill="both", expand=True)

        # File selection
        ttk.Label(frm, text="1) Select export .txt file").grid(row=0, column=0, sticky="w", **pad)
        file_row = ttk.Frame(frm)
        file_row.grid(row=1, column=0, sticky="ew", **pad)
        file_row.columnconfigure(1, weight=1)
        ttk.Button(file_row, text="Browse...", command=self.choose_file).grid(row=0, column=0, sticky="w")
        self.file_entry = ttk.Entry(file_row, textvariable=self.file_path_var)
        self.file_entry.grid(row=0, column=1, sticky="ew", padx=8)

        # Theme text
        ttk.Label(frm, text="2) Enter research question / theme").grid(row=2, column=0, sticky="w", **pad)
        self.theme_box = Text(frm, height=4, wrap="word")
        self.theme_box.grid(row=3, column=0, sticky="ew", **pad)
        self.theme_box.insert("1.0", self.theme_var.get())

        # Options
        opt_row = ttk.Frame(frm)
        opt_row.grid(row=4, column=0, sticky="w", **pad)
        ttk.Label(opt_row, text="(Optional) Limit to first N rows for a quick test:").grid(row=0, column=0, sticky="w")
        self.limit_entry = ttk.Entry(opt_row, width=7, textvariable=self.limit_rows_var)
        self.limit_entry.grid(row=0, column=1, sticky="w", padx=6)

        # Buttons
        btn_row = ttk.Frame(frm)
        btn_row.grid(row=5, column=0, sticky="w", **pad)
        ttk.Button(btn_row, text="Parse Only", command=self.parse_only).grid(row=0, column=0, padx=0)
        ttk.Button(btn_row, text="Parse + Score", command=self.parse_and_score).grid(row=0, column=1, padx=10)
        ttk.Button(btn_row, text="Export CSV", command=self.export_csv).grid(row=0, column=2, padx=0)

        # Progress
        ttk.Label(frm, text="Progress").grid(row=6, column=0, sticky="w", **pad)
        self.progress = ttk.Progressbar(frm, orient="horizontal", mode="determinate")
        self.progress.grid(row=7, column=0, sticky="ew", **pad)

        # Log
        ttk.Label(frm, text="Log").grid(row=8, column=0, sticky="w", **pad)
        self.log = Text(frm, height=12, wrap="word")
        self.log.grid(row=9, column=0, sticky="nsew", **pad)
        frm.rowconfigure(9, weight=1)
        frm.columnconfigure(0, weight=1)

        self._set_style()

    def _set_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

    def choose_file(self):
        fp = filedialog.askopenfilename(
            title="Select export .txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if fp:
            self.file_path_var.set(fp)

    def parse_only(self):
        if not self._validate_file():
            return
        self._disable_ui()
        threading.Thread(target=self._do_parse, daemon=True).start()

    def parse_and_score(self):
        if not self._validate_file():
            return
        # get theme
        theme = self.theme_box.get("1.0", END).strip()
        if not theme:
            messagebox.showwarning("Missing Theme", "Please enter a research question / theme.")
            return
        self.theme_var.set(theme)
        self._disable_ui()
        threading.Thread(target=self._do_parse_and_score, args=(theme,), daemon=True).start()

    def export_csv(self):
        if self.df is None or self.df.empty:
            messagebox.showinfo("Nothing to export", "No data loaded yet.")
            return
        out = filedialog.asksaveasfilename(
            title="Save CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="parsed_articles_scored.csv" if "relevancy_score" in self.df.columns else "parsed_articles.csv",
        )
        if out:
            self.df.to_csv(out, index=False, encoding="utf-8")
            self._log(f"Saved: {out}")

    # ---------- workers ----------
    def _do_parse(self):
        try:
            self._log("Parsing started…")
            df = parse_exportlist(self.file_path_var.get())
            n = int(self.limit_rows_var.get() or 0)
            if n > 0:
                df = df.head(n)
                self._log(f"Limited to first {n} rows for testing.")
            self.df = df
            self.progress["value"] = 100
            self._log(f"Parsing complete. Rows: {len(df)}")
        except Exception as e:
            messagebox.showerror("Parse Error", str(e))
        finally:
            self._enable_ui()

    def _do_parse_and_score(self, theme: str):
        try:
            self._log("Parsing started…")
            df = parse_exportlist(self.file_path_var.get())
            n = int(self.limit_rows_var.get() or 0)
            if n > 0:
                df = df.head(n)
                self._log(f"Limited to first {n} rows for testing.")

            total = len(df)
            if total == 0:
                self._log("No rows found in file.")
                self._enable_ui()
                return

            self.progress["value"] = 0
            self.progress["maximum"] = total

            scores = []
            for i, row in df.iterrows():
                t = row.get("title", "")
                a = row.get("abstract", "")
                s = score_one(theme, t, a)
                scores.append(s)
                self.progress["value"] = len(scores)
                self._log(f"[{len(scores)}/{total}] {('OK' if s is not None else 'None')} — {t[:80]}")
                self.root.update_idletasks()
                time.sleep(SLEEP_BETWEEN_CALLS_SEC)

            df["relevancy_score"] = scores
            self.df = df
            self._log("Scoring complete.")
        except Exception as e:
            messagebox.showerror("Scoring Error", str(e))
        finally:
            self._enable_ui()

    # ---------- helpers ----------
    def _validate_file(self):
        p = self.file_path_var.get().strip()
        if not p:
            messagebox.showwarning("No file", "Please choose an export .txt file.")
            return False
        if not Path(p).exists():
            messagebox.showerror("Not found", f"File not found:\n{p}")
            return False
        return True

    def _disable_ui(self):
        self._set_inputs_state(DISABLED)

    def _enable_ui(self):
        self._set_inputs_state(NORMAL)

    def _set_inputs_state(self, state):
        # buttons and entries
        try:
            for w in [self.file_entry, self.theme_box, self.limit_entry]:
                w.configure(state=state)
        except Exception:
            pass

    def _log(self, msg: str):
        self.log.insert(END, msg + "\n")
        self.log.see(END)

def main():
    root = Tk()
    app = SysRevGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
