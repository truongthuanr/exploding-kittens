import httpx
import asyncio

from app.main import fastapi_app


def test_healthcheck() -> None:
    async def run_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/health")

    response = asyncio.run(run_request())

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
