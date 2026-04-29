import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_new_game(client):
    resp = await client.post("/api/game/new")
    assert resp.status_code == 200
    data = resp.json()
    assert data["game_id"]
    assert len(data["alive_players"]) == 8
    assert data["phase"] == "night"


@pytest.mark.asyncio
async def test_step_without_game(client):
    import src.main as m
    m._current_game = None
    resp = await client.post("/api/game/step")
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
