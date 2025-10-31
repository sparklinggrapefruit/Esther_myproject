# docs_folder/chatgpt_helper_CH_threaded.py
from __future__ import annotations

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openai import OpenAI
import openai
from keys import open_ai_api_key

from pathlib import Path
import re
import time
import pandas as pd
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional

# ---- CONFIG ----
THEME = (
    "You are a physical activities (PA) researcher conducting a systematic review. "  # CH
    "Looking for articles that examined intervention studies which measure physical activity "
    "and that use mobile apps and/or wearable technology either to measure PA or to deliver an "
    "intervention intended to influence PA levels."
)
MODEL = "gpt-4o-mini"
#MODEL = "gpt-3.5-turbo" # maybe faster and cheaper
TEMPERATURE = 0
MAX_RETRIES = 5
SLEEP_BETWEEN_CALLS_SEC = 1.0  # 1 second between calls to be very conservative
MAX_WORKERS = 5  # Only 3 concurrent threads for safety
INPUT_CSV = Path(__file__).parent / "parsed_articles.csv"
OUTPUT_CSV = Path(__file__).parent / "parsed_articles_scored.csv"

# Thread-safe client
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
    Thread-safe version with rate limit detection.
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
                # Add small delay to be gentle with rate limits
                time.sleep(SLEEP_BETWEEN_CALLS_SEC)
                return score
        except openai.RateLimitError as e:
            print(f"⚠️  RATE LIMIT ERROR: OpenAI is throttling requests!")
            print(f"   Error details: {e}")
            print(f"   Consider reducing MAX_WORKERS ({MAX_WORKERS}) or increasing SLEEP_BETWEEN_CALLS_SEC ({SLEEP_BETWEEN_CALLS_SEC})")
            # Longer backoff for rate limits
            backoff_time = 3.0 * attempt
            print(f"   Backing off for {backoff_time:.1f} seconds before retry {attempt + 1}/{MAX_RETRIES}")
            time.sleep(backoff_time)
        except openai.APIError as e:
            if "quota" in str(e).lower() or "billing" in str(e).lower():
                print(f"💳 QUOTA/BILLING ERROR: {e}")
                print("   Check your OpenAI account billing and usage limits")
            else:
                print(f"🔧 API ERROR (attempt {attempt}): {e}")
            time.sleep(1.0 * attempt)
        except Exception as e:
            # Check for specific OpenAI rate limit errors
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                print(f"⚠️  RATE LIMIT WARNING: OpenAI is throttling requests! Error: {e}")
                print(f"   Consider reducing MAX_WORKERS or increasing SLEEP_BETWEEN_CALLS_SEC")
                # Longer backoff for rate limits
                backoff_time = 2.0 * attempt
                print(f"   Backing off for {backoff_time:.1f} seconds...")
                time.sleep(backoff_time)
            elif "quota" in error_str or "billing" in error_str:
                print(f"💳 QUOTA ERROR: {e}")
                print("   Check your OpenAI account billing and usage limits")
                time.sleep(1.0 * attempt)
            else:
                print(f"❌ Attempt {attempt} failed: {e}")
                time.sleep(0.5 * attempt)  # standard backoff
        
    return None

def score_article_with_index(article_data: Tuple[int, str, str]) -> Tuple[int, Optional[int]]:
    """
    Score a single article and return (index, score) tuple.
    """
    idx, title, abstract = article_data
    score = score_one(title, abstract)
    return (idx, score)

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

    # Prepare articles for processing
    articles = []
    for idx, row in df.iterrows():
        t = row.get(title_col, "")
        a = row.get(abstract_col, "")
        articles.append((idx, t, a))

    print(f"Processing {len(articles)} articles with {MAX_WORKERS} threads...")
    start_time = time.time()
    
    # Process articles using ThreadPoolExecutor
    scores = [None] * len(df)  # Pre-allocate scores list
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_article = {}
        for article in articles:
            future = executor.submit(score_article_with_index, article)
            future_to_article[future] = article
        
        # Collect results as they complete
        completed = 0
        for future in as_completed(future_to_article):
            try:
                idx, score = future.result()
                scores[idx] = score
                completed += 1
                # Show progress every 10 articles AND for the last few articles
                if completed % 10 == 0 or completed > len(articles) - 5:
                    elapsed_time = time.time() - start_time
                    rate = completed / elapsed_time if elapsed_time > 0 else 0
                    eta = (len(articles) - completed) / rate if rate > 0 else 0
                    print(f"Completed {completed}/{len(articles)} articles... "
                          f"Time elapsed: {elapsed_time:.1f}s, "
                          f"Rate: {rate:.1f} articles/sec, "
                          f"ETA: {eta:.1f}s")
            except Exception as e:
                print(f"Error processing article: {e}")

    end_time = time.time()
    print(f"Threaded processing completed in {end_time - start_time:.2f} seconds")

    df["relevancy_score"] = scores
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    print(df[["title", "relevancy_score"]].head(10).to_string(index=False))
    print(f"\nSaved {len(df)} rows to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()