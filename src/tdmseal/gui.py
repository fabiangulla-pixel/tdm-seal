"""GUI de TDM Seal (PySide6), sobre el mismo núcleo que usa la CLI.

Cuatro pestañas, una por vía de expresión de la reserva:

- **Sellar**: datos de la editorial, reserva, archivos PDF/EPUB, ISCC y aviso
  visible (desactivado por defecto, con confirmación).
- **Política**: condiciones de licencia por finalidad, preferencias AIPREF y
  vista previa de la página que verá quien quiera licenciar.
- **Sitio web**: `tdmrep.json`, cabeceras HTTP, robots.txt y metaetiquetas.
- **Catálogo**: manifiesto CSV/JSON con hashes, ISCC e ISBN.

El trabajo pesado (auditoría, ISCC, sellado, manifiesto) corre en QThread.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from tdmseal.aipref import CATEGORIES, AiPreferences, AiPrefError, default_preferences
from tdmseal.appconfig import AppDefaults, load_defaults, save_defaults
from tdmseal.config import SealConfig
from tdmseal.discovery import iter_documents
from tdmseal.documents import inspect_document, seal_document
from tdmseal.errors import TDMSealError
from tdmseal.iscc.content import compute_content_iscc, content_extra_available
from tdmseal.manifest import build_manifest
from tdmseal.models import PublisherInfo, TDMPolicy
from tdmseal.notice import notice_from_publisher
from tdmseal.policy.builder import PolicyOptions, build_policy_artifacts, write_policy_artifacts
from tdmseal.reporting.json_report import write_report
from tdmseal.site import build_site_artifacts, write_site_artifacts
from tdmseal.tools import tools_status

COLUMNS = ["Archivo", "Formato", "Firmado", "Cifrado / DRM", "TDM actual", "Estado", "ISCC"]
ISCC_COL = 6

_OK_COLOR = QColor("#1e7e34")
_WARN_COLOR = QColor("#9a6b00")
_ERROR_COLOR = QColor("#b02a2a")

TERM_CHOICES = [
    ("consent", "Con autorización previa"),
    ("compensate", "Con autorización y compensación económica"),
    ("free", "Libre, sin solicitud"),
    ("none", "No se ofrece licencia"),
]
AIPREF_CHOICES = [("n", "Reservado"), ("y", "Permitido"), (None, "Sin declarar")]
AIPREF_LABELS = {
    "train-ai": "Entrenar modelos de IA generativa",
    "ai-use": "Usar como entrada de sistemas de IA",
    "search": "Búsqueda e indexación con enlace",
}

STYLE = """
QWidget { font-family: "Segoe UI", "Helvetica Neue", Arial; font-size: 10pt; color: #1f2933; }
QMainWindow, QTabWidget::pane, QScrollArea { background: #f5f6f8; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; padding: 8px 18px; margin-right: 4px;
               border-bottom: 3px solid transparent; color: #52606d; font-weight: 600; }
QTabBar::tab:selected { color: #1f6f4a; border-bottom: 3px solid #1f6f4a; }
QGroupBox { background: #ffffff; border: 1px solid #e1e4e8; border-radius: 10px;
            margin-top: 14px; padding: 14px 12px 10px 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #3e4c59; }
QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser {
    background: #ffffff; border: 1px solid #cbd2d9; border-radius: 6px; padding: 5px 8px; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #1f6f4a; }
QPushButton { background: #ffffff; border: 1px solid #cbd2d9; border-radius: 6px;
              padding: 6px 14px; }
QPushButton:hover { border-color: #1f6f4a; color: #1f6f4a; }
QPushButton:disabled { color: #9aa5b1; border-color: #e1e4e8; }
QPushButton#primary { background: #1f6f4a; color: #ffffff; border: none; font-weight: 600;
                      padding: 8px 20px; }
QPushButton#primary:hover { background: #185a3c; color: #ffffff; }
QPushButton#primary:disabled { background: #9fbfae; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
QCheckBox::indicator { border: 1px solid #9aa5b1; border-radius: 4px; background: #ffffff; }
QCheckBox::indicator:checked { background: #1f6f4a; border-color: #1f6f4a; }
QRadioButton::indicator { border: 1px solid #9aa5b1; border-radius: 8px; background: #ffffff; }
QRadioButton::indicator:checked { background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
    fx:0.5, fy:0.5, stop:0 #1f6f4a, stop:0.45 #1f6f4a, stop:0.55 #ffffff, stop:1 #ffffff);
    border: 1px solid #1f6f4a; }
QTableWidget { background: #ffffff; border: 1px solid #e1e4e8; border-radius: 8px;
               gridline-color: #eef0f3; }
QHeaderView::section { background: #f0f2f5; border: none; padding: 6px;
                       font-weight: 600; color: #52606d; }
QLabel#hint { color: #616e7c; font-weight: normal; }
QLabel#status { color: #3e4c59; padding: 4px 2px; }
"""


@dataclass
class _RowState:
    path: Path
    signed: bool = False
    encrypted: bool = False


class _AuditWorker(QObject):
    file_done = Signal(int, object)  # índice de fila, PDFInfo | EPUBInfo | Exception
    iscc_done = Signal(int, object)  # índice de fila, ContentIscc | Exception
    finished = Signal()

    def __init__(self, paths: list[Path], with_iscc: bool = False) -> None:
        super().__init__()
        self._paths = paths
        self._with_iscc = with_iscc

    def run(self) -> None:
        for i, path in enumerate(self._paths):
            try:
                info = inspect_document(path)
                self.file_done.emit(i, info)
            except TDMSealError as exc:
                self.file_done.emit(i, exc)
                continue
            if self._with_iscc and not (info.encrypted or info.signed):
                try:
                    self.iscc_done.emit(i, compute_content_iscc(path))
                except Exception as exc:  # noqa: BLE001 — se muestra en la fila
                    self.iscc_done.emit(i, exc)
        self.finished.emit()


class _SealWorker(QObject):
    file_done = Signal(int, object)  # índice de fila, SealResult
    finished = Signal(int, int, int)  # ok, skipped, failed

    def __init__(self, paths: list[Path], config: SealConfig, publisher: PublisherInfo) -> None:
        super().__init__()
        self._paths = paths
        self._config = config
        self._publisher = publisher

    def run(self) -> None:
        ok = skipped = failed = 0
        for i, path in enumerate(self._paths):
            result = seal_document(path, self._config)
            if result.output_path is not None:
                report_path = result.output_path.with_suffix(
                    result.output_path.suffix + ".report.json"
                )
                write_report(result, report_path, self._publisher)
            if result.status == "success":
                ok += 1
            elif result.status == "skipped":
                skipped += 1
            else:
                failed += 1
            self.file_done.emit(i, result)
        self.finished.emit(ok, skipped, failed)


class _ManifestWorker(QObject):
    finished = Signal(object)  # Path escrito | Exception

    def __init__(self, folder: Path, out: Path, kwargs: dict) -> None:
        super().__init__()
        self._folder, self._out, self._kwargs = folder, out, kwargs

    def run(self) -> None:
        try:
            docs = iter_documents(self._folder, recursive=True)
            manifest = build_manifest(docs, base_dir=self._folder, **self._kwargs)
            self.finished.emit(manifest.write(self._out))
        except Exception as exc:  # noqa: BLE001 — se muestra al usuario
            self.finished.emit(exc)


def seal_result_details(result) -> str:
    """Texto para la ayuda emergente de la fila: por qué se omitió o falló, y avisos."""
    lines = []
    for error in result.errors:
        lines.append(f"• {error}")
    if result.validations:
        lines.append(
            "Validaciones: " + ", ".join(f"{k}={v}" for k, v in result.validations.items())
        )
    for warning in result.warnings:
        lines.append(f"Aviso: {warning}")
    if result.output_path is not None and result.status == "success":
        lines.append(f"Reporte: {result.output_path.name}.report.json")
    return "\n".join(lines) or "Sin observaciones."


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TDM Seal — reserva de derechos TDM para PDF y EPUB")
        self.resize(1000, 720)

        self._rows: list[_RowState] = []
        self._last_output_dir: Path | None = None
        self._thread: QThread | None = None
        self._worker: QObject | None = None

        self._build_ui()

    # ---- construcción de la interfaz -----------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 12, 16, 10)

        title = QLabel("Derechos de minería de textos y datos")
        title.setStyleSheet("font-size: 15pt; font-weight: 700; color: #1f2933;")
        layout.addWidget(title)
        layout.addWidget(
            _hint(
                "Declare la reserva en cada archivo, en el contenido (ISCC), en su sitio web "
                "y en una política de licencia. Nada se sube a internet."
            )
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_seal_tab(), "Sellar")
        self.tabs.addTab(self._build_policy_tab(), "Política")
        self.tabs.addTab(self._build_site_tab(), "Sitio web")
        self.tabs.addTab(self._build_catalog_tab(), "Catálogo")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, stretch=1)

        self.status_label = QLabel("Seleccione uno o varios PDF o EPUB para comenzar.")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self._apply_defaults(load_defaults())

    def _build_seal_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        publisher_group = QGroupBox("Editorial / titular de derechos")
        form = QFormLayout(publisher_group)
        self.publisher_name_edit = QLineEdit()
        self.publisher_acronym_edit = QLineEdit()
        self.publisher_acronym_edit.setMaximumWidth(140)
        self.publisher_website_edit = QLineEdit()
        self.publisher_website_edit.setPlaceholderText("https://editorial.ejemplo.edu")
        self.publisher_email_edit = QLineEdit()
        self.publisher_email_edit.setPlaceholderText("derechos@editorial.ejemplo.edu")
        form.addRow("Nombre:", self.publisher_name_edit)
        form.addRow("Sigla:", self.publisher_acronym_edit)
        form.addRow("Sitio web:", self.publisher_website_edit)
        form.addRow("Correo de derechos:", self.publisher_email_edit)
        self.btn_save_defaults = QPushButton("Guardar como valores por defecto")
        self.btn_save_defaults.clicked.connect(self._save_defaults)
        form.addRow("", self.btn_save_defaults)
        layout.addWidget(publisher_group)

        policy_group = QGroupBox("Reserva TDM")
        policy_layout = QVBoxLayout(policy_group)
        radios = QHBoxLayout()
        self.radio_reserved = QRadioButton("Reservados (recomendado)")
        self.radio_not_reserved = QRadioButton("No reservados")
        self.radio_reserved.setChecked(True)
        radios.addWidget(self.radio_reserved)
        radios.addWidget(self.radio_not_reserved)
        radios.addStretch(1)
        policy_layout.addLayout(radios)
        policy_row = QHBoxLayout()
        policy_row.addWidget(QLabel("URL de la política:"))
        self.policy_url_edit = QLineEdit()
        self.policy_url_edit.setPlaceholderText("https://editorial.ejemplo.edu/tdm/policies/1")
        policy_row.addWidget(self.policy_url_edit)
        policy_layout.addLayout(policy_row)
        layout.addWidget(policy_group)

        select_row = QHBoxLayout()
        self.btn_select_file = QPushButton("Seleccionar PDF o EPUB…")
        self.btn_select_folder = QPushButton("Seleccionar carpeta…")
        self.chk_recursive = QCheckBox("Incluir subcarpetas")
        self.chk_iscc = QCheckBox("Calcular ISCC (huella del contenido)")
        self.chk_iscc.setToolTip(
            "Calcula el ISCC (ISO 24138) de cada documento y lo guarda en sus metadatos al "
            "sellar. El código de contenido se calcula sobre el texto y no cambia al "
            "sellar. Tarda un poco más en libros largos."
        )
        self.chk_iscc.setChecked(True)
        if not content_extra_available():
            self.chk_iscc.setToolTip(
                self.chk_iscc.toolTip() + "\n\nFalta el extra 'tdm-seal[iscc]': solo se "
                "calcularán los códigos de metadatos y de bytes, no el de contenido."
            )
        for widget in (
            self.btn_select_file,
            self.btn_select_folder,
            self.chk_recursive,
            self.chk_iscc,
        ):
            select_row.addWidget(widget)
        select_row.addStretch(1)
        layout.addLayout(select_row)

        self.chk_notice = QCheckBox("Añadir página de aviso visible (cambia el contenido)")
        self.chk_notice.setToolTip(
            "Añade al final una página (PDF) o un documento (EPUB) con la reserva en "
            "lenguaje claro. No modifica las páginas existentes. No se aplica a PDF/A, "
            "PDF/UA, PDF firmados ni EPUB de maquetación fija."
        )
        self.chk_notice.setChecked(False)
        self.chk_notice.toggled.connect(self._confirm_notice)
        layout.addWidget(self.chk_notice)

        self.chk_signed = QCheckBox("Sellar también PDF ya firmados (sin invalidar la firma)")
        self.chk_signed.setToolTip(
            "Lo ideal es sellar antes de firmar. Si el PDF ya está firmado, el sello se "
            "añade al final del archivo sin tocar los bytes firmados: la firma sigue "
            "siendo válida, aunque algunos lectores avisarán de cambios posteriores a la "
            "firma (solo metadatos). Desactivado: los PDF firmados se omiten."
        )
        layout.addWidget(self.chk_signed)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(ISCC_COL, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, stretch=1)

        action_row = QHBoxLayout()
        self.btn_audit = QPushButton("Auditar")
        self.btn_apply = QPushButton("Aplicar TDM")
        self.btn_apply.setObjectName("primary")
        self.btn_apply.setEnabled(False)
        self.btn_open_folder = QPushButton("Abrir carpeta")
        self.btn_open_folder.setEnabled(False)
        action_row.addWidget(self.btn_audit)
        action_row.addWidget(self.btn_apply)
        action_row.addStretch(1)
        self.tools_label = QLabel(self._tools_summary())
        self.tools_label.setObjectName("hint")
        self.tools_label.setToolTip(
            "veraPDF y EPUBCheck son opcionales: si están, cada sellado se valida con "
            "ellos. Se instalan con scripts\\instalar_herramientas.ps1."
        )
        action_row.addWidget(self.tools_label)
        action_row.addWidget(self.btn_open_folder)
        layout.addLayout(action_row)

        self.btn_select_file.clicked.connect(self._select_file)
        self.btn_select_folder.clicked.connect(self._select_folder)
        self.btn_audit.clicked.connect(self._run_audit)
        self.btn_apply.clicked.connect(self._run_seal)
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        return tab

    def _build_policy_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)

        left = QVBoxLayout()
        terms = QGroupBox("Condiciones de licencia")
        form = QFormLayout(terms)
        self.combo_research = QComboBox()
        self.combo_non_research = QComboBox()
        for combo in (self.combo_research, self.combo_non_research):
            for value, label in TERM_CHOICES:
                combo.addItem(label, value)
        self.combo_non_research.setCurrentIndex(1)  # compensación, por defecto
        for combo in (self.combo_research, self.combo_non_research):
            combo.currentIndexChanged.connect(self._refresh_policy_preview)
        form.addRow("Investigación:", self.combo_research)
        form.addRow("Otros fines (comercial, IA):", self.combo_non_research)
        self.license_url_edit = QLineEdit()
        self.license_url_edit.setPlaceholderText("Página o formulario de licencias (opcional)")
        self.license_url_edit.editingFinished.connect(self._refresh_policy_preview)
        form.addRow("Página de licencias:", self.license_url_edit)
        # Compatibilidad: casilla anterior, equivale a "compensación" en ambos fines.
        self.chk_require_compensation = QCheckBox("Exigir compensación en todos los usos")
        self.chk_require_compensation.toggled.connect(self._refresh_policy_preview)
        form.addRow("", self.chk_require_compensation)
        left.addWidget(terms)

        aipref_group = QGroupBox("Preferencias de IA (IETF AIPREF)")
        aipref_form = QFormLayout(aipref_group)
        self.aipref_combos: dict[str, QComboBox] = {}
        for category in CATEGORIES:
            combo = QComboBox()
            for value, label in AIPREF_CHOICES:
                combo.addItem(label, value)
            combo.currentIndexChanged.connect(self._refresh_policy_preview)
            self.aipref_combos[category] = combo
            aipref_form.addRow(f"{AIPREF_LABELS[category]}:", combo)
        aipref_form.addRow(
            _hint(
                "Se publican en la cabecera HTTP Content-Usage y en robots.txt (pestaña "
                "Sitio web) y quedan en cada reporte. El borrador aún no define cómo "
                "guardarlas dentro del PDF o EPUB."
            )
        )
        left.addWidget(aipref_group)

        self.btn_build_policy = QPushButton("Generar archivos de política…")
        self.btn_build_policy.setObjectName("primary")
        self.btn_build_policy.clicked.connect(self._build_policy)
        left.addWidget(self.btn_build_policy)
        left.addStretch(1)
        layout.addLayout(left, stretch=2)

        preview_group = QGroupBox("Vista previa de la página de la política")
        preview_layout = QVBoxLayout(preview_group)
        self.policy_preview = QTextBrowser()
        self.policy_preview.setOpenExternalLinks(False)
        preview_layout.addWidget(self.policy_preview)
        self.btn_refresh_preview = QPushButton("Actualizar vista previa")
        self.btn_refresh_preview.clicked.connect(self._refresh_policy_preview)
        preview_layout.addWidget(self.btn_refresh_preview)
        layout.addWidget(preview_group, stretch=3)
        return tab

    def _build_site_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        group = QGroupBox("Señales del sitio web")
        form = QFormLayout(group)
        self.site_base_url_edit = QLineEdit()
        self.site_base_url_edit.setPlaceholderText(
            "https://editorial.ejemplo.edu/ (por defecto, el sitio web de la editorial)"
        )
        form.addRow("URL raíz del sitio:", self.site_base_url_edit)
        form.addRow(
            _hint(
                "Genera /.well-known/tdmrep.json, las cabeceras HTTP para Apache y Nginx "
                "(tdm-reservation, tdm-policy, Content-Usage), las líneas para robots.txt y "
                "las metaetiquetas HTML, con un LEEME que explica dónde va cada archivo. "
                "Usa la reserva y la URL de la política de la pestaña Sellar y las "
                "preferencias de IA de la pestaña Política."
            )
        )
        self.btn_build_site = QPushButton("Generar archivos del sitio…")
        self.btn_build_site.setObjectName("primary")
        self.btn_build_site.clicked.connect(self._build_site)
        form.addRow("", self.btn_build_site)
        layout.addWidget(group)
        self.site_output = QPlainTextEdit()
        self.site_output.setReadOnly(True)
        self.site_output.setPlaceholderText("Aquí aparecerá el contenido de tdmrep.json.")
        layout.addWidget(self.site_output, stretch=1)
        return tab

    def _build_catalog_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        group = QGroupBox("Manifiesto del catálogo")
        form = QFormLayout(group)
        form.addRow(
            _hint(
                "Una fila por obra (PDF y EPUB de la carpeta y sus subcarpetas): hashes, "
                "ISCC, ISBN, título, reserva TDM, política y preferencias de IA. Sirve para "
                "registros ISCC y para negociar licencias en bloque. CSV para Excel o JSON."
            )
        )
        self.chk_manifest_iscc = QCheckBox("Incluir ISCC de contenido (más lento)")
        self.chk_manifest_iscc.setChecked(True)
        form.addRow("", self.chk_manifest_iscc)
        self.btn_build_manifest = QPushButton("Generar manifiesto…")
        self.btn_build_manifest.setObjectName("primary")
        self.btn_build_manifest.clicked.connect(self._build_manifest)
        form.addRow("", self.btn_build_manifest)
        layout.addWidget(group)
        layout.addStretch(1)
        return tab

    # ---- valores por defecto y datos actuales ---------------------------

    def _apply_defaults(self, defaults: AppDefaults) -> None:
        self.publisher_name_edit.setText(defaults.publisher.name or "")
        self.publisher_acronym_edit.setText(defaults.publisher.acronym or "")
        self.publisher_website_edit.setText(defaults.publisher.website or "")
        self.publisher_email_edit.setText(defaults.publisher.rights_email or "")
        self.policy_url_edit.setText(defaults.policy_url or "")
        if defaults.reservation == 0:
            self.radio_not_reserved.setChecked(True)
        else:
            self.radio_reserved.setChecked(True)
        try:
            prefs = AiPreferences.parse(defaults.aipref)
        except AiPrefError:
            prefs = default_preferences()
        for category, combo in self.aipref_combos.items():
            value = prefs.get(category)
            combo.setCurrentIndex(next(i for i, (v, _) in enumerate(AIPREF_CHOICES) if v == value))

    def _current_publisher(self) -> PublisherInfo:
        return PublisherInfo(
            name=self.publisher_name_edit.text().strip() or None,
            acronym=self.publisher_acronym_edit.text().strip() or None,
            website=self.publisher_website_edit.text().strip() or None,
            rights_email=self.publisher_email_edit.text().strip() or None,
        )

    def current_aipref(self) -> AiPreferences | None:
        """Preferencias AIPREF de la pestaña Política (None si no se declara ninguna)."""
        items = [
            f"{category}={combo.currentData()}"
            for category, combo in self.aipref_combos.items()
            if combo.currentData() is not None
        ]
        return AiPreferences.parse(", ".join(items)) if items else None

    def current_policy_options(self) -> PolicyOptions:
        compensate_all = self.chk_require_compensation.isChecked()
        return PolicyOptions(
            require_compensation=compensate_all,
            research=None if compensate_all else self.combo_research.currentData(),
            non_research=None if compensate_all else self.combo_non_research.currentData(),
            policy_url=self.policy_url_edit.text().strip() or None,
            license_contact_url=self.license_url_edit.text().strip() or None,
            aipref=self.current_aipref(),
        )

    def _save_defaults(self) -> None:
        aipref = self.current_aipref()
        defaults = AppDefaults(
            publisher=self._current_publisher(),
            reservation=1 if self.radio_reserved.isChecked() else 0,
            policy_url=self.policy_url_edit.text().strip() or None,
            aipref=aipref.serialize() if aipref else default_preferences().serialize(),
        )
        save_defaults(defaults)
        self.status_label.setText("Valores por defecto guardados.")

    # ---- política -------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.tabText(index) == "Política":
            self._refresh_policy_preview()

    def _refresh_policy_preview(self, *_args) -> None:
        try:
            html = build_policy_artifacts(self._current_publisher(), self.current_policy_options())[
                "policy.html"
            ]
        except ValueError as exc:
            self.policy_preview.setHtml(
                "<p style='color:#9a6b00'><b>Aún no se puede generar la política.</b></p>"
                f"<p>{exc}</p><p>Complete los datos de la editorial en la pestaña Sellar.</p>"
            )
            return
        self.policy_preview.setHtml(html)

    def _build_policy(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Carpeta de salida para la política TDM",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not folder:
            return

        try:
            paths = write_policy_artifacts(
                Path(folder), self._current_publisher(), self.current_policy_options()
            )
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo generar la política", str(exc))
            return

        self.status_label.setText(f"Política generada en {folder}: {', '.join(paths)}")

    # ---- sitio web -------------------------------------------------------------

    def _build_site(self) -> None:
        base_url = (
            self.site_base_url_edit.text().strip() or self.publisher_website_edit.text().strip()
        )
        if not base_url:
            QMessageBox.warning(
                self, "Falta la URL del sitio", "Indique la URL raíz del sitio web."
            )
            return
        reservation = 1 if self.radio_reserved.isChecked() else 0
        aipref = self.current_aipref()
        try:
            files = build_site_artifacts(
                base_url, reservation, self.policy_url_edit.text().strip() or None, aipref
            )
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudieron generar los archivos", str(exc))
            return
        folder = QFileDialog.getExistingDirectory(
            self,
            "Carpeta donde dejar los archivos del sitio",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not folder:
            return
        write_site_artifacts(Path(folder), files)
        self.site_output.setPlainText(files[".well-known/tdmrep.json"])
        warnings = aipref.check_consistency(reservation) if aipref else []
        self.status_label.setText(
            f"Archivos del sitio generados en {folder}. Lea LEEME.txt."
            + (f" Aviso: {warnings[0]}" if warnings else "")
        )

    # ---- catálogo --------------------------------------------------------------

    def _build_manifest(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Carpeta del catálogo",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not folder:
            return
        out, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar manifiesto",
            str(Path(folder) / "catalogo_tdm.csv"),
            "CSV (*.csv);;JSON (*.json)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not out:
            return
        publisher = self._current_publisher()
        aipref = self.current_aipref()
        kwargs = {
            "with_iscc": self.chk_manifest_iscc.isChecked(),
            "aipref": aipref.serialize() if aipref else None,
            "publisher": None if publisher.is_empty() else vars(publisher),
        }
        self.btn_build_manifest.setEnabled(False)
        self.status_label.setText("Generando manifiesto…")
        worker = _ManifestWorker(Path(folder), Path(out), kwargs)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_manifest_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        self._thread, self._worker = thread, worker
        thread.start()

    def _on_manifest_finished(self, result: object) -> None:
        self.btn_build_manifest.setEnabled(True)
        if isinstance(result, Exception):
            self.status_label.setText(f"No se pudo generar el manifiesto: {result}")
        else:
            self.status_label.setText(f"Manifiesto generado: {result}")

    # ---- selección de archivos ------------------------------------------

    # DontUseNativeDialog: en el .exe de PyInstaller, el dialogo nativo de
    # Windows (COM IFileOpenDialog) nunca aparece y se queda colgado sin
    # error — problema conocido de PySide6 congelado. El dialogo propio de
    # Qt no depende de COM y funciona igual en el .exe que sin congelar.
    def _select_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar PDF o EPUB",
            "",
            "PDF y EPUB (*.pdf *.epub);;PDF (*.pdf);;EPUB (*.epub)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if paths:
            self._load_paths([Path(p) for p in paths])

    def _select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if folder:
            docs = iter_documents(Path(folder), recursive=self.chk_recursive.isChecked())
            self._load_paths(docs)

    def _load_paths(self, paths: list[Path]) -> None:
        self._rows = [_RowState(path=p) for p in paths]
        self.table.setRowCount(len(paths))
        for row, state in enumerate(self._rows):
            self.table.setItem(row, 0, QTableWidgetItem(str(state.path)))
            for col in range(1, len(COLUMNS)):
                self.table.setItem(row, col, QTableWidgetItem(""))
        self.btn_apply.setEnabled(bool(paths))
        self.status_label.setText(f"{len(paths)} archivo(s) cargados. Audite o aplique TDM.")
        if paths:
            self._run_audit()

    # ---- auditoría (solo lectura) ---------------------------------------

    def _run_audit(self) -> None:
        if not self._rows:
            return
        self._set_buttons_enabled(False)
        self.status_label.setText(
            "Auditando y calculando ISCC…" if self.chk_iscc.isChecked() else "Auditando…"
        )

        worker = _AuditWorker([r.path for r in self._rows], with_iscc=self.chk_iscc.isChecked())
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.file_done.connect(self._on_audit_file_done)
        worker.iscc_done.connect(self._on_iscc_done)
        worker.finished.connect(lambda: self._on_worker_finished("Auditoría completada."))
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_audit_file_done(self, row: int, result: object) -> None:
        if isinstance(result, Exception):
            for col in (1, 2, 3, 4):
                self._set_row_text(row, col, "—")
            self._set_row_text(row, 5, str(result), color=_ERROR_COLOR)
            return

        info = result
        self._rows[row].signed = info.signed
        self._rows[row].encrypted = info.encrypted

        if info.kind == "epub":
            fmt = f"EPUB {info.epub_version}"
        elif info.pdfa_part is not None:
            fmt = f"PDF/A-{info.pdfa_part}{(info.pdfa_conformance or '').lower()}"
        else:
            fmt = "PDF"
        self._set_row_text(row, 1, fmt)
        self._set_row_text(row, 2, "sí" if info.signed else "no")
        self._set_row_text(row, 3, "sí" if info.encrypted else "no")
        self._set_row_text(row, 4, str(info.tdm.reservation) if info.tdm.present else "—")

        if info.signed:
            self._set_row_text(row, 5, "firmado — no se modificará", color=_WARN_COLOR)
        elif info.kind == "epub" and info.encrypted:
            self._set_row_text(row, 5, "DRM — no se modificará", color=_WARN_COLOR)
        elif info.encrypted:
            self._set_row_text(row, 5, "cifrado — no se modificará", color=_WARN_COLOR)
        else:
            self._set_row_text(row, 5, "listo", color=_OK_COLOR)

    def _confirm_notice(self, checked: bool) -> None:
        """Pide confirmación explícita: el aviso cambia el contenido visible."""
        if not checked:
            return
        answer = QMessageBox.question(
            self,
            "Añadir aviso visible",
            "El aviso visible añade una página final (PDF) o un documento final (EPUB) "
            "con la reserva de derechos en lenguaje claro.\n\n"
            "Las páginas existentes no se tocan, pero el archivo deja de ser idéntico "
            "en contenido al original. ¿Desea activarlo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.chk_notice.blockSignals(True)
            self.chk_notice.setChecked(False)
            self.chk_notice.blockSignals(False)

    def _on_iscc_done(self, row: int, result: object) -> None:
        if isinstance(result, Exception):
            self._set_row_text(row, ISCC_COL, f"error: {result}", color=_ERROR_COLOR)
            return
        item = QTableWidgetItem(result.iscc)
        tooltip = [
            f"Meta-Code: {result.meta_code} ({result.name})",
            f"Text-Code (contenido): {result.text_code or '—'}",
            f"Data-Code: {result.data_code}",
            f"Instance-Code: {result.instance_code}",
            *result.warnings,
        ]
        item.setToolTip("\n".join(tooltip))
        if not result.content_computed:
            item.setForeground(_WARN_COLOR)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, ISCC_COL, item)

    # ---- sellado ----------------------------------------------------------

    def _run_seal(self) -> None:
        if not self._rows:
            return
        policy_url = self.policy_url_edit.text().strip() or None
        try:
            policy = TDMPolicy(
                reservation=1 if self.radio_reserved.isChecked() else 0,
                policy_url=policy_url,
            )
        except (ValueError, TDMSealError) as exc:
            QMessageBox.warning(self, "Política TDM inválida", str(exc))
            return

        config = SealConfig(
            policy=policy,
            compute_iscc=self.chk_iscc.isChecked(),
            aipref=self.current_aipref(),
            force_signed=self.chk_signed.isChecked(),
        )
        publisher = self._current_publisher()
        if self.chk_notice.isChecked():
            try:
                config.notice = notice_from_publisher(publisher, policy.policy_url)
            except ValueError as exc:
                QMessageBox.warning(self, "Faltan datos para el aviso", str(exc))
                return
        self._set_buttons_enabled(False)
        self.status_label.setText("Aplicando TDM…")

        worker = _SealWorker([r.path for r in self._rows], config, publisher)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.file_done.connect(self._on_seal_file_done)
        worker.finished.connect(self._on_seal_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_seal_file_done(self, row: int, result) -> None:
        if result.status == "success":
            self._last_output_dir = result.output_path.parent
            text, color = f"sellado -> {result.output_path.name}", _OK_COLOR
        elif result.status == "skipped":
            reason = "ya sellado" if result.reason_code == "TDM050" else result.reason_code
            text, color = f"omitido ({reason})", _WARN_COLOR
        else:
            text, color = f"error ({result.reason_code or 'ver detalle'})", _ERROR_COLOR
        self._set_row_text(row, 5, text, color=color)
        self.table.item(row, 5).setToolTip(seal_result_details(result))

    def _tools_summary(self) -> str:
        status = tools_status()
        parts = [
            f"veraPDF {'sí' if status['verapdf'] else 'no'}",
            f"EPUBCheck {'sí' if status['epubcheck'] else 'no'}",
        ]
        return "Validadores externos: " + ", ".join(parts)

    def _on_seal_finished(self, ok: int, skipped: int, failed: int) -> None:
        total = ok + skipped + failed
        self._on_worker_finished(
            f"{total} archivos procesados — {ok} correctos, {skipped} omitidos, {failed} con error"
        )
        self.btn_open_folder.setEnabled(self._last_output_dir is not None)

    # ---- utilidades ---------------------------------------------------

    def _on_worker_finished(self, message: str) -> None:
        self.status_label.setText(message)
        self._set_buttons_enabled(True)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self.btn_audit.setEnabled(enabled)
        self.btn_apply.setEnabled(enabled and bool(self._rows))
        self.btn_select_file.setEnabled(enabled)
        self.btn_select_folder.setEnabled(enabled)

    def _set_row_text(self, row: int, col: int, text: str, color: QColor | None = None) -> None:
        item = QTableWidgetItem(text)
        if color is not None:
            item.setForeground(color)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, col, item)

    def _open_output_folder(self) -> None:
        if self._last_output_dir is None:
            return
        if sys.platform == "win32":
            os.startfile(self._last_output_dir)  # noqa: S606 — abrir carpeta en el explorador
        else:
            QMessageBox.information(self, "Carpeta de salida", str(self._last_output_dir))


def _run_selftest_and_exit(argv: list[str]) -> None:
    """`TDM-Seal.exe --autoprueba [informe.json]`: sin ventana; escribe un JSON y sale.

    El .exe no tiene consola, así que el resultado va a un archivo (por
    defecto `%TEMP%\\tdmseal-autoprueba.json`). Código de salida 0 si todo OK.
    """
    import json
    import tempfile

    from tdmseal.selftest import run_selftest

    idx = argv.index("--autoprueba")
    out = (
        Path(argv[idx + 1])
        if len(argv) > idx + 1
        else Path(tempfile.gettempdir()) / "tdmseal-autoprueba.json"
    )
    result = run_selftest()
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    sys.exit(0 if result["ok"] else 1)


def main() -> None:
    if "--autoprueba" in sys.argv:
        _run_selftest_and_exit(sys.argv)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
