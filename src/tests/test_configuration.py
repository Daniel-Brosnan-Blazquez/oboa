"""
Tests for OBOA XML configuration parsing.
"""

import os
import unittest
from pathlib import Path
from unittest import mock

from lxml import etree

os.environ.setdefault("OBOA_LOG_PATH", "/tmp/oboa_log")

from oboa.engine.errors import OrchestrationConfigurationError
from oboa.engine.parsing import (
    _rule_from_node,
    _warn_duplicate_fields,
    get_orchestrator_configuration,
)


INPUTS = Path(__file__).parent / "inputs"


class TestConfiguration(unittest.TestCase):
    """
    Configuration parser tests.
    """

    def test_valid_configuration_returns_priority_ordered_rules(self):
        """
        Parse valid XML into an XPath evaluator over normalized rule nodes.
        """
        processor = (INPUTS / "processor_success.sh").resolve()
        path = INPUTS / "orchestrator_valid.xml"
        configuration_xpath = get_orchestrator_configuration(path)
        rules = configuration_xpath("/orchestrator_configuration/data")
        priority_ordered_rules = sorted(
            rules,
            key=lambda rule: (int(rule.get("priority")), rule.getparent().index(rule)),
        )
        matching_rules = configuration_xpath(
            "/orchestrator_configuration/data[match(data_mask, $file_name)]",
            file_name="sample.txt",
        )

        assert [rule.get("group") for rule in priority_ordered_rules] == ["high", "low"]
        assert priority_ordered_rules[0].xpath("string(data_processor)").strip() == str(processor)
        assert [rule.get("group") for rule in matching_rules] == ["high"]

    def test_unknown_group_is_rejected(self):
        """
        Reject configurations that try to use OBOA's reserved unknown group.
        """
        path = INPUTS / "orchestrator_reserved_unknown.xml"
        with self.assertRaises(OrchestrationConfigurationError):
            get_orchestrator_configuration(path)

    def test_non_executable_processor_is_rejected(self):
        """
        Reject rules whose processor path is not executable.
        """
        path = INPUTS / "orchestrator_non_executable_processor.xml"
        with self.assertRaises(OrchestrationConfigurationError):
            get_orchestrator_configuration(path)

    def test_processor_command_parameters_are_preserved(self):
        """
        Normalize processor executables without removing command parameters.
        """
        processor = (INPUTS / "processor_parameters.sh").resolve()
        configuration_xpath = get_orchestrator_configuration(
            INPUTS / "orchestrator_texts_with_processor_parameters.xml"
        )
        rule = configuration_xpath("/orchestrator_configuration/data")[0]

        assert rule.xpath("string(data_processor)").strip() == "{} -r -f %F".format(processor)

    def test_missing_malformed_and_schema_invalid_configurations_are_rejected(self):
        """
        Reject configuration files that are absent, malformed, or schema-invalid.
        """
        invalid_paths = [
            INPUTS / "missing_orchestrator.xml",
            INPUTS / "orchestrator_malformed.xml",
            INPUTS / "orchestrator_missing_required_mask.xml",
        ]
        for path in invalid_paths:
            with self.subTest(path=path):
                with self.assertRaises(OrchestrationConfigurationError):
                    get_orchestrator_configuration(path)

    def test_invalid_schema_file_is_reported(self):
        """
        Report a malformed schema file before validating a configuration.
        """
        with mock.patch("oboa.engine.parsing._schema_path", return_value=str(INPUTS / "orchestrator_malformed.xml")):
            with self.assertRaises(OrchestrationConfigurationError):
                get_orchestrator_configuration(INPUTS / "orchestrator_texts_without_processor.xml")

    def test_parser_rejects_invalid_priority_values_without_schema_validation(self):
        """
        Cover parser priority checks after schema validation is intentionally skipped.
        """
        for path in [
            INPUTS / "orchestrator_invalid_priority.xml",
            INPUTS / "orchestrator_zero_priority.xml",
        ]:
            with self.subTest(path=path):
                with self.assertRaises(OrchestrationConfigurationError):
                    get_orchestrator_configuration(path, validate_schema=False)

    def test_duplicate_fields_and_priorities_are_warned(self):
        """
        Warn operators about ambiguous but still valid duplicate configuration fields.
        """
        with self.assertLogs("oboa.engine.parsing", level="WARNING") as duplicate_logs:
            get_orchestrator_configuration(INPUTS / "orchestrator_duplicate_fields.xml")
        assert any("same group" in message for message in duplicate_logs.output)
        assert any("same data_mask" in message for message in duplicate_logs.output)

        with self.assertLogs("oboa.engine.parsing", level="WARNING") as priority_logs:
            get_orchestrator_configuration(INPUTS / "orchestrator_same_priority.xml")
        assert any("priority 1" in message for message in priority_logs.output)

    def test_duplicate_field_warning_ignores_blank_values(self):
        """
        Ignore empty duplicate-field candidates while scanning XML rules.
        """
        blank_node = etree.fromstring(
            b"""
            <data group="" priority="1">
              <data_mask></data_mask>
            </data>
            """
        )

        _warn_duplicate_fields([blank_node])

    def test_rule_from_node_keeps_relative_processors_when_no_config_dir_exists(self):
        """
        Resolve processor paths only when a configuration directory is available.
        """
        processor = os.path.relpath(INPUTS / "processor_success.sh", os.getcwd())
        expected_processor = os.path.abspath(processor)
        node = etree.fromstring(
            """
            <data group="texts" priority="1">
              <data_mask>*.txt</data_mask>
              <data_processor>{}</data_processor>
            </data>
            """.format(processor).encode("utf-8")
        )

        rule = _rule_from_node(node, 0, configuration_dir=None)

        assert rule.xpath("string(data_processor)").strip() == expected_processor
