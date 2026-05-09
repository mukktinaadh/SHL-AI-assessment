"""
LLM client module for the SHL Assessment Recommender.

Provides:
  - call_gemini()  — Google Gemini `gemini-2.5-flash` (primary)
  - call_groq()    — Groq Llama 3.1 8B Instant (fallback)
  - call_llm()     — Tries Gemini first, falls back to Groq on rate-limit errors

API keys are loaded from environment variables via python-dotenv.
"""

import logging
import os
import time

from dotenv import load_dotenv

# Always load backend/.env regardless of process cwd (e.g. uvicorn started from repo root).
_ENV_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_ENV_DIR, ".env"))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------
def call_gemini(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
) -> str:
    """
    Call Google Gemini (model `gemini-2.5-flash`).

    Args:
        system_prompt: System instructions for the model.
        user_prompt:   User-facing prompt / conversation content.
        temperature:   Sampling temperature (0.2 for classification, 0.4 for generation).

    Returns:
        Model response text as a string.

    Raises:
        google.api_core.exceptions.ResourceExhausted: On rate-limit / quota errors.
        Exception: On any other API error.
    """
    import google.generativeai as genai

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in environment")

    genai.configure(api_key=GEMINI_API_KEY)

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=2048,
        ),
    )

    response = model.generate_content(user_prompt)
    return response.text


# ---------------------------------------------------------------------------
# Groq client
# ---------------------------------------------------------------------------
def call_groq(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> str:
    """
    Call Groq Llama 3.1 8B Instant (fallback LLM).

    Args:
        system_prompt: System instructions for the model.
        user_prompt:   User-facing prompt / conversation content.
        temperature:   Ignored for API call; Groq always uses 0.2 for reliable JSON.

    Returns:
        Model response text as a string.

    Raises:
        groq.RateLimitError: On rate-limit errors.
        Exception: On any other API error.
    """
    from groq import Groq

    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set in environment")

    enforced_system = (
        "You MUST respond with valid JSON only. No markdown. No explanation. "
        "No text before or after the JSON object. "
        "Start your response with { and end with }. "
        "The JSON must have exactly these keys: reply, recommendations, end_of_conversation.\n\n"
        + system_prompt
    )

    client = Groq(api_key=GROQ_API_KEY)

    _ = temperature  # Groq always 0.2 for JSON reliability
    groq_temperature = 0.2

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": enforced_system},
            {"role": "user", "content": user_prompt},
        ],
        temperature=groq_temperature,
        max_tokens=2048,
    )

    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Unified LLM caller with fallback
# ---------------------------------------------------------------------------
def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
) -> str:
    """
    Call the primary LLM (Gemini), falling back to Groq on rate-limit errors.

    Strategy (from PRD Section 8 — Rate-Limit Handling):
      1. Try call_gemini()
      2. On ResourceExhausted / TooManyRequests / RateLimitError → wait 2s → try call_groq()
      3. On all other errors → raise with clear message

    Args:
        system_prompt: System instructions for the model.
        user_prompt:   User-facing prompt / conversation content.
        temperature:   Sampling temperature.

    Returns:
        Model response text as a string.
    """
    # Import rate-limit exception types
    from google.api_core.exceptions import ResourceExhausted, TooManyRequests

    try:
        logger.debug("Calling Gemini gemini-2.5-flash...")
        return call_gemini(system_prompt, user_prompt, temperature)

    except (ResourceExhausted, TooManyRequests) as exc:
        logger.warning("Gemini rate-limited (%s). Waiting 2s then falling back to Groq...", exc)
        time.sleep(2)

    except ValueError:
        # Missing API key — try Groq directly
        logger.warning("GEMINI_API_KEY not set. Falling back to Groq...")

    except Exception as exc:
        # Check if it's a rate-limit-like error by message (catch-all safety net)
        err_msg = str(exc).lower()
        if "rate" in err_msg or "quota" in err_msg or "limit" in err_msg or "429" in err_msg:
            logger.warning("Gemini rate-limit-like error (%s). Falling back to Groq...", exc)
            time.sleep(2)
        else:
            raise RuntimeError(f"Gemini API error (non-rate-limit): {exc}") from exc

    # --- Fallback to Groq ---
    try:
        logger.info("Calling Groq Llama 3.1 8B Instant (fallback)...")
        return call_groq(system_prompt, user_prompt, temperature=0.2)
    except Exception as exc:
        raise RuntimeError(f"Both Gemini and Groq failed. Groq error: {exc}") from exc


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    load_dotenv()

    test_system = "You are a helpful assistant. Reply in one short sentence."
    test_user = "Say hello and tell me what model you are."

    print("=" * 60)
    print("LLM Client Self-Test")
    print("=" * 60)

    # --- Test Gemini ---
    print("\n[1] Testing Gemini gemini-2.5-flash...")
    if GEMINI_API_KEY:
        try:
            result = call_gemini(test_system, test_user)
            print(f"  ✅ Gemini response: {result.strip()}")
        except Exception as e:
            print(f"  ❌ Gemini error: {e}")
    else:
        print("  ⏭️  Skipped — GEMINI_API_KEY not set")

    # --- Test Groq ---
    print("\n[2] Testing Groq Llama 3.1 8B...")
    if GROQ_API_KEY:
        try:
            result = call_groq(test_system, test_user)
            print(f"  ✅ Groq response: {result.strip()}")
        except Exception as e:
            print(f"  ❌ Groq error: {e}")
    else:
        print("  ⏭️  Skipped — GROQ_API_KEY not set")

    # --- Test unified caller ---
    print("\n[3] Testing call_llm() (Gemini → Groq fallback)...")
    if GEMINI_API_KEY or GROQ_API_KEY:
        try:
            result = call_llm(test_system, test_user)
            print(f"  ✅ call_llm response: {result.strip()}")
        except Exception as e:
            print(f"  ❌ call_llm error: {e}")
    else:
        print("  ⏭️  Skipped — no API keys set")

    print("\n" + "=" * 60)
    print("Set GEMINI_API_KEY and/or GROQ_API_KEY in backend/.env to run live tests.")
    print("=" * 60)
