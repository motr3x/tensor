from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import create_db_engine, get_db
from main import app
from models import Service
from seed import init_db


VALID_SERVICE = {
    "categoryId": 3,
    "title": "Наращивание ресниц",
    "desc": "Огромные ресницы уже через 30 минут",
    "duration": 30,
    "price": 1500.00,
}


class ServiceApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "test.db"
        self.engine = create_db_engine(self.database_path)
        init_db(self.engine)

        def get_test_db():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_db] = get_test_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.temp_directory.cleanup()

    def service_count(self):
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(Service))

    def assert_rejected(self, changes):
        count_before = self.service_count()
        response = self.client.post("/services", json={**VALID_SERVICE, **changes})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.service_count(), count_before)
        return response

    def test_valid_service_is_created_and_saved(self):
        response = self.client.post("/services", json=VALID_SERVICE)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"id": 1, **VALID_SERVICE})
        with Session(self.engine) as session:
            service = session.get(Service, 1)
            self.assertEqual(service.category_id, 3)
            self.assertEqual(service.title, VALID_SERVICE["title"])
            self.assertEqual(service.desc, VALID_SERVICE["desc"])
            self.assertEqual(service.duration, 30)
            self.assertEqual(service.price, 1500.00)

    def test_price_from_assignment_is_not_numeric(self):
        self.assert_rejected({"price": "бесплатно"})

    def test_multiple_errors_from_assignment(self):
        response = self.assert_rejected({"desc": "", "duration": 0, "price": -1500.00})
        fields = {error["loc"][-1] for error in response.json()["detail"]}
        self.assertEqual(fields, {"desc", "duration", "price"})

    def test_title_and_description_constraints(self):
        for field in ["title", "desc"]:
            for value in ["", "   ", "\t\n", "я" * 101, None, 123]:
                with self.subTest(field=field, value=value):
                    self.assert_rejected({field: value})

    def test_duration_constraints(self):
        for duration in [0, 29, 181, -1, 30.5, "час", True, None]:
            with self.subTest(duration=duration):
                self.assert_rejected({"duration": duration})

    def test_price_constraints(self):
        for price in [0, -0.01, "бесплатно", "NaN", "Infinity", True, None]:
            with self.subTest(price=price):
                self.assert_rejected({"price": price})

    def test_all_fields_are_required(self):
        for field in VALID_SERVICE:
            with self.subTest(field=field):
                data = VALID_SERVICE.copy()
                del data[field]
                response = self.client.post("/services", json=data)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(self.service_count(), 0)

    def test_valid_boundaries(self):
        for duration in [30, 180]:
            with self.subTest(duration=duration):
                response = self.client.post("/services", json={
                    **VALID_SERVICE, "title": "я" * 100, "desc": "я" * 100,
                    "duration": duration, "price": 0.01,
                })
                self.assertEqual(response.status_code, 201, response.text)

    def test_integer_price_is_accepted(self):
        response = self.client.post("/services", json={**VALID_SERVICE, "price": 1500})
        self.assertEqual(response.status_code, 201, response.text)

    def test_spaces_are_stripped_before_saving(self):
        response = self.client.post("/services", json={**VALID_SERVICE, "title": "  Стрижка  "})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "Стрижка")
        with Session(self.engine) as session:
            self.assertEqual(session.get(Service, response.json()["id"]).title, "Стрижка")

    def test_unknown_category_does_not_create_service(self):
        response = self.client.post("/services", json={**VALID_SERVICE, "categoryId": 99})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.service_count(), 0)

    def test_category_id_constraints(self):
        for category_id in [0, -1, "три", True, None]:
            with self.subTest(category_id=category_id):
                self.assert_rejected({"categoryId": category_id})

    def test_invalid_request_keeps_created_service(self):
        self.client.post("/services", json=VALID_SERVICE)
        self.assert_rejected({"price": -1500})
        self.assertEqual(self.service_count(), 1)

    def test_category_counts_are_updated(self):
        self.assertEqual(self.client.get("/categories/3").json()["servicesCount"], 0)
        self.client.post("/services", json=VALID_SERVICE)
        self.assertEqual(self.client.get("/categories/3").json()["servicesCount"], 1)
        categories = self.client.get("/categories").json()
        self.assertEqual([category["servicesCount"] for category in categories], [0, 0, 1, 0])

    def test_service_survives_database_reopening_and_initialization(self):
        self.client.post("/services", json=VALID_SERVICE)
        self.engine.dispose()
        reopened_engine = create_db_engine(self.database_path)
        try:
            init_db(reopened_engine)
            with Session(reopened_engine) as session:
                self.assertEqual(session.scalar(select(func.count()).select_from(Service)), 1)
                self.assertEqual(session.get(Service, 1).title, VALID_SERVICE["title"])
        finally:
            reopened_engine.dispose()

    def test_database_has_category_foreign_key(self):
        with Session(self.engine) as session:
            session.add(Service(category_id=99, title="Услуга", desc="Описание", duration=30, price=100))
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_previous_endpoints(self):
        self.assertEqual(self.client.get("/masters").status_code, 200)
        filtered = self.client.get("/masters", params={"specialization": "Парикмахер"})
        self.assertEqual([master["id"] for master in filtered.json()], [1])
        self.assertEqual(self.client.get("/masters/1").status_code, 200)
        self.assertEqual(self.client.get("/masters/99").status_code, 404)
        self.assertEqual(self.client.get("/categories/99").status_code, 404)


if __name__ == "__main__":
    unittest.main()
