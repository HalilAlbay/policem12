import unittest
from pdf_reader_v2 import extract_fields

class ReaderTests(unittest.TestCase):
    def test_turkish_synonyms(self):
        text = """Poliçe Numarası: ABC-123/45
Sigortalı Adı Soyadı: Ayşe Yılmaz
Vade Başlangıcı: 01.02.2026
Vade Sonu: 01.02.2027
Toplam Brüt Prim: 1.234,56 TL
Sigorta Şirketi: Örnek Sigorta A.Ş."""
        x = extract_fields(text)
        self.assertEqual(x["policy_number"], "ABC-123/45")
        self.assertEqual(x["customer_name"], "Ayşe Yılmaz")
        self.assertEqual(x["start_date"], "2026-02-01")
        self.assertEqual(x["end_date"], "2027-02-01")
        self.assertEqual(x["premium"], 1234.56)
        self.assertEqual(x["insurer"], "Örnek Sigorta A.Ş.")

    def test_english_labels(self):
        x = extract_fields("Policy Number: ZX9000\nEffective Date: 12/01/2026\nExpiration Date: 12/01/2027\nTotal Premium: 1,250.50")
        self.assertEqual(x["policy_number"], "ZX9000")
        self.assertEqual(x["start_date"], "2026-01-12")
        self.assertEqual(x["premium"], 1250.50)

    def test_invalid_date_not_guessed(self):
        x = extract_fields("Başlangıç Tarihi: 31.02.2026\nBitiş Tarihi: 01.03.2027")
        self.assertNotIn("start_date", x)

    def test_unrelated_document(self):
        self.assertEqual(extract_fields("Bu belge genel şartlar ve bilgilendirme metnidir."), {})

if __name__ == "__main__":
    unittest.main()
