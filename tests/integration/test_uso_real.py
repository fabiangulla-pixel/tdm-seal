"""Escenarios de uso real que fallaban (19/20-nov-2026)."""

from __future__ import annotations

from click.testing import CliRunner

import tdmseal.cli as cli_module
from tdmseal.appconfig import AppDefaults
from tdmseal.discovery import is_sealed_output, iter_documents


def test_reseal_same_folder_twice(monkeypatch, tmp_path, make_text_pdf, make_epub):
    """Volver a sellar una carpeta (p. ej. tras añadir libros) no da errores ni crea _TDM_TDM."""
    monkeypatch.setattr(cli_module, "load_defaults", lambda *a, **k: AppDefaults())
    make_text_pdf("a.pdf")
    make_epub("b.epub")

    first = CliRunner().invoke(cli_module.main, ["seal", str(tmp_path)])
    make_text_pdf("nuevo.pdf")  # se añade un libro
    second = CliRunner().invoke(cli_module.main, ["seal", str(tmp_path)])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert "1 correctos, 2 omitidos, 0 con error" in second.output
    assert "Ya sellado" in second.output
    assert not list(tmp_path.glob("*_TDM_TDM.*"))
    assert (tmp_path / "nuevo_TDM.pdf").exists()


def test_selftest_passes(tmp_path):
    from tdmseal.selftest import run_selftest

    result = run_selftest(tmp_path)

    assert result["ok"], result["pasos"]
    assert [s["paso"] for s in result["pasos"]] == [
        "sellar PDF con ISCC",
        "sellar EPUB con ISCC",
        "esquema de extensión PDF/A",
        "PDF firmado sin invalidar la firma",
        "política ODRL",
        "señales del sitio",
        "manifiesto del catálogo",
        "registro público, copias y ONIX",
        "firma de declaración ISCC",
    ]
    out = CliRunner().invoke(cli_module.main, ["selftest", "--dir", str(tmp_path / "otra")])
    assert out.exit_code == 0, out.output


def test_discovery_skips_sealed_outputs_but_not_explicit_files(tmp_path, make_pdf):
    make_pdf("libro.pdf")
    sealed = make_pdf("libro_TDM.pdf")

    assert [p.name for p in iter_documents(tmp_path)] == ["libro.pdf"]
    assert iter_documents(sealed) == [sealed]
    assert is_sealed_output(sealed)
    assert not is_sealed_output(tmp_path / "TDM_manual.pdf")


def test_gui_row_tooltip_explains_skip(qtbot, make_signed_pdf):
    import pytest

    pytest.importorskip("PySide6")
    import tdmseal.gui as gui_module

    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    window._load_paths([make_signed_pdf("firmado.pdf")])
    qtbot.waitUntil(lambda: window.btn_audit.isEnabled(), timeout=10000)

    window._run_seal()
    qtbot.waitUntil(lambda: "procesados" in window.status_label.text(), timeout=10000)

    tooltip = window.table.item(0, 5).toolTip()
    assert "firmas digitales" in tooltip
    assert "Validadores externos" in window.tools_label.text()


def test_gui_can_seal_signed_pdf_incrementally(qtbot, make_signed_pdf):
    import pytest

    pytest.importorskip("PySide6")
    import tdmseal.gui as gui_module

    path = make_signed_pdf("firmado.pdf")
    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    window._load_paths([path])
    qtbot.waitUntil(lambda: window.btn_audit.isEnabled(), timeout=10000)
    window.chk_signed.setChecked(True)

    window._run_seal()
    qtbot.waitUntil(lambda: "procesados" in window.status_label.text(), timeout=10000)

    sealed = path.with_name("firmado_TDM.pdf")
    assert sealed.read_bytes().startswith(path.read_bytes())
    assert "la firma sigue siendo válida" in window.table.item(0, 5).toolTip()
