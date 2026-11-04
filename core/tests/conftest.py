import keyring
import pytest
from keyring.backend import KeyringBackend


class MemoryKeyring(KeyringBackend):
    """Keeps keys in a dict so tests never touch the real system key store."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)


@pytest.fixture(autouse=True)
def memory_keyring():
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


SECRET = "s3cret"
AUTH = {"Authorization": f"Bearer {SECRET}"}


def ui_message(text: str) -> dict:
    """A chat request body as the AI SDK `useChat` sends it."""
    return {
        "trigger": "submit-message",
        "id": "chat-1",
        "messages": [{"id": "m-1", "role": "user", "parts": [{"type": "text", "text": text}]}],
    }
