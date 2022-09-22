from typing import Protocol


class Cli(Protocol):
    def info(self, text: str) -> None:
        ...
