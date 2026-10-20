"""
ABOA archive delegation client for OBOA.
"""

from oboa.engine.errors import AboaDependencyError, ArchiveDelegationError


class AboaArchiveClient():
    """
    Default archive client that delegates storage to ABOA.
    """

    def __init__(self):
        """
        Initialize the ABOA engine dependency.

        :return: None
        :rtype: None

        :raises AboaDependencyError: when ABOA cannot be imported
        """
        try:
            from aboa.engine.engine import Engine as AboaEngine
        except Exception as exc:
            raise AboaDependencyError("ABOA could not be imported: {}".format(exc)) from exc
        self.aboa_engine_class = AboaEngine

    def archive_file(self, file_path, file_group=None, delete_after_archive=False):
        """
        Archive a file through ABOA.

        :param file_path: path to the input file to archive
        :type file_path: str
        :param file_group: optional OBOA file group passed to ABOA metadata
        :type file_group: str or None
        :param delete_after_archive: remove the input after successful archive
        :type delete_after_archive: bool

        :return: return value from ``aboa.engine.engine.Engine.archive_file``
        :rtype: object

        :raises ArchiveDelegationError: when ABOA archive delegation fails
        """
        engine = self.aboa_engine_class()
        try:
            metadata = {}
            if file_group is not None:
                metadata["file_group"] = file_group
            return engine.archive_file(
                file_path,
                metadata=metadata,
                delete=delete_after_archive,
            )
        except Exception as exc:
            raise ArchiveDelegationError("ABOA archive delegation failed: {}".format(exc)) from exc
        finally:
            try:
                engine.close_session()
            except Exception:
                pass

    def close(self):
        """
        Close client resources.

        :return: None
        :rtype: None
        """
        return None
