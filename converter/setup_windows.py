import argparse
import ctypes
from pathlib import Path
import winreg

from .catalog import SUPPORTED


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "launch.pyw"
ICON = ROOT / "file-converter.ico"
VERB = "LocalFileConverter.Convert"
ASSOCIATIONS = r"Software\Classes\SystemFileAssociations"


def make_icon():
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (256, 256))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((11, 11, 245, 245), radius=54, fill="#5056c8")
    for points in (
        ((65, 99), (191, 99), (159, 67)), ((191, 99), (159, 131)),
        ((191, 157), (65, 157), (97, 125)), ((65, 157), (97, 189)),
    ):
        draw.line(points, fill="white", width=14, joint="curve")
        for x, y in points:
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill="white")
    canvas.save(ICON, sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])


def shortcut():
    from win32com.client import Dispatch

    shell = Dispatch("WScript.Shell")
    path = Path(shell.SpecialFolders("Programs")) / "File Converter.lnk"
    return shell, path


def register():
    pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.is_file():
        raise FileNotFoundError(pythonw)
    make_icon()
    command = f'"{pythonw}" "{LAUNCHER}" -- "%1"'
    for ext in sorted(SUPPORTED):
        key_path = rf"{ASSOCIATIONS}\.{ext}\shell\{VERB}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            for name, value in {"": "Convert", "MUIVerb": "Convert", "MultiSelectModel": "Single",
                                "Icon": str(ICON), "Position": "Top"}.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

    shell, path = shortcut()
    entry = shell.CreateShortcut(str(path))
    entry.TargetPath = str(pythonw)
    entry.Arguments = f'"{LAUNCHER}"'
    entry.WorkingDirectory = str(ROOT)
    entry.IconLocation = f"{ICON},0"
    entry.Description = "Convert and edit files on this device"
    entry.Save()
    notify_explorer()
    print(f"Added Convert for {len(SUPPORTED)} file extensions and installed the File Converter Start menu shortcut.")


def unregister():
    for ext in sorted(SUPPORTED):
        key_path = rf"{ASSOCIATIONS}\.{ext}\shell\{VERB}"
        for path in (key_path + r"\command", key_path):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except FileNotFoundError:
                continue
    _, path = shortcut()
    path.unlink(missing_ok=True)
    notify_explorer()
    print("Removed the Convert menu entries and the File Converter Start menu shortcut.")


def notify_explorer():
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "remove"])
    if parser.parse_args().action == "install":
        register()
    else:
        unregister()
