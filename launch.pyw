import ctypes
import sys
import traceback
from pathlib import Path


def main():
    from PySide6.QtWidgets import QApplication

    from converter.app import ConverterWindow

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LocalTools.FileConverter")
    launcher, *paths = sys.argv
    app = QApplication([launcher])
    app.setApplicationName("File Converter")
    app.setStyle("Fusion")
    window = ConverterWindow(paths[1:] if paths and paths[0] == "--" else paths)
    window.show()
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        error = traceback.format_exc()
        if sys.stderr:
            print(error, file=sys.stderr)
        if sys.executable.lower().endswith("pythonw.exe"):
            try:
                Path(__file__).with_name("launch-error.log").write_text(error, encoding="utf-8")
            finally:
                ctypes.windll.user32.MessageBoxW(None, error, "File Converter could not start", 0x10)
        sys.exit(1)
