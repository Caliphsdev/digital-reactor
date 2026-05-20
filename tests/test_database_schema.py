import unittest

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.migrations import CURRENT_SCHEMA_VERSION, run_migrations
from core.models import Base, Plant, PlantCalibration, PlantMonitoringReading
from core.plant_catalog import seed_default_plants


class DatabaseSchemaTests(unittest.TestCase):
    def test_migrations_create_real_plant_and_calibration_tables(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        run_migrations(engine)

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        self.assertIn("plants", tables)
        self.assertIn("plant_units", tables)
        self.assertIn("plant_sampling_points", tables)
        self.assertIn("plant_monitoring_readings", tables)
        self.assertIn("plant_calibrations", tables)

        monitoring_cols = {col["name"] for col in inspector.get_columns("plant_monitoring_readings")}
        for required in ["do_mgl", "mlss_mgl", "srt_days", "hrt_hours", "recycle_ratio"]:
            self.assertIn(required, monitoring_cols)

        calibration_cols = {col["name"] for col in inspector.get_columns("plant_calibrations")}
        for required in ["target", "multiplier", "n_samples", "rmse_pct", "r2"]:
            self.assertIn(required, calibration_cols)

        with engine.connect() as conn:
            version = conn.exec_driver_sql("SELECT version FROM schema_version WHERE id = 1").scalar()
        self.assertEqual(CURRENT_SCHEMA_VERSION, version)

    def test_default_plant_seed_populates_three_plants_with_units_and_points(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)

        with Session() as session:
            seed_default_plants(session)
            session.commit()
            plants = session.query(Plant).all()
            self.assertEqual(3, len(plants))
            self.assertEqual({"daspoort", "zeekoegat", "phola"}, {plant.slug for plant in plants})
            self.assertGreaterEqual(sum(len(plant.units) for plant in plants), 20)
            self.assertEqual(12, sum(len(plant.sampling_points) for plant in plants))

    def test_calibration_and_monitoring_models_can_round_trip(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)

        with Session() as session:
            seed_default_plants(session)
            plant = session.query(Plant).filter_by(slug="daspoort").first()
            reading = PlantMonitoringReading(
                plant_id=plant.id,
                sampling_date=__import__("datetime").date(2026, 1, 1),
                sampling_point_code="SP1_influent",
                cod_mgl=350.0,
                do_mgl=1.5,
                mlss_mgl=3000.0,
                srt_days=30.0,
            )
            calibration = PlantCalibration(
                plant_id=plant.id,
                target="cod",
                multiplier=1.1,
                n_samples=3,
                rmse_pct=4.5,
            )
            session.add_all([reading, calibration])
            session.commit()

            self.assertEqual(1, session.query(PlantMonitoringReading).count())
            self.assertEqual(1.1, session.query(PlantCalibration).first().multiplier)


if __name__ == "__main__":
    unittest.main()
