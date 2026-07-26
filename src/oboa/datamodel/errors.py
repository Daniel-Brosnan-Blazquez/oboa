"""
Datamodel errors for OBOA.
"""


class OboaDatamodelError(Exception):
    """
    Base datamodel error.
    """


class OboaResourcesPathNotAvailable(OboaDatamodelError):
    """
    Raised when OBOA resources cannot be located.
    """
