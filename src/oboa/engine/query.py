"""
Query interface for the OBOA inventory.
"""

from sqlalchemy.orm import scoped_session

from oboa.datamodel.base import Base, Session, engine
from oboa.datamodel.orchestrated_files import (
    OrchestratedFile,
    OrchestrationConfiguration,
    OrchestrationOperation,
)
from oboa.engine import functions
from oboa.engine.errors import InputError
from oboa.engine.operators import arithmetic_operators, text_operators


class Query():
    """
    Class for querying OBOA inventory data.
    """

    orchestrated_file_text_fields = {
        "file_uuids": OrchestratedFile.file_uuid,
        "names": OrchestratedFile.name,
        "paths": OrchestratedFile.path,
        "file_group": OrchestratedFile.file_group,
        "orchestration_configuration_uuids": OrchestratedFile.orchestration_configuration_uuid,
    }
    orchestrated_file_date_fields = {
        "reception_date_filters": OrchestratedFile.reception_date,
    }
    orchestrated_file_bool_fields = {
        "archived": OrchestratedFile.archived,
        "processed": OrchestratedFile.processed,
    }
    orchestrated_file_order_fields = {
        "file_uuid": OrchestratedFile.file_uuid,
        "name": OrchestratedFile.name,
        "path": OrchestratedFile.path,
        "file_group": OrchestratedFile.file_group,
        "group": OrchestratedFile.file_group,
        "reception_date": OrchestratedFile.reception_date,
        "archived": OrchestratedFile.archived,
        "processed": OrchestratedFile.processed,
        "orchestration_configuration_uuid": OrchestratedFile.orchestration_configuration_uuid,
    }
    configuration_text_fields = {
        "orchestration_configuration_uuids": OrchestrationConfiguration.orchestration_configuration_uuid,
        "paths": OrchestrationConfiguration.path,
        "contents": OrchestrationConfiguration.content,
    }
    configuration_date_fields = {
        "active_from_date_filters": OrchestrationConfiguration.active_from,
        "active_until_date_filters": OrchestrationConfiguration.active_until,
    }
    configuration_bool_fields = {
        "active": OrchestrationConfiguration.active,
    }
    configuration_order_fields = {
        "orchestration_configuration_uuid": OrchestrationConfiguration.orchestration_configuration_uuid,
        "path": OrchestrationConfiguration.path,
        "active_from": OrchestrationConfiguration.active_from,
        "active_until": OrchestrationConfiguration.active_until,
        "active": OrchestrationConfiguration.active,
        "content": OrchestrationConfiguration.content,
    }
    operation_text_fields = {
        "operation_uuids": OrchestrationOperation.operation_uuid,
        "operations": OrchestrationOperation.operation,
        "messages": OrchestrationOperation.message,
        "file_uuids": OrchestrationOperation.file_uuid,
    }
    operation_date_fields = {
        "time_stamp_filters": OrchestrationOperation.time_stamp,
    }
    operation_number_fields = {
        "status_filters": OrchestrationOperation.status,
    }
    operation_order_fields = {
        "operation_uuid": OrchestrationOperation.operation_uuid,
        "operation": OrchestrationOperation.operation,
        "time_stamp": OrchestrationOperation.time_stamp,
        "status": OrchestrationOperation.status,
        "message": OrchestrationOperation.message,
        "file_uuid": OrchestrationOperation.file_uuid,
    }

    def __init__(self, session=None):
        """
        Initialize the query helper.

        :param session: optional SQLAlchemy session supplied by callers or tests
        :type session: sqlalchemy.orm.session.Session or None

        :return: None
        :rtype: None
        """
        if session is None:
            scoped = scoped_session(Session)
            self.session = scoped()
        else:
            self.session = session

    def create_db(self):
        """
        Create all OBOA inventory tables.

        :return: None
        :rtype: None
        """
        Base.metadata.create_all(engine)

    def clear_db(self):
        """
        Delete all OBOA inventory rows.

        :return: None
        :rtype: None
        """
        for table in reversed(Base.metadata.sorted_tables):
            self.session.execute(table.delete())
        self.session.commit()

    def close_session(self):
        """
        Close the SQLAlchemy session owned by this query helper.

        :return: None
        :rtype: None
        """
        self.session.close()

    def get_active_orchestration_configuration(self):
        """
        Return the latest active orchestration configuration.

        :return: active configuration row or None
        :rtype: oboa.datamodel.orchestrated_files.OrchestrationConfiguration or None
        """
        return self.session.query(OrchestrationConfiguration).filter(
            OrchestrationConfiguration.active == True
        ).order_by(OrchestrationConfiguration.active_from.desc()).first()

    def get_orchestrated_files(self, file_uuids=None, names=None, paths=None,
                               file_group=None, reception_date_filters=None,
                               archived=None, processed=None,
                               orchestration_configuration_uuids=None,
                               order_by=None, group_by=None, selection="all",
                               limit=None, offset=None):
        """
        Query orchestrated-file inventory rows.

        :param file_uuids: file UUID text filter
        :param names: file name text filter
        :param paths: input path text filter
        :param file_group: file group text filter
        :param reception_date_filters: reception timestamp filters
        :param archived: archived boolean filter
        :param processed: processed boolean filter
        :param orchestration_configuration_uuids: configuration UUID text filter
        :param order_by: ordering descriptor with ``field`` and ``descending``
        :param group_by: optional field used to group complete entity results
        :param selection: selection rule: ``all``, ``first``, or ``last``
        :param limit: maximum number of rows
        :param offset: result offset

        :return: list of orchestrated files, or grouped dictionary
        :rtype: list or dict

        :raises InputError: when filters, ordering, grouping, or selection are
            invalid
        """
        query = self.session.query(OrchestratedFile)
        values = locals()
        query = self._apply_text_filters(query, values, self.orchestrated_file_text_fields)
        query = self._apply_date_filters(query, values, self.orchestrated_file_date_fields)
        query = self._apply_bool_filters(query, values, self.orchestrated_file_bool_fields)
        return self._finalize_query(
            query,
            self.orchestrated_file_order_fields,
            order_by=order_by,
            group_by=group_by,
            selection=selection,
            limit=limit,
            offset=offset,
        )

    def get_orchestration_configurations(self, orchestration_configuration_uuids=None,
                                         paths=None, contents=None, active=None,
                                         active_from_date_filters=None,
                                         active_until_date_filters=None,
                                         order_by=None, group_by=None,
                                         selection="all", limit=None, offset=None):
        """
        Query orchestration configuration history rows.

        :param orchestration_configuration_uuids: configuration UUID text filter
        :param paths: configuration path text filter
        :param contents: raw XML content text filter
        :param active: active boolean filter
        :param active_from_date_filters: activation timestamp filters
        :param active_until_date_filters: deactivation timestamp filters
        :param order_by: ordering descriptor with ``field`` and ``descending``
        :param group_by: optional field used to group complete entity results
        :param selection: selection rule: ``all``, ``first``, or ``last``
        :param limit: maximum number of rows
        :param offset: result offset

        :return: list of configurations, or grouped dictionary
        :rtype: list or dict

        :raises InputError: when filters, ordering, grouping, or selection are
            invalid
        """
        query = self.session.query(OrchestrationConfiguration)
        values = locals()
        query = self._apply_text_filters(query, values, self.configuration_text_fields)
        query = self._apply_date_filters(query, values, self.configuration_date_fields)
        query = self._apply_bool_filters(query, values, self.configuration_bool_fields)
        return self._finalize_query(
            query,
            self.configuration_order_fields,
            order_by=order_by,
            group_by=group_by,
            selection=selection,
            limit=limit,
            offset=offset,
        )

    def get_orchestration_operations(self, operation_uuids=None, operations=None,
                                     time_stamp_filters=None, status_filters=None,
                                     messages=None, file_uuids=None,
                                     order_by=None, group_by=None,
                                     selection="all", limit=None, offset=None):
        """
        Query orchestration operation audit rows.

        :param operation_uuids: operation UUID text filter
        :param operations: operation-name text filter
        :param time_stamp_filters: operation timestamp filters
        :param status_filters: numeric status filters
        :param messages: operation message text filter
        :param file_uuids: related file UUID text filter
        :param order_by: ordering descriptor with ``field`` and ``descending``
        :param group_by: optional field used to group complete entity results
        :param selection: selection rule: ``all``, ``first``, or ``last``
        :param limit: maximum number of rows
        :param offset: result offset

        :return: list of operation rows, or grouped dictionary
        :rtype: list or dict

        :raises InputError: when filters, ordering, grouping, or selection are
            invalid
        """
        query = self.session.query(OrchestrationOperation)
        values = locals()
        query = self._apply_text_filters(query, values, self.operation_text_fields)
        query = self._apply_date_filters(query, values, self.operation_date_fields)
        query = self._apply_number_filters(query, values, self.operation_number_fields)
        return self._finalize_query(
            query,
            self.operation_order_fields,
            order_by=order_by,
            group_by=group_by,
            selection=selection,
            limit=limit,
            offset=offset,
        )

    def _apply_text_filters(self, query, values, field_map):
        """
        Apply text filters to a SQLAlchemy query.

        :param query: SQLAlchemy query to modify
        :param values: call-local values containing filter descriptors
        :type values: dict
        :param field_map: mapping of argument names to SQLAlchemy columns
        :type field_map: dict

        :return: query with text predicates applied
        :rtype: sqlalchemy.orm.query.Query

        :raises InputError: when any text filter is malformed
        """
        for argument_name, column in field_map.items():
            value = values[argument_name]
            if value is not None:
                functions.is_valid_text_filter(value)
                query = query.filter(text_operators[value["op"]](column, value["filter"]))
        return query

    def _apply_date_filters(self, query, values, field_map):
        """
        Apply date filters to a SQLAlchemy query.

        :param query: SQLAlchemy query to modify
        :param values: call-local values containing filter descriptors
        :type values: dict
        :param field_map: mapping of argument names to SQLAlchemy columns
        :type field_map: dict

        :return: query with date predicates applied
        :rtype: sqlalchemy.orm.query.Query

        :raises InputError: when any date filter is malformed
        """
        for argument_name, column in field_map.items():
            value = values[argument_name]
            if value is not None:
                functions.is_valid_date_filters(value)
                for date_filter in value:
                    query = query.filter(
                        arithmetic_operators[date_filter["op"]](
                            column,
                            functions.parse_datetime(date_filter["date"]),
                        )
                    )
        return query

    def _apply_number_filters(self, query, values, field_map):
        """
        Apply numeric filters to a SQLAlchemy query.

        :param query: SQLAlchemy query to modify
        :param values: call-local values containing filter descriptors
        :type values: dict
        :param field_map: mapping of argument names to SQLAlchemy columns
        :type field_map: dict

        :return: query with numeric predicates applied
        :rtype: sqlalchemy.orm.query.Query

        :raises InputError: when any numeric filter is malformed
        """
        for argument_name, column in field_map.items():
            value = values[argument_name]
            if value is not None:
                functions.is_valid_number_filters(value)
                for number_filter in value:
                    query = query.filter(
                        arithmetic_operators[number_filter["op"]](
                            column,
                            number_filter["number"],
                        )
                    )
        return query

    def _apply_bool_filters(self, query, values, field_map):
        """
        Apply boolean filters to a SQLAlchemy query.

        :param query: SQLAlchemy query to modify
        :param values: call-local values containing filter descriptors
        :type values: dict
        :param field_map: mapping of argument names to SQLAlchemy columns
        :type field_map: dict

        :return: query with boolean predicates applied
        :rtype: sqlalchemy.orm.query.Query

        :raises InputError: when any boolean filter is malformed
        """
        for argument_name, column in field_map.items():
            value = values[argument_name]
            if value is not None:
                functions.is_valid_bool_filter(value)
                query = query.filter(arithmetic_operators[value["op"]](column, value["filter"]))
        return query

    def _finalize_query(self, query, order_fields, order_by=None, group_by=None,
                        selection="all", limit=None, offset=None):
        """
        Apply ordering, slicing, selection, and grouping to a query.

        :param query: SQLAlchemy query to finalize
        :param order_fields: fields accepted by ``order_by`` and ``group_by``
        :type order_fields: dict
        :param order_by: optional ordering descriptor
        :type order_by: dict or None
        :param group_by: optional entity field used to group full entity rows
        :type group_by: str or None
        :param selection: selection rule: ``all``, ``first``, or ``last``
        :type selection: str
        :param limit: maximum number of rows
        :type limit: int or None
        :param offset: result offset
        :type offset: int or None

        :return: list of entities, or grouped dictionary when ``group_by`` is set
        :rtype: list or dict

        :raises InputError: when ordering, grouping, or selection are invalid
        """
        if order_by is not None:
            functions.is_valid_order_by(order_by)
            if order_by["field"] not in order_fields:
                raise InputError("The order_by field {} is not valid.".format(order_by["field"]))
            column = order_fields[order_by["field"]]
            if order_by["descending"]:
                column = column.desc()
            query = query.order_by(column)
        elif selection == "last":
            query = query.order_by(list(order_fields.values())[0].desc())

        if offset is not None:
            query = query.offset(int(offset))
        if limit is not None:
            query = query.limit(int(limit))

        if selection == "first":
            row = query.first()
            rows = [] if row is None else [row]
        elif selection == "last":
            row = query.first()
            rows = [] if row is None else [row]
        elif selection == "all":
            rows = query.all()
        else:
            raise InputError("The selection {} is not valid.".format(selection))

        if group_by is not None:
            if group_by not in order_fields:
                raise InputError("The group_by field {} is not valid.".format(group_by))
            grouped = {}
            for row in rows:
                key_name = "file_group" if group_by == "group" else group_by
                grouped.setdefault(getattr(row, key_name), []).append(row)
            return grouped
        return rows
