"""
src/core/exceptions/workflow_exceptions.py
Domain exceptions for file handling and processing workflow operations.
"""

class FileHandlingError(Exception):
    """Base exception for file handling failures."""
    pass

class InvalidFileExtensionError(FileHandlingError):
    """Raised when uploaded file is not a .pdf file."""
    pass

class FileTooLargeError(FileHandlingError):
    """Raised when uploaded file exceeds maximum allowed size (e.g. 500MB)."""
    pass

class WorkflowProcessingError(Exception):
    """Base exception for workflow state machine failures."""
    pass

class InvalidWorkflowStateError(WorkflowProcessingError):
    """Raised when an invalid state transition is requested."""
    pass

class WorkflowCancelledError(WorkflowProcessingError):
    """Raised when workflow execution is cooperatively cancelled by user/caller."""
    pass
