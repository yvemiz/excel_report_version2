from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from app.core.auth_service import COOKIE_NAME


class AuthenticationMiddleware:
    def __init__(self, app, auth, allowed_origins):
        self.app, self.auth = app, auth
        self.origins = set(allowed_origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        connection = HTTPConnection(scope)
        path = scope["path"]
        protected = path.startswith(("/api/", "/static/"))
        public = path in {"/api/auth/login", "/api/auth/register", "/api/auth/logout"}
        if not protected:
            return await self.app(scope, receive, send)

        async def reject(status, detail):
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 4401 if status == 401 else 4403})
            await JSONResponse({"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"})(scope, receive, send)

        mutating = (
            scope["type"] == "websocket"
            or scope.get("method") not in ("GET", "HEAD", "OPTIONS")
            or path == "/api/pipeline/stream"
        )
        origin = connection.headers.get("origin")
        if mutating and ((origin and origin not in self.origins) or connection.headers.get("sec-fetch-site") == "cross-site"):
            return await reject(403, "请求来源不受信任")
        if scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)
        if not public:
            user = await run_in_threadpool(self.auth.get_user, connection.cookies.get(COOKIE_NAME, ""))
            if not user:
                return await reject(401, "请先登录，或登录状态已过期")
            scope.setdefault("state", {})["user"] = user

        async def private_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (key, value) for key, value in message.get("headers", [])
                    if key.lower() != b"cache-control"
                ] + [(b"cache-control", b"no-store, private")]
            await send(message)

        await self.app(scope, receive, private_send)
