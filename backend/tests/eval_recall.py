#!/usr/bin/env python3
"""
Recall@10 evaluation script for the SHL Assessment Recommender.

Replays conversation traces against the live POST /chat endpoint,
compares final recommendations against expected shortlists, and
computes per-trace and mean Recall@10.

Trace JSON format:
{
    "id": "trace_001",
    "description": "Java developer hiring",
    "turns": [
        {"role": "user", "content": "I need a Java developer assessment"}
    ],
    "expected": [
        "Core Java (Advanced Level) (New)",
        "Java 8 (New)",
        "Java Frameworks (New)"
    ]
}

Usage:
    python eval_recall.py --traces ./test_traces --endpoint http://localhost:8000

Target: Mean Recall@10 >= 0.7

Source: PRD Section 16 (Testing Strategy), Appendix (Recall@K Definition)
"""

import argparse
import json
import os
import sys
import time

import requests


# ---------------------------------------------------------------------------
# Recall@K computation
# ---------------------------------------------------------------------------
def recall_at_k(recommended: list[str], expected: list[str], k: int = 10) -> float:
    """
    Compute Recall@K.

    Recall@K = |recommended ∩ expected| / |expected|

    Names are compared case-insensitively with whitespace normalization.

    Args:
        recommended: List of assessment names returned by the agent.
        expected:    List of assessment names from the trace's ground truth.
        k:          Maximum number of recommendations to consider.

    Returns:
        Float between 0.0 and 1.0.
    """
    if not expected:
        return 1.0  # no expected items → trivially satisfied

    # Normalize names for comparison
    def normalize(name: str) -> str:
        return " ".join(name.strip().lower().split())

    rec_set = {normalize(n) for n in recommended[:k]}
    exp_set = {normalize(n) for n in expected}

    matches = rec_set & exp_set
    recall = len(matches) / len(exp_set)

    return recall


