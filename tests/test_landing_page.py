import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LandingPageTests(unittest.TestCase):
    def test_landing_page_introduces_dynamic_todo_island(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("<title>Dynamic Todo Island", html)
        self.assertIn("Dynamic Todo Island", html)
        self.assertIn("桌面顶部的待办灵动岛", html)
        self.assertIn("系统托盘", html)
        self.assertIn("dist/DynamicTodoIsland.exe", html)
        self.assertIn("待办工具桌面图标设计.png", html)


if __name__ == "__main__":
    unittest.main()
