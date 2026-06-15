from __future__ import annotations

import unittest

from desktop_app import wait_for_server


class BrokenThread:
    startup_error = RuntimeError("boom")


class DesktopStartupTests(unittest.TestCase):
    def test_wait_for_server_surfaces_background_startup_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "后台服务启动失败"):
            wait_for_server("http://127.0.0.1:9/api/health", timeout=0.2, server_thread=BrokenThread())


if __name__ == "__main__":
    unittest.main()
