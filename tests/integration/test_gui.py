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
    qtbot.waitUntil(lambda: window.btn_audit.isEnabled(), timeout=10000)

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
    qtbot.waitUntil(lambda: window.btn_audit.isEnabled(), timeout=10000)

    window._run_seal()
    qtbot.waitUntil(lambda: "procesados" in window.status_label.text(), timeout=5000)

    assert not pdf_path.with_name("gui_signed_TDM.pdf").exists()
    assert "0 correctos" in window.status_label.text()


def test_audit_fills_iscc_column_and_seal_writes_iscc(qtbot, make_text_pdf):
    pytest.importorskip("pypdfium2")
    from tdmseal.iscc.content import compute_content_iscc
    from tdmseal.pdf.inspector import inspect_pdf

    pdf_path = make_text_pdf("gui_iscc.pdf", title="Derechos y minería")
    expected = compute_content_iscc(pdf_path)
    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    assert window.chk_iscc.isChecked()

    window._load_paths([pdf_path])
    qtbot.waitUntil(lambda: window.table.item(0, gui_module.ISCC_COL).text() != "", timeout=10000)
    assert window.table.item(0, gui_module.ISCC_COL).text() == expected.iscc
    assert "Text-Code" in window.table.item(0, gui_module.ISCC_COL).toolTip()
    qtbot.waitUntil(lambda: window.btn_audit.isEnabled(), timeout=10000)

    window._run_seal()
    qtbot.waitUntil(lambda: window.btn_open_folder.isEnabled(), timeout=10000)

    declared = inspect_pdf(pdf_path.with_name("gui_iscc_TDM.pdf")).declared_iscc
    assert declared.content_code == expected.text_code


def test_gui_audits_and_seals_epub(qtbot, make_epub):
    epub_path = make_epub("gui_libro.epub")
    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    window.chk_iscc.setChecked(False)

    window._load_paths([epub_path])
    qtbot.waitUntil(lambda: window.table.item(0, 5).text() == "listo", timeout=5000)
    assert window.table.item(0, 1).text() == "EPUB 3.0"
    qtbot.waitUntil(lambda: window.btn_audit.isEnabled(), timeout=10000)

    window._run_seal()
    qtbot.waitUntil(lambda: window.btn_open_folder.isEnabled(), timeout=10000)

    assert epub_path.with_name("gui_libro_TDM.epub").exists()


def test_visible_notice_is_off_by_default_and_needs_confirmation(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    assert not window.chk_notice.isChecked()

    monkeypatch.setattr(
        gui_module.QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    window.chk_notice.setChecked(True)
    assert not window.chk_notice.isChecked()

    monkeypatch.setattr(
        gui_module.QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    window.chk_notice.setChecked(True)
    assert window.chk_notice.isChecked()


def test_gui_tabs(qtbot):
    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    names = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert names == [
        "Sellar",
        "Política",
        "Sitio web",
        "Catálogo",
        "Buscar copias",
        "Red ISCC",
    ]


def _yes(monkeypatch, answer=True):
    from PySide6.QtWidgets import QMessageBox

    button = QMessageBox.StandardButton.Yes if answer else QMessageBox.StandardButton.No
    monkeypatch.setattr(gui_module.QMessageBox, "question", lambda *a, **k: button)


def test_catalog_registry_and_match_from_gui(qtbot, monkeypatch, tmp_path, make_text_pdf):
    pytest.importorskip("pypdfium2")
    pdf = make_text_pdf("libro.pdf")
    out = tmp_path / "catalogo.json"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(pdf.parent))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **kw: (str(out), ""))
    window = gui_module.MainWindow()
    qtbot.addWidget(window)

    window._build_manifest()
    qtbot.waitUntil(lambda: "Manifiesto generado" in window.status_label.text(), timeout=20000)
    assert out.with_name("catalogo.json.huellas.json").exists()

    web = tmp_path / "web"
    web.mkdir()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(out), ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(web))
    window._build_registry()
    assert "Registro generado" in window.status_label.text()
    assert (web / "registro.json").exists()

    window.match_catalog_edit.setText(str(out))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(pdf), ""))
    window._run_match()
    qtbot.waitUntil(lambda: "idéntico" in window.match_output.toPlainText(), timeout=20000)


def test_onix_add_from_gui(qtbot, monkeypatch, tmp_path):
    src = tmp_path / "onix.xml"
    src.write_text(
        '<ONIXMessage release="3.0" xmlns="http://ns.editeur.org/onix/3.0/reference">'
        "<Product><RecordReference>e1</RecordReference><DescriptiveDetail>"
        "<ProductForm>ED</ProductForm><TitleDetail/></DescriptiveDetail></Product>"
        "</ONIXMessage>",
        encoding="utf-8",
    )
    out = tmp_path / "onix_TDM.xml"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(src), ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **kw: (str(out), ""))
    window = gui_module.MainWindow()
    qtbot.addWidget(window)

    window._onix_add()

    assert b"<EpubUsageType>11</EpubUsageType>" in out.read_bytes()
    assert "1 con reserva añadida" in window.status_label.text()


