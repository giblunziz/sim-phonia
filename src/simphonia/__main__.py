import argparse
import logging
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="simphonia")
    parser.add_argument(
        "--configuration",
        metavar="PATH",
        help=(
            "Chemin vers un fichier de configuration YAML alternatif "
            "(défaut : src/simphonia/simphonia.yaml)"
        ),
    )
    args = parser.parse_args()

    if args.configuration:
        os.environ["SIMPHONIA_CONFIG_PATH"] = args.configuration

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run("simphonia.bootstrap:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
