# Console-mode init. No sys.path setup needed: FreeCAD's module loader
# already inserts this directory into sys.path before executing this file
# (confirmed in src/App/FreeCADInit.py, RunInitPy/processMetadataFile).
# This file exists so the workbench is discovered even without the GUI
# (batch use, FreeCADCmd, future tolerance-analysis frontend).
