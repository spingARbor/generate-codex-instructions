import unittest

from src.normalize_label import normalize_label


class NormalizeLabelTest(unittest.TestCase):
    def test_trims_valid_label(self):
        self.assertEqual(normalize_label("  alpha  "), "alpha")

    def test_rejects_non_string(self):
        with self.assertRaises(TypeError):
            normalize_label(None)


if __name__ == "__main__":
    unittest.main()
