class AgentRelayError(Exception):
    """Domain exception for agent-relay orchestration logic failures."""
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
