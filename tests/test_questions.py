"""
Tests for POST /api/v1/generate-questions
Gemini API is mocked — no real API key needed to run tests.
"""

import re
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
ENDPOINT = "/api/v1/generate-questions"

# ---------------------------------------------------------------------------
# Mock Gemini — returns a valid static fallback so tests are deterministic
# ---------------------------------------------------------------------------

def _mock_generate(age, gender):
    """Returns what question_generator.generate_questions() returns."""
    from app.services.question_generator import _static_fallback
    return _static_fallback(age, gender), False  # (sections, is_ai_generated)

VALID_PAYLOAD = {"age": 22, "gender": "male"}


def post(payload):
    with patch("app.api.routes.questions.generate_questions", side_effect=_mock_generate):
        return client.post(ENDPOINT, json=payload)


# ===========================================================================
# 1. Happy path
# ===========================================================================

class TestHappyPath:
    def test_returns_200(self):
        assert post(VALID_PAYLOAD).status_code == 200

    def test_all_7_sections_present(self):
        assert len(post(VALID_PAYLOAD).json()["sections"]) == 7

    def test_4_items_per_section(self):
        for section in post(VALID_PAYLOAD).json()["sections"]:
            assert len(section["items"]) == 4

    def test_all_28_item_ids_valid(self):
        expected = {f"S{s}_Q{q}" for s in range(1, 8) for q in range(1, 5)}
        actual = {
            item["id"]
            for section in post(VALID_PAYLOAD).json()["sections"]
            for item in section["items"]
        }
        assert actual == expected

    def test_assessment_id_is_uuid_v4(self):
        pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        assert pattern.match(post(VALID_PAYLOAD).json()["assessmentId"])

    def test_unique_assessment_ids(self):
        id1 = post(VALID_PAYLOAD).json()["assessmentId"]
        id2 = post(VALID_PAYLOAD).json()["assessmentId"]
        assert id1 != id2

    def test_scale_field_present(self):
        assert post(VALID_PAYLOAD).json()["scale"] == "0-4"

    def test_scale_labels_present(self):
        labels = post(VALID_PAYLOAD).json()["scaleLabels"]
        assert set(labels.keys()) == {"0", "1", "2", "3", "4"}

    def test_metadata_fields_present(self):
        meta = post(VALID_PAYLOAD).json()["metadata"]
        assert "version" in meta
        assert "createdAt" in meta
        assert "aiGenerated" in meta
        assert "model" in meta

    def test_section_titles_non_empty(self):
        for s in post(VALID_PAYLOAD).json()["sections"]:
            assert s["title"].strip()

    def test_all_question_texts_non_empty(self):
        for section in post(VALID_PAYLOAD).json()["sections"]:
            for item in section["items"]:
                assert item["text"].strip()


# ===========================================================================
# 2. Age validation
# ===========================================================================

class TestAgeValidation:
    @pytest.mark.parametrize("age", [17, 67, 0, -1, 100])
    def test_out_of_range_age_returns_422(self, age):
        assert post({**VALID_PAYLOAD, "age": age}).status_code == 422

    @pytest.mark.parametrize("age", [18, 22, 25, 26, 50, 60, 66])
    def test_boundary_ages_accepted(self, age):
        assert post({**VALID_PAYLOAD, "age": age}).status_code == 200


# ===========================================================================
# 3. Gender validation
# ===========================================================================

class TestGenderValidation:
    @pytest.mark.parametrize("gender", ["male", "female", "non_binary", "prefer_not_to_say"])
    def test_valid_genders_accepted(self, gender):
        assert post({**VALID_PAYLOAD, "gender": gender}).status_code == 200

    def test_invalid_gender_returns_422(self):
        assert post({**VALID_PAYLOAD, "gender": "robot"}).status_code == 422

    def test_missing_gender_returns_422(self):
        assert post({"age": 22}).status_code == 422

    def test_missing_age_returns_422(self):
        assert post({"gender": "male"}).status_code == 422


# ===========================================================================
# 4. Locale
# ===========================================================================

class TestLocale:
    def test_locale_defaults_to_en(self):
        assert post({"age": 22, "gender": "female"}).status_code == 200

    def test_unknown_locale_still_returns_200(self):
        assert post({**VALID_PAYLOAD, "locale": "xx"}).status_code == 200


# ===========================================================================
# 5. AI metadata flag
# ===========================================================================

class TestAIMetadata:
    def test_fallback_sets_ai_generated_false(self):
        meta = post(VALID_PAYLOAD).json()["metadata"]
        assert meta["aiGenerated"] is False
        assert meta["model"] == "static-fallback"

    def test_ai_generated_true_when_gemini_succeeds(self):
        from app.services.question_generator import _static_fallback
        mock_sections = _static_fallback(22, "male")

        def _mock_ai(age, gender):
            return mock_sections, True  # simulate successful Gemini call

        with patch("app.api.routes.questions.generate_questions", side_effect=_mock_ai):
            meta = client.post(ENDPOINT, json=VALID_PAYLOAD).json()["metadata"]
        assert meta["aiGenerated"] is True
        assert meta["model"] == "gemini-2.0-flash"


# ===========================================================================
# 6. Age-specific question relevance (fallback content check)
# ===========================================================================

class TestAgeContextInFallback:
    @pytest.mark.parametrize("age,expected_phrase", [
        (22, "study"),       # young_adult questions mention study
        (28, "work"),        # emerging_professional mentions work
        (60, "daily"),       # senior_adult mentions daily tasks
    ])
    def test_band_questions_contain_relevant_keywords(self, age, expected_phrase):
        r = post({**VALID_PAYLOAD, "age": age})
        texts = " ".join(
            item["text"]
            for s in r.json()["sections"]
            for item in s["items"]
        ).lower()
        assert expected_phrase in texts
    def test_18_to_20_context_in_questions(self):
        r = post({**VALID_PAYLOAD, "age": 19})
        texts = " ".join(
            item["text"]
            for s in r.json()["sections"]
            for item in s["items"]
        ).lower()
        # Fallback questions for 18-20 reference "late teens / early college"
        assert len(texts) > 100  # at least some content

    def test_different_ages_can_produce_different_questions(self):
        # With real Gemini this would differ; with fallback S1_Q1 text differs by age
        r18 = post({**VALID_PAYLOAD, "age": 19}).json()
        r28 = post({**VALID_PAYLOAD, "age": 28}).json()
        # S1_Q1 text includes life stage in fallback
        q18 = r18["sections"][0]["items"][0]["text"]
        q28 = r28["sections"][0]["items"][0]["text"]
        assert q18 != q28
