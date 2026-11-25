import ctypes
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import winreg

from .catalog import OFFICE, extension


LIBREOFFICE = (
    Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "LibreOffice/program/soffice.com",
    Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "LibreOffice/program/soffice.com",
)


def export_pdf(source: Path, target: Path) -> None:
    office_app = next(name for name, types in OFFICE.items() if extension(source) in types)
    prog_id = f"{office_app}.Application"
    libreoffice = shutil.which("soffice.com") or next((str(path) for path in LIBREOFFICE if path.is_file()), None)
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\CLSID"):
            installed = True
    except OSError:
        installed = False

    if installed:
        try:
            microsoft_export(office_app, prog_id, source, target)
            return
        except Exception as error:
            if not libreoffice:
                message = getattr(error, "excepinfo", None)
                detail = (message[2] or "").strip() if message else ""
                raise ValueError(f"{office_app} could not export this file. {detail}".strip()) from error
    if libreoffice:
        with TemporaryDirectory(prefix="file-converter-office-") as profile:
            process = subprocess.run(
                [libreoffice, f"-env:UserInstallation={Path(profile).as_uri()}", "--headless",
                 "--convert-to", "pdf", "--outdir", str(target.parent), str(source)],
                capture_output=True, text=True, errors="replace", timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            exported = target.parent / f"{source.stem}.pdf"
            if exported.is_file() and process.returncode == 0:
                if exported != target:
                    os.replace(exported, target)
                return
            raise ValueError(process.stderr.strip() or "LibreOffice could not export this file.")
    raise ValueError(f"Install Microsoft {office_app} or LibreOffice to export this file to PDF.")


def microsoft_export(name: str, prog_id: str, source: Path, target: Path) -> None:
    import pythoncom
    from win32com.client import DispatchEx

    pythoncom.CoInitialize()
    app = document = None
    shared = name == "PowerPoint" and bool(ctypes.windll.user32.FindWindowW("PPTFrameClass", None))
    security = alerts = word_links = None
    try:
        app = DispatchEx(prog_id)
        if name == "PowerPoint":
            shared = shared or app.Presentations.Count > 0
            security, alerts = app.AutomationSecurity, app.DisplayAlerts
        app.AutomationSecurity = 3
        if name == "Word":
            app.DisplayAlerts = 0
            word_links = app.Options.UpdateLinksAtOpen
            app.Options.UpdateLinksAtOpen = False
            document = app.Documents.Open(
                FileName=str(source), ReadOnly=True, AddToRecentFiles=False, Visible=False,
                PasswordDocument="\x01", ConfirmConversions=False, NoEncodingDialog=True,
            )
            document.ExportAsFixedFormat(str(target), 17)
        elif name == "Excel":
            app.DisplayAlerts = False
            document = app.Workbooks.Open(str(source), 0, True, Password="\x01", IgnoreReadOnlyRecommended=True)
            document.ExportAsFixedFormat(0, str(target))
        else:
            app.DisplayAlerts = 1
            document = app.Presentations.Open(str(source), True, False, False)
            document.SaveAs(str(target), 32)
    finally:
        try:
            if document is not None:
                if name == "PowerPoint":
                    document.Close()
                else:
                    document.Close(False)
        finally:
            try:
                if app is not None:
                    if name == "PowerPoint" and (shared or app.Presentations.Count > 0):
                        if security is not None:
                            app.AutomationSecurity = security
                            app.DisplayAlerts = alerts
                    else:
                        try:
                            if word_links is not None:
                                app.Options.UpdateLinksAtOpen = word_links
                        finally:
                            app.Quit()
            finally:
                pythoncom.CoUninitialize()
