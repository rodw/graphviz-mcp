from __future__ import annotations


class PerCallClient:
    """MCP client that opens a fresh session per call.

    (An async-generator fixture holding an anyio task group would be torn down in another task.)
    """

    def __init__(self, server: object) -> None:
        self._server = server

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        from mcp import Client

        async def _call(*args, **kwargs):  # type: ignore[no-untyped-def]
            async with Client(self._server) as c:  # type: ignore[arg-type]
                return await getattr(c, name)(*args, **kwargs)

        return _call
