import json
from pathlib import Path
import pytest
from importer.parser import (ReportFile, ReportParseError, extract_gray_zones,
                             extract_json_block, load_report_file, parse_filename, parse_report)
from importer.models import ProductReport

FIX = Path(__file__).parent / "fixtures"


def test_parse_filename():
    assert parse_filename(Path("product--cement--claude.md")) == ("product", "cement", "claude")
    with pytest.raises(ValueError):
        parse_filename(Path("cement.md"))


def test_load_and_extract(tmp_path):
    src = FIX / "report_product_ok.md"
    path = tmp_path / "product--cement--claude.md"
    path.write_text(src.read_text())
    rf = load_report_file(path)
    assert rf.kind == "product" and rf.model == "claude" and len(rf.file_hash) == 64
    block = extract_json_block(rf.markdown)
    assert json.loads(block)["product"]["hs_code"] == "2523290000"
    zones = extract_gray_zones(rf.markdown)
    assert len(zones) == 2 and "тариф" in zones[0].lower()


def test_parse_report_ok(tmp_path):
    src = FIX / "report_product_ok.md"
    path = tmp_path / "product--cement--claude.md"
    path.write_text(src.read_text())
    report = parse_report(load_report_file(path))
    assert isinstance(report, ProductReport)


def test_parse_report_broken_json_uses_llm(tmp_path):
    good = json.loads(extract_json_block((FIX / "report_product_ok.md").read_text()))
    path = tmp_path / "product--cement--gpt.md"
    path.write_text("# x\n```json\n{broken json!!!\n```\n")

    class FakeLLM:
        def convert_to_schema(self, markdown, kind):
            return good
    report = parse_report(load_report_file(path), llm=FakeLLM())
    assert isinstance(report, ProductReport)


def test_parse_report_broken_no_llm_raises(tmp_path):
    path = tmp_path / "product--cement--gpt.md"
    path.write_text("# x\n```json\n{broken\n```\n")
    with pytest.raises(ReportParseError):
        parse_report(load_report_file(path))
