"""
OBOA inventory SQLAlchemy models.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from oboa.datamodel.base import Base


def _isoformat(value):
    """
    Format optional datetime values for JSON serialization.

    :param value: datetime value to format
    :type value: datetime.datetime or None

    :return: ISO-8601 text or an empty string
    :rtype: str
    """
    if value is None:
        return ""
    return value.isoformat()


def _stringify(value):
    """
    Format optional scalar values for JSON serialization.

    :param value: scalar value to format
    :type value: object

    :return: text value or an empty string
    :rtype: str
    """
    if value is None:
        return ""
    return str(value)


class OrchestrationConfiguration(Base):
    """
    Persisted history entry for an orchestration XML configuration.
    """

    __tablename__ = "orchestration_configurations"

    orchestration_configuration_uuid = Column(Text, primary_key=True)
    path = Column(Text, nullable=False, index=True)
    active_from = Column(DateTime, nullable=False, index=True)
    active_until = Column(DateTime, index=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    content = Column(Text, nullable=False)
    orchestratedFiles = relationship("OrchestratedFile", back_populates="orchestrationConfiguration")

    def __init__(self, orchestration_configuration_uuid, path, active_from, content,
                 active_until=None, active=True):
        """
        Build an orchestration configuration history row.

        :param orchestration_configuration_uuid: configuration UUID
        :param path: source XML configuration path
        :param active_from: activation timestamp
        :param content: raw XML configuration content
        :param active_until: deactivation timestamp, if any
        :param active: flag indicating whether this configuration is active

        :return: None
        :rtype: None
        """
        self.orchestration_configuration_uuid = str(orchestration_configuration_uuid)
        self.path = path
        self.active_from = active_from
        self.active_until = active_until
        self.active = active
        self.content = content

    def jsonify(self):
        """
        Serialize the configuration row.

        :return: JSON-ready dictionary
        :rtype: dict
        """
        return {
            "orchestration_configuration_uuid": _stringify(self.orchestration_configuration_uuid),
            "path": _stringify(self.path),
            "active_from": _isoformat(self.active_from),
            "active_until": _isoformat(self.active_until),
            "active": _stringify(self.active),
            "content": _stringify(self.content),
        }


class OrchestratedFile(Base):
    """
    Inventory row for a file orchestrated by OBOA.
    """

    __tablename__ = "orchestrated_files"

    file_uuid = Column(Text, primary_key=True)
    name = Column(Text, nullable=False, index=True)
    path = Column(Text, nullable=False, index=True)
    file_group = Column(Text, nullable=False, index=True)
    reception_date = Column(DateTime, nullable=False, index=True)
    archived = Column(Boolean, nullable=False, default=False, index=True)
    processed = Column(Boolean, nullable=False, default=False, index=True)
    orchestration_configuration_uuid = Column(
        Text,
        ForeignKey("orchestration_configurations.orchestration_configuration_uuid"),
        nullable=True,
        index=True,
    )
    orchestrationConfiguration = relationship(
        "OrchestrationConfiguration",
        back_populates="orchestratedFiles",
    )

    def __init__(self, file_uuid, name, path, file_group, reception_date,
                 archived=False, processed=False, orchestration_configuration=None):
        """
        Build an orchestrated-file inventory row.

        :param file_uuid: file UUID
        :param name: input file name
        :param path: original input file path
        :param file_group: matched orchestration group or ``unknown``
        :param reception_date: file reception timestamp
        :param archived: flag indicating whether archiving succeeded
        :param processed: flag indicating whether processing is complete
        :param orchestration_configuration: associated configuration history row

        :return: None
        :rtype: None
        """
        self.file_uuid = str(file_uuid)
        self.name = name
        self.path = path
        self.file_group = file_group
        self.reception_date = reception_date
        self.archived = archived
        self.processed = processed
        self.orchestrationConfiguration = orchestration_configuration
        if orchestration_configuration is not None:
            self.orchestration_configuration_uuid = str(
                orchestration_configuration.orchestration_configuration_uuid
            )

    def jsonify(self):
        """
        Serialize the orchestrated-file row.

        :return: JSON-ready dictionary
        :rtype: dict
        """
        return {
            "file_uuid": _stringify(self.file_uuid),
            "name": _stringify(self.name),
            "path": _stringify(self.path),
            "group": _stringify(self.file_group),
            "file_group": _stringify(self.file_group),
            "reception_date": _isoformat(self.reception_date),
            "archived": _stringify(self.archived),
            "processed": _stringify(self.processed),
            "orchestration_configuration_uuid": _stringify(self.orchestration_configuration_uuid),
        }


class OrchestrationOperation(Base):
    """
    Durable audit row for an OBOA operation.
    """

    __tablename__ = "orchestration_operations"

    operation_uuid = Column(Text, primary_key=True)
    operation = Column(Text, nullable=False, index=True)
    time_stamp = Column(DateTime, nullable=False, index=True)
    status = Column(Integer, nullable=False, index=True)
    message = Column(Text, index=True)
    file_uuid = Column(Text, ForeignKey("orchestrated_files.file_uuid"), index=True)
    orchestratedFile = relationship("OrchestratedFile", backref="operations")

    def __init__(self, operation_uuid, operation, time_stamp, status, message=None,
                 orchestrated_file=None):
        """
        Build an orchestration operation audit row.

        :param operation_uuid: operation UUID
        :param operation: operation name
        :param time_stamp: operation timestamp
        :param status: numeric status code
        :param message: optional operation message
        :param orchestrated_file: optional related orchestrated-file row

        :return: None
        :rtype: None
        """
        self.operation_uuid = str(operation_uuid)
        self.operation = operation
        self.time_stamp = time_stamp
        self.status = int(status)
        self.message = message
        self.orchestratedFile = orchestrated_file
        if orchestrated_file is not None:
            self.file_uuid = str(orchestrated_file.file_uuid)

    def jsonify(self):
        """
        Serialize the operation row.

        :return: JSON-ready dictionary
        :rtype: dict
        """
        return {
            "operation_uuid": _stringify(self.operation_uuid),
            "operation": _stringify(self.operation),
            "time_stamp": _isoformat(self.time_stamp),
            "status": _stringify(self.status),
            "message": _stringify(self.message),
            "file_uuid": _stringify(self.file_uuid),
        }
