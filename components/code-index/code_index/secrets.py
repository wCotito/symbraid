from __future__ import annotations


SERVICE = "CodeIndex"


def get_secret(reference: str) -> str:
    if not reference:
        return ""
    import keyring

    return keyring.get_password(SERVICE, reference) or ""


def set_secret(reference: str, value: str) -> None:
    if not reference:
        raise ValueError("secret reference cannot be empty")
    import keyring

    keyring.set_password(SERVICE, reference, value)
