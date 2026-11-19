"""Info heredado de un tráiler anterior (actualización incremental sin /Info)."""

from __future__ import annotations

from pathlib import Path

import pikepdf
import pytest

from tdmseal.pdf.docinfo import effective_docinfo, find_inherited_info


@pytest.fixture
def incremental_pdf(make_incremental_pdf) -> Path:
    return make_incremental_pdf(
        "incremental.pdf", title="Los días biches", subject="Prueba para el autor"
    )


def test_pikepdf_alone_does_not_see_inherited_info(incremental_pdf):
    with pikepdf.open(incremental_pdf) as pdf:
        assert "/Info" not in pdf.trailer


def test_find_inherited_info(incremental_pdf):
    with pikepdf.open(incremental_pdf) as pdf:
        info = find_inherited_info(pdf, incremental_pdf)
        assert str(info["/Title"]) == "Los días biches"


def test_effective_docinfo_includes_inherited(incremental_pdf):
    info = effective_docinfo(incremental_pdf)
    assert info["/Title"] == "Los días biches"
    assert info["/Subject"] == "Prueba para el autor"


def test_normal_pdf_has_no_inherited_info(make_pdf):
    path = make_pdf()
    with pikepdf.open(path) as pdf:
        assert find_inherited_info(pdf, path) is None
