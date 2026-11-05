"""The account routes. No answer ever holds a token; none is cached by the webview."""

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from qsone.account.session import Account


class SignInIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: Literal["ar", "en"] = "en"
    device: bool = False


def _answer(body: dict) -> JSONResponse:
    return JSONResponse(body, headers={"Cache-Control": "no-store"})


def router(account: Account) -> APIRouter:
    r = APIRouter()

    @r.get("/account")
    def state() -> JSONResponse:
        return _answer(account.state())

    @r.post("/account/sign-in")
    def sign_in(body: SignInIn) -> JSONResponse:
        return _answer(account.sign_in(body.locale, body.device))

    @r.post("/account/cancel")
    def cancel() -> JSONResponse:
        return _answer(account.cancel())

    @r.delete("/account")
    def sign_out() -> JSONResponse:
        return _answer(account.sign_out())

    return r
