"""Redact configured secrets even if a device reflects them in a response."""

import os
from enum import Enum


def configured_secrets(endpoints):
    return [
        os.environ[name]
        for ep in endpoints.values()
        if (name := ep.snmp.get("community_env")) and os.environ.get(name)
    ]


def redact(value, secrets):
    if isinstance(value, Enum):
        return value
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {redact(k, secrets): redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    return value
