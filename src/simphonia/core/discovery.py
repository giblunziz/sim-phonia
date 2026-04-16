import importlib
import logging
import pkgutil

log = logging.getLogger(__name__)


def discover(package: str) -> int:
    pkg = importlib.import_module(package)
    if not hasattr(pkg, "__path__"):
        raise TypeError(f"{package!r} is not a package")

    count = 0
    for mod_info in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + "."):
        importlib.import_module(mod_info.name)
        count += 1

    log.info("discovered %d module(s) under %s", count, package)
    return count
