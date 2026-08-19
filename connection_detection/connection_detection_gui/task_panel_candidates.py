"""Task panel listing connection candidates for manual confirm/reject.

Deliberately does not auto-decide anything (matches the "candidate list,
no automatic determination" requirement): every row starts Undecided, and
only rows the user explicitly sets to Accept become part of
graph.confirmed_connections() when the panel is closed.
"""
from __future__ import annotations

import FreeCAD
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from connection_detection.graph_export import apply_fem_constraints, write_json

_COLUMNS = ["Part A", "Part B", "Type", "Vorschlag", "Abstand [mm]", "Durchdringung", "Entscheidung"]
_DECISIONS = ["Unentschieden", "Annehmen", "Ablehnen"]


class TaskPanelCandidates:
    def __init__(self, graph, doc):
        self.graph = graph
        self.doc = doc

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("Verbindungskandidaten")
        layout = QtWidgets.QVBoxLayout(self.form)

        info = QtWidgets.QLabel(
            f"{len(graph.parts)} Bauteile, {len(graph.candidates)} Kandidaten. "
            "Zeile anklicken hebt die beteiligten Flächen im 3D-View hervor."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QtWidgets.QTableWidget(len(graph.candidates), len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self._decision_boxes: list[QtWidgets.QComboBox] = []
        self._populate_table()

        self.table.currentCellChanged.connect(self._on_row_selected)

        button_row = QtWidgets.QHBoxLayout()
        accept_all_btn = QtWidgets.QPushButton("Alle anzeigen: Annehmen")
        accept_all_btn.clicked.connect(lambda: self._set_all_decisions("Annehmen"))
        reject_all_btn = QtWidgets.QPushButton("Alle anzeigen: Ablehnen")
        reject_all_btn.clicked.connect(lambda: self._set_all_decisions("Ablehnen"))
        button_row.addWidget(accept_all_btn)
        button_row.addWidget(reject_all_btn)
        layout.addLayout(button_row)

    def _populate_table(self):
        for row, candidate in enumerate(self.graph.candidates):
            values = [
                self.graph.parts[candidate.part_a].label,
                self.graph.parts[candidate.part_b].label,
                candidate.surface_type,
                candidate.proposed_type,
                f"{candidate.distance:.4f}",
                "ja" if candidate.penetration else "nein",
            ]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                self.table.setItem(row, col, item)

            combo = QtWidgets.QComboBox()
            combo.addItems(_DECISIONS)
            combo.currentIndexChanged.connect(self._make_decision_handler(row))
            self.table.setCellWidget(row, len(_COLUMNS) - 1, combo)
            self._decision_boxes.append(combo)

        self.table.resizeColumnsToContents()

    def _make_decision_handler(self, row: int):
        def handler(index: int):
            candidate = self.graph.candidates[row]
            candidate.confirmed = {0: None, 1: True, 2: False}[index]
        return handler

    def _set_all_decisions(self, decision: str):
        index = _DECISIONS.index(decision)
        for combo in self._decision_boxes:
            combo.setCurrentIndex(index)

    def _on_row_selected(self, row: int, *_args):
        Gui.Selection.clearSelection()
        if row < 0 or row >= len(self.graph.candidates):
            return
        candidate = self.graph.candidates[row]
        part_a = self.graph.parts[candidate.part_a]
        part_b = self.graph.parts[candidate.part_b]
        Gui.Selection.addSelection(part_a.doc_name, part_a.doc_object_name, candidate.face_a)
        Gui.Selection.addSelection(part_b.doc_name, part_b.doc_object_name, candidate.face_b)

    def getStandardButtons(self):
        return int(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)

    def accept(self):
        apply_fem_constraints(self.graph.candidates)
        confirmed = self.graph.confirmed_connections()

        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self.form, "Verbindungsgraph speichern", "", "JSON (*.json)"
        )
        if path:
            write_json(self.graph, path)

        FreeCAD.Console.PrintMessage(
            f"connection_detection: {len(confirmed)} von {len(self.graph.candidates)} "
            "Kandidaten bestätigt.\n"
        )
        Gui.Selection.clearSelection()
        Gui.Control.closeDialog()
        return True

    def reject(self):
        Gui.Selection.clearSelection()
        Gui.Control.closeDialog()
        return True
