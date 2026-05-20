import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread

from ui.plants_screen import PlantCalibrationWorker, PlantImportWorker


class ResponsivenessStructureTests(unittest.TestCase):
    def test_daspoort_import_and_calibration_use_background_threads(self):
        self.assertTrue(issubclass(PlantImportWorker, QThread))
        self.assertTrue(issubclass(PlantCalibrationWorker, QThread))
        self.assertTrue(hasattr(PlantImportWorker, "result_ready"))
        self.assertTrue(hasattr(PlantCalibrationWorker, "result_ready"))


if __name__ == "__main__":
    unittest.main()
