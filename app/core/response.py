import asyncio

from fastapi.responses import JSONResponse, Response

from app.models import SimulatedResponse


async def build_simulated_response(config: SimulatedResponse) -> Response:
    if config.delay_ms:
        await asyncio.sleep(config.delay_ms / 1000)
    if isinstance(config.body, (dict, list, int, float, bool)):
        return JSONResponse(
            content=config.body,
            status_code=config.status,
            headers=config.headers,
        )
    return Response(
        content=config.body or b"",
        status_code=config.status,
        headers=config.headers,
    )

