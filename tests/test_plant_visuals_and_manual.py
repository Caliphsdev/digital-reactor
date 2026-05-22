import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap

from core.plant_catalog import DEFAULT_PLANTS
from ui.help_screen import TOPICS
from ui.plants_screen import PlantProcessOverview
from simulation.plant_model import PlantTwinInputs, run_plant_twin


def _app():
    return QApplication.instance() or QApplication([])


def _plant(slug):
    return next(item for item in DEFAULT_PLANTS if item["slug"] == slug)


class PlantManualTests(unittest.TestCase):
    def test_manual_documents_real_plant_scientific_twins(self):
        titles = [title for title, _ in TOPICS]
        self.assertIn("Real Plant Scientific Twins", titles)

        html = dict(TOPICS)["Real Plant Scientific Twins"]
        for required in [
            "Scientific Twin",
            "Daspoort",
            "Zeekoegat",
            "Phola",
            "PFAS",
            "HRT",
            "SRT",
            "MLSS",
            "calibration",
        ]:
            self.assertIn(required, html)


class PlantProcessDiagramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_visual_uses_catalog_process_order(self):
        for plant in DEFAULT_PLANTS:
            diagram = PlantProcessOverview(plant, plant["units"], plant["sampling_points"])
            expected = [unit.name for unit in plant["units"]]
            self.assertEqual(expected, diagram.ordered_unit_names())

    def test_visual_uses_catalog_sampling_order(self):
        for plant in DEFAULT_PLANTS:
            diagram = PlantProcessOverview(plant, plant["units"], plant["sampling_points"])
            expected = [point.code for point in plant["sampling_points"]]
            self.assertEqual(expected, diagram.ordered_sampling_codes())

    def test_visual_categories_distinguish_major_unit_types(self):
        self.assertEqual("preliminary", PlantProcessOverview.category_for_unit("screening_grit"))
        self.assertEqual("primary", PlantProcessOverview.category_for_unit("primary_settling"))
        self.assertEqual("anaerobic", PlantProcessOverview.category_for_unit("anaerobic"))
        self.assertEqual("anoxic", PlantProcessOverview.category_for_unit("anoxic"))
        self.assertEqual("aerobic", PlantProcessOverview.category_for_unit("aerobic"))
        self.assertEqual("clarification", PlantProcessOverview.category_for_unit("secondary_clarifier"))
        self.assertEqual("disinfection", PlantProcessOverview.category_for_unit("disinfection"))
        self.assertEqual("pond", PlantProcessOverview.category_for_unit("reed_bed"))
        self.assertEqual("biofilm", PlantProcessOverview.category_for_unit("trickling_filter"))
        self.assertEqual("sludge", PlantProcessOverview.category_for_unit("sludge_handling"))

    def test_visual_layout_grows_for_narrow_responsive_widths(self):
        phola = _plant("phola")
        diagram = PlantProcessOverview(phola, phola["units"], phola["sampling_points"])
        wide = diagram._layout_for_width(1100)
        narrow = diagram._layout_for_width(360)

        self.assertEqual("pond_biofilm_wetland", wide["layout_type"])
        self.assertEqual("phola_vertical", narrow["layout_type"])
        self.assertEqual(1, narrow["columns"])
        self.assertGreater(narrow["required_height"], wide["required_height"])

    def test_each_plant_uses_the_correct_clear_layout(self):
        expectations = {
            "daspoort": "bnr_lanes",
            "zeekoegat": "bnr_lanes",
            "phola": "pond_biofilm_wetland",
        }
        for plant in DEFAULT_PLANTS:
            overview = PlantProcessOverview(plant, plant["units"], plant["sampling_points"])
            self.assertEqual(expectations[plant["slug"]], overview._layout_for_width(1100)["layout_type"])

    def test_daspoort_research_trickling_filter_is_context_not_mainline(self):
        plant = _plant("daspoort")
        overview = PlantProcessOverview(plant, plant["units"], plant["sampling_points"])
        context_names = [unit.name for unit in overview._context_units()]
        main_names = [unit.name for unit in overview._main_units()]

        self.assertIn("Heritage Trickling Filters", context_names)
        self.assertNotIn("Heritage Trickling Filters", main_names)

    def test_animation_timer_pauses_on_hide_and_resumes_on_show(self):
        plant = _plant("zeekoegat")
        overview = PlantProcessOverview(plant, plant["units"], plant["sampling_points"])
        overview.show()
        self.app.processEvents()
        self.assertTrue(overview.animation_active())

        overview.hide()
        self.app.processEvents()
        self.assertFalse(overview.animation_active())

        overview.show()
        self.app.processEvents()
        self.assertTrue(overview.animation_active())
        overview.hide()

    def test_zeekoegat_mode_updates_visual_badge_state(self):
        plant = _plant("zeekoegat")
        overview = PlantProcessOverview(plant, plant["units"], plant["sampling_points"])
        overview.set_bnr_mode("Modified UCT")
        self.assertEqual("Modified UCT", overview._bnr_mode)

    def test_pfas_fate_summary_distinguishes_transfer_paths(self):
        plant = _plant("daspoort")
        overview = PlantProcessOverview(plant, plant["units"], plant["sampling_points"])
        inputs = PlantTwinInputs(
            plant_slug="daspoort",
            flow_mld=38.0,
            hrt_hours=12.0,
            srt_days=30.0,
            mlss_mgl=3000.0,
            do_mgl=1.5,
            temp_c=22.0,
            ph=7.5,
            recycle_ratio=4.0,
            organic_loading=0.0,
            nitrogen_loading=0.0,
            inf_cod_mgl=350.0,
            inf_nh4_mgl=45.0,
            inf_tn_mgl=70.0,
            inf_tp_mgl=8.0,
            inf_pfas_ugl=50.0,
            pfas_type="short-chain",
        )
        overview.set_results(inputs, run_plant_twin(inputs))
        summary = overview.pfas_fate_summary()

        self.assertIn("effluent", summary)
        self.assertIn("sludge/solids", summary)
        self.assertIn("unresolved", summary)
        self.assertIn("not destruction", summary)

    def test_each_plant_visual_renders_offscreen_at_desktop_and_narrow_widths(self):
        for plant in DEFAULT_PLANTS:
            overview = PlantProcessOverview(plant, plant["units"], plant["sampling_points"])
            for width, height in [(1100, 720), (380, 980)]:
                overview.resize(width, height)
                pixmap = QPixmap(width, height)
                overview.render(pixmap)
                self.assertFalse(pixmap.isNull())


if __name__ == "__main__":
    unittest.main()
