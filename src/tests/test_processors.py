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
from oboa.processors.base_processor import (
    build_processor_command,
    execute_processor,
    normalize_processor_command,
    validate_processor,
)


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

    def test_execute_processor_with_parameter_template(self):
        """
        Replace ``%F`` with the staged file path in processor commands.
        """
        processor = INPUTS / "processor_parameters.sh"
        path = INPUTS / "sample.txt"
        row = OrchestratedFile(
            uuid.uuid4(),
            "sample.txt",
            str(path),
            "texts",
            datetime.datetime.utcnow(),
        )

        result = execute_processor("{} -r -f %F".format(processor), str(path), row)

        assert result["returncode"] == 0

    def test_build_processor_command_keeps_backward_compatibility(self):
        """
        Append the file path when no explicit ``%F`` placeholder is configured.
        """
        processor = str(INPUTS / "processor_success.sh")
        path = str(INPUTS / "sample.txt")

        assert build_processor_command("{} --flag %F".format(processor), path) == [
            processor,
            "--flag",
            path,
        ]
        assert build_processor_command("{} --flag".format(processor), path) == [
            processor,
            "--flag",
            path,
        ]

    def test_validate_processor_accepts_missing_optional_processor(self):
        """
        Accept rules that do not define a data processor.
        """
        assert validate_processor(None) is True
        assert validate_processor("{} --flag".format(INPUTS / "processor_success.sh")) is True

    def test_validate_processor_rejects_missing_and_non_executable_paths(self):
        """
        Reject processor paths that cannot be executed by OBOA.
        """
        with self.assertRaises(ProcessorError):
            validate_processor(str(INPUTS / "missing_processor.sh"))
        with self.assertRaises(ProcessorError):
            validate_processor(str(INPUTS / "processor_not_executable.sh"))

    def test_normalize_processor_command_resolves_only_the_executable(self):
        """
        Preserve processor parameters while normalizing relative executables.
        """
        command = normalize_processor_command(
            "processor_parameters.sh -r -f %F",
            configuration_dir=str(INPUTS),
        )

        assert command == "{} -r -f %F".format(
            (INPUTS / "processor_parameters.sh").resolve()
        )

    def test_normalize_processor_command_accepts_path_commands(self):
        """
        Resolve command names from PATH when they are not configuration files.
        """
        with mock.patch(
            "oboa.processors.base_processor.shutil.which",
            return_value="/usr/bin/processor",
        ):
            with mock.patch(
                "oboa.processors.base_processor.os.path.isfile",
                side_effect=lambda path: path == "/usr/bin/processor",
            ):
                with mock.patch("oboa.processors.base_processor.os.access", return_value=True):
                    command = normalize_processor_command(
                        "processor -r -f %F",
                        configuration_dir=str(INPUTS),
                    )

        assert command == "/usr/bin/processor -r -f %F"

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
