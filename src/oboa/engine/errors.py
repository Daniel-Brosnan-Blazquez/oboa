"""
Engine errors for OBOA.
"""


class OboaError(Exception):
    """
    Base OBOA engine error.
    """


class InputError(OboaError):
    """
    Raised when public API inputs are invalid.
    """


class OboaResourcesPathNotAvailable(OboaError):
    """
    Raised when resource files cannot be located.
    """


class OboaSchemasPathNotAvailable(OboaError):
    """
    Raised when schema files cannot be located.
    """


class OboaLogPathNotAvailable(OboaError):
    """
    Raised when the log path cannot be located or created.
    """


class OrchestrationConfigurationError(OboaError):
    """
    Raised when orchestration configuration is invalid.
    """


class OrchestrationError(OboaError):
    """
    Raised when orchestration fails.
    """


class ArchiveDelegationError(OboaError):
    """
    Raised when ABOA archive delegation fails.
    """


class AboaDependencyError(ArchiveDelegationError):
    """
    Raised when ABOA is not importable or cannot be initialized.
    """


class ProcessorError(OboaError):
    """
    Raised when a data processor fails.
    """


class PollingError(OboaError):
    """
    Raised when polling cannot proceed.
    """


class DaemonError(OboaError):
    """
    Raised when daemon lifecycle management fails.
    """
