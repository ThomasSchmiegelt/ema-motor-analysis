class ConnectionDetectionWorkbench(Workbench):
    "Connection Detection workbench: geometric connection candidates for multi-body FEM/tolerance analysis"

    MenuText = "Connection Detection"
    ToolTip = "Detect part-to-part connection candidates in imported assemblies"

    def __init__(self):
        # Import (and the path derived from it) must happen inside a method,
        # not at the exec'd script's top level or in the class body: FreeCAD
        # runs Init.py/InitGui.py via exec(code, globals(), locals()) inside
        # a helper function, so top-level names land in that call's locals()
        # dict, not the module's real globals() -- which is exactly what a
        # class *body* falls back to (skipping locals()) once its own
        # namespace search misses. A method's own `import` statement isn't
        # affected: it's a normal local binding in that method's frame.
        import os

        import connection_detection

        repo_root = os.path.dirname(os.path.dirname(connection_detection.__file__))
        self.__class__.Icon = os.path.join(
            repo_root, "connection_detection_gui", "resources", "icons", "ConnectionDetection.svg"
        )

    def Initialize(self):
        import connection_detection_gui  # noqa: F401  (registers commands via FreeCADGui.addCommand)

        commands = ["CD_DetectConnections"]
        self.appendToolbar("Connection Detection", commands)
        self.appendMenu("Connection Detection", commands)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(ConnectionDetectionWorkbench())
