import argparse
import json
import sys
from typing import Any

from simcli.client import DEFAULT_BASE_URL, SimphoniaClient
from simcli.errors import InvalidPayload, NotFound, ServerError, ServerUnreachable, SimcliError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="simcli", description="CLI client for the simphonia server")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help=f"server base URL (default: {DEFAULT_BASE_URL})")

    sub = parser.add_subparsers(dest="command", required=True)

    p_bus = sub.add_parser("bus", help="bus operations")
    bus_sub = p_bus.add_subparsers(dest="bus_command", required=True)

    bus_sub.add_parser("list", help="list all buses")

    p_commands = bus_sub.add_parser("commands", help="list commands of a bus")
    p_commands.add_argument("bus_name")

    p_dispatch = sub.add_parser("dispatch", help="dispatch a command on a bus")
    p_dispatch.add_argument("bus_name")
    p_dispatch.add_argument("code")
    p_dispatch.add_argument(
        "--payload",
        default=None,
        help='JSON payload passed as kwargs to the callback (e.g. \'{"key": "value"}\')',
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        with SimphoniaClient(base_url=args.url) as client:
            if args.command == "bus" and args.bus_command == "list":
                _render(client.list_buses())
            elif args.command == "bus" and args.bus_command == "commands":
                _render(client.list_commands(args.bus_name))
            elif args.command == "dispatch":
                payload = _parse_payload(args.payload)
                _render(client.dispatch(args.bus_name, args.code, payload))
            else:
                print(f"unknown command: {args.command}", file=sys.stderr)
                return 2
        return 0
    except NotFound as exc:
        print(f"not found: {exc}", file=sys.stderr)
        return 4
    except ServerUnreachable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except ServerError as exc:
        print(f"server error: {exc}", file=sys.stderr)
        return 5
    except InvalidPayload as exc:
        print(f"invalid payload: {exc}", file=sys.stderr)
        return 2
    except SimcliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _parse_payload(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidPayload(f"payload is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise InvalidPayload("payload must be a JSON object")
    return data


def _render(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))
