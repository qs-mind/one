"""The search model's routes: its state, and the engineer's Download, Stop, Pause and Resume."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from qsone import copy
from qsone.meaning.service import Meaning


def router(meaning: Meaning) -> APIRouter:
    r = APIRouter()

    @r.get("/meaning")
    def status() -> dict:
        return meaning.status()

    @r.post("/meaning/download")
    def download() -> JSONResponse:
        if meaning.unavailable():
            return JSONResponse({"error": copy.MEANING_NOT_ON_THIS_COMPUTER}, status_code=409)
        meaning.download()
        return JSONResponse(meaning.status(), status_code=202)

    @r.post("/meaning/stop")
    def stop() -> dict:
        meaning.stop_download()
        return meaning.status()

    @r.post("/meaning/pause")
    def pause() -> dict:
        meaning.pause()
        return meaning.status()

    @r.post("/meaning/resume")
    def resume() -> dict:
        meaning.resume()
        return meaning.status()

    return r
