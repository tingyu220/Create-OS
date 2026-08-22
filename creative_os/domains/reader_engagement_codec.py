from __future__ import annotations

import json
from typing import Any


class ReaderEngagementCodec:
    SCHEMA_VERSION = 1

    @classmethod
    def encode(cls, payload: dict[str, Any]) -> str:
        if not isinstance(payload, dict) or payload.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported schema")
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def decode(cls, raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw, object_pairs_hook=cls._unique_pairs)
        except ValueError:
            raise
        if not isinstance(payload, dict) or set(payload) not in ({"schema_version"}, {"schema_version", "record_type", "record"}):
            raise ValueError("fields must match schema")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported schema")
        return payload

    @staticmethod
    def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
