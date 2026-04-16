import logging

import uvicorn


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run("simphonia.bootstrap:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
