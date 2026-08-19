from __future__ import annotations

from pathlib import Path

from tdmseal.models import PublisherInfo, SealResult
from tdmseal.reporting.json_report import build_report


def _minimal_result() -> SealResult:
    return SealResult(
        input_path=Path("libro.pdf"),
        output_path=Path("libro_TDM.pdf"),
        status="success",
        operation="create",
    )


def test_build_report_without_publisher_omits_section():
    report = build_report(_minimal_result())

    assert report["publisher"] is None


def test_build_report_with_publisher_includes_fields():
    publisher = PublisherInfo(
        name="Editorial Universidad Ejemplo",
        acronym="EUE",
        website="https://editorial.example.edu",
        rights_email="derechos@editorial.example.edu",
    )

    report = build_report(_minimal_result(), publisher)

    assert report["publisher"] == {
        "name": "Editorial Universidad Ejemplo",
        "acronym": "EUE",
        "website": "https://editorial.example.edu",
        "rights_email": "derechos@editorial.example.edu",
    }


def test_build_report_with_empty_publisher_omits_section():
    report = build_report(_minimal_result(), PublisherInfo())

    assert report["publisher"] is None
