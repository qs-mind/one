"""AI keys live only in the system key store. Never log or return a key."""

import logging

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE = "QS Mind One"  # not "ONE": the saved keys are stored under this name; renaming loses them
log = logging.getLogger(__name__)


def get_key(provider: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, provider)
    except KeyringError:
        log.warning("system key store not available; treating the %s key as missing", provider)
        return None


def set_key(provider: str, value: str) -> None:
    """Raises `keyring.errors.KeyringError` when the system key store is not available."""
    keyring.set_password(SERVICE, provider, value)


def delete_key(provider: str) -> None:
    """Raises `keyring.errors.KeyringError` when the system key store is not available."""
    try:
        keyring.delete_password(SERVICE, provider)
    except PasswordDeleteError:
        pass  # there was no key