def test_timestamp_needs_confirmation(qtbot, monkeypatch, tmp_path):
    from tdmseal import timestamp

    manifest = tmp_path / "m.json"
    manifest.write_text("{}", encoding="utf-8")
    calls = []

    def fake_create(path, url):
        calls.append(url)
        return timestamp.Receipt(
            "m.json", "00", url, "2026-11-21T18:00:00Z", "01", "1.2", 1, "x", "m.json.tsr"
        )

    monkeypatch.setattr(timestamp, "create_timestamp", fake_create)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(manifest), ""))
    window = gui_module.MainWindow()
    qtbot.addWidget(window)

    _yes(monkeypatch, False)
    window._timestamp_manifest()
    assert calls == []

    _yes(monkeypatch, True)
    window._timestamp_manifest()
    qtbot.waitUntil(lambda: "Sellado el 2026-11-21" in window.status_label.text(), timeout=5000)
    assert calls == ["https://freetsa.org/tsr"]


def test_hub_keygen_and_declare_from_gui(qtbot, monkeypatch, tmp_path, make_text_pdf):
    pytest.importorskip("pypdfium2")
    from tdmseal.iscc import hub

    monkeypatch.setenv("TDMSEAL_HUB_KEY", str(tmp_path / "clave.json"))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(tmp_path))
    warnings = []
    monkeypatch.setattr(gui_module.QMessageBox, "warning", lambda *a, **k: warnings.append(a))
    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    assert "Aún no hay clave" in window.hub_identity_label.text()

    window.hub_domain_edit.setText("editorial.example.edu")
    window._hub_keygen()
    did = (tmp_path / "did.json").read_text(encoding="utf-8")
    assert "did:web:editorial.example.edu" in did
    assert "did:web:editorial.example.edu" in window.hub_identity_label.text()
    window._hub_keygen()  # no reemplaza la clave existente
    assert warnings and "Ya hay una clave" in warnings[-1][1]

    pdf = make_text_pdf("obra.pdf")
    sent = []
    monkeypatch.setattr(hub, "check_did_published", lambda key, timeout=30: None)

    def fake_declare(note, url, timeout=30):
        assert hub.verify_note(note)
        sent.append(url)
        return {"iscc_id": "ISCC:MAIGPRUEBA", "seq": 0, "receipt": None}

    monkeypatch.setattr(hub, "declare", fake_declare)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **kw: ([str(pdf)], ""))
    _yes(monkeypatch, True)
    window._hub_declare()
    qtbot.waitUntil(lambda: "ISCC:MAIGPRUEBA" in window.hub_output.toPlainText(), timeout=20000)
    assert sent == ["https://staging.iscc.id"]  # por defecto, la red de pruebas
    assert pdf.with_name("obra.pdf.iscc-declaracion.json").exists()


def test_aipref_defaults_and_policy_preview(qtbot):
    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    assert window.current_aipref().serialize() == "train-ai=n, ai-use=n, search=y"

    window._refresh_policy_preview()
    assert "Aún no se puede generar" in window.policy_preview.toPlainText()

    window.publisher_name_edit.setText("Editorial Universidad Ejemplo")
    window.publisher_website_edit.setText("https://editorial.example.edu")
    window.publisher_email_edit.setText("derechos@editorial.example.edu")
    window.tabs.setCurrentIndex(1)  # abrir la pestaña Política refresca la vista previa
    text = window.policy_preview.toPlainText()
    assert "invitación a pedir licencia" in text
    assert "compensación económica" in text  # otros fines, por defecto


def test_aipref_undeclared_category_is_omitted(qtbot):
    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    window.aipref_combos["search"].setCurrentIndex(2)  # sin declarar

    assert window.current_aipref().serialize() == "train-ai=n, ai-use=n"


def test_build_site_writes_files(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(tmp_path))
    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    window.publisher_website_edit.setText("https://editorial.example.edu")

    window._build_site()

    assert (tmp_path / ".well-known" / "tdmrep.json").exists()
    assert (tmp_path / "servidor" / "nginx.conf").exists()
    assert '"tdm-reservation": 1' in window.site_output.toPlainText()


def test_build_manifest_from_gui(qtbot, monkeypatch, tmp_path, make_text_pdf):
    make_text_pdf("a.pdf")
    out = tmp_path / "catalogo.json"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(tmp_path))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **kw: (str(out), ""))
    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    window.chk_manifest_iscc.setChecked(False)

    window._build_manifest()
    qtbot.waitUntil(lambda: "Manifiesto generado" in window.status_label.text(), timeout=10000)

    assert out.exists()


def test_iscc_unchecked_leaves_column_empty(qtbot, make_text_pdf):
    window = gui_module.MainWindow()
    qtbot.addWidget(window)
    window.chk_iscc.setChecked(False)

    window._load_paths([make_text_pdf("sin_iscc.pdf")])
    qtbot.waitUntil(lambda: window.btn_audit.isEnabled(), timeout=10000)

    assert window.table.item(0, gui_module.ISCC_COL).text() == ""


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
