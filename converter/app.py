import os
from pathlib import Path
import subprocess

from PySide6.QtCore import QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget, QFileDialog,
)

from .catalog import IMAGE_INPUTS, OFFICE_INPUTS, SUPPORTED, available, extension
from .engine import Result, execute, validate_settings
from .theme import ACCENT, MUTED, STYLE, icon


def label(text, style=None, *, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if style:
        widget.setObjectName(style)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback=None, *, symbol=None, style=None, tooltip=None):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if style:
        widget.setObjectName(style)
    if symbol:
        widget.setIcon(icon(symbol, "#ffffff" if style == "primary" else ACCENT))
        widget.setIconSize(QSize(19, 19))
    if callback:
        widget.clicked.connect(callback)
    if tooltip:
        widget.setToolTip(tooltip)
        widget.setAccessibleName(tooltip)
    return widget


def icon_label(symbol, style, size, *, color=ACCENT):
    widget = QLabel()
    widget.setObjectName(style)
    widget.setFixedSize(size, size)
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    length = round(size * 0.52)
    widget.setPixmap(icon(symbol, color, length).pixmap(QSize(length, length), 2))
    return widget


def panel(style):
    widget = QFrame()
    widget.setObjectName(style)
    return widget


def layout(parent, margins=(0, 0, 0, 0), spacing=10, *, horizontal=False):
    body = QHBoxLayout(parent) if horizontal else QVBoxLayout(parent)
    body.setContentsMargins(*margins)
    body.setSpacing(spacing)
    return body


def scroll_area():
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    content.setObjectName("transparent")
    scroll.setWidget(content)
    return scroll, content


def clear_layout(body):
    while item := body.takeAt(0):
        if widget := item.widget():
            widget.setParent(None)
            widget.deleteLater()
        elif children := item.layout():
            clear_layout(children)


def size_label(size):
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


class ConversionJob(QThread):
    progress = Signal(int, int, str)
    completed = Signal(object)

    def __init__(self, operation, paths, options, destination, parent):
        super().__init__(parent)
        self.arguments = operation, paths, options, destination, self.progress.emit

    def run(self):
        try:
            outcome = execute(*self.arguments)
        except Exception as error:
            outcome = Result(errors=[str(error).strip() or type(error).__name__])
        self.completed.emit(outcome)


