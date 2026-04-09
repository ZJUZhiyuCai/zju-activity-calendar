import os
import unittest

from core.runtime_flags import is_auth_refresh_enabled


class RuntimeFlagsTests(unittest.TestCase):
    def setUp(self):
        self._old_auth_env = os.environ.get("WE_RSS.AUTH")
        os.environ.pop("WE_RSS.AUTH", None)

    def tearDown(self):
        if self._old_auth_env is None:
            os.environ.pop("WE_RSS.AUTH", None)
        else:
            os.environ["WE_RSS.AUTH"] = self._old_auth_env

    def test_auth_refresh_disabled_by_default(self):
        self.assertFalse(is_auth_refresh_enabled())

    def test_auth_refresh_supports_legacy_env_flag(self):
        os.environ["WE_RSS.AUTH"] = "True"
        self.assertTrue(is_auth_refresh_enabled())

    def test_auth_refresh_force_flag_overrides_runtime_config(self):
        self.assertTrue(is_auth_refresh_enabled(force=True))


if __name__ == "__main__":
    unittest.main()
