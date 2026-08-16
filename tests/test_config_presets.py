from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.config_presets import load_config_bundle, load_preset_configs


class ConfigPresetTests(unittest.TestCase):
    def test_repo_bundle_contains_expected_presets(self) -> None:
        configs = load_config_bundle(Path("data/erc_configs2.json"))

        self.assertEqual(len(configs), 4)
        self.assertTrue(all(config["mode"] == "嵌套" for config in configs))
        self.assertTrue(all(config["benchmark_code"] == "H00300.CSI" for config in configs))

    def test_presets_follow_latest_data_without_mutating_source(self) -> None:
        source = {
            "version": 1,
            "configs": [
                {
                    "name": "示例",
                    "mode": "基础",
                    "custom_end": "2026-05-25",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configs.json"
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")

            presets = load_preset_configs(path)
            raw_configs = load_config_bundle(path)

        self.assertTrue(presets[0]["auto_end_date"])
        self.assertTrue(presets[0]["_preset"])
        self.assertNotIn("auto_end_date", raw_configs[0])
        self.assertNotIn("_preset", raw_configs[0])

    def test_invalid_bundle_shape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configs.json"
            path.write_text('{"configs": {"name": "bad"}}', encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config_bundle(path)


if __name__ == "__main__":
    unittest.main()