class ConverterWindow(QMainWindow):
    def __init__(self, paths):
        super().__init__()
        self.paths = []
        self.destination = None
        self.operation = None
        self.choices = []
        self.fields = {}
        self.tool_buttons = {}
        self.merge_hint = None
        self.job = None
        self.outcome = None
        self.setWindowTitle("File Converter")
        app_icon = Path(__file__).resolve().parents[1] / "file-converter.ico"
        self.setWindowIcon(QIcon(str(app_icon)) if app_icon.is_file() else icon("brand"))
        self.setMinimumSize(850, 540)
        self.resize(1100, 765)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        self.build_window()
        self.add_paths(paths)
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.choose_files)

    def build_window(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        main = layout(root, spacing=0)

        topbar = QWidget()
        topbar.setObjectName("topbar")
        top = layout(topbar, (26, 14, 26, 14), 12, horizontal=True)
        top.addWidget(icon_label("brand", "brandMark", 40, color="white"))
        brand_widget = QWidget()
        brand = layout(brand_widget, spacing=0)
        brand.addWidget(label("File Converter", "brandTitle"))
        brand.addWidget(label("Files stay on this device", "hint"))
        top.addWidget(brand_widget)
        top.addStretch()
        self.add_files_button = button("Add files", self.choose_files, symbol="add")
        top.addWidget(self.add_files_button)
        main.addWidget(topbar)

        canvas = QWidget()
        canvas.setObjectName("canvas")
        columns = layout(canvas, (26, 23, 26, 23), 20, horizontal=True)
        self.workspace, workspace = scroll_area()
        work = layout(workspace, (0, 0, 4, 0), 14)
        work.addWidget(label("Your files", "title"))
        self.drop = panel("drop")
        self.drop.setProperty("active", False)
        drop_inner = layout(self.drop, (16, 20, 16, 20), 8)
        drop_inner.addWidget(icon_label("upload", "emptyIcon", 48), alignment=Qt.AlignmentFlag.AlignHCenter)
        drop_inner.addWidget(label("Drop files here", "subheading"), alignment=Qt.AlignmentFlag.AlignHCenter)
        formats = label("PDFs, images, Office documents and text", "muted", wrap=True)
        formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_inner.addWidget(formats)
        drop_inner.addWidget(button("Browse files", self.choose_files, symbol="add", style="primary"),
                             alignment=Qt.AlignmentFlag.AlignHCenter)
        work.addWidget(self.drop)

        self.queue = panel("surface")
        queue = layout(self.queue, (13, 9, 13, 9), 2)
        self.files = QListWidget()
        self.files.setAccessibleName("Selected files in output order")
        self.files.setStyleSheet("QListWidget { border: 0; } QListWidget::item { min-height: 22px; }")
        self.files.currentRowChanged.connect(self.update_queue_buttons)
        queue.addWidget(self.files)
        queue_bar = QWidget()
        bar = layout(queue_bar, spacing=2, horizontal=True)
        self.file_count = label("", "hint")
        bar.addWidget(self.file_count)
        bar.addStretch()
        self.move_up = button("", lambda: self.move_file(-1), symbol="up", style="rowButton", tooltip="Move selected file up")
        self.move_down = button("", lambda: self.move_file(1), symbol="down", style="rowButton", tooltip="Move selected file down")
        self.remove_file = button("", self.remove_selected, symbol="close", style="rowButton", tooltip="Remove selected file")
        for control in (self.move_up, self.move_down, self.remove_file):
            control.setFixedSize(34, 30)
            bar.addWidget(control)
        self.clear_files = button("Clear", self.clear_selection, style="ghost")
        bar.addWidget(self.clear_files)
        queue.addWidget(queue_bar)
        work.addWidget(self.queue)

        self.notice = label("", "warning", wrap=True)
        self.notice.hide()
        work.addWidget(self.notice)
        self.tool_area = QWidget()
        tool_area = layout(self.tool_area, spacing=12)
        tool_header_widget = QWidget()
        tool_header = layout(tool_header_widget, spacing=12, horizontal=True)
        tool_header.addWidget(label("Available tools", "subheading"))
        tool_header.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a tool")
        self.search.setAccessibleName("Find a tool")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", MUTED), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setMaximumWidth(185)
        self.search.textChanged.connect(self.render_tools)
        tool_header.addWidget(self.search)
        tool_area.addWidget(tool_header_widget)
        tool_grid = QWidget()
        self.tools = layout(tool_grid, spacing=10)
        tool_area.addWidget(tool_grid)
        work.addWidget(self.tool_area)
        work.addStretch()
        columns.addWidget(self.workspace, 1)

        side = panel("side")
        side.setFixedWidth(326)
        side_inner = layout(side, (17, 16, 17, 15), 13)
        settings_scroll, settings = scroll_area()
        self.settings = layout(settings, (1, 0, 4, 2), 9)
        side_inner.addWidget(settings_scroll, 1)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        side_inner.addWidget(line)
        side_inner.addWidget(label("Save to", "fieldLabel"))
        output_widget = QWidget()
        out_row = layout(output_widget, spacing=5, horizontal=True)
        self.output_folder = QLineEdit("Same folder as the original")
        self.output_folder.setReadOnly(True)
        self.output_folder.setAccessibleName("Output folder")
        out_row.addWidget(self.output_folder, 1)
        self.choose_output_button = button("", self.choose_output, symbol="folder", tooltip="Choose output folder")
        self.choose_output_button.setFixedWidth(38)
        out_row.addWidget(self.choose_output_button)
        self.clear_output_button = button("", self.reset_output, symbol="close", style="ghost", tooltip="Use original folder")
        self.clear_output_button.setFixedWidth(32)
        self.clear_output_button.hide()
        out_row.addWidget(self.clear_output_button)
        side_inner.addWidget(output_widget)

        self.status = label("", "hint", wrap=True)
        self.status.hide()
        side_inner.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.hide()
        side_inner.addWidget(self.progress)

        self.result_panel = panel("result")
        result_box = layout(self.result_panel, (10, 8, 10, 8), 5)
        self.result_label = label("", "success", wrap=True)
        result_box.addWidget(self.result_label)
        self.results_button = button("View results", self.show_results, symbol="arrow")
        result_box.addWidget(self.results_button)
        side_inner.addWidget(self.result_panel)
        self.result_panel.hide()

        self.run_button = button("Choose files to begin", self.start_conversion, symbol="arrow", style="primary")
        self.run_button.setMinimumHeight(43)
        side_inner.addWidget(self.run_button)
        columns.addWidget(side)
        main.addWidget(canvas, 1)

    def choose_files(self):
        if self.job:
            return
        filters = [f"Supported files ({' '.join('*.' + ext for ext in sorted(SUPPORTED))})",
                   "PDF files (*.pdf)",
                   f"Images ({' '.join('*.' + ext for ext in sorted(IMAGE_INPUTS))})",
                   f"Office documents ({' '.join('*.' + ext for ext in sorted(OFFICE_INPUTS))})",
                   "Text files (*.txt *.md)", "All files (*)"]
        start = str(self.paths[-1].parent) if self.paths else ""
        paths, _ = QFileDialog.getOpenFileNames(self, "Add files to convert", start, ";;".join(filters))
        if paths:
            self.add_paths(paths)

    def add_paths(self, paths):
        if self.job:
            return
        skipped = []
        known = {os.path.normcase(str(path)) for path in self.paths}
        for path in paths:
            try:
                candidate = Path(path).resolve()
                if not candidate.is_file() or extension(candidate) not in SUPPORTED:
                    skipped.append(candidate.name or str(path))
                    continue
            except OSError:
                skipped.append(str(path))
                continue
            identity = os.path.normcase(str(candidate))
            if identity not in known:
                self.paths.append(candidate)
                known.add(identity)
        self.refresh_selection(len(self.paths) - 1)
        if skipped:
            first = ", ".join(skipped[:3])
            rest = f" and {len(skipped) - 3} more" if len(skipped) > 3 else ""
            self.set_notice(f"Could not add {first}{rest}. Choose supported files.")

    def refresh_selection(self, row=0):
        self.drop.setVisible(not self.paths)
        self.queue.setVisible(bool(self.paths))
        self.tool_area.setVisible(bool(self.paths))
        self.files.clear()
        for path in self.paths:
            ext = extension(path)
            try:
                size = size_label(path.stat().st_size)
            except OSError:
                size = "Unavailable"
            item = QListWidgetItem(icon("image" if ext in IMAGE_INPUTS else "file"), f"{path.name}   ·   {size}")
            item.setToolTip(str(path))
            self.files.addItem(item)
        self.files.setFixedHeight(min(154, 4 + 39 * len(self.paths)))
        if self.paths:
            self.files.setCurrentRow(min(max(row, 0), len(self.paths) - 1))
        self.file_count.setText(f"{len(self.paths)} {'file' if len(self.paths) == 1 else 'files'} selected")
        self.choices = available(self.paths)
        choice_ids = [choice.id for choice in self.choices]
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.search.setVisible(len(self.choices) > 5)
        self.set_notice("These file types have no shared tool. Remove files or choose a matching group."
                        if self.paths and not self.choices else "")
        keep_settings = self.operation is not None and self.operation.id in choice_ids
        if not keep_settings:
            preference = "image-jpg" if {extension(path) for path in self.paths} == {"png"} else ""
            self.operation = next((choice for choice in self.choices if choice.id == preference),
                                  self.choices[0] if self.choices else None)
        self.update_queue_buttons()
        self.render_tools()
        if not keep_settings or (("password" in self.fields) != any(extension(path) == "pdf" for path in self.paths)):
            self.render_settings()
        else:
            self.update_run()

    def update_queue_buttons(self, *_):
        row = self.files.currentRow()
        self.move_up.setEnabled(row > 0 and not self.job)
        self.move_down.setEnabled(0 <= row < len(self.paths) - 1 and not self.job)
        self.remove_file.setEnabled(row >= 0 and not self.job)

    def set_notice(self, message):
        self.notice.setText(message)
        self.notice.setVisible(bool(message))

    def move_file(self, offset):
        row = self.files.currentRow()
        target = row + offset
        if 0 <= row < len(self.paths) and 0 <= target < len(self.paths):
            self.paths[row], self.paths[target] = self.paths[target], self.paths[row]
            self.refresh_selection(target)

    def remove_selected(self):
        row = self.files.currentRow()
        if 0 <= row < len(self.paths):
            self.paths.pop(row)
            self.refresh_selection(row)

    def clear_selection(self):
        self.paths.clear()
        self.refresh_selection()

    def render_tools(self, *_):
        clear_layout(self.tools)
        self.tool_buttons.clear()
        query = self.search.text().casefold().strip()
        groups = {}
        for operation in self.choices:
            if query in f"{operation.label} {operation.description} {operation.category}".casefold():
                groups.setdefault(operation.category, []).append(operation)
        for category, operations in groups.items():
            self.tools.addWidget(label(category, "groupHeading"))
            grid = QGridLayout()
            grid.setSpacing(8)
            for index in range(3):
                grid.setColumnStretch(index, 1)
            for index, operation in enumerate(operations):
                tool = button(operation.label, lambda _, selected=operation: self.pick_tool(selected),
                              symbol=operation.icon, style="tool", tooltip=operation.description)
                tool.setAccessibleName(operation.label)
                tool.setCheckable(True)
                tool.setChecked(self.operation == operation)
                tool.setEnabled(not self.job)
                tool.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
                self.tool_buttons[operation.id] = tool
                grid.addWidget(tool, index // 3, index % 3)
            self.tools.addLayout(grid)
        if query and not groups:
            self.tools.addWidget(label("No tools match your search.", "muted"))

    def pick_tool(self, operation):
        changed = self.operation != operation
        self.operation = operation
        for key, control in self.tool_buttons.items():
            control.setChecked(key == operation.id)
        if changed:
            self.render_settings()

    def render_settings(self):
        clear_layout(self.settings)
        self.fields.clear()
        self.merge_hint = None
        self.set_status("")
        if not self.operation:
            self.settings.addWidget(icon_label("brand", "selectedIcon", 46))
            self.settings.addWidget(label("Choose a file", "selectedTitle"))
            self.settings.addWidget(label("Add a file to see its conversion and editing tools.", "muted", wrap=True))
            self.settings.addStretch()
            self.update_run()
            return

        op = self.operation.id
        heading_widget = QWidget()
        heading = layout(heading_widget, spacing=10, horizontal=True)
        heading.addWidget(icon_label(self.operation.icon, "selectedIcon", 44))
        title_widget = QWidget()
        title = layout(title_widget, spacing=1)
        title.addWidget(label(self.operation.category, "hint"))
        title.addWidget(label(self.operation.label, "selectedTitle", wrap=True))
        heading.addWidget(title_widget, 1)
        self.settings.addWidget(heading_widget)
        self.settings.addWidget(label(self.operation.description, "muted", wrap=True))
        self.settings.addSpacing(5)

        if op in {"rotate", "number", "watermark", "extract", "delete", "reorder"} or op.startswith("pdf-"):
            optional = op not in {"extract", "delete", "reorder"}
            prompt = "All pages" if optional else ("3, 1, 2, 4–10" if op == "reorder" else "1, 3–5")
            self.add_text("pages", "Pages", prompt)
        if op.startswith("pdf-"):
            self.add_combo("dpi", "Resolution", [("150 DPI", 150), ("96 DPI", 96), ("200 DPI", 200), ("300 DPI", 300), ("600 DPI", 600)])
        if op in {"image-jpg", "image-webp", "image-avif", "image-heic", "pdf-jpg", "pdf-webp"}:
            self.add_spin("quality", "Quality", 1, 100, 90, "%")
        if op == "split":
            mode = self.add_combo("split_mode", "Split method", [("One file per page", "pages"),
                                  ("Every N pages", "interval"), ("Custom ranges", "ranges")])
            interval = self.add_spin("interval", "Pages per file", 1, 9999, 2)
            ranges = self.add_text("ranges", "Ranges separated by semicolons", "1–3; 4–7; 8")
            mode.currentIndexChanged.connect(lambda index: (interval.setVisible(index == 1), ranges.setVisible(index == 2)))
            interval.hide()
            ranges.hide()
        if op == "rotate":
            self.add_combo("rotation", "Clockwise rotation", [("90°", 90), ("180°", 180), ("270°", 270)])
        if op == "compress":
            self.add_combo("compression", "Compression", [("Lossless optimization", "lossless"),
                           ("Balanced (150 DPI images)", "balanced"), ("Smaller file (96 DPI images)", "small")])
        if op == "watermark":
            self.add_text("watermark", "Watermark text", "Confidential", limit=180)
            self.add_spin("opacity", "Opacity", 5, 100, 28, "%")
        if op == "number":
            self.add_spin("number_start", "First page number", 0, 99999, 1)
        if op == "resize":
            self.add_spin("width", "Maximum width", 1, 20000, 1920, " px")
            self.add_spin("height", "Maximum height", 1, 20000, 1080, " px")
            self.settings.addWidget(label("Images keep their proportions. Smaller images keep their current size.", "hint", wrap=True))
        if any(extension(path) == "pdf" for path in self.paths):
            self.add_text("password", "Current PDF password" if op == "unlock" else "Current PDF password (optional)",
                          "Only for password-protected PDFs", secret=True)
        if op == "protect":
            self.add_text("new_password", "New password", "Enter a password", secret=True)
            self.add_text("confirm_password", "Confirm password", "Enter it again", secret=True)
        if op == "merge":
            self.merge_hint = label("Add at least two files to merge.", "hint", wrap=True)
            self.settings.addWidget(self.merge_hint)
        self.settings.addStretch()
        self.update_run()

    def add_field(self, key, text, control):
        row = QWidget()
        box = layout(row, spacing=3)
        field_label = label(text, "fieldLabel")
        field_label.setBuddy(control)
        control.setAccessibleName(text)
        box.addWidget(field_label)
        box.addWidget(control)
        self.settings.addWidget(row)
        self.fields[key] = control
        return row

    def add_text(self, key, text, placeholder, *, secret=False, limit=None):
        control = QLineEdit()
        control.setPlaceholderText(placeholder)
        if secret:
            control.setEchoMode(QLineEdit.EchoMode.Password)
        if limit:
            control.setMaxLength(limit)
        return self.add_field(key, text, control)

    def add_spin(self, key, text, minimum, maximum, value, unit=""):
        control = QSpinBox()
        control.setRange(minimum, maximum)
        control.setValue(value)
        control.setSuffix(unit)
        return self.add_field(key, text, control)

    def add_combo(self, key, text, choices):
        control = QComboBox()
        for title, value in choices:
            control.addItem(title, value)
        self.add_field(key, text, control)
        return control

    def choose_output(self):
        start = self.destination or (self.paths[0].parent if self.paths else Path.home())
        path = QFileDialog.getExistingDirectory(self, "Choose output folder", str(start))
        if path:
            self.destination = Path(path)
            self.output_folder.setText(str(self.destination))
            self.output_folder.setToolTip(str(self.destination))
            self.clear_output_button.show()

    def reset_output(self):
        self.destination = None
        self.update_output_label()
        self.output_folder.setToolTip("")
        self.clear_output_button.hide()

    def update_run(self):
        if self.merge_hint is not None:
            self.merge_hint.setVisible(len(self.paths) < 2)
        self.update_output_label()
        self.run_button.setEnabled(bool(self.operation) and not self.job and
                                   (self.operation.id != "merge" or len(self.paths) >= 2))
        if not self.operation:
            title = "Choose files to begin" if not self.paths else "Choose a compatible file group"
        elif self.job:
            title = "Working…"
        elif self.operation.category == "Convert":
            title = "Convert"
        else:
            title = self.operation.label
        self.run_button.setText(title)

    def update_output_label(self):
        if not self.destination:
            grouped = self.operation and self.operation.id in {"merge", "image-pdf"} and len(self.paths) > 1
            self.output_folder.setText("Folder of the first file" if grouped else "Same folder as the original")

    def set_status(self, text):
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def start_conversion(self):
        if not self.operation or self.job:
            return
        options = {}
        for key, field in self.fields.items():
            if isinstance(field, QComboBox):
                options[key] = field.currentData()
            elif isinstance(field, QSpinBox):
                options[key] = field.value()
            else:
                options[key] = field.text()
        try:
            validate_settings(self.operation.id, options)
        except ValueError as error:
            self.set_status(str(error))
            return
        self.result_panel.hide()
        self.job = ConversionJob(self.operation.id, list(self.paths), options, self.destination, self)
        self.job.progress.connect(self.report_progress)
        self.job.completed.connect(self.show_completion)
        self.job.finished.connect(self.finish_job)
        self.set_busy(True)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.set_status("Preparing files…")
        self.job.start()

    def set_busy(self, busy):
        for control in (self.add_files_button, self.queue, self.drop, self.tool_area, self.settings.parentWidget(),
                        self.choose_output_button, self.clear_output_button):
            control.setEnabled(not busy)
        self.update_queue_buttons()
        self.update_run()

    def report_progress(self, done, count, name):
        if count > 1:
            self.progress.setRange(0, count)
            self.progress.setValue(done)
        if name:
            self.set_status(f"Working on {name}…")

    def show_completion(self, outcome):
        self.outcome = outcome
        self.set_status("")
        self.progress.hide()
        count = len(outcome.outputs)
        summary = f"Saved {count} {'file' if count == 1 else 'files'}" if count else "Could not complete the operation"
        if count and outcome.errors:
            summary += f" · {len(outcome.errors)} failed"
        self.result_label.setObjectName("warning" if outcome.errors else "success")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        self.result_label.setText(summary)
        self.results_button.setText("View details" if outcome.errors or outcome.notes else "Show files")
        self.result_panel.show()

    def finish_job(self):
        self.job.deleteLater()
        self.job = None
        self.set_busy(False)

    def show_results(self):
        if not self.outcome:
            return
        result = self.outcome
        if len(result.outputs) == 1 and not (result.notes or result.errors):
            reveal_in_explorer(result.outputs[0])
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Conversion results")
        dialog.resize(570, 365)
        body = layout(dialog, (19, 18, 19, 18), 11)
        body.addWidget(label(self.result_label.text(), "subheading", wrap=True))
        if result.outputs:
            files = QListWidget()
            for path in result.outputs:
                item = QListWidgetItem(icon("file"), path.name)
                item.setToolTip(str(path))
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                files.addItem(item)
            files.setCurrentRow(0)
            files.itemDoubleClicked.connect(lambda item: QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole))))
            body.addWidget(files, 1)
            body.addWidget(button("Show in File Explorer", lambda: reveal_in_explorer(Path(files.currentItem().data(Qt.ItemDataRole.UserRole))),
                                  symbol="folder"), alignment=Qt.AlignmentFlag.AlignLeft)
        if result.errors or result.notes:
            details = QPlainTextEdit("\n\n".join(result.errors + result.notes))
            details.setReadOnly(True)
            body.addWidget(details, 1)
        body.addWidget(button("Close", dialog.accept), alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def set_drag_active(self, active):
        self.drop.setProperty("active", active)
        self.drop.style().unpolish(self.drop)
        self.drop.style().polish(self.drop)

    def dragEnterEvent(self, event):
        if not self.job and any(url.isLocalFile() for url in event.mimeData().urls()):
            self.set_drag_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.set_drag_active(False)
        event.accept()

    def dropEvent(self, event):
        self.set_drag_active(False)
        if not self.job:
            self.add_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.job:
            event.ignore()
            self.set_status("A conversion is running. This window can close when it finishes.")
            return
        super().closeEvent(event)


def reveal_in_explorer(path):
    explorer = Path(os.environ.get("SystemRoot", "C:/Windows")) / "explorer.exe"
    subprocess.Popen(f'"{explorer}" /select,"{path}"')
