from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.config_presets import load_config_bundle, load_default_preset, load_preset_configs


class ConfigPresetTests(unittest.TestCase):
    def test_repo_bundle_contains_expected_presets(self) -> None:
        configs = load_config_bundle(Path("data/erc_configs2.json"))

        self.assertEqual(len(configs), 4)
        self.assertTrue(all(config["mode"] == "嵌套" for config in configs))
        self.assertTrue(all(config["benchmark_code"] == "H00300.CSI" for config in configs))
        self.assertEqual([config["name"] for config in configs if config.get("default")], ["自由现金流+成长100+长债+黄金+豆粕"])

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

    def test_requested_config_is_the_default_and_tracks_latest_data(self) -> None:
        config = load_default_preset(Path("data/erc_configs2.json"))

        self.assertEqual(config["name"], "自由现金流+成长100+长债+黄金+豆粕")
        self.assertEqual(config["benchmark_code"], "H00300.CSI")
        self.assertEqual(
            [asset for group in config["nested_groups"] for asset in group["assets"]],
            ["480092.CNI", "480080.CNI", "CBA21801.CS", "AU9999.SGE", "159985.SZ"],
        )
        self.assertTrue(config["auto_end_date"])
        self.assertTrue(config["_preset"])

    def test_multiple_defaults_are_rejected(self) -> None:
        source = {
            "configs": [
                {"name": "A", "default": True},
                {"name": "B", "default": True},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configs.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_default_preset(path)

    def test_invalid_bundle_shape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configs.json"
            path.write_text('{"configs": {"name": "bad"}}', encoding="utf-8")

            with self.assertRaises(ValueError):
                load_config_bundle(path)


if __name__ == "__main__":
    unittest.main()
