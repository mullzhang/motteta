class MottetaError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 4):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def conflict(message: str) -> MottetaError:
    return MottetaError("conflict", message, 3)
