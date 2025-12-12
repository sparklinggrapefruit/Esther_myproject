from __future__ import annotations

import asyncio
import time
import re
from pathlib import Path
from typing import List, Tuple, Optional

import pandas as pd
from openai import AsyncOpenAI
import openai


# -----------------------------
# OpenAI client initialization
# -----------------------------
client: AsyncOpenAI | None = None


def init_openai_client(api_key: str) -> None:
    """
    Initialize the OpenAI Async client once (call this from GUI on app startup).
    """
    global client
    api_key = (api_key or "").strip()

    if not api_key:
        raise ValueError("Empty API key.")

    # Soft validation (helps users catch copy/paste mistakes)
    if not api_key.startswith("sk-"):
        raise ValueError("That doesn't look like an OpenAI API key (should start with 'sk-').")

    client = AsyncOpenAI(api_key=api_key)


def _require_client() -> AsyncOpenAI:
    """
    Ensure the OpenAI client has been initialized before any scoring call.
    """
    if client is None:
        raise RuntimeError(
            "OpenAI client not initialized.\n\n"
            "Please enter your OpenAI API key when the app opens."
        )
    return client


# ---- CONFIG ----
THEME = (
    "Describe your systematic review theme here. "
    "For example: 'Interventions that use mobile health apps to improve physical activity "
    "in adults with chronic conditions.'"
)

MODEL = "gpt-4o-mini"
TEMPERATURE = 0
MAX_RETRIES = 5
SLEEP_BETWEEN_CALLS_SEC = 0.2  # be gentle with rate limits
MAX_CONCURRENT_REQUESTS = 5    # Control concurrency to respect rate limits

DEFAULT_INPUT_CSV = Path("data/parsed_articles.csv")
DEFAULT_OUTPUT_CSV = Path("data/parsed_articles_scored.csv")


def build_messages(theme: str, title: str, abstract: str):
    """
    Create a generic prompt so the model scores relevance to the provided theme (any topic)
    on a 1–10 integer scale and returns ONLY that integer.
    """
    abstract = abstract if isinstance(abstract, str) else ""
    title = title if isinstance(title, str) else ""

    system_msg = (
        "You are an expert researcher assisting with a systematic review. "
        "Given a research theme/question and an article's title and abstract, "
        "score how RELEVANT the article is to that theme on a 1–10 integer scale. "
        "Return ONLY the integer (no text, no explanations). "
        "Use only the information in the title and abstract."
    )

    user_msg = f"""
Research theme / question:
{theme}

Scoring rubric (return ONLY a single integer 1–10):

10 = Extremely strong match. The article is clearly and directly about the theme above;
     the research question, methods, and outcomes are highly aligned.
8–9 = Strong match. The article is clearly related to the theme and substantially focused on it,
       but may be missing some aspects or has a somewhat broader scope.
6–7 = Moderate match. The article is partially about the theme or addresses it as one of several
       topics, but it is not the central focus.
4–5 = Weak match. The article has only a tangential or indirect connection to the theme.
2–3 = Barely related. The article is largely about something else, with only minor overlap.
1   = Unrelated. The article does not meaningfully address the theme above.

Instructions:
- Base your score ONLY on the title and abstract below.
- Interpret "relevance" as how helpful this article would be for a systematic review on the theme.
- Return ONLY a single integer from 1 to 10 with no additional text.

Title: {title or "(no title)"}

Abstract:
{abstract or "(no abstract)"}
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


async def score_one_async(
    title: str,
    abstract: str,
    semaphore: asyncio.Semaphore,
    theme: str
) -> int | None:
    """
    Async scoring of a single article with semaphore for rate limiting
    and robust error handling.
    """
    c = _require_client()

    async with semaphore:
        msgs = build_messages(theme, title, abstract)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await c.chat.completions.create(
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
                msg = str(e).lower()

                # Friendly handling for the most common failures
                if "401" in msg or "invalid_api_key" in msg or "incorrect api key" in msg:
                    print("❌ INVALID API KEY (401).")
                    print("   The provided key is not accepted by OpenAI.")
                    print("   If using a project key (sk-proj-...), ensure billing/model access is enabled.")
                    return None

                if "quota" in msg or "billing" in msg:
                    print("💳 BILLING / QUOTA ERROR.")
                    print("   Check your OpenAI billing status and usage limits.")
                    return None

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
                    print("💳 ASYNC QUOTA/BILLING ERROR:", e)
                    await asyncio.sleep(1.0 * attempt)

                else:
                    print(f"❌ ASYNC attempt {attempt} failed:", e)
                    await asyncio.sleep(0.5 * attempt)

        return None


async def process_batch_async(
    articles: List[Tuple[int, str, str]],
    theme: str
) -> List[Tuple[int, Optional[int]]]:
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


async def main_async(
    theme: str,
    input_csv: Path = DEFAULT_INPUT_CSV,
    output_csv: Path = DEFAULT_OUTPUT_CSV
):
    if not input_csv.exists():
        raise FileNotFoundError(
            f"Could not find {input_csv}. Make sure you created parsed_articles.csv first."
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
    scores = [score for _, score in results]

    end_time = time.time()
    print(f"Async processing completed in {end_time - start_time:.2f} seconds")

    df["relevancy_score"] = scores
    output_csv.parent.mkdir(exist_ok=True, parents=True)
    df.to_csv(output_csv, index=False, encoding="utf-8")

    print(df[["title", "relevancy_score"]].head(10).to_string(index=False))
    print(f"\nSaved {len(df)} rows to {output_csv}")


def run_scoring(
    theme: str,
    input_csv: str | Path = DEFAULT_INPUT_CSV,
    output_csv: str | Path = DEFAULT_OUTPUT_CSV
):
    """
    Synchronous wrapper so we can call scoring from GUI.
    NOTE: Requires init_openai_client(api_key) to have been called already.
    """
    input_csv = Path(input_csv)
    output_csv = Path(output_csv)
    asyncio.run(main_async(theme, input_csv, output_csv))


# NOTE:
# We intentionally do NOT provide a __main__ CLI runner here,
# because the intended workflow is a packaged .exe that prompts for the key on startup.
