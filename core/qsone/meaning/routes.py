"""The search model's route: its state. Nothing to press: it downloads and prepares by itself."""

from fastapi import APIRouter

from qsone.meaning.service import Meaning


def router(meaning: Meaning) -> APIRouter:
    r = APIRouter()

    @r.get("/meaning")
    def status() -> dict:
        return meaning.status()

    return r
