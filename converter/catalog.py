from dataclasses import dataclass
from pathlib import Path


IMAGE_OUTPUTS = {
    "png": "PNG", "jpg": "JPG", "webp": "WebP", "avif": "AVIF",
    "tiff": "TIFF", "bmp": "BMP", "gif": "GIF", "ico": "ICO",
    "heic": "HEIC",
}
IMAGE_INPUTS = set(IMAGE_OUTPUTS) | {"jpeg", "tif", "heif", "jpe", "jfif"}
OFFICE = {
    "Word": {"doc", "docx", "rtf", "odt"},
    "Excel": {"xls", "xlsx", "ods", "csv"},
    "PowerPoint": {"ppt", "pptx", "odp"},
}
OFFICE_INPUTS = set().union(*OFFICE.values())
SUPPORTED = IMAGE_INPUTS | OFFICE_INPUTS | {"pdf", "txt", "md"}


@dataclass(frozen=True)
class Operation:
    id: str
    label: str
    description: str
    category: str
    icon: str


OPERATIONS = {
    operation.id: operation for operation in (
        Operation("word", "Word document", "Convert PDF or text to an editable DOCX document.", "Convert", "text"),
        Operation("text", "Plain text", "Extract readable text into a UTF-8 TXT file.", "Convert", "text"),
        Operation("image-pdf", "PDF document", "Make a PDF from images, one image per page.", "Convert", "file"),
        Operation("office-pdf", "PDF document", "Export with a locally installed Office app or LibreOffice.", "Convert", "file"),
        Operation("text-pdf", "PDF document", "Save your text as a printable PDF.", "Convert", "file"),
        Operation("merge", "Merge to PDF", "Combine files in the order shown.", "Pages", "merge"),
        Operation("split", "Split PDF", "Create separate files by page, interval or custom ranges.", "Pages", "split"),
        Operation("extract", "Extract pages", "Save the selected pages in a new PDF.", "Pages", "file"),
        Operation("reorder", "Reorder pages", "Enter all page numbers in the order you want.", "Pages", "merge"),
        Operation("delete", "Delete pages", "Create a copy with the selected pages removed.", "Pages", "trash"),
        Operation("rotate", "Rotate pages", "Turn all pages or a range by 90, 180 or 270 degrees.", "Pages", "rotate"),
        Operation("compress", "Compress PDF", "Optimize the PDF or reduce the resolution of its images.", "Edit PDF", "compress"),
        Operation("ocr", "Make searchable", "Recognize English text on scanned pages.", "Edit PDF", "text"),
        Operation("watermark", "Watermark", "Place custom text in the center of each selected page.", "Edit PDF", "edit"),
        Operation("number", "Add page numbers", "Add a page number in the bottom margin.", "Edit PDF", "text"),
        Operation("flatten", "Flatten PDF", "Make form fields and annotations part of the page.", "Edit PDF", "layers"),
        Operation("protect", "Protect PDF", "Require a password to open a new AES-256 encrypted copy.", "Edit PDF", "lock"),
        Operation("unlock", "Unlock PDF", "Save a copy without the current password.", "Edit PDF", "unlock"),
        Operation("resize", "Resize images", "Scale images to fit within a width and height.", "Edit image", "resize"),
    )
}
for extension, label in IMAGE_OUTPUTS.items():
    for prefix, description in (
        ("image", f"Save each image as {label}."),
        ("pdf", f"Render each PDF page as a {label} image."),
    ):
        operation_id = f"{prefix}-{extension}"
        OPERATIONS[operation_id] = Operation(operation_id, label, description, "Convert", "image")


def extension(path: Path) -> str:
    return path.suffix.removeprefix(".").lower()


def available(paths: list[Path]) -> list[Operation]:
    suffixes = {extension(path) for path in paths}
    if not suffixes:
        return []

    choices = []
    if suffixes == {"pdf"}:
        choices = ["word", "text", *[f"pdf-{ext}" for ext in ("png", "jpg", "webp", "tiff")]]
        choices += ["merge", "split", "extract", "reorder", "delete", "rotate", "compress", "ocr",
                    "watermark", "number", "flatten", "protect", "unlock"]
    elif suffixes <= IMAGE_INPUTS:
        choices = [*[f"image-{ext}" for ext in IMAGE_OUTPUTS], "image-pdf", "resize"]
        if len(paths) > 1:
            choices.append("merge")
    elif suffixes <= (IMAGE_INPUTS | {"pdf"}):
        choices = ["merge"]
    elif suffixes <= {"txt", "md"}:
        choices = ["word", "text-pdf"]
    elif suffixes <= OFFICE_INPUTS:
        choices = ["office-pdf"]
        if suffixes == {"docx"}:
            choices.append("text")
    return [OPERATIONS[choice] for choice in choices]
