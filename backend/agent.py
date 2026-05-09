"""
Agent orchestration for the SHL Assessment Recommender.

Provides:
  - classify_intent()          — LLM-based intent classification
  - validate_recommendations() — Anti-hallucination URL whitelist filter
  - generate_response()        — LLM response generation with catalog grounding
  - run_agent()                — Full pipeline: classify → retrieve → generate

Source: PRD Section 8, Section 14 Steps 6, 8, 9.
"""

import json
import logging
import re

from llm import call_llm
from prompts import (
    AGENT_SYSTEM_TEMPLATE,
    INTENT_CLASSIFIER_SYSTEM,
    REFUSE_REPLY,
    TASK_CLARIFY,
    TASK_COMPARE,
    TASK_RECOMMEND,
    TASK_REFINE,
    format_messages,
)
from retriever import retrieve
from schemas import ChatRequest, ChatResponse, Recommendation

logger = logging.getLogger(__name__)

VALID_INTENTS = {"CLARIFY", "RECOMMEND", "REFINE", "COMPARE", "REFUSE"}

# Max turns before forcing a recommendation (PRD: 8 turns max, force by turn 7)
FORCE_RECOMMEND_THRESHOLD = 7


# ---------------------------------------------------------------------------
# 1. Intent classifier
# ---------------------------------------------------------------------------
def classify_intent(messages: list) -> str:
    """
    Classify the user's intent from conversation history.

    Uses the INTENT_CLASSIFIER_SYSTEM prompt with temperature=0.1
    (low temperature for deterministic classification).

    Args:
        messages: List of message dicts or Pydantic Message objects.

    Returns:
        One of: CLARIFY, RECOMMEND, REFINE, COMPARE, REFUSE.
        Defaults to CLARIFY if the LLM output is unexpected.
    """
    conversation = format_messages(messages)

    try:
        raw = call_llm(
            system_prompt=INTENT_CLASSIFIER_SYSTEM,
            user_prompt=conversation,
            temperature=0.1,
        )
        intent = raw.strip().upper()

        # Strip any extra text the LLM might add
        # Take only the first word in case of "RECOMMEND - because..."
        intent = intent.split()[0] if intent else "CLARIFY"
        # Remove any punctuation
        intent = re.sub(r"[^A-Z]", "", intent)

        if intent in VALID_INTENTS:
            logger.info("Intent classified: %s", intent)
            return intent

        logger.warning("Unexpected intent '%s' from LLM, defaulting to CLARIFY", intent)
        return "CLARIFY"

    except Exception as exc:
        logger.error("Intent classification failed: %s. Defaulting to CLARIFY", exc)
        return "CLARIFY"


# ---------------------------------------------------------------------------
# 2. Anti-hallucination: URL whitelist validation
# ---------------------------------------------------------------------------
def validate_recommendations(
    recs: list[dict],
    catalog: list[dict],
) -> list[dict]:
    """
    Filter recommendations against the catalog URL whitelist.

    Every recommendation URL must exist in catalog.json. Any entry with
    a fabricated or mismatched URL is dropped and logged as a warning.

    Args:
        recs:    List of recommendation dicts (name, url, test_type).
        catalog: The full catalog list loaded from catalog.json.

    Returns:
        Filtered list containing only catalog-grounded recommendations.
    """
    # Build URL whitelist for fast lookup
    valid_urls = {item["url"] for item in catalog if item.get("url")}

    # Also build a name→url map for fuzzy recovery
    name_to_item = {}
    for item in catalog:
        name_lower = item.get("name", "").strip().lower()
        if name_lower:
            name_to_item[name_lower] = item

    validated = []
    for rec in recs:
        url = rec.get("url", "")
        name = rec.get("name", "")

        if url in valid_urls:
            validated.append(rec)
            continue

        # Fuzzy recovery: if the URL is wrong but the name matches a catalog item,
        # substitute the correct URL from the catalog
        name_lower = name.strip().lower()
        if name_lower in name_to_item:
            correct = name_to_item[name_lower]
            logger.warning(
                "Recommendation '%s' had wrong URL '%s' — corrected to '%s'",
                name, url, correct["url"],
            )
            rec["url"] = correct["url"]
            # Also fix test_type if needed
            if correct.get("test_type"):
                test_type = correct["test_type"]
                rec["test_type"] = ", ".join(test_type) if isinstance(test_type, list) else test_type
            validated.append(rec)
            continue

        # No match at all — drop it
        logger.warning(
            "DROPPED hallucinated recommendation: name='%s' url='%s' (not in catalog)",
            name, url,
        )

    if len(validated) < len(recs):
        logger.info(
            "Validation: kept %d of %d recommendations (%d dropped)",
            len(validated), len(recs), len(recs) - len(validated),
        )

    return validated


