import secrets

from fastapi import Depends, FastAPI, HTTPException, Request


def create_app(secret: str) -> FastAPI:
    """Build the core app. Every route needs `Authorization: Bearer <secret>`."""
    expected = f"Bearer {secret}".encode()

    def check_secret(request: Request) -> None:
        given = request.headers.get("authorization", "").encode()
        if not secrets.compare_digest(given, expected):
            raise HTTPException(status_code=401)

    app = FastAPI(
        dependencies=[Depends(check_secret)], docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    return app
