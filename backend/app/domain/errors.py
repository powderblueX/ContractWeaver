"""Expected workflow failures mapped to HTTP at the application boundary."""


class InvalidContractInput(ValueError):
    pass


class WorkspaceNotFound(LookupError):
    pass


class WorkspaceConflict(InvalidContractInput):
    pass