# ---------------------------------------------------------------------------
# 3. Response generation
# ---------------------------------------------------------------------------
def _build_catalog_context(retrieved_docs: list[dict]) -> str:
    """Format retrieved documents into a catalog context string for the prompt."""
    if not retrieved_docs:
        return "(No matching assessments found in catalog)"

    lines = []
    for i, doc in enumerate(retrieved_docs, 1):
        lines.append(
            f"{i}. {doc['name']}\n"
            f"   URL: {doc['url']}\n"
            f"   Test Type: {doc.get('test_type', '')}\n"
            f"   Description: {doc.get('description', 'N/A')}\n"
            f"   Job Levels: {doc.get('job_levels', '')}"
        )
    return "\n\n".join(lines)


def _select_task_instruction(intent: str) -> str:
    """Select the task instruction string based on classified intent."""
    return {
        "CLARIFY": TASK_CLARIFY,
        "RECOMMEND": TASK_RECOMMEND,
        "REFINE": TASK_REFINE,
        "COMPARE": TASK_COMPARE,
    }.get(intent, TASK_CLARIFY)


def _parse_llm_json(raw: str) -> dict:
    """
    Parse JSON from LLM output, handling markdown fences and common issues.

    The LLM may wrap output in ```json ... ``` fences, or include trailing
    text after the JSON object. This function handles all those cases.
    """
    text = raw.strip()

    # 1. Try to extract a JSON block enclosed in markdown fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    else:
        # 2. Fallback: extract from the first '{' to the last '}'
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM JSON output: %s\nRaw output: %s", exc, raw[:500])
        return {}


def generate_response(
    messages: list,
    intent: str,
    retrieved_docs: list[dict],
    catalog: list[dict],
) -> ChatResponse:
    """
    Generate a ChatResponse by calling the LLM with catalog-grounded context.

    Steps:
      1. Build catalog_context string from retrieved_docs
      2. Select task instruction based on intent
      3. Fill AGENT_SYSTEM_TEMPLATE and call LLM
      4. Parse JSON from response
      5. Validate recommendation URLs against catalog
      6. Return ChatResponse

    Args:
        messages:       Conversation history.
        intent:         Classified intent (CLARIFY, RECOMMEND, REFINE, COMPARE).
        retrieved_docs: Retrieved assessment dicts from ChromaDB.
        catalog:        Full catalog list for URL validation.

    Returns:
        ChatResponse with reply, recommendations, and end_of_conversation flag.
    """
    catalog_context = _build_catalog_context(retrieved_docs)
    task_instruction = _select_task_instruction(intent)
    conversation = format_messages(messages)

    # Build the full system prompt
    system_prompt = AGENT_SYSTEM_TEMPLATE.format(
        catalog_context=catalog_context,
        messages=conversation,
        task_instruction=task_instruction,
    )

    # Temperature: 0.2 for classification-like tasks, 0.4 for generation
    temperature = 0.3 if intent == "CLARIFY" else 0.4

    try:
        raw = call_llm(
            system_prompt=system_prompt,
            user_prompt=conversation,
            temperature=temperature,
        )
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return ChatResponse(
            reply="I'm having trouble processing your request right now. Could you try again?",
            recommendations=[],
            end_of_conversation=False,
        )

    # --- Parse response based on intent ---
    if intent in ("RECOMMEND", "REFINE"):
        parsed = _parse_llm_json(raw)
        if not parsed:
            # Fallback: use raw text as reply with no recommendations
            return ChatResponse(
                reply=raw.strip()[:1000],
                recommendations=[],
                end_of_conversation=False,
            )

        reply = parsed.get("reply", "Here are my recommendations:")
        raw_recs = parsed.get("recommendations", [])
        eoc = parsed.get("end_of_conversation", False)

        # Validate each recommendation against catalog
        valid_recs = validate_recommendations(raw_recs, catalog)

        # Convert to Recommendation models (cap at 10)
        recommendations = [
            Recommendation(
                name=r.get("name", ""),
                url=r.get("url", ""),
                test_type=r.get("test_type", ""),
            )
            for r in valid_recs[:10]
        ]

        return ChatResponse(
            reply=reply,
            recommendations=recommendations,
            end_of_conversation=eoc,
        )

    elif intent == "COMPARE":
        # Comparison: return text reply, optionally with the compared assessments
        return ChatResponse(
            reply=raw.strip(),
            recommendations=[],
            end_of_conversation=False,
        )

    else:
        # CLARIFY or fallback: plain text reply, no recommendations
        return ChatResponse(
            reply=raw.strip(),
            recommendations=[],
            end_of_conversation=False,
        )


