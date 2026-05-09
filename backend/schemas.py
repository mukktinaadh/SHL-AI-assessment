"""
Pydantic v2 schemas for the SHL Assessment Recommender API.

Models:
  - Message:        A single conversation turn (user or assistant).
  - ChatRequest:    Incoming POST /chat payload.
  - Recommendation: A single assessment recommendation.
  - ChatResponse:   Outgoing POST /chat response.

Schema is non-negotiable — deviations fail the automated evaluator.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class Message(BaseModel):
    """A single message in the conversation history."""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """
    POST /chat request body.

    Constraints (from PRD Section 10):
      - messages must contain at least 1 message
      - messages must alternate user/assistant
      - Last message must be from user
      - Max 8 messages total (enforced by service layer, not schema)
    """

    messages: list[Message] = Field(..., min_length=1)

    @field_validator("messages")
    @classmethod
    def last_message_must_be_user(cls, v: list[Message]) -> list[Message]:
        if v[-1].role != "user":
            raise ValueError("Last message must be from user role")
        return v


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class Recommendation(BaseModel):
    """A single assessment recommendation grounded in the SHL catalog."""

    name: str
    url: str
    test_type: str


class ChatResponse(BaseModel):
    """
    POST /chat response body.

    Constraints (from PRD Section 10):
      - reply is always a non-empty string
      - recommendations is always [] OR array of 1–10 objects. Never null.
      - end_of_conversation signals whether the agent considers the task done
    """

    reply: str
    recommendations: list[Recommendation] = Field(default_factory=list)
    end_of_conversation: bool = False

    @field_validator("recommendations")
    @classmethod
    def recommendations_length(cls, v: list[Recommendation]) -> list[Recommendation]:
        if v is None:
            raise ValueError("recommendations must not be null")
        if len(v) > 10:
            raise ValueError(
                f"recommendations must contain at most 10 items, got {len(v)}"
            )
        return v


# ---------------------------------------------------------------------------
# Self-tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from pydantic import ValidationError

    passed = 0
    failed = 0

    def ok(label: str):
        global passed
        passed += 1
        print(f"  ✅ {label}")

    def fail(label: str, err: str):
        global failed
        failed += 1
        print(f"  ❌ {label}: {err}")

    print("Running schema validation tests...\n")

    # --- Message ---
    print("[Message]")
    try:
        Message(role="user", content="hello")
        ok("Valid user message")
    except Exception as e:
        fail("Valid user message", str(e))

    try:
        Message(role="assistant", content="hi there")
        ok("Valid assistant message")
    except Exception as e:
        fail("Valid assistant message", str(e))

    try:
        Message(role="system", content="nope")  # type: ignore
        fail("Invalid role rejected", "should have raised")
    except ValidationError:
        ok("Invalid role rejected")

    # --- ChatRequest ---
    print("\n[ChatRequest]")
    try:
        ChatRequest(messages=[Message(role="user", content="hi")])
        ok("Single user message")
    except Exception as e:
        fail("Single user message", str(e))

    try:
        ChatRequest(
            messages=[
                Message(role="user", content="hi"),
                Message(role="assistant", content="hello"),
                Message(role="user", content="help me"),
            ]
        )
        ok("Multi-turn conversation")
    except Exception as e:
        fail("Multi-turn conversation", str(e))

    try:
        ChatRequest(messages=[])  # type: ignore
        fail("Empty messages rejected", "should have raised")
    except ValidationError:
        ok("Empty messages rejected")

    try:
        ChatRequest(
            messages=[
                Message(role="user", content="hi"),
                Message(role="assistant", content="bye"),
            ]
        )
        fail("Last message=assistant rejected", "should have raised")
    except ValidationError:
        ok("Last message=assistant rejected")

    try:
        ChatRequest(messages=[Message(role="assistant", content="only assistant")])
        fail("Single assistant message rejected", "should have raised")
    except ValidationError:
        ok("Single assistant message rejected")

    # --- Recommendation ---
    print("\n[Recommendation]")
    try:
        Recommendation(name="OPQ32r", url="https://shl.com/opq32r", test_type="P")
        ok("Valid recommendation")
    except Exception as e:
        fail("Valid recommendation", str(e))

    # --- ChatResponse ---
    print("\n[ChatResponse]")
    try:
        ChatResponse(reply="Here are some options", recommendations=[], end_of_conversation=False)
        ok("Empty recommendations list")
    except Exception as e:
        fail("Empty recommendations list", str(e))

    try:
        ChatResponse(
            reply="Found these",
            recommendations=[
                Recommendation(name=f"Test {i}", url=f"https://shl.com/t{i}", test_type="K")
                for i in range(10)
            ],
            end_of_conversation=True,
        )
        ok("10 recommendations (max)")
    except Exception as e:
        fail("10 recommendations (max)", str(e))

    try:
        ChatResponse(
            reply="Too many",
            recommendations=[
                Recommendation(name=f"Test {i}", url=f"https://shl.com/t{i}", test_type="K")
                for i in range(11)
            ],
        )
        fail("11 recommendations rejected", "should have raised")
    except ValidationError:
        ok("11 recommendations rejected")

    try:
        resp = ChatResponse(reply="Clarifying question")
        assert resp.recommendations == [], "default should be empty list"
        assert resp.end_of_conversation is False, "default should be False"
        ok("Defaults (empty recs, eoc=False)")
    except Exception as e:
        fail("Defaults", str(e))

    # --- Summary ---
    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 40}")
    exit(1 if failed else 0)
