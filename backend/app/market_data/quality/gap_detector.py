"""STRATLAB Market Data Quality: Sequence Gap & Drop Detector.

Tracks monotonic exchange sequence IDs per instrument to detect lost packets,
network transmission gaps, and duplicate events.
"""

from typing import Dict, Optional


class SequenceGapDetector:
    """
    Monitors incoming message sequence counters for drops, gaps, and duplicates.
    """
    def __init__(self, reset_threshold: int = 1000):
        # Maps instrument_id -> last observed sequence_id
        self._last_seq: Dict[str, int] = {}
        # Metrics per instrument
        self._total_events: Dict[str, int] = {}
        self._dropped_events: Dict[str, int] = {}
        self._duplicate_events: Dict[str, int] = {}
        self._reset_threshold = reset_threshold

    def check_sequence(self, instrument_id: str, seq_id: Optional[int]) -> Dict[str, bool | int]:
        """
        Evaluate incoming sequence ID.
        Returns:
            {
                "is_gap": bool,
                "is_duplicate": bool,
                "is_reset": bool,
                "dropped_count": int,
                "expected_seq": int,
            }
        """
        self._total_events[instrument_id] = self._total_events.get(instrument_id, 0) + 1

        if seq_id is None:
            return {
                "is_gap": False,
                "is_duplicate": False,
                "is_reset": False,
                "dropped_count": 0,
                "expected_seq": 0,
            }

        last_seq = self._last_seq.get(instrument_id)
        if last_seq is None:
            self._last_seq[instrument_id] = seq_id
            return {
                "is_gap": False,
                "is_duplicate": False,
                "is_reset": False,
                "dropped_count": 0,
                "expected_seq": seq_id,
            }

        expected = last_seq + 1

        # Case 1: Normal in-order sequence
        if seq_id == expected:
            self._last_seq[instrument_id] = seq_id
            return {
                "is_gap": False,
                "is_duplicate": False,
                "is_reset": False,
                "dropped_count": 0,
                "expected_seq": expected,
            }

        # Case 2: Sequence reset (e.g. daily session restart: seq drops from 50000 to 1)
        if seq_id < last_seq and (last_seq - seq_id) > self._reset_threshold:
            self._last_seq[instrument_id] = seq_id
            return {
                "is_gap": False,
                "is_duplicate": False,
                "is_reset": True,
                "dropped_count": 0,
                "expected_seq": 1,
            }

        # Case 3: Duplicate or late out-of-order packet
        if seq_id <= last_seq:
            self._duplicate_events[instrument_id] = self._duplicate_events.get(instrument_id, 0) + 1
            return {
                "is_gap": False,
                "is_duplicate": True,
                "is_reset": False,
                "dropped_count": 0,
                "expected_seq": expected,
            }

        # Case 4: Sequence gap (dropped packets)
        dropped = seq_id - expected
        self._dropped_events[instrument_id] = self._dropped_events.get(instrument_id, 0) + dropped
        self._last_seq[instrument_id] = seq_id
        return {
            "is_gap": True,
            "is_duplicate": False,
            "is_reset": False,
            "dropped_count": dropped,
            "expected_seq": expected,
        }

    def get_stats(self, instrument_id: str) -> Dict[str, int | float]:
        """Return drop rate statistics for an instrument."""
        total = self._total_events.get(instrument_id, 0)
        dropped = self._dropped_events.get(instrument_id, 0)
        dups = self._duplicate_events.get(instrument_id, 0)
        drop_rate = (dropped / (total + dropped) * 100.0) if (total + dropped) > 0 else 0.0
        return {
            "total_events": total,
            "dropped_events": dropped,
            "duplicate_events": dups,
            "drop_rate_pct": round(drop_rate, 4),
        }
