"""
Custom exceptions for the Rucio workflow package.

These exceptions mirror the error handling patterns used in PanDA-Rucio interactions.
"""

class RucioWorkflowError(Exception):
    """Base exception for all Rucio workflow errors."""
    
    def __init__(self, message: str, error_code: int = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code

    def __str__(self):
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


class DatasetError(RucioWorkflowError):
    """Exception raised for dataset-related errors."""
    pass


class FileRegistrationError(RucioWorkflowError):
    """Exception raised for file registration errors."""
    pass


class ValidationError(RucioWorkflowError):
    """Exception raised for validation errors."""
    pass


class RucioClientError(RucioWorkflowError):
    """Exception raised for Rucio client errors."""
    pass


class WorkflowExecutionError(RucioWorkflowError):
    """Exception raised for workflow execution errors."""
    pass
