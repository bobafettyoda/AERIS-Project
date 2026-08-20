from __future__ import annotations

import unittest

import pandas as pd

from analysis.parcels.pipeline import keyword_evidence, keyword_mask


class ParcelKeywordClassificationTests(unittest.TestCase):
    def test_keyword_match_uses_word_boundaries(self) -> None:
        values = pd.Series(["State government", "Estate residential"])
        result = keyword_mask(values, ["state"])
        self.assertEqual(result.tolist(), [True, False])

    def test_keyword_evidence_records_rule(self) -> None:
        values = pd.Series(["Public university campus"])
        evidence = keyword_evidence(values, ["public", "university"])
        self.assertEqual(evidence.iloc[0], "public; university")


if __name__ == "__main__":
    unittest.main()
