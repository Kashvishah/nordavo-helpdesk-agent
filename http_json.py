"""Small JSON GET helper with retries for temporary helpdesk failures."""

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any


MAX_RETRIES = 3


def _is_timeout(error: urllib.error.URLError) -> bool:
    return isinstance(error.reason, (TimeoutError, socket.timeout))


def _redact(message: str, request: urllib.request.Request) -> str:
    for _, value in request.header_items():
        if value:
            message = message.replace(value, "[redacted]")
    return message


def get_json(
    request: urllib.request.Request,
    *,
    service: str,
    timeout: float = 30,
) -> Any:
    retries = 0
    while True:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            temporary = error.code == 429 or 500 <= error.code <= 599
            if temporary and retries < MAX_RETRIES:
                delay = 0.25 * (2**retries)
                if error.code == 429:
                    try:
                        delay = max(delay, float(error.headers.get("Retry-After", delay)))
                    except (AttributeError, TypeError, ValueError):
                        pass
                time.sleep(delay)
                retries += 1
                continue
            body = error.read(200).decode("utf-8", errors="replace")
            body = _redact(body, request)
            suffix = f" after {retries} retries" if temporary else ""
            raise RuntimeError(
                f"{service} HTTP {error.code}{suffix}; "
                f"response body (first 200 characters): {body}"
            ) from None
        except urllib.error.URLError as error:
            if _is_timeout(error) and retries < MAX_RETRIES:
                time.sleep(0.25 * (2**retries))
                retries += 1
                continue
            reason = error.reason
            message = _redact(f"{type(reason).__name__}: {reason}", request)
            suffix = f" after {retries} retries" if _is_timeout(error) else ""
            raise RuntimeError(f"{service} network error{suffix}: {message}") from None
        except (TimeoutError, socket.timeout) as error:
            if retries < MAX_RETRIES:
                time.sleep(0.25 * (2**retries))
                retries += 1
                continue
            raise RuntimeError(
                f"{service} timed out after {retries} retries."
            ) from None
