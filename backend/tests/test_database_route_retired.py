from pathlib import Path

from app.main import app


BACKEND_DIR = Path(__file__).resolve().parents[1]
API_FILE = BACKEND_DIR / "app" / "api" / "v1" / "api.py"
DATABASE_ENDPOINT_FILE = BACKEND_DIR / "app" / "api" / "v1" / "endpoints" / "database.py"


def test_database_management_router_is_not_registered():
    content = API_FILE.read_text(encoding="utf-8")

    assert " database," not in content
    assert "include_router(database.router" not in content


def test_database_management_endpoint_module_is_absent():
    assert not DATABASE_ENDPOINT_FILE.exists()


def test_database_management_routes_are_absent_from_app():
    assert all(
        not route.path.startswith("/api/v1/database")
        for route in app.routes
    )


def test_database_management_routes_are_absent_from_openapi():
    assert all(
        not path.startswith("/api/v1/database")
        for path in app.openapi()["paths"]
    )
