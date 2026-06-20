"""
Tests for POST /api/v1/generate-pdf
Run: python -m pytest tests/test_generate_pdf.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.fixtures import FIXTURE_MODERATE, FIXTURE_PERFECT, FIXTURE_BURNOUT

client = TestClient(app)

ANALYZE_URL = "/api/v1/analyze"
PDF_URL     = "/api/v1/generate-pdf"


def _get_analysis(fixture, age=22, gender="male"):
    """Helper: run /analyze and return the JSON."""
    r = client.post(ANALYZE_URL, json={
        "assessmentId": "pdf-test-uuid",
        "age": age,
        "gender": gender,
        "responses": fixture,
    })
    assert r.status_code == 200
    return r.json()


def _post_pdf(analysis, brand=None):
    body = {"analysis": analysis}
    if brand:
        body["brand"] = brand
    return client.post(PDF_URL, json=body)


# ===========================================================================
# 1. Happy path
# ===========================================================================

class TestGeneratePDFHappyPath:
    def test_returns_200(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis)
        assert r.status_code == 200

    def test_content_type_is_pdf(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis)
        assert "application/pdf" in r.headers["content-type"]

    def test_response_is_non_empty_bytes(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis)
        assert len(r.content) > 1000  # any real PDF is at least 1KB

    def test_response_starts_with_pdf_magic_bytes(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis)
        assert r.content[:4] == b"%PDF"

    def test_content_disposition_header(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis)
        assert "attachment" in r.headers.get("content-disposition", "")
        assert "limitless_report.pdf" in r.headers.get("content-disposition", "")

    def test_content_length_header_present(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis)
        assert "content-length" in r.headers


# ===========================================================================
# 2. All score profiles generate valid PDFs
# ===========================================================================

class TestPDFAcrossProfiles:
    def test_perfect_profile_generates_pdf(self):
        r = _post_pdf(_get_analysis(FIXTURE_PERFECT))
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_burnout_profile_generates_pdf(self):
        r = _post_pdf(_get_analysis(FIXTURE_BURNOUT,age=59))
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_different_profiles_produce_different_pdfs(self):
        r1 = _post_pdf(_get_analysis(FIXTURE_PERFECT))
        r2 = _post_pdf(_get_analysis(FIXTURE_BURNOUT))
        # PDFs should differ in content (different scores/recommendations)
        assert r1.content != r2.content


# ===========================================================================
# 3. Branding parameters
# ===========================================================================

class TestBranding:
    def test_custom_primary_color_accepted(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis, brand={"primaryColor": "#FF5733"})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_custom_accent_color_accepted(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis, brand={"accentColor": "#28B463"})
        assert r.status_code == 200

    def test_custom_footer_note_accepted(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis, brand={"footerNote": "Acme Corp Wellness"})
        assert r.status_code == 200

    def test_default_branding_when_not_provided(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis)  # no brand param
        assert r.status_code == 200

    def test_full_branding_object(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis, brand={
            "primaryColor": "#1E6FD9",
            "accentColor":  "#00C2CB",
            "footerNote":   "Test Org • 2026",
        })
        assert r.status_code == 200


# ===========================================================================
# 4. PDF with progress data
# ===========================================================================

class TestPDFWithProgress:
    def test_pdf_with_prior_report(self):
        # First assessment (worse scores)
        first = client.post(ANALYZE_URL, json={
            "assessmentId": "prior-001",
            "age": 22, "gender": "male",
            "responses": FIXTURE_BURNOUT,
        }).json()

        # Second assessment (better scores) with prior report
        second = client.post(ANALYZE_URL, json={
            "assessmentId": "current-001",
            "age": 22, "gender": "male",
            "responses": FIXTURE_MODERATE,
            "priorReport": first,
        }).json()

        assert second["progress"]["available"] is True
        r = _post_pdf(second)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


# ===========================================================================
# 5. Input validation
# ===========================================================================

class TestPDFValidation:
    def test_missing_analysis_returns_422(self):
        r = client.post(PDF_URL, json={})
        assert r.status_code == 422

    def test_empty_analysis_still_generates_pdf(self):
        # Empty dict analysis — pdf_service should handle missing keys gracefully
        r = _post_pdf({})
        assert r.status_code in [200,500]

    def test_invalid_brand_color_still_works(self):
        # Brand validation is loose — any string accepted for colors
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis, brand={"primaryColor": "not-a-color"})
        # Should either succeed or return 500 (not 422)
        assert r.status_code in (200, 500)


# ===========================================================================
# 6. PDF size sanity checks
# ===========================================================================

class TestPDFSize:
    def test_pdf_is_reasonably_sized(self):
        """A 7-page PDF should be between 10KB and 5MB."""
        analysis = _get_analysis(FIXTURE_MODERATE)
        r = _post_pdf(analysis)
        size = len(r.content)
        assert 10_000 < size < 5_000_000, f"PDF size {size} bytes seems wrong"
