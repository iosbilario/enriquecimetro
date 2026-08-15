"""Testes de integração do pipeline com fixtures sintéticas.

As fixtures são geradas em tempo de teste (nenhum dado fictício é commitado
junto aos dados reais; tudo vive em diretórios temporários).
"""
import csv
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from common import load_config  # noqa: E402
from match_candidates import build_matches  # noqa: E402
from generate_site_data import build  # noqa: E402
from transform import attach_assets, load_candidates  # noqa: E402
from validate import validate_staging  # noqa: E402
from common import write_json  # noqa: E402

CAND_HEADER = [
    "SQ_CANDIDATO", "NM_CANDIDATO", "NM_URNA_CANDIDATO", "NR_CPF_CANDIDATO",
    "SG_UF", "DS_CARGO", "SG_PARTIDO", "NM_PARTIDO", "DT_NASCIMENTO",
    "DS_SITUACAO_CANDIDATURA", "NR_CANDIDATO", "NM_EMAIL",
]
ASSET_HEADER = [
    "SQ_CANDIDATO", "DS_TIPO_BEM_CANDIDATO", "DS_BEM_CANDIDATO", "VR_BEM_CANDIDATO",
]

CPF_A = "52998224725"  # CPFs sintéticos com checksum válido
CPF_B = "15350946056"


def make_zip(path: Path, filename: str, header: list, rows: list, encoding="latin-1"):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", quotechar='"', quoting=csv.QUOTE_ALL)
    writer.writerow(header)
    writer.writerows(rows)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(filename, buf.getvalue().encode(encoding))


class PipelineFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

        make_zip(self.tmp / "cand22.zip", "consulta_cand_2022_SP.csv", CAND_HEADER, [
            ["100", "JOÃO DA CONCEIÇÃO", "JOÃO DO POVO", CPF_A, "SP",
             "DEPUTADO FEDERAL", "PXA", "Partido Xis A", "01/01/1970", "APTO", "1111", "x@y.z"],
            ["101", "MARIA SILVA", "MARIA", CPF_B, "SP",
             "DEPUTADO ESTADUAL", "PXB", "Partido Xis B", "02/02/1980", "APTO", "2222", "a@b.c"],
            ["102", "PEDRO SEM DOCUMENTO", "PEDRO", "", "SP",
             "SENADOR", "PXC", "Partido Xis C", "03/03/1975", "APTO", "3333", ""],
            ["103", "ANA SOZINHA", "ANA", "11111111111", "SP",
             "GOVERNADOR", "PXD", "Partido Xis D", "04/04/1985", "APTO", "4444", ""],
        ])
        make_zip(self.tmp / "bens22.zip", "bem_candidato_2022_SP.csv", ASSET_HEADER, [
            ["100", "Casa", "CASA NA CAPITAL", "150000,00"],
            ["100", "Veículo", "AUTOMOVEL", "50000,00"],
            ["101", "Poupança", "CONTA POUPANCA", "0,00"],
            ["102", "Terreno", "SITIO", "1.000.000,00"],
        ])
        make_zip(self.tmp / "cand26.zip", "consulta_cand_2026_SP.csv", CAND_HEADER, [
            ["200", "JOÃO DA CONCEIÇÃO", "JOÃO DO POVO", CPF_A, "SP",
             "DEPUTADO FEDERAL", "PXA", "Partido Xis A", "01/01/1970", "APTO", "1111", "x@y.z"],
            ["201", "PEDRO SEM DOCUMENTO", "PEDRO", "#NULO#", "SP",
             "SENADOR", "PXC", "Partido Xis C", "03/03/1975", "APTO", "3333", ""],
            ["202", "NOVATO TOTAL", "NOVATO", "", "RJ",
             "DEPUTADO FEDERAL", "PXE", "Partido Xis E", "05/05/1990", "APTO", "5555", ""],
        ])
        make_zip(self.tmp / "bens26.zip", "bem_candidato_2026_SP.csv", ASSET_HEADER, [
            ["200", "Casa", "CASA NA CAPITAL", "900000,00"],
            ["200", "Aplicação", "FUNDO", "100000,00"],
            ["201", "Terreno", "SITIO", "2.000.000,00"],
        ])

        self.e2022 = load_candidates(self.tmp / "cand22.zip")
        attach_assets(self.e2022, self.tmp / "bens22.zip")
        self.e2026 = load_candidates(self.tmp / "cand26.zip")
        attach_assets(self.e2026, self.tmp / "bens26.zip")
        self.elections = {2022: self.e2022, 2026: self.e2026}
        self.persons = build_matches(self.elections)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def person_by_sq(self, year, sq):
        for p in self.persons:
            if p["elections"].get(str(year)) == sq:
                return p
        return None

    def test_transform_sums_assets(self):
        self.assertEqual(self.e2022["100"]["assets_total"], 200000.0)
        self.assertEqual(self.e2022["100"]["assets_count"], 2)
        self.assertEqual(self.e2022["101"]["assets_total"], 0.0)
        self.assertEqual(self.e2022["102"]["assets_total"], 1000000.0)

    def test_sensitive_columns_never_extracted(self):
        for cand in list(self.e2022.values()) + list(self.e2026.values()):
            self.assertNotIn("email", {k.lower() for k in cand})

    def test_exact_match_by_cpf(self):
        p = self.person_by_sq(2026, "200")
        self.assertEqual(p["match_status"], "exact")
        self.assertEqual(p["elections"]["2022"], "100")

    def test_probable_match_by_name_birth(self):
        p = self.person_by_sq(2026, "201")
        self.assertEqual(p["match_status"], "probable")
        self.assertEqual(p["elections"]["2022"], "102")

    def test_unverified_never_invented(self):
        p22 = self.person_by_sq(2022, "101")
        self.assertEqual(p22["match_status"], "unverified")
        p26 = self.person_by_sq(2026, "202")
        self.assertEqual(p26["match_status"], "unverified")
        # CPF inválido (dígitos repetidos) não pode virar match exato
        p_ana = self.person_by_sq(2022, "103")
        self.assertEqual(p_ana["match_status"], "unverified")

    def test_generate_and_validate_no_cpf_leak(self):
        config = load_config()
        config = {**config, "validation": {**config["validation"], "min_candidates_per_election": 1}}
        files = build(config, self.elections, self.persons, {})
        staging = self.tmp / "staging"
        for rel, data in files.items():
            write_json(staging / rel, data)

        problems = validate_staging(staging, config, {CPF_A, CPF_B})
        self.assertEqual(problems, [], f"validação falhou: {problems}")

        blob = "".join(
            p.read_text(encoding="utf-8") for p in staging.rglob("*.json")
        )
        self.assertNotIn(CPF_A, blob)
        self.assertNotIn(CPF_B, blob)
        self.assertNotIn("cpf", blob.lower())

    def test_schema_of_candidate_detail(self):
        config = load_config()
        files = build(config, self.elections, self.persons, {})
        p = self.person_by_sq(2026, "200")
        detail = files[f"candidates/{p['id'][:2]}.json"][p["id"]]
        for key in ("id", "name", "ballot_name", "match_status", "elections", "change"):
            self.assertIn(key, detail)
        self.assertEqual(detail["elections"]["2022"]["assets_total"], 200000.0)
        self.assertEqual(detail["elections"]["2026"]["assets_total"], 1000000.0)
        self.assertEqual(detail["change"]["absolute"], 800000.0)
        self.assertEqual(detail["change"]["percentage"], 400.0)
        self.assertEqual(detail["change"]["multiple"], 5.0)

    def test_zero_baseline_yields_null_percentage(self):
        config = load_config()
        # força cenário: MARIA (patrimônio 0 em 2022) presente também em 2026
        e2026 = dict(self.e2026)
        maria26 = dict(self.e2022["101"])
        maria26["sq"] = "299"
        maria26["assets"] = [{"type": "Casa", "description": "APTO", "value": 300000.0}]
        maria26["assets_total"] = 300000.0
        maria26["assets_count"] = 1
        e2026["299"] = maria26
        elections = {2022: self.e2022, 2026: e2026}
        persons = build_matches(elections)
        p = next(x for x in persons if x["elections"].get("2026") == "299")
        self.assertEqual(p["match_status"], "exact")
        files = build(config, elections, persons, {})
        detail = files[f"candidates/{p['id'][:2]}.json"][p["id"]]
        self.assertIsNone(detail["change"]["percentage"])
        self.assertIsNone(detail["change"]["multiple"])
        self.assertEqual(detail["change"]["absolute"], 300000.0)

    def test_rankings_only_exact(self):
        config = load_config()
        files = build(config, self.elections, self.persons, {})
        for key, block in files["rankings.json"]["rankings"].items():
            for entry in block["entries"]:
                detail = files[f"candidates/{entry['id'][:2]}.json"][entry["id"]]
                self.assertEqual(detail["match_status"], "exact", key)


