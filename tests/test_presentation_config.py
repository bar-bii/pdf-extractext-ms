import importlib

import pytest
from httpx import ASGITransport, AsyncClient

from presentation import main


def test_root_path_se_toma_de_la_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("ROOT_PATH", "/api")

    reloaded = importlib.reload(main)

    try:
        assert reloaded.app.root_path == "/api"
    finally:
        monkeypatch.delenv("ROOT_PATH")
        importlib.reload(main)


def test_root_path_es_vacio_por_defecto(monkeypatch):
    monkeypatch.delenv("ROOT_PATH", raising=False)

    reloaded = importlib.reload(main)

    assert reloaded.app.root_path == ""


@pytest.mark.asyncio
async def test_root_redirige_al_swagger_respetando_el_root_path(monkeypatch):
    monkeypatch.setenv("ROOT_PATH", "/api")
    reloaded = importlib.reload(main)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=reloaded.app), base_url="http://test"
        ) as client:
            response = await client.get("/")

        assert response.status_code == 307
        assert response.headers["location"] == "/api/docs"
    finally:
        monkeypatch.delenv("ROOT_PATH")
        importlib.reload(main)
