"""
Tests for OBOA function helpers.
"""

import datetime
import os
import unittest
from unittest import mock

os.environ.setdefault("OBOA_LOG_PATH", "/tmp/oboa_log")

from oboa.datamodel import functions as datamodel_functions
from oboa.datamodel.errors import OboaResourcesPathNotAvailable as DatamodelResourcesPathNotAvailable
from oboa.engine import functions as engine_functions
from oboa.engine.errors import (
    InputError,
    OboaLogPathNotAvailable,
    OboaResourcesPathNotAvailable,
    OboaSchemasPathNotAvailable,
)


class TestFunctionHelpers(unittest.TestCase):
    """
    Function helper tests.
    """

    def test_default_paths_point_to_packaged_resources(self):
        """
        Resolve default resource and schema paths inside the OBOA package.
        """
        assert os.path.isdir(engine_functions.default_resources_path())
        assert os.path.isdir(engine_functions.default_schemas_path())
        assert os.path.isdir(datamodel_functions.default_resources_path())

    def test_invalid_resource_schema_and_log_paths_are_rejected(self):
        """
        Reject unavailable configured paths before the engine uses them.
        """
        missing_path = "/tmp/oboa_missing_path_for_tests"
        with mock.patch.dict(os.environ, {"OBOA_RESOURCES_PATH": missing_path}):
            with self.assertRaises(OboaResourcesPathNotAvailable):
                engine_functions.get_resources_path()
            with self.assertRaises(DatamodelResourcesPathNotAvailable):
                datamodel_functions.get_resources_path()

        with mock.patch.dict(os.environ, {"OBOA_SCHEMAS_PATH": missing_path}):
            with self.assertRaises(OboaSchemasPathNotAvailable):
                engine_functions.get_schemas_path()

        with mock.patch("oboa.engine.functions.os.makedirs", side_effect=OSError("denied")):
            with self.assertRaises(OboaLogPathNotAvailable):
                engine_functions.get_log_path()

    def test_read_configuration_applies_environment_overrides(self):
        """
        Apply runtime environment overrides to the packaged engine configuration.
        """
        env = {
            "OBOA_RESOURCES_PATH": engine_functions.default_resources_path(),
            "OBOA_POLLING_DIR": "/tmp/oboa_polling_override",
            "OBOA_POLLING_FREQUENCY": "7",
            "OBOA_PROCESSING_DIR": "/tmp/oboa_processing_override",
            "OBOA_ERROR_DIR": "/tmp/oboa_error_override",
            "OBOA_DELETE_AFTER_ARCHIVE": "off",
            "OBOA_DAEMON_PID_FILE": "/tmp/oboa_override.pid",
            "OBOA_DAEMON_DATABASE_STARTUP_ATTEMPTS": "5",
            "OBOA_DAEMON_DATABASE_STARTUP_WAIT_SECONDS": "0.25",
        }
        with mock.patch.dict(os.environ, env):
            config = engine_functions.read_configuration()

        assert config["ORCHESTRATION"]["polling_dir"] == "/tmp/oboa_polling_override"
        assert config["ORCHESTRATION"]["polling_frequency"] == 7
        assert config["ORCHESTRATION"]["processing_dir"] == "/tmp/oboa_processing_override"
        assert config["ORCHESTRATION"]["error_dir"] == "/tmp/oboa_error_override"
        assert config["ORCHESTRATION"]["delete_after_archive"] is False
        assert config["DAEMON"]["pid_file"] == "/tmp/oboa_override.pid"
        assert config["DAEMON"]["database_startup_attempts"] == 5
        assert config["DAEMON"]["database_startup_wait_seconds"] == 0.25

    def test_read_configuration_accepts_database_startup_aliases(self):
        """
        Apply DDBB-named daemon database startup retry overrides.
        """
        env = {
            "OBOA_RESOURCES_PATH": engine_functions.default_resources_path(),
            "OBOA_DDBB_STARTUP_ATTEMPTS": "3",
            "OBOA_DDBB_STARTUP_WAIT_SECONDS": "1.5",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = engine_functions.read_configuration()

        assert config["DAEMON"]["database_startup_attempts"] == 3
        assert config["DAEMON"]["database_startup_wait_seconds"] == 1.5

    def test_read_configuration_uses_defaults_when_optional_env_is_absent(self):
        """
        Keep packaged defaults when optional runtime environment variables are absent.
        """
        with mock.patch.dict(os.environ, {
            "OBOA_RESOURCES_PATH": engine_functions.default_resources_path(),
        }, clear=True):
            config = engine_functions.read_configuration()

        assert config["ORCHESTRATION"]["polling_dir"] == "/oboa_polling"
        assert config["ORCHESTRATION"]["processing_dir"] == "/oboa_processing"
        assert config["ORCHESTRATION"]["error_dir"] == "/oboa_error"
        assert config["DAEMON"]["pid_file"] == "/tmp/oboa.pid"
        assert config["DAEMON"]["database_startup_attempts"] == 30
        assert config["DAEMON"]["database_startup_wait_seconds"] == 2

    def test_datamodel_configuration_applies_database_host_override(self):
        """
        Apply the datamodel database host override from the environment.
        """
        env = {
            "OBOA_RESOURCES_PATH": datamodel_functions.default_resources_path(),
            "OBOA_DDBB_HOST": "db.example.test",
        }
        with mock.patch.dict(os.environ, env):
            config = datamodel_functions.read_configuration()

        assert config["DDBB_CONFIGURATION"]["host"] == "db.example.test"

    def test_datamodel_configuration_uses_default_host_without_override(self):
        """
        Keep the packaged datamodel host when no override is configured.
        """
        with mock.patch.dict(os.environ, {
            "OBOA_RESOURCES_PATH": datamodel_functions.default_resources_path(),
        }, clear=True):
            config = datamodel_functions.read_configuration()

        assert config["DDBB_CONFIGURATION"]["host"] != "db.example.test"

    def test_read_configuration_rejects_invalid_environment_values(self):
        """
        Surface invalid environment values as parser errors.
        """
        with mock.patch.dict(os.environ, {
            "OBOA_RESOURCES_PATH": engine_functions.default_resources_path(),
            "OBOA_DELETE_AFTER_ARCHIVE": "sometimes",
        }):
            with self.assertRaises(InputError):
                engine_functions.read_configuration()

        with mock.patch.dict(os.environ, {
            "OBOA_RESOURCES_PATH": engine_functions.default_resources_path(),
            "OBOA_POLLING_FREQUENCY": "slow",
        }):
            with self.assertRaises(ValueError):
                engine_functions.read_configuration()

    def test_parse_bool_accepts_booleans_and_rejects_unknown_values(self):
        """
        Parse native booleans and reject text outside the accepted vocabulary.
        """
        assert engine_functions.parse_bool(True) is True
        assert engine_functions.parse_bool(False) is False
        with self.assertRaises(InputError):
            engine_functions.parse_bool("maybe")

    def test_datetime_helpers_parse_supported_inputs(self):
        """
        Parse datetime objects, strings, None, and reject malformed dates.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        assert engine_functions.parse_datetime(now) is now
        assert engine_functions.parse_datetime(None) is None
        assert engine_functions.parse_datetime("2026-08-07T12:30:00").year == 2026
        assert engine_functions.is_datetime("2026-08-07T12:30:00") is True
        assert engine_functions.is_datetime("not-a-date") is False

    def test_order_text_date_number_and_bool_validator_failures(self):
        """
        Validate all public filter descriptors and their failure branches.
        """
        invalid_descriptors = [
            (engine_functions.is_valid_order_by, "name"),
            (engine_functions.is_valid_order_by, {"field": "name"}),
            (engine_functions.is_valid_order_by, {"field": 1, "descending": False}),
            (engine_functions.is_valid_order_by, {"field": "name", "descending": "no"}),
            (engine_functions.is_valid_text_filter, "sample"),
            (engine_functions.is_valid_text_filter, {"filter": "sample"}),
            (engine_functions.is_valid_text_filter, {"filter": "sample", "op": "bad"}),
            (engine_functions.is_valid_text_filter, {"filter": "sample", "op": "in"}),
            (engine_functions.is_valid_text_filter, {"filter": 10, "op": "like"}),
            (engine_functions.is_valid_date_filters, {"date": "2026-08-07", "op": "=="}),
            (engine_functions.is_valid_date_filters, ["2026-08-07"]),
            (engine_functions.is_valid_date_filters, [{"date": "2026-08-07"}]),
            (engine_functions.is_valid_date_filters, [{"date": "2026-08-07", "op": "bad"}]),
            (engine_functions.is_valid_date_filters, [{"date": "not-a-date", "op": "=="}]),
            (engine_functions.is_valid_number_filters, {"number": 1, "op": "=="}),
            (engine_functions.is_valid_number_filters, [1]),
            (engine_functions.is_valid_number_filters, [{"number": 1}]),
            (engine_functions.is_valid_number_filters, [{"number": 1, "op": "bad"}]),
            (engine_functions.is_valid_number_filters, [{"number": "many", "op": "=="}]),
            (engine_functions.is_valid_bool_filter, True),
            (engine_functions.is_valid_bool_filter, {"filter": True}),
            (engine_functions.is_valid_bool_filter, {"filter": True, "op": "bad"}),
            (engine_functions.is_valid_bool_filter, {"filter": "true", "op": "=="}),
        ]
        for validator, descriptor in invalid_descriptors:
            with self.subTest(validator=validator.__name__, descriptor=descriptor):
                with self.assertRaises(InputError):
                    validator(descriptor)

        assert engine_functions.is_valid_text_filter({"filter": ["a", "b"], "op": "in"})
        assert engine_functions.is_valid_date_filters([{"date": "2026-08-07", "op": "=="}])
        assert engine_functions.is_valid_number_filters([{"number": "3.14", "op": ">"}])
        assert engine_functions.is_valid_bool_filter({"filter": True, "op": "=="})


def test_parse_bool():
    """
    Parse accepted true and false string values.
    """
    assert engine_functions.parse_bool("true") is True
    assert engine_functions.parse_bool("no") is False
