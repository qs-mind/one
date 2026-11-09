from qsone.engine.types import Text


class NoAI(Exception):
    """No model to run on; `text` says why in plain words."""

    def __init__(self, text: Text) -> None:
        super().__init__(text["en"])
        self.text = text


class BriefBusy(Exception):
    def __init__(self, brief_id: str) -> None:
        super().__init__(brief_id)
        self.brief_id = brief_id


class _Fail(Exception):
    """Ends the Brief as failed, with these plain words."""

    def __init__(self, text: Text) -> None:
        super().__init__(text["en"])
        self.text = text


class _Busy(Exception):
    """The Subscription Link reached its limit: like a busy provider."""
