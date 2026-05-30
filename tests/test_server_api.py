import asyncio

import pytest
from fastapi.testclient import TestClient

from server import (
    ConversationInsight,
    _insight_needs_context,
    app,
    classify_conversation_intent,
    classify_intent,
    is_identity_query,
    model_routing_advice,
)


def test_health_endpoint():
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    json = r.json()
    assert json.get("status") == "online"


@pytest.mark.parametrize(
    ("text", "expected_category", "expected_emotion"),
    [
        ("I need help planning my week and prioritizing tasks", "PLANNING", "neutral"),
        ("Please remind me tomorrow morning", "REMINDERS", "neutral"),
        ("Can you check my calendar for next week?", "CALENDAR", "neutral"),
        ("I need to organize my notes for class", "NOTES", "neutral"),
        ("Find research sources for my project", "RESEARCH", "neutral"),
        ("My code is throwing a traceback in Python", "DEBUGGING", "neutral"),
        ("Open the settings and lower the brightness", "SYSTEM_CONTROL", "neutral"),
        ("Move this report into the project folder", "FILE_MANAGEMENT", "neutral"),
        ("Mujhe kal ke meeting ke baare mein yaad dilao", "CALENDAR", "neutral"),
        ("Main thak gaya hu aur kaafi stress me hu", "EMOTIONAL_SUPPORT", "fatigue"),
        ("I'm feeling frustrated and confused about this bug", "DEBUGGING", "frustration"),
        ("Can you translate this sentence to Hindi?", "TRANSLATION", "neutral"),
    ],
)
def test_conversation_intelligence_fallback_categories(text, expected_category, expected_emotion):
    insight = asyncio.run(classify_conversation_intent(text, None, []))
    assert insight.category == expected_category
    assert insight.emotion == expected_emotion
    assert insight.assistant_mode
    assert insight.confidence > 0


@pytest.mark.parametrize(
    ("insight", "section", "expected"),
    [
        (ConversationInsight(category="CODING", use_project_history=True), "project", True),
        (ConversationInsight(category="CALENDAR", required_systems=["calendar"]), "calendar", True),
        (ConversationInsight(category="EMAIL", required_systems=["email"]), "mail", True),
        (ConversationInsight(category="DEBUGGING", required_systems=["screen_analysis"]), "screen", True),
        (ConversationInsight(category="GENERAL_CHAT"), "memory", False),
    ],
)
def test_insight_context_selection(insight, section, expected):
    assert _insight_needs_context(insight, section) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("who are you", True),
        ("what are you doing", False),
        ("tera creator kaun hai", True),
        ("tell me your name", True),
    ],
)
def test_identity_query_detection(text, expected):
    assert is_identity_query(text) is expected


def test_model_routing_advice_warns_on_small_model():
    warning = model_routing_advice("phi3:mini")
    assert warning is not None
    assert "too small" in warning.lower()


def test_model_routing_advice_accepts_recommended_model():
    assert model_routing_advice("qwen2.5:7b") is None


def test_classify_intent_keeps_conversation_fields():
    result = asyncio.run(classify_intent("main thak gaya hu", None))
    assert result["action"] == "chat"
    assert result["category"] == "EMOTIONAL_SUPPORT"
    assert result["emotion"] == "fatigue"
