from typing import Any

import httpx

from simcli.errors import NotFound, ServerError, ServerUnreachable

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 5.0


class SimphoniaClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "SimphoniaClient":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def list_buses(self) -> list[dict[str, Any]]:
        return self._get("/bus")

    def list_commands(self, bus_name: str) -> list[dict[str, Any]]:
        return self._get(f"/bus/{bus_name}/commands")

    def dispatch(self, bus_name: str, code: str, payload: dict[str, Any] | None = None) -> Any:
        body = {"code": code, "payload": payload or {}}
        data = self._post(f"/bus/{bus_name}/dispatch", body)
        return data.get("result") if isinstance(data, dict) else data

    def _get(self, path: str) -> Any:
        try:
            resp = self._http.get(path)
        except httpx.RequestError as exc:
            raise ServerUnreachable(self.base_url, exc) from exc
        return self._read(resp)

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        try:
            resp = self._http.post(path, json=body)
        except httpx.RequestError as exc:
            raise ServerUnreachable(self.base_url, exc) from exc
        return self._read(resp)

    @staticmethod
    def _read(resp: httpx.Response) -> Any:
        if resp.status_code == 404:
            raise NotFound(_describe_error(resp))
        if resp.status_code >= 400:
            raise ServerError(resp.status_code, _describe_error(resp))
        return resp.json()


def _describe_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text or f"HTTP {resp.status_code}"

    detail = data.get("detail") if isinstance(data, dict) else None
    if isinstance(detail, dict) and "error" in detail:
        err = detail["error"]
        return f"{err.get('type', '?')}: {err.get('message', '')}"
    return str(detail or data)
