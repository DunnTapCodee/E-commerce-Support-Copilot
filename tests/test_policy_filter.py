"""Offline unit tests for services/document_service/src/policy_filter.py.

Runs 100% offline with DISABLE_EXTERNAL_LLM=true or mocked LLM responses and
does not modify repository data/knowledge_base/policies.json.
"""
import asyncio
import io
import os
import unittest
import zipfile
from unittest.mock import AsyncMock, patch

from contracts.schemas import RawPolicyFilterRequest, RetrievedDocument
import services.document_service.src.policy_filter as pf


class TestPolicyFilterOffline(unittest.TestCase):
    def setUp(self):
        self.sample_existing = [
            RetrievedDocument(
                doc_id="POL-001",
                category="shipping",
                title="Existing Shipping",
                content="Existing",
                is_active=True,
                policy_type="permanent",
            )
        ]

    def test_extract_dates_and_tags_parsing(self):
        eff, exp = pf._extract_dates_from_text(
            "Chính sách áp dụng từ 01/01/2025 đến 2025-12-31 cho đổi trả 14 ngày."
        )
        self.assertEqual(eff, "2025-01-01")
        self.assertEqual(exp, "2025-12-31")

        eff2, exp2 = pf._extract_dates_from_text("Hiệu lực 15/03/2025 đến 30/06/2025.")
        self.assertEqual((eff2, exp2), ("2025-03-15", "2025-06-30"))

        tags = pf._extract_tags("Hỗ trợ freeship, hoàn tiền 7 ngày và bảo hành chính hãng.")
        self.assertIn("freeship", tags)
        self.assertIn("hoàn tiền", tags)
        self.assertIn("bảo hành", tags)

    def test_extract_text_from_txt_and_docx_bytes(self):
        txt_out = pf.extract_text_from_file_bytes("policy.txt", "Chính sách hoàn tiền 30 ngày".encode("utf-8"))
        self.assertIn("hoàn tiền 30 ngày", txt_out)

        buf = io.BytesIO()
        xml_body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Quy định đổi trả Tiki</w:t></w:r></w:p></w:body>"
            "</w:document>"
        )
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", xml_body)
        docx_out = pf.extract_text_from_file_bytes("policy.docx", buf.getvalue())
        self.assertEqual(docx_out, "Quy định đổi trả Tiki")

    def test_filter_raw_policy_heuristic_offline_fallback(self):
        req = RawPolicyFilterRequest(
            raw_text=(
                "Khuyến mãi Tết tạm thời 2025\n"
                "Áp dụng giảm giá voucher freeship từ 01/02/2025 cho đơn hàng."
            )
        )
        with patch.dict(os.environ, {"DISABLE_EXTERNAL_LLM": "true"}, clear=False), patch.object(
            pf.policy_manager, "load_policies", return_value=self.sample_existing
        ), patch.object(pf, "_llm_extract_openai", new=AsyncMock(return_value=None)):
            res = asyncio.run(pf.filter_raw_policy(req))

        self.assertEqual(res.confidence_score, 0.70)
        self.assertEqual(res.extracted_policy.policy_type, "temporary")
        self.assertEqual(res.extracted_policy.effective_date, "2025-02-01")
        self.assertTrue(any("Heuristic Rule" in w for w in res.warnings))
        self.assertTrue(any("ngày hết hạn" in w for w in res.warnings))

    def test_filter_bulk_raw_policy_uses_llm_items_when_mocked(self):
        mock_items = [
            {
                "title": "Bảo hành mở rộng 2099",
                "category": "warranty",
                "policy_type": "temporary",
                "effective_date": "2024-01-01",
                "expiration_date": "2099-12-31",
                "content": "Bảo hành chính hãng trong suốt thời gian hiệu lực.",
                "tags": ["bảo hành"],
            }
        ]
        with patch.object(pf.policy_manager, "load_policies", return_value=self.sample_existing), patch.object(
            pf, "_llm_extract_openai_items", new=AsyncMock(return_value=mock_items)
        ):
            results = asyncio.run(pf.filter_bulk_raw_policy("Chính sách bảo hành mở rộng"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].confidence_score, 0.92)
        self.assertEqual(results[0].extracted_policy.category, "warranty")
        self.assertTrue(results[0].extracted_policy.is_active)

    def test_empty_raw_text_raises_value_error(self):
        with self.assertRaises(ValueError):
            asyncio.run(pf.filter_raw_policy(RawPolicyFilterRequest(raw_text="   ")))
        with self.assertRaises(ValueError):
            asyncio.run(pf.filter_bulk_raw_policy("   "))


if __name__ == "__main__":
    unittest.main()
