import os

import FreeCAD
import FreeCADGui as Gui

from connection_detection import DetectionConfig, detect_connections, detect_connections_in_document

from .task_panel_candidates import TaskPanelCandidates

_ICON_PATH = os.path.join(os.path.dirname(__file__), "resources", "icons", "ConnectionDetection.svg")


class CmdDetectConnections:
    def GetResources(self):
        return {
            "Pixmap": _ICON_PATH,
            "MenuText": "Detect Connections",
            "ToolTip": "Find part-to-part connection candidates in the active document",
        }

    def IsActive(self):
        return Gui.ActiveDocument is not None

    def Activated(self):
        doc = Gui.ActiveDocument.Document
        config = DetectionConfig()
        graph = detect_connections_in_document(doc, config)

        if graph.is_single_body():
            FreeCAD.Console.PrintMessage(
                "connection_detection: single-body document, nothing to detect.\n"
            )
            return
        if not graph.candidates:
            FreeCAD.Console.PrintMessage(
                f"connection_detection: {len(graph.parts)} parts, no candidates "
                "within the configured tolerance band.\n"
            )
            return

        panel = TaskPanelCandidates(graph, doc)
        Gui.Control.showDialog(panel)


def register_commands():
    Gui.addCommand("CD_DetectConnections", CmdDetectConnections())
