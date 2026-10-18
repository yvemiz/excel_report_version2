import unittest

from app.pipeline.dsml_guard import DSML_MARK, DeepSeekDsmlFilter


class DeepSeekFilterCompatibilityTest(unittest.TestCase):
    def test_provider_filter_contract(self):
        item = DeepSeekDsmlFilter()
        self.assertEqual(item.name, "deepseek_dsml")
        self.assertTrue(item.message)
        clean, leaked = item.sanitize(f"正文\n<｜｜DSML｜｜ calls>")
        self.assertEqual(clean, "正文")
        self.assertTrue(leaked)
        self.assertIn(DSML_MARK, "<｜｜DSML｜｜ calls>")


if __name__ == "__main__":
    unittest.main()
