"""
Tests for executable processor helpers.
"""

import datetime
import os
import unittest
import uuid
from pathlib import Path
from unittest import mock

os.environ.setdefault("OBOA_LOG_PATH", "/tmp/oboa_log")

from oboa.engine.errors import ProcessorError
from oboa.datamodel.orchestrated_files import OrchestratedFile
from oboa.processors.base_processor import execute_processor, validate_processor


INPUTS = Path(__file__).parent / "inputs"


class TestProcessors(unittest.TestCase):
    """
    Processor helper tests.
    """

    def test_execute_processor(self):
        """
        Execute a processor script with the expected file context.
        """
        processor = INPUTS / "processor_success.sh"
        path = INPUTS / "sample.txt"
        row = OrchestratedFile(
            uuid.uuid4(),
            "sample.txt",
            str(path),
            "texts",
            datetime.datetime.utcnow(),
        )

        result = execute_processor(str(processor), str(path), row)

        assert result["returncode"] == 0

    def test_validate_processor_accepts_missing_optional_processor(self):
        """
        Accept rules that do not define a data processor.
        """
        assert validate_processor(None) is True

    def test_validate_processor_rejects_missing_and_non_executable_paths(self):
        """
        Reject processor paths that cannot be executed by OBOA.
        """
        with self.assertRaises(ProcessorError):
            validate_processor(str(INPUTS / "missing_processor.sh"))
        with self.assertRaises(ProcessorError):
            validate_processor(str(INPUTS / "processor_not_executable.sh"))

    def test_execute_processor_raises_on_non_zero_exit_status(self):
        """
        Surface processor non-zero exits as processor errors.
        """
        path = INPUTS / "sample.txt"
        row = OrchestratedFile(
            uuid.uuid4(),
            "sample.txt",
            str(path),
            "texts",
            datetime.datetime.utcnow(),
        )

        with self.assertRaises(ProcessorError):
            execute_processor(str(INPUTS / "processor_failure.sh"), str(path), row)

    def test_execute_processor_wraps_subprocess_errors(self):
        """
        Convert low-level subprocess errors into OBOA processor errors.
        """
        path = INPUTS / "sample.txt"
        row = OrchestratedFile(
            uuid.uuid4(),
            "sample.txt",
            str(path),
            "texts",
            datetime.datetime.utcnow(),
        )

        with mock.patch("oboa.processors.base_processor.subprocess.run", side_effect=OSError("boom")):
            with self.assertRaises(ProcessorError):
                execute_processor(str(INPUTS / "processor_success.sh"), str(path), row)
