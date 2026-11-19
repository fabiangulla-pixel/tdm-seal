"""GUI de TDM Seal (PySide6), sobre el mismo núcleo que usa la CLI.

Sigue el mockup de la sección 12 de la especificación: cuatro decisiones
principales (reservar TDM, política, archivo/carpeta, salida) y todo lo
demás inferido automáticamente del PDF (sección 33/34).
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
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tdmseal.appconfig import AppDefaults, load_defaults, save_defaults
from tdmseal.config import SealConfig
from tdmseal.discovery import iter_pdfs
from tdmseal.errors import TDMSealError
from tdmseal.iscc.content import compute_content_iscc, content_extra_available
from tdmseal.models import PublisherInfo, TDMPolicy
from tdmseal.pdf.inspector import inspect_pdf
from tdmseal.policy.builder import PolicyOptions, write_policy_artifacts
from tdmseal.reporting.json_report import write_report
from tdmseal.seal import seal_pdf

COLUMNS = ["Archivo", "PDF/A", "Firmado", "Cifrado", "TDM actual", "Estado", "ISCC"]
ISCC_COL = 6

_OK_COLOR = QColor("#1e7e34")
_WARN_COLOR = QColor("#b8860b")
_ERROR_COLOR = QColor("#b02a2a")


@dataclass
class _RowState:
    path: Path
    signed: bool = False
    encrypted: bool = False


class _AuditWorker(QObject):
    file_done = Signal(int, object)  # índice de fila, PDFInfo | Exception
    iscc_done = Signal(int, object)  # índice de fila, ContentIscc | Exception
    finished = Signal()

    def __init__(self, paths: list[Path], with_iscc: bool = False) -> None:
        super().__init__()
        self._paths = paths
        self._with_iscc = with_iscc

    def run(self) -> None:
        for i, path in enumerate(self._paths):
            try:
                info = inspect_pdf(path)
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
            result = seal_pdf(path, self._config)
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TDM Seal — declaraciones TDMRep para PDF editoriales")
        self.resize(880, 600)

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

        title = QLabel("Derechos de minería de textos y datos")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        publisher_group = QGroupBox("Editorial / titular de derechos")
        publisher_form = QVBoxLayout(publisher_group)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Nombre:"))
        self.publisher_name_edit = QLineEdit()
        row1.addWidget(self.publisher_name_edit)
        row1.addWidget(QLabel("Sigla:"))
        self.publisher_acronym_edit = QLineEdit()
        self.publisher_acronym_edit.setMaximumWidth(100)
        row1.addWidget(self.publisher_acronym_edit)
        publisher_form.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Sitio web:"))
        self.publisher_website_edit = QLineEdit()
        row2.addWidget(self.publisher_website_edit)
        row2.addWidget(QLabel("Correo de derechos:"))
        self.publisher_email_edit = QLineEdit()
        row2.addWidget(self.publisher_email_edit)
        publisher_form.addLayout(row2)
        row3 = QHBoxLayout()
        self.btn_save_defaults = QPushButton("Guardar como valores por defecto")
        self.chk_require_compensation = QCheckBox("Exigir compensación económica")
        self.btn_build_policy = QPushButton("Generar artefactos de política…")
        row3.addWidget(self.btn_save_defaults)
        row3.addWidget(self.chk_require_compensation)
        row3.addWidget(self.btn_build_policy)
        row3.addStretch(1)
        publisher_form.addLayout(row3)
        layout.addWidget(publisher_group)

        policy_group = QGroupBox("Reserva TDM")
        policy_layout = QVBoxLayout(policy_group)
        self.radio_reserved = QRadioButton("Reservados (recomendado)")
        self.radio_not_reserved = QRadioButton("No reservados")
        self.radio_reserved.setChecked(True)
        policy_layout.addWidget(self.radio_reserved)
        policy_layout.addWidget(self.radio_not_reserved)

        policy_row = QHBoxLayout()
        policy_row.addWidget(QLabel("Política TDM (URL, opcional):"))
        self.policy_url_edit = QLineEdit()
        self.policy_url_edit.setPlaceholderText("https://editorial.example.edu/tdm/policy.jsonld")
        policy_row.addWidget(self.policy_url_edit)
        policy_layout.addLayout(policy_row)
        layout.addWidget(policy_group)

        select_row = QHBoxLayout()
        self.btn_select_file = QPushButton("Seleccionar PDF…")
        self.btn_select_folder = QPushButton("Seleccionar carpeta…")
        self.chk_recursive = QCheckBox("Incluir subcarpetas")
        self.chk_iscc = QCheckBox("Calcular ISCC (huella del contenido)")
        self.chk_iscc.setToolTip(
            "Calcula el ISCC (ISO 24138) de cada PDF y lo guarda en sus metadatos al "
            "sellar. El código de contenido se calcula sobre el texto y no cambia al "
            "sellar. Tarda un poco más en libros largos."
        )
        self.chk_iscc.setChecked(True)
        if not content_extra_available():
            self.chk_iscc.setToolTip(
                self.chk_iscc.toolTip() + "\n\nFalta el extra 'tdm-seal[iscc]': solo se "
                "calcularán los códigos de metadatos y de bytes, no el de contenido."
            )
        select_row.addWidget(self.btn_select_file)
        select_row.addWidget(self.btn_select_folder)
        select_row.addWidget(self.chk_recursive)
        select_row.addWidget(self.chk_iscc)
        select_row.addStretch(1)
        layout.addLayout(select_row)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(ISCC_COL, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table, stretch=1)

        action_row = QHBoxLayout()
        self.btn_audit = QPushButton("AUDITAR")
        self.btn_apply = QPushButton("APLICAR TDM")
        self.btn_apply.setEnabled(False)
        self.btn_open_folder = QPushButton("Abrir carpeta")
        self.btn_open_folder.setEnabled(False)
        action_row.addWidget(self.btn_audit)
        action_row.addWidget(self.btn_apply)
        action_row.addStretch(1)
        action_row.addWidget(self.btn_open_folder)
        layout.addLayout(action_row)

        self.status_label = QLabel("Selecciona uno o varios PDF para comenzar.")
        layout.addWidget(self.status_label)

        self.btn_select_file.clicked.connect(self._select_file)
        self.btn_select_folder.clicked.connect(self._select_folder)
        self.btn_audit.clicked.connect(self._run_audit)
        self.btn_apply.clicked.connect(self._run_seal)
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        self.btn_save_defaults.clicked.connect(self._save_defaults)
        self.btn_build_policy.clicked.connect(self._build_policy)

        self._apply_defaults(load_defaults())

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

    def _current_publisher(self) -> PublisherInfo:
        return PublisherInfo(
            name=self.publisher_name_edit.text().strip() or None,
            acronym=self.publisher_acronym_edit.text().strip() or None,
            website=self.publisher_website_edit.text().strip() or None,
            rights_email=self.publisher_email_edit.text().strip() or None,
        )

    def _save_defaults(self) -> None:
        defaults = AppDefaults(
            publisher=self._current_publisher(),
            reservation=1 if self.radio_reserved.isChecked() else 0,
            policy_url=self.policy_url_edit.text().strip() or None,
        )
        save_defaults(defaults)
        self.status_label.setText("Valores por defecto guardados.")

    def _build_policy(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Carpeta de salida para la política TDM",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not folder:
            return

        options = PolicyOptions(require_compensation=self.chk_require_compensation.isChecked())
        try:
            paths = write_policy_artifacts(Path(folder), self._current_publisher(), options)
        except ValueError as exc:
            QMessageBox.warning(self, "Faltan datos de la editorial", str(exc))
            return

        self.status_label.setText(f"Política generada en {folder}: {', '.join(paths)}")

    # ---- selección de archivos ------------------------------------------

    # DontUseNativeDialog: en el .exe de PyInstaller, el dialogo nativo de
    # Windows (COM IFileOpenDialog) nunca aparece y se queda colgado sin
    # error — problema conocido de PySide6 congelado. El dialogo propio de
    # Qt no depende de COM y funciona igual en el .exe que sin congelar.
    def _select_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar PDF",
            "",
            "PDF (*.pdf)",
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
            pdfs = iter_pdfs(Path(folder), recursive=self.chk_recursive.isChecked())
            self._load_paths(pdfs)

    def _load_paths(self, paths: list[Path]) -> None:
        self._rows = [_RowState(path=p) for p in paths]
        self.table.setRowCount(len(paths))
        for row, state in enumerate(self._rows):
            self.table.setItem(row, 0, QTableWidgetItem(str(state.path)))
            for col in range(1, len(COLUMNS)):
                self.table.setItem(row, col, QTableWidgetItem(""))
        self.btn_apply.setEnabled(bool(paths))
        self.status_label.setText(f"{len(paths)} archivo(s) cargados. Audita o aplica TDM.")
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
            self._set_row_text(row, 1, "—")
            self._set_row_text(row, 2, "—")
            self._set_row_text(row, 3, "—")
            self._set_row_text(row, 4, "—")
            self._set_row_text(row, 5, str(result), color=_ERROR_COLOR)
            return

        info = result
        self._rows[row].signed = info.signed
        self._rows[row].encrypted = info.encrypted

        pdfa = "no"
        if info.pdfa_part is not None:
            pdfa = f"A-{info.pdfa_part}{(info.pdfa_conformance or '').lower()}"
        self._set_row_text(row, 1, pdfa)
        self._set_row_text(row, 2, "sí" if info.signed else "no")
        self._set_row_text(row, 3, "sí" if info.encrypted else "no")
        self._set_row_text(row, 4, str(info.tdm.reservation) if info.tdm.present else "—")

        if info.signed:
            self._set_row_text(row, 5, "firmado — no se modificará", color=_WARN_COLOR)
        elif info.encrypted:
            self._set_row_text(row, 5, "cifrado — no se modificará", color=_WARN_COLOR)
        else:
            self._set_row_text(row, 5, "listo", color=_OK_COLOR)

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

        config = SealConfig(policy=policy, compute_iscc=self.chk_iscc.isChecked())
        publisher = self._current_publisher()
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
            self._set_row_text(row, 5, f"sellado -> {result.output_path.name}", color=_OK_COLOR)
        elif result.status == "skipped":
            self._set_row_text(row, 5, f"omitido ({result.reason_code})", color=_WARN_COLOR)
        else:
            self._set_row_text(row, 5, f"error ({result.reason_code})", color=_ERROR_COLOR)

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


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
