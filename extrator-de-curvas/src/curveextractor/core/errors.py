"""Structured domain errors translated at the user interface boundary."""


class DomainError(ValueError):
    def __init__(self, code: str, **details: object) -> None:
        self.code = code
        self.details = details
        super().__init__(f"{code}: {details}")
