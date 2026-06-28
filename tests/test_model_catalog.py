import unittest

from app.ai.model_catalog import get_model, list_models, recommend_model


class ModelCatalogTest(unittest.TestCase):
    def test_recommend_model_by_ram(self) -> None:
        self.assertEqual(recommend_model(8).id, "small")
        self.assertEqual(recommend_model(16).id, "medium")
        self.assertEqual(recommend_model(32).id, "large")

    def test_get_model_unknown(self) -> None:
        self.assertIsNone(get_model("missing"))

    def test_model_urls_are_real_and_sizes_match(self) -> None:
        expected_sizes = {"small": 1.93, "medium": 4.68, "large": 8.99}
        for model in list_models():
            self.assertNotIn("example.com", model.download_url)
            self.assertIn("huggingface.co", model.download_url)
            self.assertEqual(model.size_gb, expected_sizes[model.id])


if __name__ == "__main__":
    unittest.main()
