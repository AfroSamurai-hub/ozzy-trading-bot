import json
import os
import tempfile
import unittest
from pathlib import Path

import dynamic_config


class DynamicConfigTests(unittest.TestCase):
    def setUp(self):
        self.original_path = os.environ.get("HERMES_DYNAMIC_CONFIG")
        dynamic_config._CACHE = {}
        dynamic_config._LAST_LOADED_TIME = 0.0
        dynamic_config._LAST_MTIME = 0.0

    def tearDown(self):
        if self.original_path is None:
            os.environ.pop("HERMES_DYNAMIC_CONFIG", None)
        else:
            os.environ["HERMES_DYNAMIC_CONFIG"] = self.original_path
        dynamic_config._CACHE = {}
        dynamic_config._LAST_LOADED_TIME = 0.0
        dynamic_config._LAST_MTIME = 0.0

    def test_get_symbol_param_prefers_symbol_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "dynamic.json"
            config_path.write_text(
                json.dumps(
                    {
                        "adx_threshold": 25.0,
                        "per_symbol": {
                            "XAUUSDT": {
                                "adx_threshold": 18.0,
                            }
                        },
                    }
                )
            )
            os.environ["HERMES_DYNAMIC_CONFIG"] = str(config_path)

            self.assertEqual(dynamic_config.get_symbol_param("XAUUSDT", "adx_threshold", 25.0), 18.0)

    def test_get_symbol_param_falls_back_to_global(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "dynamic.json"
            config_path.write_text(json.dumps({"adx_threshold": 25.0, "per_symbol": {}}))
            os.environ["HERMES_DYNAMIC_CONFIG"] = str(config_path)

            self.assertEqual(dynamic_config.get_symbol_param("SUIUSDT", "adx_threshold", 20.0), 25.0)


if __name__ == "__main__":
    unittest.main()
