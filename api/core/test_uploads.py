"""Uploads are judged by their contents and size, and stored under names that say nothing about anyone."""

import io
import re
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers

from core.uploads import DOCUMENT, EVIDENCE, sniff, stored_name, validate_upload

PDF = b"%PDF-1.7\n%demo"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"


def office(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        for name in ("[Content_Types].xml", *names):
            package.writestr(name, "<x/>")
    return buffer.getvalue()


def upload(name: str, content: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content)


@pytest.mark.parametrize(
    ("name", "content", "kind"),
    [
        ("scan.pdf", PDF, "pdf"),
        ("photo.jpg", JPEG, "jpeg"),
        ("photo.JPEG", JPEG, "jpeg"),
        ("photo.png", PNG, "png"),
        ("photo.webp", WEBP, "webp"),
        ("photo.heic", HEIC, "heic"),
        ("letter.docx", office("word/document.xml"), "docx"),
        ("sheet.xlsx", office("xl/workbook.xml"), "xlsx"),
    ],
)
def test_accepted_kinds(name, content, kind):
    file = upload(name, content)
    assert sniff(file) == kind
    assert validate_upload(file, DOCUMENT) is file
    assert file.read(4) == content[:4]  # the checks leave the file ready to be stored from the start


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("note.pdf", b"<html><script>alert(1)</script></html>", "do not match its name"),
        ("note.jpg", PDF, "do not match its name"),
        ("note.svg", b"<svg onload='alert(1)'/>", "Send a PDF"),
        ("setup.exe", b"MZ\x90\x00", "Send a PDF"),
        ("page.html", b"<html></html>", "Send a PDF"),
        ("macro.docx", office("word/document.xml", "word/vbaProject.bin"), "do not match its name"),
        ("broken.docx", b"PK\x03\x04 not really a zip", "do not match its name"),
        ("noext", PDF, "Send a PDF"),
    ],
)
def test_refused_files_say_what_to_send(name, content, message):
    with pytest.raises(serializers.ValidationError) as refused:
        validate_upload(upload(name, content), DOCUMENT)
    assert message in str(refused.value.detail[0])


def test_evidence_takes_photographs_and_pdfs_only():
    with pytest.raises(serializers.ValidationError) as refused:
        validate_upload(upload("note.docx", office("word/document.xml")), EVIDENCE)
    assert "a photograph (JPG, PNG, HEIC) or a PDF" in str(refused.value.detail[0])
    assert validate_upload(upload("note.jpg", JPEG), EVIDENCE)


def test_size_limits_come_from_settings(settings):
    settings.UPLOAD_LIMIT_DOCUMENT_MB = 1
    big = upload("scan.pdf", PDF + b"0" * (1024 * 1024))
    with pytest.raises(serializers.ValidationError) as refused:
        validate_upload(big, DOCUMENT)
    assert str(refused.value.detail[0]) == "The file is larger than 1 MB."


def test_stored_names_are_random_and_keep_only_the_extension():
    first = stored_name(None, "Asha Persaud medical note.PDF")
    second = stored_name(None, "Asha Persaud medical note.PDF")
    assert first != second
    assert re.fullmatch(r"employees/\d{4}/\d{2}/[0-9a-f]{32}\.pdf", first)
    assert "Asha" not in first
