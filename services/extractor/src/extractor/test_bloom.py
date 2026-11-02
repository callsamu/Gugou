"""Tests for :mod:`extractor.bloom`."""

from __future__ import annotations

import pytest

from extractor.bloom import BloomFilter

URL = "https://example.com/article"


def test_bloom_filter_has_no_false_negatives() -> None:
    bloom = BloomFilter(capacity=10_000, error_rate=0.01)
    values = [f"https://example.com/{index}" for index in range(5_000)]

    for value in values:
        assert bloom.add(value)

    assert all(value in bloom for value in values)


def test_bloom_filter_reports_duplicate_adds() -> None:
    bloom = BloomFilter(capacity=100, error_rate=0.01)

    assert bloom.add(URL)
    assert not bloom.add(URL)
    assert bloom.add_many([URL, "https://example.com/other"]) == 1


def test_bloom_filter_rejects_invalid_sizes() -> None:
    with pytest.raises(ValueError):
        BloomFilter(capacity=0)
    with pytest.raises(ValueError):
        BloomFilter(error_rate=0)
    with pytest.raises(ValueError):
        BloomFilter(error_rate=1)
