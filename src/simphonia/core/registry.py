from simphonia.core.bus import Bus
from simphonia.core.errors import BusNotFound


class BusRegistry:
    def __init__(self) -> None:
        self._buses: dict[str, Bus] = {}

    def get_or_create(self, bus_name: str) -> Bus:
        bus = self._buses.get(bus_name)
        if bus is None:
            bus = Bus(bus_name)
            self._buses[bus_name] = bus
        return bus

    def get(self, bus_name: str) -> Bus:
        try:
            return self._buses[bus_name]
        except KeyError:
            raise BusNotFound(bus_name) from None

    def all(self) -> dict[str, Bus]:
        return dict(self._buses)

    def reset(self) -> None:
        self._buses.clear()


_default = BusRegistry()


def default_registry() -> BusRegistry:
    return _default
