from contextlib import contextmanager
from dataclasses import dataclass, field
from html import escape
from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
from typing import Callable

from .catalog import IMAGE_INPUTS, IMAGE_OUTPUTS, available, extension


TESSDATA = Path(__file__).resolve().parents[1] / "tessdata"
PIL_FORMATS = {"jpg": "JPEG", "tiff": "TIFF", "heic": "HEIF", **{
    ext: ext.upper() for ext in IMAGE_OUTPUTS if ext not in {"jpg", "tiff", "heic"}
}}


@dataclass
class Result:
    outputs: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def page_selection(value: str, count: int, *, allow_empty: bool = False) -> list[int]:
    value = value.strip()
    if not value:
        if allow_empty:
            return list(range(count))
        raise ValueError("Enter page numbers or ranges, such as 1, 3–5.")
    pages = []
    for piece in value.split(","):
        match = re.fullmatch(r"\s*([0-9]+)\s*(?:[-–]\s*([0-9]+)\s*)?", piece)
        if not match:
            raise ValueError(f"Invalid page selection: {piece.strip()!r}.")
        first, last = int(match[1]), int(match[2] or match[1])
        if not (1 <= first <= count and 1 <= last <= count):
            raise ValueError(f"Page numbers must be between 1 and {count}.")
        step = 1 if first <= last else -1
        pages.extend(number - 1 for number in range(first, last + step, step))
    if len(pages) != len(set(pages)):
        raise ValueError("Enter each page number only once per output.")
    return pages


def validate_settings(operation: str, options: dict) -> None:
    if operation in {"extract", "delete", "reorder"} and not options.get("pages", "").strip():
        raise ValueError("Enter the page numbers or ranges first.")
    if operation == "split" and options.get("split_mode") == "ranges" and not options.get("ranges", "").strip():
        raise ValueError("Enter page ranges, separated by semicolons.")
    if operation == "watermark" and not options.get("watermark", "").strip():
        raise ValueError("Enter the text you want to use as a watermark.")
    if operation == "protect":
        password = options.get("new_password", "")
        if not password.strip() or len(password.encode("utf-8")) > 40:
            raise ValueError("Enter a nonblank password of at most 40 UTF-8 bytes.")
        if password != options.get("confirm_password", ""):
            raise ValueError("The new passwords do not match.")


def execute(
    operation: str,
    paths: list[Path],
    options: dict,
    output_dir: Path | None = None,
    progress: Callable[[int, int, str], None] = lambda *_: None,
) -> Result:
    paths = [Path(path).resolve() for path in paths]
    if operation not in {choice.id for choice in available(paths)}:
        raise ValueError("This tool is unavailable for the selected files.")
    validate_settings(operation, options)

    if operation == "merge" and len(paths) < 2:
        raise ValueError("Add at least two PDFs or images to merge.")
    grouped = operation in {"merge", "image-pdf"}
    jobs = [paths] if grouped else [[path] for path in paths]
    result = Result()
    for index, sources in enumerate(jobs):
        source = sources[0]
        label = source.name if not grouped or len(sources) == 1 else f"{len(sources)} files"
        progress(index, len(jobs), label)
        destination = Path(output_dir).resolve() if output_dir else source.parent
        try:
            with TemporaryDirectory(prefix=".file-converter-", dir=destination) as temp:
                staging = Path(temp)
                if grouped:
                    combine(operation, sources, staging, options)
                else:
                    convert_one(operation, source, staging, options, result.notes)
                staged = sorted(staging.iterdir())
                if not staged:
                    raise ValueError("The tool did not produce an output file.")
                for output in staged:
                    result.outputs.append(publish(output, destination))
        except Exception as error:
            message = str(error).strip() or type(error).__name__
            result.errors.append(f"{label}: {message}")
    progress(len(jobs), len(jobs), "")
    return result


