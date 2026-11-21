"""Composición de la página de aviso: debe caber en formatos de libro reales."""

from __future__ import annotations

import pytest

from tdmseal.notice import NoticeOptions, _wrap_url, layout_pdf_notice

LONG = NoticeOptions(
    "Editorial Universidad Distrital Francisco José de Caldas",
    "derechos.editorial@universidad.edu.co",
    "https://editorial.universidad.edu.co/tdm/politica-de-licencias-mineria",
)


@pytest.mark.parametrize(
    "size",
    [(595, 842), (420, 595), (312, 504), (432, 648)],
    ids=["A4", "A5", "bolsillo", "6x9in"],
)
def test_notice_fits_book_formats_with_both_languages(size):
    width, height = size
    margin, font_size, leading, lines, dropped = layout_pdf_notice(LONG, width, height)

    assert not dropped
    assert font_size >= 7.0
    assert len(lines) * leading <= height - 2 * margin
    assert any("Rights reservation" in text for text, _ in lines)


def test_tiny_page_keeps_spanish_and_warns():
    import pikepdf

    from tdmseal.notice import add_pdf_notice_page

    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(200, 260))
    warnings = add_pdf_notice_page(pdf, LONG)

    assert any("solo en español" in w for w in warnings)
    assert layout_pdf_notice(LONG, 200, 260)[4]


def test_url_breaks_only_after_slashes():
    url = "https://editorial.universidad.edu.co/tdm/politica-de-licencias-mineria"
    lines = _wrap_url(url, 40)

    assert "".join(lines) == url
    assert all(len(ln) <= 40 for ln in lines)
    assert all(ln.endswith("/") for ln in lines[:-1])


def test_notice_mentions_machine_readable_reservation():
    (_, es), (_, en) = LONG.paragraphs()
    assert any("legible por máquina" in p for p in es)
    assert any("machine-readable" in p for p in en)
    assert "se reserva expresamente" in es[0]
