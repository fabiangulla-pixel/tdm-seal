from __future__ import annotations

from tdmseal.iscc import compute_iscc


def test_compute_iscc_is_deterministic_for_same_content(make_pdf):
    path = make_pdf("book.pdf", page_count=2)

    first = compute_iscc(path)
    second = compute_iscc(path)

    assert first.iscc == second.iscc
    assert first.iscc.startswith("ISCC:")


def test_compute_iscc_is_independent_of_filename_and_location(make_pdf, tmp_path):
    original = make_pdf("original_name.pdf", page_count=2)
    renamed = tmp_path / "subdir"
    renamed.mkdir()
    renamed_path = renamed / "otro_nombre_distinto.pdf"
    renamed_path.write_bytes(original.read_bytes())

    assert compute_iscc(original).iscc == compute_iscc(renamed_path).iscc


def test_compute_iscc_changes_with_content(make_pdf):
    small = make_pdf("small.pdf", page_count=1)
    large = make_pdf("large.pdf", page_count=5)

    assert compute_iscc(small).iscc != compute_iscc(large).iscc


def test_compute_iscc_combines_data_and_instance_units(make_pdf):
    path = make_pdf("book.pdf")

    result = compute_iscc(path)

    assert result.data_code.startswith("ISCC:")
    assert result.instance_code.startswith("ISCC:")
    assert result.datahash
    assert result.filesize == path.stat().st_size
