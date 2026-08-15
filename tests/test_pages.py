import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from generate_pages import candidate_page, fmt_brl, fmt_pct, ssr_card  # noqa: E402

DETAIL = {
    "id": "abc123def456",
    "name": "JOÃO DA CONCEIÇÃO",
    "ballot_name": "JOÃO DO POVO",
    "match_status": "exact",
    "outlier": False,
    "multiple": 5.0,
    "elections": {
        "2022": {"year": 2022, "party": "PXA", "party_name": "Partido Xis A", "uf": "SP",
                 "office": "DEPUTADO FEDERAL", "situation": "APTO", "assets_total": 200000.0,
                 "assets_count": 1, "assets": [{"type": "Casa", "description": "CASA", "value": 200000.0}]},
        "2026": {"year": 2026, "party": "PXA", "party_name": "Partido Xis A", "uf": "SP",
                 "office": "DEPUTADO FEDERAL", "situation": "APTO", "assets_total": 1000000.0,
                 "assets_count": 1, "assets": [{"type": "Casa", "description": "CASA", "value": 1000000.0}]},
    },
    "change": {"absolute": 800000.0, "percentage": 400.0, "multiple": 5.0},
}
META = {"generated_at": "2026-08-15T00:00:00+00:00", "sources": []}
CFG = {"site": {"base_url": "https://example.org/enr", "name": "Enriquecímetro",
                "tagline": "tagline"}}


class TestFormat(unittest.TestCase):
    def test_brl(self):
        self.assertEqual(fmt_brl(1234567.89), "R$ 1.234.567,89")
        self.assertEqual(fmt_brl(None), "—")

    def test_pct(self):
        self.assertEqual(fmt_pct(400.0), "+400,0%")
        self.assertIsNone(fmt_pct(None))


class TestCandidatePage(unittest.TestCase):
    def test_page_content(self):
        html_out = candidate_page(CFG, DETAIL, META)
        self.assertIn("João da Conceição", html_out)
        self.assertIn("R$ 1.000.000,00", html_out)
        self.assertIn('rel="canonical"', html_out)
        self.assertIn("application/ld+json", html_out)
        self.assertIn("+400,0%", html_out)
        self.assertNotIn("cpf", html_out.lower())

    def test_zero_baseline(self):
        d = dict(DETAIL)
        d["change"] = {"absolute": 1000000.0, "percentage": None, "multiple": None}
        d["multiple"] = None
        out = candidate_page(CFG, d, META)
        self.assertIn("não aplicável", out)
        self.assertNotIn("infinito", out.lower())

    def test_ssr_card(self):
        card = ssr_card({"id": "abc", "name": "X", "ballot_name": "X", "party": "P",
                         "uf": "SP", "office": "SENADOR", "a2022": 1.0, "a2026": 2.0,
                         "change_abs": 1.0, "change_pct": 100.0})
        self.assertIn('href="c/abc.html"', card)


if __name__ == "__main__":
    unittest.main()
