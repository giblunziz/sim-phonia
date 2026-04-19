import argparse
import asyncio
import logging
import os

import uvicorn


async def _serve(http_port: int, character: str | None, mcp_port: int) -> None:
    from simphonia.bootstrap import build_app

    http_app = build_app()
    configs = [uvicorn.Config(http_app, host="127.0.0.1", port=http_port, log_config=None)]

    from simphonia.facade import build_mcp_app
    mcp_app = build_mcp_app(character)
    configs.append(uvicorn.Config(mcp_app, host="127.0.0.1", port=mcp_port, log_config=None))
    logging.getLogger(__name__).info(
        "MCP player : http://127.0.0.1:%d/sse%s",
        mcp_port,
        f" (personnage : {character})" if character else " (from_char requis dans les appels)",
    )
    logging.getLogger(__name__).info(
        "MCP mj     : http://127.0.0.1:%d/sse/mj",
        mcp_port,
    )

    await asyncio.gather(*[uvicorn.Server(c).serve() for c in configs])


def main() -> None:
    parser = argparse.ArgumentParser(prog="simphonia")
    parser.add_argument(
        "--configuration",
        metavar="PATH",
        help="Chemin vers un fichier de configuration YAML alternatif",
    )
    parser.add_argument(
        "--character",
        metavar="SLUG",
        help="Personnage actif — active le serveur MCP sur --mcp-port (ex: antoine)",
    )
    parser.add_argument("--port", type=int, default=8000, metavar="PORT")
    parser.add_argument("--mcp-port", type=int, default=8001, metavar="PORT")
    args = parser.parse_args()

    if args.configuration:
        os.environ["SIMPHONIA_CONFIG_PATH"] = args.configuration

    from simphonia.logging_config import setup_logging
    setup_logging()
    asyncio.run(_serve(args.port, args.character, args.mcp_port))


if __name__ == "__main__":
    main()
