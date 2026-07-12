class AgyFlowError(Exception):
    """Domain exception for agy-flow orchestration logic failures."""
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