if __name__ == "__main__":
    unittest.main()


class TestBrasilUfDuplication(unittest.TestCase):
    """O ZIP do TSE traz _BRASIL.csv E arquivos por UF com as mesmas linhas."""

    def test_assets_not_double_counted(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            make_zip(tmp / "cand.zip", "consulta_cand_2022_BRASIL.csv", CAND_HEADER, [
                ["100", "JOÃO DA CONCEIÇÃO", "JOÃO", CPF_A, "SP",
                 "DEPUTADO FEDERAL", "PXA", "Partido Xis A", "01/01/1970", "APTO", "1111", ""],
            ])
            header = ASSET_HEADER + ["NR_ORDEM_BEM_CANDIDATO"]
            rows = [
                ["100", "Casa", "CASA NA CAPITAL", "150000,00", "1"],
                ["100", "Veículo", "AUTOMOVEL", "50000,00", "2"],
            ]
            buf1, buf2 = io.StringIO(), io.StringIO()
            for buf in (buf1, buf2):
                w = csv.writer(buf, delimiter=";", quotechar='"', quoting=csv.QUOTE_ALL)
                w.writerow(header)
                w.writerows(rows)
            with zipfile.ZipFile(tmp / "bens.zip", "w") as zf:
                zf.writestr("bem_candidato_2022_BRASIL.csv", buf1.getvalue().encode("latin-1"))
                zf.writestr("bem_candidato_2022_SP.csv", buf2.getvalue().encode("latin-1"))

            cands = load_candidates(tmp / "cand.zip")
            attach_assets(cands, tmp / "bens.zip")
            self.assertEqual(cands["100"]["assets_count"], 2)
            self.assertEqual(cands["100"]["assets_total"], 200000.0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
