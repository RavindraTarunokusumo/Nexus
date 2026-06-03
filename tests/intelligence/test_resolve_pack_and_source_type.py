"""Unit tests for _resolve_pack_and_source_type (B4).

All tests are pure unit tests — no DB session needed.  Source and Document ORM
instances are constructed in-memory (SQLAlchemy declarative models can be
instantiated without a session).

Precedence rules:
- URL-domain match always beats title-regex match.
- Within each pass, profiles are iterated in pack declaration order; the first
  profile whose url_domains (or title_regex) matches wins.
- Pass 3: pack.metadata.supported_source_types[0] is the fallback.
- Pass 4: "ai_news_article" is the absolute safety net (empty supported_source_types).
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models import Document, Source
from app.domain_packs.loader import clear_cache, load_pack
from app.intelligence.extraction import _resolve_pack_and_source_type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source(domain_pack: str = "personal_ai_tech") -> Source:
    return Source(
        id=uuid.uuid4(),
        name="Test Source",
        source_type="rss",
        url=None,
        domain_pack=domain_pack,
    )


def _doc(url: str | None = None, title: str | None = None) -> Document:
    return Document(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        title=title,
        url=url,
        content_hash="test-hash",
    )


@pytest.fixture(autouse=True)
def _clear_pack_cache():
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# Pass 1 — URL-domain matching
# ---------------------------------------------------------------------------


class TestUrlDomainMatch:
    def test_techcrunch_matches_ai_news_article(self) -> None:
        source = _source()
        doc = _doc(url="https://techcrunch.com/2024/01/some-post")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "ai_news_article"

    def test_arxiv_matches_research_paper(self) -> None:
        source = _source()
        doc = _doc(url="https://arxiv.org/abs/2401.12345")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "research_paper_or_report"

    def test_openai_blog_matches_model_release_note(self) -> None:
        # url_domains entry is "openai.com/blog" — substring match in the full URL
        source = _source()
        doc = _doc(url="https://openai.com/blog/gpt-4o-mini")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "model_release_note"

    def test_epoch_ai_matches_forecast(self) -> None:
        source = _source()
        doc = _doc(url="https://epoch.ai/blog/compute-trends")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "forecast_or_opinion"

    def test_nvd_nist_matches_security_disclosure(self) -> None:
        source = _source()
        doc = _doc(url="https://nvd.nist.gov/vuln/detail/CVE-2024-12345")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "security_or_safety_disclosure"

    def test_url_match_returns_correct_pack(self) -> None:
        source = _source()
        doc = _doc(url="https://arxiv.org/abs/2401.99999")
        pack, _ = _resolve_pack_and_source_type(source, doc)
        assert pack.metadata.pack_id == "personal_ai_tech"

    def test_source_url_used_when_document_url_is_none(self) -> None:
        # Source.url is used as fallback when Document.url is None
        source = _source()
        source.url = "https://techcrunch.com"
        doc = _doc(url=None, title=None)
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "ai_news_article"


# ---------------------------------------------------------------------------
# Pass 2 — title-regex matching
# ---------------------------------------------------------------------------


class TestTitleRegexMatch:
    def test_introducing_capital_matches_product_announcement(self) -> None:
        source = _source()
        doc = _doc(url=None, title="Introducing Claude 3.7")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "product_or_tool_announcement"

    def test_security_cve_title_matches_security_disclosure(self) -> None:
        source = _source()
        doc = _doc(url=None, title="CVE-2024-12345 prompt injection disclosed")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "security_or_safety_disclosure"

    def test_funding_series_b_matches_funding_update(self) -> None:
        source = _source()
        doc = _doc(url=None, title="Acme raises $100M Series B")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "funding_or_company_update"

    def test_mmlu_benchmark_title_matches_benchmark_report(self) -> None:
        source = _source()
        doc = _doc(url=None, title="MMLU benchmark results for GPT-4")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "benchmark_report"

    def test_source_name_used_when_title_is_none(self) -> None:
        source = _source()
        source.name = "CVE-2025-99999 vulnerability report"
        doc = _doc(url=None, title=None)
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "security_or_safety_disclosure"


# ---------------------------------------------------------------------------
# Case-insensitivity of title regex
# ---------------------------------------------------------------------------


class TestTitleRegexCaseInsensitive:
    def test_uppercase_mmlu(self) -> None:
        source = _source()
        doc = _doc(url=None, title="MMLU benchmark results")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "benchmark_report"

    def test_lowercase_mmlu(self) -> None:
        source = _source()
        doc = _doc(url=None, title="mmlu benchmark results")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "benchmark_report"

    def test_mixed_case_vulnerability(self) -> None:
        source = _source()
        doc = _doc(url=None, title="Critical VULNERABILITY in open-source model")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "security_or_safety_disclosure"


# ---------------------------------------------------------------------------
# URL beats title — precedence
# ---------------------------------------------------------------------------


class TestUrlBeatsTitlePrecedence:
    def test_url_match_wins_over_title_regex(self) -> None:
        # URL points to arxiv (research_paper_or_report) but title looks like a
        # product announcement — URL-domain pass must win.
        source = _source()
        doc = _doc(
            url="https://arxiv.org/abs/2401.99999",
            title="Introducing a new research framework",
        )
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "research_paper_or_report"


# ---------------------------------------------------------------------------
# Pass 3 — fallback to supported_source_types[0]
# ---------------------------------------------------------------------------


class TestFallbackToSupportedSourceTypes:
    def test_no_match_falls_back_to_first_supported_type(self) -> None:
        source = _source()
        doc = _doc(url="https://random.example.com", title="random text")
        pack, profile = _resolve_pack_and_source_type(source, doc)
        # personal_ai_tech.yaml lists "ai_news_article" first
        assert profile == pack.metadata.supported_source_types[0]
        assert profile == "ai_news_article"


# ---------------------------------------------------------------------------
# Pass 4 — empty supported_source_types falls back to "ai_news_article"
# ---------------------------------------------------------------------------


class TestEmptySupportedSourceTypesSafetyNet:
    def test_empty_supported_source_types_returns_ai_news_article(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When supported_source_types is empty and nothing matches, the
        absolute safety net must return 'ai_news_article'."""
        import app.domain_packs.loader as loader_module
        import copy
        import yaml
        from pathlib import Path

        # Build a minimal pack with no url_domains/title_regex and an empty
        # supported_source_types list.
        minimal: dict = {
            "metadata": {
                "pack_id": "empty_pack",
                "domain": "testing",
                "version": "0.1.0",
                "supported_source_types": [],
            },
            "telos": {"primary_purposes": ["test"]},
            "semantic_object_families": {
                "findings": {
                    "purpose": "test",
                    "object_types": ["finding"],
                    "core_type_mapping": {"finding": "observation"},
                    "mvp_claim_type": {"finding": "research_finding"},
                }
            },
            "relation_grammar": {"core_relations": ["supports"]},
            "model_routing_policy": {
                "default_route": {
                    "segmenting": "T0",
                    "basic_facets": "T1",
                    "semantic_compression_easy": "T1",
                    "semantic_compression_ambiguous": "T2",
                    "relation_classification_easy": "T2",
                    "synthesis": "T3",
                    "audit_or_high_impact": "T4",
                }
            },
        }

        tmp = Path(__file__).parent / "_tmp_empty_pack"
        tmp.mkdir(exist_ok=True)
        (tmp / "empty_pack.yaml").write_text(yaml.dump(minimal), encoding="utf-8")
        monkeypatch.setattr(loader_module, "_pack_dir", lambda: tmp)

        source = Source(
            id=uuid.uuid4(),
            name="Empty Source",
            source_type="rss",
            url=None,
            domain_pack="empty_pack",
        )
        doc = _doc(url="https://nowhere.example.com", title="no match here")

        try:
            _, profile = _resolve_pack_and_source_type(source, doc)
            assert profile == "ai_news_article"
        finally:
            (tmp / "empty_pack.yaml").unlink(missing_ok=True)
            tmp.rmdir()


# ---------------------------------------------------------------------------
# Multiple URL matches — first profile in declaration order wins
# ---------------------------------------------------------------------------


class TestMultipleUrlMatchesDeclOrderWins:
    def test_first_profile_wins_when_url_matches_multiple(self) -> None:
        # "techcrunch.com" is declared in ai_news_article (first profile in pack).
        # Even if a later profile theoretically had the same hint, the first wins.
        source = _source()
        doc = _doc(url="https://techcrunch.com/some-article")
        _, profile = _resolve_pack_and_source_type(source, doc)
        assert profile == "ai_news_article"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_same_inputs_same_output(self) -> None:
        source = _source()
        doc = _doc(url="https://arxiv.org/abs/2401.12345")
        result1 = _resolve_pack_and_source_type(source, doc)
        result2 = _resolve_pack_and_source_type(source, doc)
        assert result1[1] == result2[1]
