
from __future__ import annotations

import asyncio
import time
import re
from pathlib import Path
from typing import List, Tuple, Optional

import pandas as pd
from openai import AsyncOpenAI
import openai

from config_loader import get_api_key



# ---- CONFIG ----
THEME = (
    "You are a behavioral medicine researcher conducting a systematic review. "
    "Looking for articles that examined intervention studies which measure physical activity "
    "and that use mobile apps and/or wearable technology either to measure PA or to deliver an "
    "intervention intended to influence PA levels."
)

MODEL = "gpt-4o-mini"
TEMPERATURE = 0
MAX_RETRIES = 5
SLEEP_BETWEEN_CALLS_SEC = 0.2  # be gentle with rate limits
MAX_CONCURRENT_REQUESTS = 5    # Control concurrency to respect rate limits

DEFAULT_INPUT_CSV = Path("data/parsed_articles.csv")
DEFAULT_OUTPUT_CSV = Path("data/parsed_articles_scored.csv")

client = AsyncOpenAI(api_key=get_api_key())


def build_messages(theme: str, title: str, abstract: str):
    """
    Create a strict prompt so the model returns ONLY an integer 1-10.
    """
    abstract = abstract if isinstance(abstract, str) else ""

    system_msg = (
        "You are an expert in physical activity (PA), scoring abstracts for a systematic review. "
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
    return max(1, min(10, score))


async def score_one_async(title: str,
                          abstract: str,
                          semaphore: asyncio.Semaphore,
                          theme: str) -> int | None:
    """
    Async scoring of a single article with semaphore for rate limiting
    and robust error handling.
    """
    async with semaphore:
        msgs = build_messages(theme, title, abstract)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.chat.completions.create(
                    model=MODEL,
                    messages=msgs,
                    temperature=TEMPERATURE,
                )
                content = resp.choices[0].message.content
                score = extract_score(content)
                if score is not None:
                    return score

            except openai.RateLimitError as e:
                print("⚠️ ASYNC RATE LIMIT ERROR:", e)
                backoff_time = 3.0 * attempt
                print(f"   Backing off for {backoff_time:.1f}s (attempt {attempt}/{MAX_RETRIES})")
                await asyncio.sleep(backoff_time)

            except openai.APIError as e:
                if "quota" in str(e).lower() or "billing" in str(e).lower():
                    print("💳 ASYNC QUOTA/BILLING ERROR:", e)
                    print("   Check your OpenAI account billing and usage limits.")
                else:
                    print(f"🔧 ASYNC API ERROR (attempt {attempt}): {e}")
                await asyncio.sleep(1.0 * attempt)

            except Exception as e:
                error_str = str(e).lower()
                if "rate limit" in error_str or "429" in error_str:
                    print("⚠️ ASYNC RATE LIMIT WARNING:", e)
                    backoff_time = 2.0 * attempt
                    print(f"   Backing off for {backoff_time:.1f}s...")
                    await asyncio.sleep(backoff_time)
                elif "quota" in error_str or "billing" in error_str:
                    print("💳 ASYNC QUOTA ERROR:", e)
                    print("   Check your OpenAI account billing and usage limits.")
                    await asyncio.sleep(1.0 * attempt)
                else:
                    print(f"❌ ASYNC attempt {attempt} failed:", e)
                    await asyncio.sleep(0.5 * attempt)

        return None


async def process_batch_async(articles: List[Tuple[int, str, str]],
                              theme: str) -> List[Tuple[int, Optional[int]]]:
    """
    Process a batch of articles asynchronously.
    articles: List of (index, title, abstract)
    Returns: List of (index, score)
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    start_time = time.time()
    completed = 0

    async def score_with_index(idx: int, title: str, abstract: str) -> Tuple[int, Optional[int]]:
        nonlocal completed
        score = await score_one_async(title, abstract, semaphore, theme)
        await asyncio.sleep(SLEEP_BETWEEN_CALLS_SEC)

        completed += 1
        if completed % 10 == 0 or completed > len(articles) - 5:
            elapsed_time = time.time() - start_time
            rate = completed / elapsed_time if elapsed_time > 0 else 0
            eta = (len(articles) - completed) / rate if rate > 0 else 0
            print(
                f"ASYNC Completed {completed}/{len(articles)} articles... "
                f"Time elapsed: {elapsed_time:.1f}s, "
                f"Rate: {rate:.1f} articles/s, "
                f"ETA: {eta:.1f}s"
            )

        return (idx, score)

    tasks = [score_with_index(idx, title, abstract) for idx, title, abstract in articles]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed: List[Tuple[int, Optional[int]]] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"❌ ASYNC error processing article {i}: {result}")
            processed.append((i, None))
        else:
            processed.append(result)

    return processed


async def main_async(theme: str,
                     input_csv: Path = DEFAULT_INPUT_CSV,
                     output_csv: Path = DEFAULT_OUTPUT_CSV):
    if not input_csv.exists():
        raise FileNotFoundError(
            f"Could not find {input_csv}. Make sure you ran parser.py to create it."
        )

    df = pd.read_csv(input_csv)

    title_col = "title"
    abstract_col = "abstract"

    if title_col not in df.columns or abstract_col not in df.columns:
        raise ValueError(
            f"CSV must contain '{title_col}' and '{abstract_col}' columns. "
            f"Found: {df.columns.tolist()}"
        )

    articles: List[Tuple[int, str, str]] = []
    for idx, row in df.iterrows():
        t = row.get(title_col, "")
        a = row.get(abstract_col, "")
        articles.append((idx, t, a))

    print(f"Processing {len(articles)} articles asynchronously...")
    start_time = time.time()

    results = await process_batch_async(articles, theme)

    results.sort(key=lambda x: x[0])
    scores = [score for idx, score in results]

    end_time = time.time()
    print(f"Async processing completed in {end_time - start_time:.2f} seconds")

    df["relevancy_score"] = scores
    output_csv.parent.mkdir(exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8")

    print(df[["title", "relevancy_score"]].head(10).to_string(index=False))
    print(f"\nSaved {len(df)} rows to {output_csv}")


def run_scoring(theme: str,
                input_csv: str | Path = DEFAULT_INPUT_CSV,
                output_csv: str | Path = DEFAULT_OUTPUT_CSV):
    """
    Synchronous wrapper so we can call scoring from GUI or CLI.
    """
    input_csv = Path(input_csv)
    output_csv = Path(output_csv)
    asyncio.run(main_async(theme, input_csv, output_csv))


if __name__ == "__main__":
    # CLI usage: just uses the default THEME
    run_scoring(THEME)
