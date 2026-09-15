"""
Configuration helpers for the OBOA datamodel.
"""

import json
import os

from oboa.datamodel.errors import OboaResourcesPathNotAvailable


def default_resources_path():
    """
    Return the package default resources path.

    :return: package ``config`` directory path
    :rtype: str
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config"))


def get_resources_path():
    """
    Return the configured OBOA resources path.

    :return: resource directory containing ``datamodel.json``
    :rtype: str

    :raises OboaResourcesPathNotAvailable: when the configured directory is not
        available
    """
    resources_path = os.environ.get("OBOA_RESOURCES_PATH", default_resources_path())
    if not os.path.isdir(resources_path):
        raise OboaResourcesPathNotAvailable(
            "The OBOA resources path {} is not available".format(resources_path)
        )
    return resources_path


def read_configuration():
    """
    Read the datamodel configuration JSON.

    :return: parsed datamodel configuration
    :rtype: dict

    :raises OboaResourcesPathNotAvailable: when the resources directory is not
        available
    """
    with open(os.path.join(get_resources_path(), "datamodel.json"), encoding="utf-8") as json_data_file:
        config = json.load(json_data_file)

    if "OBOA_DDBB_HOST" in os.environ:
        config["DDBB_CONFIGURATION"]["host"] = os.environ["OBOA_DDBB_HOST"]

    return config
