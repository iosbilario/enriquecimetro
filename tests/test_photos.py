import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_photos import index_photos_by_sq, sq_from_photo_name  # noqa: E402


class TestPhotoNames(unittest.TestCase):
    def test_extract_sq(self):
        self.assertEqual(sq_from_photo_name("FAC10002544107_div.jpg"), "10002544107")
        self.assertEqual(sq_from_photo_name("FSP260001234567_div.jpeg"), "260001234567")

    def test_subfolder_and_case(self):
        self.assertEqual(sq_from_photo_name("fotos/FTO270001621504_DIV.JPG"), "270001621504")

    def test_rejects_other_files(self):
        self.assertIsNone(sq_from_photo_name("leiame.pdf"))
        self.assertIsNone(sq_from_photo_name("F_div.jpg"))

    def test_index(self):
        idx = index_photos_by_sq(
            ["FAC111_div.jpg", "FAC222_div.jpg", "leiame.txt"]
        )
        self.assertEqual(idx, {"111": "FAC111_div.jpg", "222": "FAC222_div.jpg"})


if __name__ == "__main__":
    unittest.main()
