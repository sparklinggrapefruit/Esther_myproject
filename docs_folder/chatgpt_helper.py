
# docs_folder/chatgpt_helper.py
from __future__ import annotations

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openai import OpenAI
from keys import open_ai_api_key

from pathlib import Path
import re
import time
import pandas as pd

# ---- CONFIG ----
THEME = (
    "Looking for articles that examined intervention studies which measure physical activity "
    "and that use mobile apps and/or wearable technology either to measure PA or to deliver an "
    "intervention intended to influence PA levels."
)
MODEL = "gpt-4o-mini"
TEMPERATURE = 0
MAX_RETRIES = 3
SLEEP_BETWEEN_CALLS_SEC = 0.2  # be gentle with rate limits
INPUT_CSV = Path(__file__).parent / "parsed_articles.csv"
OUTPUT_CSV = Path(__file__).parent / "parsed_articles_scored.csv"

client = OpenAI(api_key=open_ai_api_key)

def build_messages(theme: str, title: str, abstract: str):
    """
    Create a strict prompt so the model returns ONLY an integer 1-10.
    """
    # Guard against None/NaN abstracts
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

Return ONLY a single integer 1-10, nothing else.
""".strip()

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

def extract_score(text: str) -> int | None:
    """
    Pull a clean integer 1-10 out of the model's text response.
    """
    if not isinstance(text, str):
        return None
    m = re.search(r"\b(10|[1-9])\b", text.strip())
    if not m:
        return None
    score = int(m.group(1))
    # Clamp just in case
    return max(1, min(10, score))

def score_one(title: str, abstract: str) -> int | None:
    """
    Call the API with retries; return an int 1-10 or None on failure.
    """
    msgs = build_messages(THEME, title, abstract)
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
        except Exception as e:
            # You could log e here if desired
            pass
        time.sleep(0.5 * attempt)  # simple backoff
    return None

def main():
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Could not find {INPUT_CSV}. Make sure you ran app.py to create it.")

    df = pd.read_csv(INPUT_CSV)

    # Expecting columns: authors, title, abstract, year published, DOI
    # If your capitalization differs, adjust here:
    title_col = "title"
    abstract_col = "abstract"

    if title_col not in df.columns or abstract_col not in df.columns:
        raise ValueError(f"CSV must contain '{title_col}' and '{abstract_col}' columns. Found: {df.columns.tolist()}")

    scores = []
    for idx, row in df.iterrows():
        t = row.get(title_col, "")
        a = row.get(abstract_col, "")
        s = score_one(t, a)
        scores.append(s)
        time.sleep(SLEEP_BETWEEN_CALLS_SEC)

    df["relevancy_score"] = scores
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    print(df[["title", "relevancy_score"]].head(10).to_string(index=False))
    print(f"\nSaved {len(df)} rows to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()