def publish(output: Path, destination: Path) -> Path:
    for number in range(1, 10001):
        suffix = f" ({number})" if number > 1 else ""
        stem = output.stem
        while len(f"{stem}{suffix}{output.suffix}".encode("utf-16-le")) > 500:
            stem = stem[:-1]
        target = destination / f"{stem}{suffix}{output.suffix}"
        try:
            os.rename(output, target)
            return target
        except FileExistsError:
            continue
    raise ValueError("Too many output files already have this name.")


def named(directory: Path, source: Path, suffix: str, ext: str) -> Path:
    stem = source.stem
    while len(f"{stem}{suffix}.{ext}".encode("utf-16-le")) > 480:
        stem = stem[:-1]
    return directory / f"{stem}{suffix}.{ext}"


@contextmanager
def open_pdf(path: Path, password: str):
    import pymupdf as pdf

    with pdf.open(path) as document:
        # Checking needs_pass probes an empty password, so do it before authenticating.
        protected = bool(document.needs_pass)
        if protected and (not password or not document.authenticate(password)):
            raise ValueError("Enter the correct PDF password in Tool settings.")
        if not document.is_pdf or not document.page_count:
            raise ValueError("This is an empty or invalid PDF.")
        yield document, protected


def save_pdf(document, target, **settings):
    import pymupdf as pdf

    options = dict(garbage=3, deflate=True, encryption=pdf.PDF_ENCRYPT_KEEP)
    options.update(settings)
    encrypted = options["encryption"] != pdf.PDF_ENCRYPT_NONE and (
        options["encryption"] != pdf.PDF_ENCRYPT_KEEP or (document.metadata or {}).get("encryption")
    )
    options["use_objstms"] = 0 if encrypted else 1
    document.save(target, **options)


def combine(operation: str, paths: list[Path], output: Path, options: dict):
    import pymupdf as pdf

    name = paths[0].stem[:100] if operation == "image-pdf" and len(paths) == 1 else (
        "Merged files" if operation == "merge" else "Images")
    password = options.get("password", "")
    protected = False
    bookmarks = []
    with pdf.open() as document:
        for path in paths:
            if extension(path) in IMAGE_INPUTS:
                add_image_pages(document, path)
            else:
                with open_pdf(path, password) as (source, source_protected):
                    protected = protected or source_protected
                    offset = document.page_count
                    document.insert_pdf(source)
                    for level, title, page in source.get_toc():
                        bookmarks.append([level, title, page + offset if page > 0 else -1])
        if bookmarks:
            document.set_toc(bookmarks)
        protection = {"encryption": pdf.PDF_ENCRYPT_AES_256, "user_pw": password} if protected else {}
        save_pdf(document, output / f"{name}.pdf", **protection)