# ---------------------------------------------------------------------------
# 4. Full agent pipeline
# ---------------------------------------------------------------------------
def _synthesize_query(messages: list) -> str:
    """
    Synthesize a search query from the full conversation history.

    Extracts key signals (role, skills, level) from user messages
    to form a focused retrieval query.
    """
    user_messages = []
    for msg in messages:
        role = msg.role if hasattr(msg, "role") else msg.get("role", "")
        content = msg.content if hasattr(msg, "content") else msg.get("content", "")
        if role == "user":
            user_messages.append(content)

    # Combine all user messages — most recent first for recency bias
    return " ".join(reversed(user_messages))


def _extract_comparison_names(last_message: str) -> list[str]:
    """
    Extract assessment names from a comparison request.

    Looks for patterns like "compare X and Y" or "difference between X and Y".
    """
    # Try to find names in quotes first
    quoted = re.findall(r'"([^"]+)"', last_message)
    if len(quoted) >= 2:
        return quoted[:2]

    # Try "between X and Y" pattern
    between_match = re.search(
        r"(?:between|compare)\s+(.+?)\s+(?:and|vs\.?|versus)\s+(.+?)(?:\?|$|\.)",
        last_message,
        re.IGNORECASE,
    )
    if between_match:
        return [between_match.group(1).strip(), between_match.group(2).strip()]

    # Fallback: just use the whole message as query
    return []


def run_agent(
    request: ChatRequest,
    catalog: list[dict],
    collection,
) -> ChatResponse:
    """
    Full agent pipeline: classify → retrieve → generate.

    Flow (from PRD Section 14 Step 9):
      1. Classify intent from messages
      2. If REFUSE → return hardcoded refusal, empty recommendations
      3. If CLARIFY → retrieve with short query, generate clarifying question
      4. If RECOMMEND or REFINE → retrieve top 20, generate shortlist
      5. If COMPARE → retrieve both assessment names, generate comparison
      6. Hard cap: if messages >= 7, force RECOMMEND

    Args:
        request:    ChatRequest with conversation messages.
        catalog:    Full catalog list (for URL validation).
        collection: ChromaDB collection (for retrieval).

    Returns:
        ChatResponse with reply, recommendations, and end_of_conversation flag.
    """
    messages = request.messages

    # --- Step 1: Classify intent ---
    intent = classify_intent(messages)

    # --- Hard cap: force recommendation near turn limit ---
    if len(messages) >= FORCE_RECOMMEND_THRESHOLD and intent not in ("REFUSE", "COMPARE"):
        logger.info(
            "Turn count (%d) >= %d — forcing RECOMMEND intent",
            len(messages), FORCE_RECOMMEND_THRESHOLD,
        )
        intent = "RECOMMEND"

    # --- Step 2: REFUSE ---
    if intent == "REFUSE":
        logger.info("Refusing off-topic query")
        return ChatResponse(
            reply=REFUSE_REPLY,
            recommendations=[],
            end_of_conversation=False,
        )

    # --- Step 3: CLARIFY ---
    if intent == "CLARIFY":
        query = _synthesize_query(messages)
        retrieved = retrieve(collection, query, n=10) if query.strip() else []
        return generate_response(messages, intent, retrieved, catalog)

    # --- Step 4: RECOMMEND or REFINE ---
    if intent in ("RECOMMEND", "REFINE"):
        query = _synthesize_query(messages)
        retrieved = retrieve(collection, query, n=20)
        return generate_response(messages, intent, retrieved, catalog)

    # --- Step 5: COMPARE ---
    if intent == "COMPARE":
        last_msg = messages[-1]
        last_content = last_msg.content if hasattr(last_msg, "content") else last_msg.get("content", "")

        names = _extract_comparison_names(last_content)

        # Retrieve both assessments by name
        retrieved = []
        if names:
            for name in names:
                results = retrieve(collection, name, n=3)
                retrieved.extend(results)
        else:
            # Fallback: use the full message as query
            retrieved = retrieve(collection, last_content, n=10)

        # Deduplicate by URL
        seen_urls = set()
        deduped = []
        for doc in retrieved:
            if doc["url"] not in seen_urls:
                seen_urls.add(doc["url"])
                deduped.append(doc)
        retrieved = deduped

        return generate_response(messages, intent, retrieved, catalog)

    # Fallback (should never reach here)
    logger.warning("Unexpected intent '%s' in run_agent — falling back to CLARIFY", intent)
    return generate_response(messages, "CLARIFY", [], catalog)


