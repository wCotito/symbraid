from __future__ import annotations

import os
import re


SERVICE = "Symbraid"
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def env_reference(variable_name: str) -> str:
    if not _ENV_NAME.fullmatch(variable_name):
        raise ValueError("invalid environment variable name")
    return f"env:{variable_name}"


def keyring_reference(name: str) -> str:
    if not name or name.startswith("env:"):
        raise ValueError("invalid keyring secret reference")
    return name if name.startswith("keyring:") else f"keyring:{name}"


def _keyring_name(reference: str) -> str:
    return reference.removeprefix("keyring:")


def get_secret(reference: str) -> str:
    if not reference:
        return ""
    if reference.startswith("env:"):
        name = reference[4:]
        if not _ENV_NAME.fullmatch(name):
            raise ValueError("invalid environment secret reference")
        return os.environ.get(name, "")
    import keyring

    name = _keyring_name(reference)
    value = keyring.get_password(SERVICE, name)
    if value is not None:
        return value
    return ""


def set_secret(reference: str, value: str) -> None:
    if not reference:
        raise ValueError("secret reference cannot be empty")
    if reference.startswith("env:"):
        raise ValueError("environment secrets are provided by the process, not stored")
    import keyring

    keyring.set_password(SERVICE, _keyring_name(reference), value)


_MISSING = object()


class SecretUpdate:
    """A reversible update of one credential in the Symbraid keyring service."""

    def __init__(self, reference: str, value: str):
        if not reference:
            raise ValueError("secret reference cannot be empty")
        if reference.startswith("env:"):
            raise ValueError("environment secrets are provided by the process, not stored")
        self.reference = reference
        self.value = value
        self._old_value: object = _MISSING
        self._applied = False

    def apply(self) -> None:
        if self._applied:
            raise RuntimeError("secret update is already active")
        import keyring

        self._old_value = keyring.get_password(SERVICE, _keyring_name(self.reference))
        self._applied = True
        try:
            set_secret(self.reference, self.value)
        except BaseException:
            try:
                self.rollback()
            except BaseException as rollback_error:
                raise RuntimeError("Secret update failed and its previous value could not be restored") from rollback_error
            raise

    def _restore(self) -> None:
        import keyring

        name = _keyring_name(self.reference)
        if self._old_value is None:
            try:
                keyring.delete_password(SERVICE, name)
            except Exception as exc:
                missing_type = getattr(getattr(keyring, "errors", None), "PasswordDeleteError", None)
                if missing_type is None or not isinstance(exc, missing_type):
                    raise
        elif self._old_value is not _MISSING:
            keyring.set_password(SERVICE, name, str(self._old_value))

    def rollback(self) -> None:
        if not self._applied:
            return
        self._restore()
        self._old_value = _MISSING
        self._applied = False

    def commit(self) -> None:
        if not self._applied:
            return
        self._old_value = _MISSING
        self._applied = False

    def __enter__(self) -> "SecretUpdate":
        self.apply()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False
