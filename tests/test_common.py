import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from common import (  # noqa: E402
    compute_change,
    is_valid_cpf,
    normalize_name,
    parse_brl,
    public_candidate_id,
    quartiles,
)


class TestParseBrl(unittest.TestCase):
    def test_simple_decimal(self):
        self.assertEqual(parse_brl("50000,00"), 50000.0)

    def test_thousands_separator(self):
        self.assertEqual(parse_brl("1.234.567,89"), 1234567.89)

    def test_integer_only(self):
        self.assertEqual(parse_brl("500000"), 500000.0)

    def test_negative(self):
        self.assertEqual(parse_brl("-1500,50"), -1500.5)

    def test_quoted_and_spaces(self):
        self.assertEqual(parse_brl(' "18327,66" '), 18327.66)

    def test_null_markers(self):
        self.assertIsNone(parse_brl("#NULO#"))
        self.assertIsNone(parse_brl(""))
        self.assertIsNone(parse_brl(None))

    def test_garbage(self):
        self.assertIsNone(parse_brl("abc"))
        self.assertIsNone(parse_brl("12,34,56"))

    def test_float_precision(self):
        self.assertEqual(parse_brl("0,1") + parse_brl("0,2"), 0.30000000000000004)
        # a soma agregada é arredondada no transform; aqui garantimos centavos exatos
        self.assertEqual(parse_brl("1109,45"), 1109.45)


class TestNormalizeName(unittest.TestCase):
    def test_accents(self):
        self.assertEqual(normalize_name("João da Conceição"), "JOAO DA CONCEICAO")

    def test_spaces(self):
        self.assertEqual(normalize_name("  Maria   José "), "MARIA JOSE")

    def test_empty(self):
        self.assertEqual(normalize_name(None), "")


class TestCpf(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(is_valid_cpf("52998224725"))

    def test_invalid_checksum(self):
        self.assertFalse(is_valid_cpf("52998224726"))

    def test_repeated_digits(self):
        self.assertFalse(is_valid_cpf("11111111111"))

    def test_wrong_length(self):
        self.assertFalse(is_valid_cpf("1234567890"))
        self.assertFalse(is_valid_cpf(None))


class TestChange(unittest.TestCase):
    def test_increase(self):
        c = compute_change(100000.0, 500000.0)
        self.assertEqual(c["absolute"], 400000.0)
        self.assertEqual(c["percentage"], 400.0)
        self.assertEqual(c["multiple"], 5.0)

    def test_zero_baseline(self):
        c = compute_change(0.0, 500000.0)
        self.assertEqual(c["absolute"], 500000.0)
        self.assertIsNone(c["percentage"])
        self.assertIsNone(c["multiple"])

    def test_missing_side(self):
        c = compute_change(None, 500000.0)
        self.assertIsNone(c["absolute"])
        self.assertIsNone(c["percentage"])

    def test_decrease(self):
        c = compute_change(500000.0, 100000.0)
        self.assertEqual(c["absolute"], -400000.0)
        self.assertEqual(c["percentage"], -80.0)


class TestPublicId(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(
            public_candidate_id(2026, "260001234567"),
            public_candidate_id(2026, "260001234567"),
        )

    def test_no_input_leak(self):
        pid = public_candidate_id(2026, "260001234567")
        self.assertEqual(len(pid), 12)
        self.assertNotIn("260001234567", pid)

    def test_different_inputs(self):
        self.assertNotEqual(
            public_candidate_id(2026, "1"), public_candidate_id(2022, "1")
        )


class TestQuartiles(unittest.TestCase):
    def test_basic(self):
        q = quartiles([1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(q, (2.5, 6.5))

    def test_too_small(self):
        self.assertIsNone(quartiles([1, 2, 3]))


if __name__ == "__main__":
    unittest.main()


class TestRedaction(unittest.TestCase):
    def test_formatted_cpf(self):
        from common import redact_personal_numbers
        self.assertNotIn("529.982.247-25",
                         redact_personal_numbers("EMPRESTIMO A FULANO CPF 529.982.247-25"))

    def test_bare_valid_cpf(self):
        from common import redact_personal_numbers
        self.assertNotIn("52998224725",
                         redact_personal_numbers("DIVIDA CPF 52998224725 VALOR X"))

    def test_keeps_non_cpf_numbers(self):
        from common import redact_personal_numbers
        # 11 dígitos com checksum inválido (ex.: RENAVAM) são preservados
        self.assertIn("12345678900", redact_personal_numbers("RENAVAM 12345678900"))
        self.assertIn("2020", redact_personal_numbers("CARRO ANO 2020"))

    def test_empty(self):
        from common import redact_personal_numbers
        self.assertEqual(redact_personal_numbers(None), "")
