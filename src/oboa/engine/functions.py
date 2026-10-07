"""
Common functions for the OBOA engine.
"""

import datetime
import json
import os

from dateutil import parser

from oboa.engine.errors import (
    InputError,
    OboaLogPathNotAvailable,
    OboaResourcesPathNotAvailable,
    OboaSchemasPathNotAvailable,
)
from oboa.engine.operators import arithmetic_operators, text_operators


def _package_path(*parts):
    """
    Build an absolute path inside the OBOA package tree.

    :param parts: path fragments below ``oboa``
    :type parts: tuple

    :return: absolute package path
    :rtype: str
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", *parts))


def default_resources_path():
    """
    Return the default package resources path.

    :return: package ``config`` directory
    :rtype: str
    """
    return _package_path("config")


def default_schemas_path():
    """
    Return the default package schemas path.

    :return: package ``schemas`` directory
    :rtype: str
    """
    return _package_path("schemas")


def get_resources_path():
    """
    Return the configured resource directory.

    :return: resource directory containing engine and datamodel configuration
    :rtype: str

    :raises OboaResourcesPathNotAvailable: when the configured directory does
        not exist or is not a directory
    """
    resources_path = os.environ.get("OBOA_RESOURCES_PATH", default_resources_path())
    if not os.path.isdir(resources_path):
        raise OboaResourcesPathNotAvailable(
            "The OBOA resources path {} is not available".format(resources_path)
        )
    return resources_path


def get_schemas_path():
    """
    Return the configured schema directory.

    :return: directory containing OBOA XML schemas
    :rtype: str

    :raises OboaSchemasPathNotAvailable: when the configured directory does not
        exist or is not a directory
    """
    schemas_path = os.environ.get("OBOA_SCHEMAS_PATH", default_schemas_path())
    if not os.path.isdir(schemas_path):
        raise OboaSchemasPathNotAvailable(
            "The OBOA schemas path {} is not available".format(schemas_path)
        )
    return schemas_path


def get_log_path():
    """
    Return the configured log directory.

    :return: log directory path
    :rtype: str

    :raises OboaLogPathNotAvailable: when the log directory cannot be created
    """
    log_path = os.environ.get("OBOA_LOG_PATH", "/tmp/oboa_log")
    try:
        os.makedirs(log_path, exist_ok=True)
    except OSError as exc:
        raise OboaLogPathNotAvailable(
            "The OBOA log path {} is not available".format(log_path)
        ) from exc
    return log_path


def read_configuration():
    """
    Read the engine configuration JSON.

    Environment variables may override selected orchestration and daemon
    settings after the JSON file is loaded.

    :return: parsed engine configuration
    :rtype: dict

    :raises OboaResourcesPathNotAvailable: when the resources directory is not
        available
    :raises InputError: when ``OBOA_DELETE_AFTER_ARCHIVE`` is not a valid
        boolean value
    :raises ValueError: when integer or floating-point environment overrides
        cannot be converted
    """
    with open(os.path.join(get_resources_path(), "engine.json"), encoding="utf-8") as json_data_file:
        config = json.load(json_data_file)

    orchestration_config = config.setdefault("ORCHESTRATION", {})
    daemon_config = config.setdefault("DAEMON", {})
    orchestration_config.setdefault("error_dir", "/oboa_error")
    daemon_config.setdefault("database_startup_attempts", 30)
    daemon_config.setdefault("database_startup_wait_seconds", 2)

    if "OBOA_POLLING_DIR" in os.environ:
        orchestration_config["polling_dir"] = os.environ["OBOA_POLLING_DIR"]
    if "OBOA_POLLING_FREQUENCY" in os.environ:
        orchestration_config["polling_frequency"] = int(os.environ["OBOA_POLLING_FREQUENCY"])
    if "OBOA_PROCESSING_DIR" in os.environ:
        orchestration_config["processing_dir"] = os.environ["OBOA_PROCESSING_DIR"]
    if "OBOA_ERROR_DIR" in os.environ:
        orchestration_config["error_dir"] = os.environ["OBOA_ERROR_DIR"]
    if "OBOA_DELETE_AFTER_ARCHIVE" in os.environ:
        orchestration_config["delete_after_archive"] = parse_bool(os.environ["OBOA_DELETE_AFTER_ARCHIVE"])
    if "OBOA_DAEMON_PID_FILE" in os.environ:
        daemon_config["pid_file"] = os.environ["OBOA_DAEMON_PID_FILE"]
    database_attempts = os.environ.get(
        "OBOA_DAEMON_DATABASE_STARTUP_ATTEMPTS",
        os.environ.get("OBOA_DDBB_STARTUP_ATTEMPTS"),
    )
    database_wait_seconds = os.environ.get(
        "OBOA_DAEMON_DATABASE_STARTUP_WAIT_SECONDS",
        os.environ.get("OBOA_DDBB_STARTUP_WAIT_SECONDS"),
    )
    if database_attempts is not None:
        daemon_config["database_startup_attempts"] = int(database_attempts)
    if database_wait_seconds is not None:
        daemon_config["database_startup_wait_seconds"] = float(database_wait_seconds)

    return config


def parse_bool(value):
    """
    Parse a boolean-like value.

    :param value: value to parse
    :type value: bool or str

    :return: parsed boolean value
    :rtype: bool

    :raises InputError: when the value cannot be interpreted as a boolean
    """
    if isinstance(value, bool):
        return value
    value = str(value).strip().lower()
    if value in ("1", "true", "yes", "y", "on"):
        return True
    if value in ("0", "false", "no", "n", "off"):
        return False
    raise InputError("{} is not a valid boolean".format(value))


def is_datetime(value):
    """
    Check whether a value is parseable as datetime.

    :param value: candidate datetime value
    :type value: object

    :return: True when the value can be parsed as a datetime
    :rtype: bool
    """
    try:
        parse_datetime(value)
    except Exception:
        return False
    return True


def parse_datetime(value):
    """
    Parse a datetime value.

    :param value: datetime object, datetime-like string, or None
    :type value: datetime.datetime or str or None

    :return: parsed datetime object, or None when the input is None
    :rtype: datetime.datetime or None

    :raises dateutil.parser.ParserError: when string parsing fails
    """
    if value is None or isinstance(value, datetime.datetime):
        return value
    return parser.parse(str(value))


def is_valid_order_by(order_by):
    """
    Validate an ordering descriptor.

    :param order_by: dictionary with ``field`` and ``descending`` keys
    :type order_by: dict

    :return: True when the descriptor is valid
    :rtype: bool

    :raises InputError: when the descriptor is malformed
    """
    if type(order_by) != dict:
        raise InputError("The parameter order_by must be a dictionary.")
    if set(order_by.keys()) != set(["field", "descending"]):
        raise InputError("Every order_by should have keys field and descending.")
    if type(order_by["field"]) != str:
        raise InputError("The key field inside order_by must be a string.")
    if type(order_by["descending"]) != bool:
        raise InputError("The key descending inside order_by must be a boolean.")
    return True


def is_valid_text_filter(text_filter):
    """
    Validate a text-filter descriptor.

    :param text_filter: dictionary with ``filter`` and ``op`` keys
    :type text_filter: dict

    :return: True when the descriptor is valid
    :rtype: bool

    :raises InputError: when the descriptor is malformed or uses an unsupported
        operator
    """
    if type(text_filter) != dict:
        raise InputError("The parameter text_filter must be a dictionary.")
    if set(text_filter.keys()) != set(["filter", "op"]):
        raise InputError("Every text_filter should have keys filter and op.")
    if text_filter["op"] not in text_operators:
        raise InputError("The specified op is not a valid text operator.")
    if text_filter["op"] in ("in", "notin"):
        if type(text_filter["filter"]) != list:
            raise InputError("The filter for in/notin operators must be a list.")
    elif type(text_filter["filter"]) != str:
        raise InputError("The filter for text operators must be a string.")
    return True


def is_valid_date_filters(date_filters):
    """
    Validate date-filter descriptors.

    :param date_filters: list of dictionaries with ``date`` and ``op`` keys
    :type date_filters: list

    :return: True when all descriptors are valid
    :rtype: bool

    :raises InputError: when any descriptor is malformed or contains an invalid
        date/operator
    """
    if type(date_filters) != list:
        raise InputError("The parameter date_filters must be a list.")
    for date_filter in date_filters:
        if type(date_filter) != dict:
            raise InputError("The parameter date_filters must contain dictionaries.")
        if set(date_filter.keys()) != set(["date", "op"]):
            raise InputError("Every date_filter should have keys date and op.")
        if date_filter["op"] not in arithmetic_operators:
            raise InputError("The specified op is not a valid operator.")
        if not is_datetime(date_filter["date"]):
            raise InputError("The specified date is not valid.")
    return True


def is_valid_number_filters(number_filters):
    """
    Validate numeric-filter descriptors.

    :param number_filters: list of dictionaries with ``number`` and ``op`` keys
    :type number_filters: list

    :return: True when all descriptors are valid
    :rtype: bool

    :raises InputError: when any descriptor is malformed or contains an invalid
        number/operator
    """
    if type(number_filters) != list:
        raise InputError("The parameter number_filters must be a list.")
    for number_filter in number_filters:
        if type(number_filter) != dict:
            raise InputError("The parameter number_filters must contain dictionaries.")
        if set(number_filter.keys()) != set(["number", "op"]):
            raise InputError("Every number_filter should have keys number and op.")
        if number_filter["op"] not in arithmetic_operators:
            raise InputError("The specified op is not a valid operator.")
        try:
            float(number_filter["number"])
        except (TypeError, ValueError) as exc:
            raise InputError("The specified number is not valid.") from exc
    return True


def is_valid_bool_filter(bool_filter):
    """
    Validate a boolean-filter descriptor.

    :param bool_filter: dictionary with ``filter`` and ``op`` keys
    :type bool_filter: dict

    :return: True when the descriptor is valid
    :rtype: bool

    :raises InputError: when the descriptor is malformed or contains an invalid
        boolean/operator
    """
    if type(bool_filter) != dict:
        raise InputError("The parameter bool_filter must be a dictionary.")
    if set(bool_filter.keys()) != set(["filter", "op"]):
        raise InputError("Every bool_filter should have keys filter and op.")
    if bool_filter["op"] not in arithmetic_operators:
        raise InputError("The specified op is not a valid operator.")
    if type(bool_filter["filter"]) != bool:
        raise InputError("The bool filter value must be a boolean.")
    return True