# ---------------------------------------------------------------------------
# Self-test (no LLM calls — tests helpers only)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")

    print("=" * 60)
    print("Agent module self-test (helper functions only)")
    print("=" * 60)

    # Test _synthesize_query
    test_messages = [
        {"role": "user", "content": "I need an assessment"},
        {"role": "assistant", "content": "What role?"},
        {"role": "user", "content": "Mid-level Java developer"},
    ]
    query = _synthesize_query(test_messages)
    assert "Java" in query
    assert "assessment" in query
    print("  ✅ _synthesize_query works")

    # Test _extract_comparison_names
    assert _extract_comparison_names('Compare "OPQ32r" and "MQ"') == ["OPQ32r", "MQ"]
    assert _extract_comparison_names("What's the difference between OPQ32r and Verify G+?") == ["OPQ32r", "Verify G+"]
    print("  ✅ _extract_comparison_names works")

    # Test _parse_llm_json
    raw_json = '```json\n{"reply": "Here", "recommendations": [{"name": "Test", "url": "https://x.com", "test_type": "K"}]}\n```'
    parsed = _parse_llm_json(raw_json)
    assert parsed["reply"] == "Here"
    assert len(parsed["recommendations"]) == 1
    print("  ✅ _parse_llm_json (with fences) works")

    raw_json2 = 'Sure! {"reply": "OK", "recommendations": []} extra text'
    parsed2 = _parse_llm_json(raw_json2)
    assert parsed2["reply"] == "OK"
    print("  ✅ _parse_llm_json (with surrounding text) works")

    # Test validate_recommendations
    fake_catalog = [
        {"name": "Java 8 (New)", "url": "https://shl.com/java-8", "test_type": ["K"]},
        {"name": "OPQ32r", "url": "https://shl.com/opq32r", "test_type": ["P"]},
    ]
    recs = [
        {"name": "Java 8 (New)", "url": "https://shl.com/java-8", "test_type": "K"},
        {"name": "FAKE TEST", "url": "https://fake.com/test", "test_type": "X"},
        {"name": "OPQ32r", "url": "https://wrong-url.com", "test_type": "P"},  # wrong URL but valid name
    ]
    valid = validate_recommendations(recs, fake_catalog)
    assert len(valid) == 2  # Java 8 passes, FAKE dropped, OPQ32r URL corrected
    assert valid[0]["url"] == "https://shl.com/java-8"
    assert valid[1]["url"] == "https://shl.com/opq32r"  # URL was corrected
    print("  ✅ validate_recommendations: keeps valid, drops hallucinated, corrects wrong URLs")

    # Test _build_catalog_context
    ctx = _build_catalog_context([
        {"name": "Test A", "url": "https://x.com/a", "test_type": "K", "description": "Desc A", "job_levels": "Entry"},
    ])
    assert "Test A" in ctx
    assert "https://x.com/a" in ctx
    print("  ✅ _build_catalog_context works")

    # Test _select_task_instruction
    assert "clarify" in _select_task_instruction("CLARIFY").lower() or "question" in _select_task_instruction("CLARIFY").lower()
    assert "JSON" in _select_task_instruction("RECOMMEND")
    print("  ✅ _select_task_instruction works")

    print(f"\n{'=' * 60}")
    print("✅ All agent helper tests passed (no LLM calls made)")
    print(f"{'=' * 60}")
