"""Validation tests for the ingestion Pydantic payloads.

These tests pin the contract from review finding F2: `source_name` is a DB
column, not a filesystem path, so the lowercase-identifier regex was lifted
from it. `domain_pack` still enforces the regex - that is the actual
path-traversal boundary for `load_pack()`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.routes_ingestion import IngestTextPayload, IngestURLPayload


class TestSourceNameAcceptsMixedCase:
    """source_name flows into Source.name (a DB column) so casing should be free."""

    def test_text_payload_accepts_mixed_case_source_name(self) -> None:
        payload = IngestTextPayload(
            title="t",
            text="x",
            source_name="TechCrunch",
            domain_pack="personal_ai_tech",
        )
        assert payload.source_name == "TechCrunch"

    def test_text_payload_accepts_source_name_with_spaces(self) -> None:
        payload = IngestTextPayload(
            title="t",
            text="x",
            source_name="The Verge",
            domain_pack="personal_ai_tech",
        )
        assert payload.source_name == "The Verge"

    def test_url_payload_accepts_mixed_case_source_name(self) -> None:
        payload = IngestURLPayload(
            url="https://example.com/article",
            source_name="TechCrunch",
            domain_pack="personal_ai_tech",
        )
        assert payload.source_name == "TechCrunch"


class TestDomainPackStillEnforcesIdentifierRegex:
    """domain_pack flows into the filesystem path inside load_pack() so the
    lowercase-identifier regex must still reject any traversal attempt."""

    @pytest.mark.parametrize(
        "bad_pack",
        [
            "../etc/passwd",
            "..\\foo",
            "a/../b",
            "Personal_AI_Tech",  # uppercase rejected
            "with spaces",
            "",
        ],
    )
    def test_text_payload_rejects_bad_domain_pack(self, bad_pack: str) -> None:
        with pytest.raises(ValidationError):
            IngestTextPayload(
                title="t",
                text="x",
                source_name="manual",
                domain_pack=bad_pack,
            )

    @pytest.mark.parametrize(
        "bad_pack",
        [
            "../etc/passwd",
            "..\\foo",
            "a/../b",
            "Personal_AI_Tech",
            "with spaces",
            "",
        ],
    )
    def test_url_payload_rejects_bad_domain_pack(self, bad_pack: str) -> None:
        with pytest.raises(ValidationError):
            IngestURLPayload(
                url="https://example.com/article",
                source_name="manual",
                domain_pack=bad_pack,
            )

    def test_valid_domain_pack_is_accepted(self) -> None:
        payload = IngestTextPayload(
            title="t",
            text="x",
            source_name="TechCrunch",
            domain_pack="personal_ai_tech",
        )
        assert payload.domain_pack == "personal_ai_tech"
