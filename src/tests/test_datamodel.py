"""
Tests for OBOA datamodel serialization helpers.
"""

import datetime
import os
import unittest
import uuid

os.environ.setdefault("OBOA_LOG_PATH", "/tmp/oboa_log")

from oboa.datamodel.orchestrated_files import (
    OrchestratedFile,
    OrchestrationConfiguration,
    OrchestrationOperation,
)


class TestDatamodelSerialization(unittest.TestCase):
    """
    Datamodel JSON serialization tests.
    """

    def test_jsonify_formats_missing_optional_values_as_empty_strings(self):
        """
        Serialize optional missing dates, messages, and foreign keys consistently.
        """
        now = datetime.datetime.utcnow()
        configuration = OrchestrationConfiguration(
            uuid.uuid4(),
            "/tmp/orchestrator.xml",
            now,
            "<orchestrator_configuration/>",
        )
        orchestrated_file = OrchestratedFile(
            uuid.uuid4(),
            "sample.txt",
            "/tmp/sample.txt",
            "texts",
            now,
        )
        operation = OrchestrationOperation(
            uuid.uuid4(),
            "poll",
            now,
            0,
        )

        assert configuration.jsonify()["active_until"] == ""
        assert orchestrated_file.jsonify()["orchestration_configuration_uuid"] == ""
        assert operation.jsonify()["message"] == ""
        assert operation.jsonify()["file_uuid"] == ""
