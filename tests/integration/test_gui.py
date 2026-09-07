from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QFileDialog  # noqa: E402

import tdmseal.gui as gui_module  # noqa: E402
from tdmseal.appconfig import AppDefaults  # noqa: E402
from tdmseal.models import PublisherInfo  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_appconfig(monkeypatch):
    """Nunca tocar ~/.tdmseal/config.json real durante los tests de GUI."""
    store: dict[str, AppDefaults] = {}

    def fake_load(path=None):
        return store.get("defaults", AppDefaults())

    def fake_save(defaults, path=None):
        store["defaults"] = defaults

    monkeypatch.setattr(gui_module, "load_defaults", fake_load)
    monkeypatch.setattr(gui_module, "save_defaults", fake_save)
    return store


def test_select_file_via_dialog_runs_audit(qtbot, monkeypatch, make_pdf):
    pdf_path = make_pdf("gui_audit.pdf")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **kw: ([str(pdf_path)], ""))

    window = gui_module.MainWindow()
    qtbot.addWidget(window)

    qtbot.mouseClick(window.btn_select_file, Qt.MouseButton.LeftButton)

    def _audited():
        item = window.table.item(0, 5)
        return item is not None and item.text() != ""

    qtbot.waitUntil(_audited)
    assert window.table.item(0, 0).text() == str(pdf_path)
    assert window.table.item(0, 5).text() == "listo"


def test_apply_tdm_seals_file_and_enables_open_folder(qtbot, make_pdf):
    pdf_path = make_pdf("gui_seal.pdf")
    window = gui_module.MainWindow()
    qtbot.addWidget(window)

    window._load_paths([pdf_path])
    qtbot.waitUntil(lambda: window.table.item(0, 5).text() == "listo", timeout=5000)

    window._run_seal()
    qtbot.waitUntil(lambda: window.btn_open_folder.isEnabled(), timeout=5000)

    output_path = pdf_path.with_name("gui_seal_TDM.pdf")
    assert output_path.exists()
    assert "1 correctos" in window.status_label.text()


def test_apply_tdm_skips_signed_pdf(qtbot, make_signed_pdf):
    pdf_path = make_signed_pdf("gui_signed.pdf")
    window = gui_module.MainWindow()
    qtbot.addWidget(window)

    window._load_paths([pdf_path])
    qtbot.waitUntil(lambda: window.table.item(0, 5).text() != "", timeout=5000)
    assert "firmado" in window.table.item(0, 5).text()

    window._run_seal()
    qtbot.waitUntil(lambda: "procesados" in window.status_label.text(), timeout=5000)

    assert not pdf_path.with_name("gui_signed_TDM.pdf").exists()
    assert "0 correctos" in window.status_label.text()


def test_save_defaults_persists_publisher_and_policy(qtbot, isolate_appconfig):
    window = gui_module.MainWindow()
    qtbot.addWidget(window)

    window.publisher_name_edit.setText("Editorial Universidad Ejemplo")
    window.publisher_acronym_edit.setText("EUE")
    window.policy_url_edit.setText("https://editorial.example.edu/tdm/policy.jsonld")
    window.radio_not_reserved.setChecked(True)

    window._save_defaults()

    saved = isolate_appconfig["defaults"]
    assert saved.publisher == PublisherInfo(
        name="Editorial Universidad Ejemplo",
        acronym="EUE",
        website=None,
        rights_email=None,
    )
    assert saved.reservation == 0
    assert saved.policy_url == "https://editorial.example.edu/tdm/policy.jsonld"


def test_build_policy_writes_artifacts(qtbot, monkeypatch, tmp_path):
    output_dir = tmp_path / "policy_out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(output_dir))

    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    window.publisher_name_edit.setText("Editorial Universidad Ejemplo")
    window.publisher_website_edit.setText("https://editorial.example.edu")
    window.publisher_email_edit.setText("derechos@editorial.example.edu")

    window._build_policy()

    assert (output_dir / "policy.jsonld").exists()
    assert (output_dir / "policy.html").exists()
    assert (output_dir / "tdmrep.json").exists()
    assert "Política generada" in window.status_label.text()


def test_build_policy_warns_on_missing_data(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(tmp_path))
    monkeypatch.setattr(gui_module.QMessageBox, "warning", lambda *a, **kw: None)

    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    # Sin nombre/sitio web/correo: debe advertir y no escribir nada.

    window._build_policy()

    assert not (tmp_path / "policy.jsonld").exists()


def test_startup_prefills_from_saved_defaults(qtbot, isolate_appconfig):
    isolate_appconfig["defaults"] = AppDefaults(
        publisher=PublisherInfo(name="Editorial Precargada"),
        reservation=0,
        policy_url="https://example.org/policy.jsonld",
    )

    window = gui_module.MainWindow()
    qtbot.addWidget(window)

    assert window.publisher_name_edit.text() == "Editorial Precargada"
    assert window.radio_not_reserved.isChecked()
    assert window.policy_url_edit.text() == "https://example.org/policy.jsonld"
