from __future__ import annotations

import unittest

from benchmarks.run import QUALITY_FIELDS, empty_performance, quality_metrics


class QualityMetricTests(unittest.TestCase):
    def test_file_level_metrics_deduplicate_chunk_hits_and_are_bounded(self):
        hits = [
            {"path": "src/auth.py", "text": "first chunk"},
            {"path": "src/auth.py", "text": "second chunk"},
            {"path": "src/cache.py", "text": "cache chunk"},
            {"path": "src/decoy.py", "text": "decoy"},
        ]
        query = {
            "relevant": ["src/auth.py", "src/cache.py"],
            "relevant_files": ["src/auth.py", "src/cache.py"],
        }

        metrics = quality_metrics(hits, query)

        self.assertEqual(metrics["ndcg@10"], 1.0)
        self.assertEqual(metrics["recall@5"], 1.0)
        for field in QUALITY_FIELDS:
            value = metrics[field]
            if isinstance(value, float):
                self.assertGreaterEqual(value, 0.0, field)
                self.assertLessEqual(value, 1.0, field)

    def test_latency_schema_describes_measured_cli_invocations(self):
        performance = empty_performance(5)
        self.assertIn("warmed_cli_invocation_latency_ms", performance)
        self.assertNotIn("warm_query_latency_ms", performance)


if __name__ == "__main__":
    unittest.main()