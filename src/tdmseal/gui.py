"""GUI de TDM Seal (PySide6), sobre el mismo núcleo que usa la CLI.

Cuatro pestañas, una por vía de expresión de la reserva:

- **Sellar**: datos de la editorial, reserva, archivos PDF/EPUB, ISCC y aviso
  visible (desactivado por defecto, con confirmación).
- **Política**: condiciones de licencia por finalidad, preferencias AIPREF y
  vista previa de la página que verá quien quiera licenciar.
- **Sitio web**: `tdmrep.json`, cabeceras HTTP, robots.txt y metaetiquetas.
- **Catálogo**: manifiesto CSV/JSON con hashes, ISCC e ISBN (y huellas por
  fragmentos); sello de tiempo RFC 3161; registro público; ONIX.
- **Buscar copias**: ¿este archivo (o volcado de texto) es uno de mis libros?
- **Red ISCC**: identidad did:web y declaración directa en un hub ISCC.

Lo que usa la red (sello de tiempo, red ISCC) pide confirmación antes.

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
            written = manifest.write(self._out)
            if self._kwargs.get("with_iscc"):
                from tdmseal.fingerprint import write_fingerprints

                works = {row["archivo"]: d for row, d in zip(manifest.rows, docs, strict=True)}
                write_fingerprints(written, works)
            self.finished.emit(written)
        except Exception as exc:  # noqa: BLE001 — se muestra al usuario
            self.finished.emit(exc)


class _TaskWorker(QObject):
    """Ejecuta una función en otro hilo y devuelve su resultado (o la excepción)."""

    finished = Signal(object)

    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.finished.emit(self._fn())
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

    def closeEvent(self, event) -> None:  # noqa: N802 — nombre de Qt
        # Destruir un QThread que sigue corriendo aborta el proceso (qFatal):
        # pasaba de forma intermitente al cerrar la ventana justo después de una
        # auditoría (visto en las pruebas, 2 de cada 5 corridas). Se espera a
        # que terminen los hilos antes de cerrar.
        for thread in self.findChildren(QThread):
            try:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(30000)
            except RuntimeError:  # objeto C++ ya borrado por deleteLater
                continue
        super().closeEvent(event)

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
                "y en una política de licencia. Nada sale de este equipo salvo que usted lo "
                "pida (sello de tiempo, red ISCC), y los libros nunca."
            )
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_seal_tab(), "Sellar")
        self.tabs.addTab(self._build_policy_tab(), "Política")
        self.tabs.addTab(self._build_site_tab(), "Sitio web")
        self.tabs.addTab(self._build_catalog_tab(), "Catálogo")
        self.tabs.addTab(self._build_match_tab(), "Buscar copias")
        self.tabs.addTab(self._build_hub_tab(), "Red ISCC")
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

        proof = QGroupBox("Prueba de fecha y registro público")
        pform = QFormLayout(proof)
        pform.addRow(
            _hint(
                "El sello de tiempo RFC 3161 prueba ante terceros la fecha de la reserva: "
                "se pide sobre el manifiesto (.json) y cubre todas sus obras. Usa internet y "
                "envía solo la huella SHA-256, nunca los libros. El registro público es un "
                "sitio web con una ficha por obra, que usted publica donde quiera."
            )
        )
        self.combo_tsa = QComboBox()
        for code, label in (
            ("freetsa", "FreeTSA"),
            ("digicert", "DigiCert"),
            ("sectigo", "Sectigo"),
        ):
            self.combo_tsa.addItem(label, code)
        pform.addRow("Autoridad de sellado:", self.combo_tsa)
        self.btn_timestamp = QPushButton("Sellar en el tiempo un manifiesto…")
        self.btn_timestamp.clicked.connect(self._timestamp_manifest)
        pform.addRow("", self.btn_timestamp)
        self.registry_url_edit = QLineEdit()
        self.registry_url_edit.setPlaceholderText(
            "https://editorial.ejemplo.edu/registro/ (opcional)"
        )
        pform.addRow("URL del registro:", self.registry_url_edit)
        self.btn_registry = QPushButton("Generar registro público…")
        self.btn_registry.setObjectName("primary")
        self.btn_registry.clicked.connect(self._build_registry)
        pform.addRow("", self.btn_registry)
        layout.addWidget(proof)

        onix = QGroupBox("ONIX 3.0 para distribuidores y librerías")
        oform = QFormLayout(onix)
        oform.addRow(
            _hint(
                "Añade la restricción de minería de textos y datos (EpubUsageType 11) a cada "
                "producto digital de su ONIX, sin tocar nada más, o crea un ONIX mínimo desde "
                "una carpeta de PDF y EPUB."
            )
        )
        row = QHBoxLayout()
        self.btn_onix_add = QPushButton("Añadir la reserva a mi ONIX…")
        self.btn_onix_add.clicked.connect(self._onix_add)
        self.btn_onix_build = QPushButton("Crear ONIX desde una carpeta…")
        self.btn_onix_build.clicked.connect(self._onix_build)
        row.addWidget(self.btn_onix_add)
        row.addWidget(self.btn_onix_build)
        row.addStretch(1)
        oform.addRow(row)
        layout.addWidget(onix)
        layout.addStretch(1)
        return tab

    def _build_match_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        group = QGroupBox("¿Este archivo es uno de mis libros?")
        form = QFormLayout(group)
        form.addRow(
            _hint(
                "Compara un archivo encontrado (en internet, en un conjunto de datos de "
                "entrenamiento…) con su catálogo. Reconoce copias renombradas o sin metadatos, "
                "extractos y libros dentro de volcados de texto (.txt, .jsonl). Use el "
                "manifiesto .json que generó en la pestaña Catálogo. Sin conexión."
            )
        )
        cat_row = QHBoxLayout()
        self.match_catalog_edit = QLineEdit()
        self.match_catalog_edit.setPlaceholderText("Manifiesto .json del catálogo")
        btn_cat = QPushButton("Elegir…")
        btn_cat.clicked.connect(self._choose_match_catalog)
        cat_row.addWidget(self.match_catalog_edit, stretch=1)
        cat_row.addWidget(btn_cat)
        form.addRow("Catálogo:", cat_row)
        self.btn_match = QPushButton("Elegir archivo y comparar…")
        self.btn_match.setObjectName("primary")
        self.btn_match.clicked.connect(self._run_match)
        form.addRow("", self.btn_match)
        layout.addWidget(group)
        self.match_output = QPlainTextEdit()
        self.match_output.setReadOnly(True)
        self.match_output.setPlaceholderText("Aquí aparecerá el resultado de la comparación.")
        layout.addWidget(self.match_output, stretch=1)
        return tab

    def _build_hub_tab(self) -> QWidget:
        from tdmseal.iscc.hub import HUB_NAMES

        tab = QWidget()
        layout = QVBoxLayout(tab)
        ident = QGroupBox("1. Identidad de la editorial (una sola vez)")
        iform = QFormLayout(ident)
        iform.addRow(
            _hint(
                "Para declarar en la red ISCC sin intermediarios, la editorial firma con su "
                "propia clave. Se crea aquí y se guarda en este equipo; usted publica el "
                "archivo did.json en su dominio, en /.well-known/did.json."
            )
        )
        self.hub_domain_edit = QLineEdit()
        self.hub_domain_edit.setPlaceholderText("editorial.ejemplo.edu")
        iform.addRow("Dominio:", self.hub_domain_edit)
        self.btn_hub_keygen = QPushButton("Crear clave y did.json…")
        self.btn_hub_keygen.clicked.connect(self._hub_keygen)
        iform.addRow("", self.btn_hub_keygen)
        self.hub_identity_label = _hint("")
        iform.addRow(self.hub_identity_label)
        layout.addWidget(ident)

        decl = QGroupBox("2. Declarar obras")
        dform = QFormLayout(decl)
        dform.addRow(
            _hint(
                "Cada declaración queda registrada en un hub público con fecha y un recibo "
                "firmado por el hub. Usa internet: se envían el ISCC, las huellas y la firma, "
                "nunca el archivo. Pruebe primero en la red de pruebas."
            )
        )
        self.combo_hub = QComboBox()
        for hub_id, name in HUB_NAMES.items():
            self.combo_hub.addItem(name, hub_id)
        dform.addRow("Hub:", self.combo_hub)
        self.combo_network = QComboBox()
        self.combo_network.addItem("Red de pruebas (testnet)", "testnet")
        self.combo_network.addItem("Red real (mainnet)", "mainnet")
        dform.addRow("Red:", self.combo_network)
        self.btn_hub_declare = QPushButton("Elegir archivos y declarar…")
        self.btn_hub_declare.setObjectName("primary")
        self.btn_hub_declare.clicked.connect(self._hub_declare)
        dform.addRow("", self.btn_hub_declare)
        layout.addWidget(decl)
        self.hub_output = QPlainTextEdit()
        self.hub_output.setReadOnly(True)
        layout.addWidget(self.hub_output, stretch=1)
        self._refresh_hub_identity()
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
            # JSON por defecto: lo necesitan el registro público y la búsqueda de copias.
            str(Path(folder) / "catalogo_tdm.json"),
            "JSON (*.json);;CSV para Excel (*.csv)",
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

    def _start_task(self, fn, on_done, button: QPushButton, message: str) -> None:
        """Corre `fn` en otro hilo; `on_done(resultado o excepción)` en la interfaz."""
        button.setEnabled(False)
        self.status_label.setText(message)
        worker = _TaskWorker(fn)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def done(result: object) -> None:
            button.setEnabled(True)
            on_done(result)

        worker.finished.connect(done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        self._thread, self._worker = thread, worker
        thread.start()

    def _open_file(self, title: str, filters: str) -> Path | None:
        path, _ = QFileDialog.getOpenFileName(
            self, title, "", filters, options=QFileDialog.Option.DontUseNativeDialog
        )
        return Path(path) if path else None

    def _save_file(self, title: str, suggested: Path, filters: str) -> Path | None:
        path, _ = QFileDialog.getSaveFileName(
            self, title, str(suggested), filters, options=QFileDialog.Option.DontUseNativeDialog
        )
        return Path(path) if path else None

    def _pick_folder(self, title: str) -> Path | None:
        folder = QFileDialog.getExistingDirectory(
            self, title, options=QFileDialog.Option.DontUseNativeDialog
        )
        return Path(folder) if folder else None

    # ---- prueba de fecha, registro y ONIX ------------------------------------

    def _timestamp_manifest(self) -> None:
        from tdmseal.timestamp import create_timestamp, resolve_tsa

        path = self._open_file("Manifiesto a sellar", "Manifiesto (*.json *.csv);;Todos (*)")
        if path is None:
            return
        url = resolve_tsa(self.combo_tsa.currentData())
        answer = QMessageBox.question(
            self,
            "Usar internet",
            f"Se enviará a {url} solo la huella SHA-256 de {path.name} (no su contenido) para "
            "obtener un sello de tiempo. ¿Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def done(result: object) -> None:
            if isinstance(result, Exception):
                self.status_label.setText(f"No se pudo obtener el sello de tiempo: {result}")
            else:
                self.status_label.setText(
                    f"Sellado el {result.fecha_sellada_utc} (UTC) por {result.tsa}: "
                    f"{path.name}.tsr y {path.name}.tsr.json."
                )

        self._start_task(
            lambda: create_timestamp(path, url), done, self.btn_timestamp, "Pidiendo el sello…"
        )

    def _build_registry(self) -> None:
        from tdmseal.registry import build_registry

        manifest = self._open_file("Manifiesto .json del catálogo", "JSON (*.json)")
        if manifest is None:
            return
        folder = self._pick_folder("Carpeta donde generar el registro")
        if folder is None:
            return
        try:
            result = build_registry(manifest, folder, self.registry_url_edit.text().strip() or None)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "No se pudo generar el registro", str(exc))
            return
        proof = "con sello de tiempo" if result.timestamped else "sin sello de tiempo"
        self.status_label.setText(
            f"Registro generado ({result.works} obras, {proof}) en {folder}. Abra index.html "
            "para revisarlo y publique la carpeta en su sitio."
        )

    def _onix_add(self) -> None:
        from tdmseal.onix import add_tdm_to_onix

        src = self._open_file("ONIX 3.0 de la editorial", "ONIX (*.xml *.onix);;Todos (*)")
        if src is None:
            return
        out = self._save_file(
            "Guardar ONIX con la reserva",
            src.with_name(f"{src.stem}_TDM{src.suffix}"),
            "XML (*.xml)",
        )
        if out is None:
            return
        if out.resolve() == src.resolve():
            QMessageBox.warning(self, "ONIX", "Elija un archivo distinto del original.")
            return
        reservation = 1 if self.radio_reserved.isChecked() else 0
        try:
            data, change = add_tdm_to_onix(src.read_bytes(), reservation)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "No se pudo procesar el ONIX", str(exc))
            return
        out.write_bytes(data)
        self.status_label.setText(f"ONIX: {change.summary()} -> {out}")

    def _onix_build(self) -> None:
        from tdmseal.onix import build_onix

        folder = self._pick_folder("Carpeta con PDF y EPUB")
        if folder is None:
            return
        out = self._save_file("Guardar ONIX", folder / "catalogo_onix.xml", "XML (*.xml)")
        if out is None:
            return
        reservation = 1 if self.radio_reserved.isChecked() else 0
        sender = self.publisher_name_edit.text().strip() or None

        def work():
            docs = iter_documents(folder, recursive=True)
            rows = build_manifest(docs, base_dir=folder).rows
            out.write_bytes(build_onix(rows, reservation, sender))
            return len(rows)

        def done(result: object) -> None:
            if isinstance(result, Exception):
                self.status_label.setText(f"No se pudo crear el ONIX: {result}")
            else:
                self.status_label.setText(f"ONIX con {result} obra(s): {out}")

        self._start_task(work, done, self.btn_onix_build, "Creando el ONIX…")

    # ---- buscar copias ---------------------------------------------------------

    def _choose_match_catalog(self) -> None:
        path = self._open_file("Manifiesto .json o registro.json", "JSON (*.json)")
        if path is not None:
            self.match_catalog_edit.setText(str(path))

    def _run_match(self) -> None:
        from tdmseal.match import match_file

        catalog = Path(self.match_catalog_edit.text().strip())
        if not catalog.is_file():
            QMessageBox.warning(self, "Falta el catálogo", "Elija primero el manifiesto .json.")
            return
        target = self._open_file(
            "Archivo a comparar",
            "Documentos y texto (*.pdf *.epub *.txt *.jsonl *.json *.md *.html *.htm *.xml)",
        )
        if target is None:
            return

        def done(result: object) -> None:
            if isinstance(result, Exception):
                self.match_output.setPlainText(f"No se pudo comparar: {result}")
                return
            if not result:
                self.match_output.setPlainText(
                    f"{target.name}: no corresponde a ninguna obra del catálogo."
                )
                return
            lines = [f"{target.name}:"]
            for m in result:
                reserva = {1: "reservado", 0: "autorizado"}.get(m.reservation, "sin declaración")
                lines.append(f"• {m.describe()} — TDM {reserva}")
                if m.policy:
                    lines.append(f"  Política: {m.policy}")
            self.match_output.setPlainText("\n".join(lines))

        self._start_task(lambda: match_file(target, catalog), done, self.btn_match, "Comparando…")

    # ---- red ISCC ----------------------------------------------------------------

    def _refresh_hub_identity(self) -> None:
        from tdmseal.iscc.hub import HubError, did_url, key_path, load_key

        try:
            key = load_key()
        except (HubError, OSError, ValueError, KeyError):
            self.hub_identity_label.setText(f"Aún no hay clave (se guardará en {key_path()}).")
            return
        self.hub_identity_label.setText(
            f"Identidad: {key.controller}. El did.json debe estar publicado en "
            f"{did_url(key.controller)}."
        )

    def _hub_keygen(self) -> None:
        import json as _json

        from tdmseal.iscc.hub import HubError, did_url, generate_key, key_path, save_key

        domain = self.hub_domain_edit.text().strip()
        try:
            key = generate_key(domain)
        except ValueError as exc:
            QMessageBox.warning(self, "Dominio no válido", str(exc))
            return
        if key_path().exists():
            QMessageBox.warning(
                self,
                "Ya hay una clave",
                f"Ya existe una clave en {key_path()}. No se reemplaza desde aquí: las "
                "declaraciones hechas con ella dejarían de poder borrarse.",
            )
            return
        folder = self._pick_folder("Carpeta donde dejar did.json")
        if folder is None:
            return
        try:
            save_key(key)
        except HubError as exc:
            QMessageBox.warning(self, "No se pudo guardar la clave", str(exc))
            return
        (folder / "did.json").write_text(
            _json.dumps(key.did_document(), indent=2) + "\n", encoding="utf-8"
        )
        self._refresh_hub_identity()
        self.hub_output.setPlainText(
            f"Clave creada y guardada en {key_path()} (no la comparta).\n"
            f"Publique {folder / 'did.json'} en {did_url(key.controller)}\n"
            "Después podrá declarar obras."
        )

    def _hub_declare(self) -> None:
        from tdmseal.iscc.hub import (
            HUB_NAMES,
            HubError,
            check_did_published,
            declare_file,
            hub_url,
            load_key,
        )

        try:
            key = load_key()
        except (HubError, OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, "Falta la identidad", str(exc))
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Obras a declarar",
            "",
            "PDF y EPUB (*.pdf *.epub)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not paths:
            return
        hub_id = self.combo_hub.currentData()
        network = self.combo_network.currentData()
        _, url = hub_url(hub_id, network)
        answer = QMessageBox.question(
            self,
            "Usar internet",
            f"Se declararán {len(paths)} obra(s) en {HUB_NAMES[hub_id]} ({url}). Se envían el "
            "ISCC, las huellas y la firma de la editorial; nunca los archivos. ¿Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def work():
            check_did_published(key)
            lines = []
            for p in paths:
                try:
                    record, out = declare_file(Path(p), key, hub_id, network)
                    lines.append(f"✔ {Path(p).name}: {record['iscc_id']} ({out.name})")
                except (HubError, ValueError, OSError) as exc:
                    lines.append(f"✖ {Path(p).name}: {exc}")
            return lines

        def done(result: object) -> None:
            if isinstance(result, Exception):
                self.hub_output.setPlainText(f"No se pudo declarar: {result}")
            else:
                self.hub_output.setPlainText("\n".join(result))
            self.status_label.setText("Declaración terminada.")

        self._start_task(work, done, self.btn_hub_declare, "Declarando en la red ISCC…")

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