# ---------------------------------------------------------------------------
# Trace replay
# ---------------------------------------------------------------------------
def replay_trace(
    trace: dict,
    endpoint: str,
    max_turns: int = 8,
    verbose: bool = True,
) -> dict:
    """
    Replay a conversation trace against the /chat endpoint.

    Sends user turns from the trace one at a time, accumulating the full
    history (stateless API — full history sent each request).

    Stops when:
      - All user turns in the trace are exhausted
      - end_of_conversation == True in the response
      - max_turns reached

    Args:
        trace:     Trace dict with keys: id, turns, expected.
        endpoint:  Base URL of the API (e.g., http://localhost:8000).
        max_turns: Maximum number of turns before forced stop.
        verbose:   Print turn-by-turn details.

    Returns:
        Dict with keys: trace_id, recommendations, expected, recall, turns_used, error.
    """
    trace_id = trace.get("id", "unknown")
    user_turns = [t for t in trace["turns"] if t["role"] == "user"]
    expected = trace.get("expected", [])

    messages = []  # accumulated conversation history
    final_recs = []
    turns_used = 0
    error = None

    chat_url = f"{endpoint.rstrip('/')}/chat"

    for turn_idx, user_turn in enumerate(user_turns):
        if turns_used >= max_turns:
            if verbose:
                print(f"    ⚠️  Max turns ({max_turns}) reached — stopping")
            break

        # Add user message to history
        messages.append({"role": "user", "content": user_turn["content"]})
        turns_used += 1

        if verbose:
            print(f"    Turn {turns_used} [User]: {user_turn['content'][:80]}...")

        # Call the API
        try:
            resp = requests.post(
                chat_url,
                json={"messages": messages},
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            error = str(exc)
            if verbose:
                print(f"    ❌ API error: {error}")
            break

        reply = data.get("reply", "")
        recs = data.get("recommendations", [])
        eoc = data.get("end_of_conversation", False)

        if verbose:
            print(f"    Turn {turns_used} [Agent]: {reply[:80]}...")
            if recs:
                print(f"    → {len(recs)} recommendations returned")

        # Add assistant reply to history
        messages.append({"role": "assistant", "content": reply})

        # Capture recommendations (always use the latest)
        if recs:
            final_recs = recs

        # Check end of conversation
        if eoc:
            if verbose:
                print(f"    ✅ Agent signaled end_of_conversation")
            break

        # Small delay between turns
        time.sleep(0.5)

    # If we exhausted all user turns but got no recommendations, try once more
    # with a forced "please recommend now" message (mimics evaluator behavior)
    if not final_recs and turns_used < max_turns and not error:
        messages.append({"role": "user", "content": "Please give me your recommendations now."})
        turns_used += 1

        if verbose:
            print(f"    Turn {turns_used} [User]: (forced) Please give me your recommendations now.")

        try:
            resp = requests.post(
                chat_url,
                json={"messages": messages},
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            recs = data.get("recommendations", [])
            if recs:
                final_recs = recs
                if verbose:
                    print(f"    → {len(recs)} recommendations returned (forced)")
        except Exception as exc:
            error = str(exc)

    # Extract recommendation names
    rec_names = [r.get("name", "") for r in final_recs]

    # Compute Recall@10
    recall = recall_at_k(rec_names, expected, k=10)

    return {
        "trace_id": trace_id,
        "recommendations": rec_names,
        "expected": expected,
        "recall": recall,
        "turns_used": turns_used,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def load_traces(traces_dir: str) -> list[dict]:
    """Load all JSON trace files from a directory."""
    traces = []
    if not os.path.isdir(traces_dir):
        print(f"❌ Traces directory not found: {traces_dir}")
        sys.exit(1)

    for filename in sorted(os.listdir(traces_dir)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(traces_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            trace = json.load(f)
        # Ensure required fields
        if "turns" not in trace:
            print(f"  ⚠️  Skipping {filename}: missing 'turns' field")
            continue
        if "id" not in trace:
            trace["id"] = os.path.splitext(filename)[0]
        traces.append(trace)

    return traces


def main():
    parser = argparse.ArgumentParser(
        description="Recall@10 evaluation for SHL Assessment Recommender"
    )
    parser.add_argument(
        "--traces",
        required=True,
        help="Path to directory containing trace JSON files",
    )
    parser.add_argument(
        "--endpoint",
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress turn-by-turn output",
    )
    args = parser.parse_args()

    # Load traces
    traces = load_traces(args.traces)
    print(f"Loaded {len(traces)} traces from {args.traces}")

    if not traces:
        print("No traces found. Exiting.")
        sys.exit(1)

    # Check endpoint health
    try:
        health = requests.get(f"{args.endpoint}/health", timeout=10)
        health.raise_for_status()
        print(f"Endpoint {args.endpoint} is healthy ✅")
    except Exception as exc:
        print(f"❌ Cannot reach {args.endpoint}/health: {exc}")
        print("   Make sure the server is running: uvicorn main:app --port 8000")
        sys.exit(1)

    print()
    print("=" * 70)
    print(f"{'Trace ID':<25s} {'Turns':>5s} {'Recs':>4s} {'Expected':>8s} {'Recall@10':>10s}")
    print("=" * 70)

    results = []
    for trace in traces:
        verbose = not args.quiet
        if verbose:
            print(f"\n  ▶ Trace: {trace['id']} — {trace.get('description', '')}")

        result = replay_trace(trace, args.endpoint, verbose=verbose)
        results.append(result)

        status = "✅" if result["recall"] >= 0.7 else "⚠️ " if result["recall"] > 0 else "❌"
        print(
            f"  {status} {result['trace_id']:<23s} "
            f"{result['turns_used']:>5d} "
            f"{len(result['recommendations']):>4d} "
            f"{len(result['expected']):>8d} "
            f"{result['recall']:>10.2%}"
        )

        if result["error"]:
            print(f"     Error: {result['error']}")

    # Summary
    recalls = [r["recall"] for r in results]
    mean_recall = sum(recalls) / len(recalls) if recalls else 0.0

    print()
    print("=" * 70)
    print(f"  Mean Recall@10:  {mean_recall:.2%}")
    print(f"  Target:          ≥ 70.00%")
    print(f"  Status:          {'✅ PASS' if mean_recall >= 0.7 else '❌ BELOW TARGET'}")
    print(f"  Traces evaluated: {len(results)}")
    print("=" * 70)

    # Exit with non-zero if below target
    sys.exit(0 if mean_recall >= 0.7 else 1)


if __name__ == "__main__":
    main()
