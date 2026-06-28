import unittest

from app.ai.model_catalog import get_model, recommend_model


class ModelCatalogTest(unittest.TestCase):
    def test_recommend_model_by_ram(self) -> None:
        self.assertEqual(recommend_model(8).id, "small")
        self.assertEqual(recommend_model(16).id, "medium")
        self.assertEqual(recommend_model(32).id, "large")

    def test_get_model_unknown(self) -> None:
        self.assertIsNone(get_model("missing"))


if __name__ == "__main__":
    unittest.main()
