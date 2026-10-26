"""Expected workflow failures mapped to HTTP at the application boundary."""


class InvalidContractInput(ValueError):
    """表示可向用户说明的业务参数或流程输入错误。"""

    pass


class WorkspaceNotFound(LookupError):
    """表示任务不存在或对当前用户不可见。"""

    pass


class WorkspaceConflict(InvalidContractInput):
    """表示修订、租约或并发操作与当前状态冲突。"""

    pass
