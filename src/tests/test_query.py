"""
Tests for OBOA query filters.
"""

import datetime
import os
import unittest
import uuid
from pathlib import Path

os.environ.setdefault("OBOA_LOG_PATH", "/tmp/oboa_log")

from oboa.datamodel.base import Base, engine
from oboa.datamodel.orchestrated_files import (
    OrchestratedFile,
    OrchestrationConfiguration,
    OrchestrationOperation,
)
from oboa.engine.errors import InputError
from oboa.engine.query import Query


INPUTS = Path(__file__).parent / "inputs"


class TestQuery(unittest.TestCase):
    """
    Query filter tests.
    """

    def setUp(self):
        """
        Seed query tests with one archived and one unarchived file.
        """
        Base.metadata.create_all(engine)
        self.query = Query()
        self.query.clear_db()
        self.now = datetime.datetime.utcnow()
        self.configuration = OrchestrationConfiguration(
            uuid.uuid4(),
            str(INPUTS / "orchestrator_empty.xml"),
            self.now - datetime.timedelta(minutes=1),
            (INPUTS / "orchestrator_empty.xml").read_text(encoding="utf-8"),
        )
        self.query.session.add(self.configuration)
        self.text_file = OrchestratedFile(
            uuid.uuid4(),
            "sample.txt",
            str(INPUTS / "sample.txt"),
            "texts",
            self.now,
            archived=True,
            processed=True,
            orchestration_configuration=self.configuration,
        )
        self.binary_file = OrchestratedFile(
            uuid.uuid4(),
            "sample.bin",
            str(INPUTS / "sample.bin"),
            "unknown",
            self.now + datetime.timedelta(seconds=1),
            archived=False,
            processed=True,
            orchestration_configuration=self.configuration,
        )
        self.query.session.add(self.text_file)
        self.query.session.add(self.binary_file)
        self.archive_operation = OrchestrationOperation(
            uuid.uuid4(),
            "archive",
            self.now + datetime.timedelta(seconds=2),
            10,
            message="archive failed sample.txt",
            orchestrated_file=self.text_file,
        )
        self.process_operation = OrchestrationOperation(
            uuid.uuid4(),
            "process",
            self.now + datetime.timedelta(seconds=3),
            9,
            message="processor failed",
            orchestrated_file=self.binary_file,
        )
        self.query.session.add(self.archive_operation)
        self.query.session.add(self.process_operation)
        self.query.session.commit()

    def tearDown(self):
        """
        Close the query session while leaving rows available for inspection.
        """
        self.query.close_session()

    def test_text_and_bool_filters(self):
        """
        Combine text and boolean filters when selecting orchestrated files.
        """
        rows = self.query.get_orchestrated_files(
            file_group={"filter": "texts", "op": "like"},
            archived={"filter": True, "op": "=="},
        )
        assert [row.name for row in rows] == ["sample.txt"]

    def test_group_by(self):
        """
        Group orchestrated-file query results by file group.
        """
        grouped = self.query.get_orchestrated_files(group_by="file_group")
        assert sorted(grouped.keys()) == ["texts", "unknown"]

    def test_create_db_can_be_called_more_than_once(self):
        """
        Keep schema creation idempotent for callers that initialize repeatedly.
        """
        self.query.create_db()

    def test_file_query_date_order_selection_and_pagination(self):
        """
        Apply date filters, ordering, first/last selection, limit, and offset.
        """
        rows = self.query.get_orchestrated_files(
            reception_date_filters=[{"date": self.now - datetime.timedelta(seconds=1), "op": ">"}],
            order_by={"field": "name", "descending": True},
        )
        assert [row.name for row in rows] == ["sample.txt", "sample.bin"]

        paged = self.query.get_orchestrated_files(
            order_by={"field": "name", "descending": False},
            limit=1,
            offset=1,
        )
        assert [row.name for row in paged] == ["sample.txt"]

        assert len(self.query.get_orchestrated_files(selection="first")) == 1
        assert len(self.query.get_orchestrated_files(selection="last")) == 1

    def test_configuration_query_filters_and_grouping(self):
        """
        Filter configuration history by text, date, boolean state, and grouping.
        """
        rows = self.query.get_orchestration_configurations(
            paths={"filter": "%orchestrator_empty%", "op": "like"},
            contents={"filter": "%orchestrator_configuration%", "op": "like"},
            active={"filter": True, "op": "=="},
            active_from_date_filters=[{"date": self.now - datetime.timedelta(minutes=2), "op": ">"}],
            order_by={"field": "path", "descending": True},
            selection="first",
        )
        grouped = self.query.get_orchestration_configurations(group_by="active")

        assert [row.orchestration_configuration_uuid for row in rows] == [
            self.configuration.orchestration_configuration_uuid
        ]
        assert list(grouped.keys()) == [True]

    def test_operation_query_filters_text_dates_numbers_and_selection(self):
        """
        Filter operation rows by text, dates, numeric status, related files, and ordering.
        """
        rows = self.query.get_orchestration_operations(
            operations={"filter": "archive", "op": "=="},
            messages={"filter": "%sample.txt%", "op": "like"},
            file_uuids={"filter": [self.text_file.file_uuid], "op": "in"},
            time_stamp_filters=[{"date": self.now, "op": ">"}],
            status_filters=[{"number": 10, "op": "=="}],
        )
        grouped = self.query.get_orchestration_operations(group_by="status")
        last = self.query.get_orchestration_operations(selection="last")

        assert [row.operation for row in rows] == ["archive"]
        assert sorted(grouped.keys()) == [9, 10]
        assert len(last) == 1

    def test_query_rejects_invalid_order_group_and_selection(self):
        """
        Reject invalid final query controls on public query interfaces.
        """
        invalid_calls = [
            lambda: self.query.get_orchestrated_files(order_by={"field": "bad", "descending": False}),
            lambda: self.query.get_orchestrated_files(group_by="bad"),
            lambda: self.query.get_orchestrated_files(selection="middle"),
            lambda: self.query.get_orchestration_configurations(order_by={"field": "bad", "descending": False}),
            lambda: self.query.get_orchestration_configurations(group_by="bad"),
            lambda: self.query.get_orchestration_configurations(selection="middle"),
            lambda: self.query.get_orchestration_operations(order_by={"field": "bad", "descending": False}),
            lambda: self.query.get_orchestration_operations(group_by="bad"),
            lambda: self.query.get_orchestration_operations(selection="middle"),
        ]
        for call in invalid_calls:
            with self.subTest(call=call):
                with self.assertRaises(InputError):
                    call()
