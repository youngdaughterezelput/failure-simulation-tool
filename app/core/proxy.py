from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import Request
from fastapi.responses import Response
from starlette.datastructures import Headers


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def build_upstream_url(target_api_url: str, request: Request) -> str:
    target = urlsplit(target_api_url)
    base_path = target.path.rstrip("/")
    request_path = request.url.path

    return urlunsplit(
        (
            target.scheme,
            target.netloc,
            f"{base_path}{request_path}",
            request.url.query,
            "",
        )
    )


def filter_request_headers(headers: Headers) -> list[tuple[bytes, bytes]]:
    excluded = HOP_BY_HOP_HEADERS | {"host", "content-length"}
    return [
        (name, value)
        for name, value in headers.raw
        if name.decode("latin-1").lower() not in excluded
    ]


def filter_response_headers(headers: httpx.Headers) -> list[tuple[bytes, bytes]]:
    # HTTPX decodes compressed content before exposing response.content, so the
    # original encoding and length must not be forwarded
    excluded = HOP_BY_HOP_HEADERS | {"content-encoding", "content-length"}
    return [
        (name.encode("latin-1"), value.encode("latin-1"))
        for name, value in headers.multi_items()
        if name.lower() not in excluded
    ]


async def proxy_request(request: Request, *, target_api_url: str, client: httpx.AsyncClient,) -> Response:
    upstream_response = await client.request(
        method=request.method,
        url=build_upstream_url(target_api_url, request),
        headers=filter_request_headers(request.headers),
        content=await request.body(),
    )
    response = Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
    )
    response.raw_headers.extend(filter_response_headers(upstream_response.headers))
    return response
