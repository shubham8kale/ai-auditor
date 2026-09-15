"""Bound request bodies before multipart parsing, including chunked uploads."""

from starlette.responses import JSONResponse


class RequestBodyLimit:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        lengths = [value for key, value in scope.get("headers", []) if key.lower() == b"content-length"]
        if lengths and (len(lengths) != 1 or len(lengths[0]) > 20 or not lengths[0].isdigit()):
            return await JSONResponse({"detail": "Invalid Content-Length."}, status_code=400)(
                scope, receive, send
            )
        if lengths and int(lengths[0]) > self.max_bytes:
            return await self.reject(scope, receive, send)

        # Bound bytes actually received; a missing or understated header is not a limit.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                return await self.reject(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        return await self.app(scope, bounded_receive, send)

    async def reject(self, scope, receive, send):
        return await JSONResponse({"detail": "Request exceeds the upload limit."}, status_code=413)(
            scope, receive, send
        )
