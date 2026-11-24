"""Unit tests for the reproducible held-out generation benchmark."""
from __future__ import annotations
import unittest
from scripts.run_generation_test_benchmark import group_unique_requests, latency_summary, score_command, shell_tokens

class GenerationBenchmarkTests(unittest.TestCase):
    def test_duplicate_requests_keep_all_paired_reference_commands(self):
        rows = [
            {"example_id": "a", "group_id": "g1", "request": "List files", "reference_command": "ls"},
            {"example_id": "b", "group_id": "g2", "request": "List files", "reference_command": "find . -maxdepth 1"},
            {"example_id": "c", "group_id": "g3", "request": "Show cwd", "reference_command": "pwd"},
        ]
        cases = group_unique_requests(rows)
        self.assertEqual(len(cases), 2)
        case = next(row for row in cases if row["request"] == "List files")
        self.assertEqual(set(case["reference_commands"]), {"ls", "find . -maxdepth 1"})
        self.assertEqual(len(case["example_ids"]), 2)

    def test_scoring_accepts_any_paired_reference(self):
        refs = ["echo  hello", "printf '%s\\n' hello"]
        self.assertTrue(score_command("printf '%s\\n' hello", refs)["exact_match"])
        self.assertTrue(score_command("echo hello", refs)["shell_token_match"])
        self.assertFalse(score_command("echo world", refs)["shell_token_match"])

    def test_shell_tokenizer_normalizes_quote_style(self):
        self.assertEqual(shell_tokens("echo 'hello world'"), shell_tokens('echo "hello world"'))
        self.assertNotEqual(shell_tokens("echo hello"), shell_tokens("echo goodbye"))

    def test_latency_summary_includes_distribution_and_spread(self):
        result = latency_summary([1.0, 2.0, 3.0, 4.0, 10.0])
        self.assertEqual(result["count"], 5)
        self.assertEqual(result["min_seconds"], 1.0)
        self.assertEqual(result["max_seconds"], 10.0)
        self.assertEqual(result["median_seconds"], 3.0)
        self.assertEqual(result["range_seconds"], 9.0)
        self.assertIn("p95_seconds", result)
        self.assertIn("population_stddev_seconds", result)

    def test_empty_latency_summary(self):
        self.assertEqual(latency_summary([]), {"count": 0})

if __name__ == "__main__":
    unittest.main()