def convert_one(operation: str, source: Path, output: Path, options: dict, notes: list[str]):
    ext = extension(source)
    if ext == "pdf":
        with open_pdf(source, options.get("password", "")) as (document, protected):
            convert_pdf(operation, source, document, protected, output, options, notes)
    elif ext in IMAGE_INPUTS:
        target_ext = ext if operation == "resize" else operation.removeprefix("image-")
        target_ext = {"jpeg": "jpg", "jpe": "jpg", "jfif": "jpg", "tif": "tiff", "heif": "heic"}.get(target_ext, target_ext)
        suffix = " - resized" if operation == "resize" else ""
        convert_image(source, named(output, source, suffix, target_ext), target_ext, options, operation == "resize", notes)
    elif operation == "office-pdf":
        from .office import export_pdf

        export_pdf(source, named(output, source, "", "pdf"))
    elif operation == "text":
        from docx import Document
        from docx.table import Table

        blocks = []
        for item in Document(source).iter_inner_content():
            if isinstance(item, Table):
                blocks.extend("\t".join(cell.text for cell in row.cells) for row in item.rows)
            else:
                blocks.append(item.text)
        named(output, source, "", "txt").write_text("\n".join(blocks), encoding="utf-8")
    else:
        content = source.read_bytes()
        try:
            text = content.decode("utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("cp1252", errors="replace")
        if operation == "word":
            text_to_word([text], named(output, source, "", "docx"))
        else:
            text_to_pdf(text, named(output, source, "", "pdf"))


@lru_cache(maxsize=1)
def enable_image_codecs():
    import pillow_heif

    pillow_heif.register_heif_opener()


def flatten_color(image):
    from PIL import Image

    rgba = image.convert("RGBA")
    background = Image.new("RGB", image.size, "white")
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def add_image_pages(document, source):
    from PIL import Image, ImageOps, ImageSequence

    enable_image_codecs()
    with Image.open(source) as image:
        for frame in ImageSequence.Iterator(image):
            frame = ImageOps.exif_transpose(frame)
            dpi = frame.info.get("dpi", (150, 150))
            dpi_x, dpi_y = (max(36, min(1200, float(value or 150))) for value in dpi[:2])
            width, height = frame.width * 72 / dpi_x, frame.height * 72 / dpi_y
            scale = min(1, 14000 / max(width, height))
            page = document.new_page(width=width * scale, height=height * scale)
            payload = BytesIO()
            flatten_color(frame).save(payload, format="PNG")
            page.insert_image(page.rect, stream=payload.getvalue())


def convert_image(source, target, ext, options, resize, notes):
    from PIL import Image, ImageOps, ImageSequence

    enable_image_codecs()
    with Image.open(source) as image:
        multi_frame = ext in {"png", "webp", "avif", "tiff", "gif", "heic"}
        if getattr(image, "n_frames", 1) > 1 and not multi_frame:
            notes.append(f"{source.name}: {IMAGE_OUTPUTS[ext]} stores only the first frame.")
        frames = []
        durations = []
        for frame in ImageSequence.Iterator(image):
            normalized = ImageOps.exif_transpose(frame)
            if resize:
                normalized.thumbnail((options.get("width", 1920), options.get("height", 1080)), Image.Resampling.LANCZOS)
            if ext in {"jpg", "bmp"}:
                normalized = flatten_color(normalized)
            elif ext in {"webp", "avif", "gif", "ico", "heic"} or normalized.mode in {"CMYK", "YCbCr", "LAB", "HSV"}:
                normalized = normalized.convert("RGBA" if "A" in normalized.getbands() or "transparency" in normalized.info else "RGB")
            frames.append(normalized)
            durations.append(max(1, round(frame.info.get("duration", 100) or 100)))
            if not multi_frame:
                break
        settings = image_settings(ext, options)
        if len(frames) > 1:
            settings.update(save_all=True, append_images=frames[1:])
            if ext in {"png", "webp", "avif", "gif"}:
                settings.update(duration=durations, loop=image.info.get("loop", 0))
        if ext == "ico":
            thumbnail = frames[0].copy()
            thumbnail.thumbnail((256, 256), Image.Resampling.LANCZOS)
            icon = Image.new("RGBA", (256, 256))
            icon.paste(thumbnail, ((256 - thumbnail.width) // 2, (256 - thumbnail.height) // 2))
            frames[0] = icon
            settings["sizes"] = [(size, size) for size in (16, 24, 32, 48, 64, 128, 256)]
        frames[0].save(target, format=PIL_FORMATS[ext], **settings)


def image_settings(ext, options):
    if ext in {"jpg", "webp", "avif", "heic"}:
        return {"quality": options.get("quality", 90)}
    if ext == "tiff":
        return {"compression": "tiff_deflate"}
    return {}


def scan_text(page):
    text = page.get_text(sort=True).strip()
    if text or not TESSDATA.joinpath("eng.traineddata").is_file():
        return text
    return page.get_text(textpage=ocr_page(page), sort=True).strip()


def ocr_page(page):
    dpi = min(240, max(72, int(72 * (16_000_000 / page.rect.get_area()) ** 0.5)))
    return page.get_textpage_ocr(full=True, dpi=dpi, language="eng", tessdata=str(TESSDATA))


def text_to_word(pages, target):
    from docx import Document

    document = Document()
    for index, text in enumerate(pages):
        if index:
            document.add_page_break()
        for line in text.splitlines():
            clean = re.sub(r"[^\x09\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]", "", line)
            document.add_paragraph(clean)
    document.save(target)


def text_to_pdf(content, target):
    import pymupdf as pdf

    body = "<body>" + "".join(f"<p>{escape(line) if line else '&nbsp;'}</p>" for line in content.expandtabs(4).split("\n")) + "</body>"
    story = pdf.Story(html=body, user_css="p { font-family: sans-serif; font-size: 11pt; margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }")
    media = pdf.paper_rect("a4")
    story.write_with_links(lambda *_: (media, media + (45, 45, -45, -45), None)).save(target)


def convert_pdf(operation, source, document, protected, output, options, notes):
    import pymupdf as pdf

    if operation in {"word", "text"}:
        export_pdf_text(operation, source, document, output, options, notes)
        return
    if operation.startswith("pdf-"):
        from PIL import Image

        ext = operation.removeprefix("pdf-")
        dpi = options.get("dpi", 150)
        padding = max(2, len(str(document.page_count)))
        pages = page_selection(options.get("pages", ""), document.page_count, allow_empty=True)
        for index in pages:
            page = document[index]
            if page.rect.get_area() * (dpi / 72) ** 2 > 50_000_000:
                raise ValueError("The rendered image would be too large. Choose a lower resolution.")
            pix = page.get_pixmap(dpi=dpi, colorspace=pdf.csRGB, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            suffix = f" - page {index + 1:0{padding}}" if document.page_count > 1 else ""
            image.save(named(output, source, suffix, ext), format=PIL_FORMATS[ext], dpi=(dpi, dpi), **image_settings(ext, options))
        return

    settings = {}
    if operation == "split":
        split_pdf(source, document, protected, output, options)
        return
    if operation in {"extract", "reorder", "delete"}:
        pages = page_selection(options.get("pages", ""), document.page_count)
        if operation == "reorder" and len(pages) != document.page_count:
            raise ValueError("To reorder pages, include every page exactly once.")
        if operation == "delete":
            removed = set(pages)
            pages = [index for index in range(document.page_count) if index not in removed]
            if not pages:
                raise ValueError("A PDF must contain at least one page.")
        document.select(pages)
    elif operation == "rotate":
        for index in page_selection(options.get("pages", ""), document.page_count, allow_empty=True):
            page = document[index]
            page.set_rotation((page.rotation + options.get("rotation", 90)) % 360)
    elif operation == "compress":
        profile = options.get("compression", "lossless")
        if profile != "lossless":
            dpi, quality = (150, 78) if profile == "balanced" else (96, 55)
            document.rewrite_images(dpi_threshold=dpi + 25, dpi_target=dpi, quality=quality)
        settings["garbage"] = 4
    elif operation in {"number", "watermark"}:
        stamp(document, operation, options)
    elif operation == "flatten":
        document.bake(annots=True, widgets=True)
    elif operation == "ocr":
        if not TESSDATA.joinpath("eng.traineddata").is_file():
            raise ValueError("English OCR data is missing. Run Install.ps1 to restore it.")
        recognized = add_searchable_text(document)
        if not recognized:
            notes.append(f"{source.name}: No additional text was recognized.")
    elif operation == "protect":
        settings.update(encryption=pdf.PDF_ENCRYPT_AES_256, user_pw=options["new_password"])
    elif operation == "unlock":
        if not protected and not document.metadata.get("encryption"):
            raise ValueError("This PDF does not have password protection.")
        settings["encryption"] = pdf.PDF_ENCRYPT_NONE

    suffix = {"extract": "extracted", "reorder": "reordered", "delete": "pages removed", "rotate": "rotated",
              "compress": "compressed", "number": "numbered", "watermark": "watermarked", "flatten": "flattened",
              "ocr": "searchable", "protect": "protected", "unlock": "unlocked"}[operation]
    target = named(output, source, f" - {suffix}", "pdf")
    save_pdf(document, target, **settings)
    if operation == "compress":
        original_size = source.stat().st_size
        saved_size = target.stat().st_size
        if saved_size >= original_size:
            shutil.copyfile(source, target)
            notes.append(f"{source.name}: No size reduction was possible with these settings. Saved an identical copy.")
        else:
            notes.append(f"{source.name}: Reduced file size by {(original_size - saved_size) / original_size:.1%}.")


def split_pdf(source, document, protected, output, options):
    import pymupdf as pdf

    count = document.page_count
    mode = options.get("split_mode", "pages")
    if mode == "ranges":
        groups = [page_selection(group, count) for group in options.get("ranges", "").split(";")]
    else:
        interval = 1 if mode == "pages" else max(1, options.get("interval", 2))
        groups = [list(range(index, min(index + interval, count))) for index in range(0, count, interval)]
    padding = max(2, len(str(len(groups))))
    serialized = document.tobytes(encryption=pdf.PDF_ENCRYPT_KEEP)
    for index, group in enumerate(groups, 1):
        with pdf.open("pdf", serialized) as part:
            if protected and not part.authenticate(options["password"]):
                raise ValueError("Could not preserve password protection for the split output.")
            part.select(group)
            save_pdf(part, named(output, source, f" - part {index:0{padding}}", "pdf"))


def stamp(document, operation, options):
    import pymupdf as pdf

    pages = page_selection(options.get("pages", ""), document.page_count, allow_empty=True)
    for index in pages:
        page = document[index]
        bounds = page.rect
        if operation == "number":
            text = str(index + options.get("number_start", 1))
            box = pdf.Rect(0, bounds.height * 0.93, bounds.width, bounds.height)
            css = "font-size: 10pt; color: #263244;"
            opacity = 1
        else:
            text = options["watermark"].strip()
            box = pdf.Rect(bounds.width * 0.05, bounds.height * 0.45, bounds.width * 0.95, bounds.height * 0.6)
            css = "font-size: 42pt; font-weight: bold; color: #475569;"
            opacity = options.get("opacity", 28) / 100
        page.insert_htmlbox(box * page.derotation_matrix,
                            f"<p style='margin:0; text-align:center; {css}'>{escape(text)}</p>",
                            rotate=page.rotation, opacity=opacity)


def add_searchable_text(document):
    import pymupdf as pdf

    total = 0
    for page in document:
        if page.get_text().strip():
            continue
        text_page = ocr_page(page)
        words = page.get_text("words", textpage=text_page)
        shape = page.new_shape()
        for x0, y0, x1, y1, word, *_ in words:
            point = pdf.Point(x0, y1 - (y1 - y0) * 0.2)
            size = max(1, (y1 - y0) * 0.8)
            width = pdf.get_text_length(word, fontsize=size)
            transform = pdf.Matrix((x1 - x0) / width, 1) if width and x1 > x0 else pdf.Matrix(1, 1)
            shape.insert_text(point, word, fontsize=size, render_mode=3, morph=(point, transform))
        if words:
            shape.commit()
            total += len(words)
    return total


def export_pdf_text(operation, source, document, output, options, notes):
    pages = [page.get_text(sort=True).strip() for page in document]
    scanned = [index for index, text in enumerate(pages) if not text and document[index].get_image_info()]
    if operation == "word" and not scanned:
        from pdf2docx import Converter

        target = named(output, source, "", "docx")
        try:
            converter = Converter(str(source), password=options.get("password", ""))
            try:
                converter.convert(str(target), multi_processing=False)
            finally:
                converter.close()
            if target.is_file() and target.stat().st_size > 0:
                return
        except Exception:
            target.unlink(missing_ok=True)
        notes.append(f"{source.name}: Saved editable text because the original layout could not be reconstructed.")
    for index in scanned:
        pages[index] = scan_text(document[index])
    if scanned and operation == "word":
        notes.append(f"{source.name}: Scanned pages were converted using English OCR. The DOCX uses a plain-text layout.")
    if scanned and not any(pages[index] for index in scanned):
        notes.append(f"{source.name}: No text was recognized on the scanned pages.")
    if operation == "word":
        text_to_word(pages, named(output, source, "", "docx"))
    else:
        named(output, source, "", "txt").write_text("\n\n".join(pages), encoding="utf-8")
