import pytest

from app.intelligence.tiers import validate_writer_tier


def test_validate_writer_tier_accepts_valid_tier():
    validate_writer_tier("t2")


def test_validate_writer_tier_rejects_invalid_tier():
    with pytest.raises(ValueError, match="created_by_tier"):
        validate_writer_tier("t0")


def test_validate_writer_tier_accepts_t3_and_t4():
    validate_writer_tier("t3")
    validate_writer_tier("t4")
