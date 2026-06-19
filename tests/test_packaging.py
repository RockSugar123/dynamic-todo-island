import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app


class PackagingTests(unittest.TestCase):
    def test_resource_path_uses_source_directory_by_default(self):
        self.assertEqual(app.resource_path("icon.ico"), ROOT / "icon.ico")

    def test_resource_path_uses_pyinstaller_temp_directory_when_frozen(self):
        original_meipass = getattr(sys, "_MEIPASS", None)
        had_meipass = hasattr(sys, "_MEIPASS")
        try:
            sys._MEIPASS = str(ROOT / "dist" / "_internal")
            self.assertEqual(app.resource_path("icon.ico"), ROOT / "dist" / "_internal" / "icon.ico")
        finally:
            if had_meipass:
                sys._MEIPASS = original_meipass
            else:
                delattr(sys, "_MEIPASS")

    def test_tray_icon_loads_prepared_asset(self):
        icon = app.load_icon_image()
        self.assertEqual(icon.mode, "RGBA")
        self.assertGreaterEqual(icon.width, 16)
        self.assertGreaterEqual(icon.height, 16)

    def test_taskbar_hidden_style_marks_window_as_tool_window(self):
        original_style = app.WS_EX_APPWINDOW | 0x20
        hidden_style = app.taskbar_hidden_exstyle(original_style)

        self.assertFalse(hidden_style & app.WS_EX_APPWINDOW)
        self.assertTrue(hidden_style & app.WS_EX_TOOLWINDOW)
        self.assertTrue(hidden_style & 0x20)

    def test_pyinstaller_spec_uses_icon_asset_and_no_console(self):
        spec = (ROOT / "DynamicTodoIsland.spec").read_text(encoding="utf-8")
        self.assertIn("name='DynamicTodoIsland'", spec)
        self.assertIn("icon='icon.ico'", spec)
        self.assertIn("console=False", spec)
        self.assertIn("('icon.ico', '.')", spec)


if __name__ == "__main__":
    unittest.main()
