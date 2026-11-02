"""A small in-memory Bloom filter for per-worker URL deduplication."""

from __future__ import annotations

import hashlib
import math
import threading
from collections.abc import Iterable


class BloomFilter:
    """A compact probabilistic set with no false negatives.

    False positives are possible, so callers should treat membership as a
    best-effort hint. The filter deliberately holds no references to the
    original values.
    """

    def __init__(self, capacity: int = 100_000, error_rate: float = 0.01) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if not 0 < error_rate < 1:
            raise ValueError("error_rate must be between 0 and 1")

        bit_count = math.ceil(-(capacity * math.log(error_rate)) / math.log(2) ** 2)
        self._bits = bytearray((bit_count + 7) // 8)
        self._bit_count = bit_count
        self._hash_count = max(1, round(bit_count / capacity * math.log(2)))
        self._lock = threading.Lock()

    @property
    def bit_count(self) -> int:
        """Number of bits in the filter."""
        return self._bit_count

    def _indexes(self, value: str) -> list[int]:
        digest = hashlib.blake2b(value.encode(), digest_size=16).digest()
        first = int.from_bytes(digest[:8], "big")
        second = int.from_bytes(digest[8:], "big") or 1
        return [(first + index * second) % self._bit_count for index in range(self._hash_count)]

    def _contains_indexes(self, indexes: list[int]) -> bool:
        return all(self._bits[bit >> 3] & (1 << (bit & 7)) for bit in indexes)

    def __contains__(self, value: str) -> bool:
        indexes = self._indexes(value)
        with self._lock:
            return self._contains_indexes(indexes)

    def add(self, value: str) -> bool:
        """Add ``value``; return True when it was not probably present."""
        indexes = self._indexes(value)
        with self._lock:
            if self._contains_indexes(indexes):
                return False
            for bit in indexes:
                self._bits[bit >> 3] |= 1 << (bit & 7)
            return True

    def add_many(self, values: Iterable[str]) -> int:
        """Add every value and return how many were newly added."""
        return sum(self.add(value) for value in values)
