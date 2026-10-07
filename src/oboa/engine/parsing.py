"""
XML parsing helpers for OBOA orchestration configuration.
"""

import logging
import os
from collections import defaultdict

from lxml import etree

from oboa.engine.errors import OrchestrationConfigurationError
from oboa.engine.functions import get_schemas_path
from oboa.engine.xpath_functions import register_xpath_functions


logger = logging.getLogger(__name__)
RESERVED_GROUPS = {"unknown"}


def _schema_path():
    """
    Return the OBOA orchestration schema path.

    :return: absolute schema path
    :rtype: str

    :raises OboaSchemasPathNotAvailable: when the schema directory is not
        available
    """
    return os.path.join(get_schemas_path(), "oboa_orchestrator_configuration.xsd")


def _validate_with_lxml(configuration_xml):
    """
    Validate an XML configuration with the OBOA XSD.

    :param configuration_xml: parsed XML configuration file
    :type configuration_xml: lxml.etree._ElementTree

    :return: None
    :rtype: None

    :raises OrchestrationConfigurationError: when the schema is malformed or the
        configuration does not pass validation
    """
    try:
        xml_schema = etree.XMLSchema(etree.parse(_schema_path()))
    except etree.XMLSyntaxError as exc:
        raise OrchestrationConfigurationError("The schema file is not valid XML: {}".format(exc))
    if not xml_schema.validate(configuration_xml):
        errors = "\n".join([str(error) for error in xml_schema.error_log])
        raise OrchestrationConfigurationError(
            "The configuration does not pass the schema validation: {}".format(errors)
        )


def _warn_duplicate_fields(data_nodes):
    """
    Log warnings for duplicate rule groups or masks.

    :param data_nodes: XML ``data`` rule nodes
    :type data_nodes: list

    :return: None
    :rtype: None
    """
    extractors = {
        "group": lambda node: node.get("group"),
        "data_mask": lambda node: node.xpath("string(data_mask)").strip(),
    }
    for field_name, extractor in extractors.items():
        values = defaultdict(list)
        for node in data_nodes:
            value = extractor(node)
            if value is not None and str(value).strip() != "":
                values[str(value).strip()].append(node)
        for value, duplicated_nodes in values.items():
            if len(duplicated_nodes) > 1:
                lines = [
                    str(node.sourceline)
                    for node in duplicated_nodes
                    if node.sourceline is not None
                ]
                line_message = " at lines {}".format(", ".join(lines)) if lines else ""
                logger.warning(
                    "Orchestration configuration contains multiple data nodes with the same {} '{}'{}.".format(
                        field_name,
                        value,
                        line_message,
                    )
                )


def _rule_from_node(node, index=0, configuration_dir=None):
    """
    Validate and normalize one XML rule node.

    Relative processor paths are resolved against ``configuration_dir``.

    :param node: XML ``data`` rule node
    :type node: lxml.etree._Element
    :param index: rule position in XML order
    :type index: int
    :param configuration_dir: directory containing the XML configuration
    :type configuration_dir: str or None

    :return: normalized XML rule node
    :rtype: lxml.etree._Element

    :raises OrchestrationConfigurationError: when the rule uses a reserved
        group, invalid priority, or non-executable processor
    """
    group = node.get("group").strip()
    if group in RESERVED_GROUPS:
        raise OrchestrationConfigurationError(
            "The group value {} is reserved by OBOA".format(group)
        )
    try:
        priority = int(node.get("priority"))
    except (TypeError, ValueError) as exc:
        raise OrchestrationConfigurationError("The priority must be an integer") from exc
    if priority < 1:
        raise OrchestrationConfigurationError("The priority must be greater than zero")

    data_processor = node.xpath("string(data_processor)").strip()
    if data_processor != "":
        data_processor = os.path.expanduser(data_processor)
        if not os.path.isabs(data_processor) and configuration_dir is not None:
            data_processor = os.path.join(configuration_dir, data_processor)
        data_processor = os.path.abspath(data_processor)
        if not (os.path.isfile(data_processor) and os.access(data_processor, os.X_OK)):
            raise OrchestrationConfigurationError(
                "The data_processor {} is not an executable file".format(data_processor)
            )
        data_processor_nodes = node.xpath("data_processor")
        if data_processor_nodes:
            data_processor_nodes[0].text = data_processor

    return node


def get_orchestrator_configuration(configuration_path, validate_schema=True):
    """
    Parse and validate an OBOA orchestration configuration.

    :param configuration_path: path to the XML configuration file
    :type configuration_path: str
    :param validate_schema: flag indicating whether to validate against the XSD
    :type validate_schema: bool

    :return: XPath evaluator for the parsed configuration
    :rtype: lxml.etree.XPathEvaluator

    :raises OrchestrationConfigurationError: when the configuration is missing,
        malformed, invalid, or references an invalid processor
    """
    if not os.path.exists(configuration_path):
        raise OrchestrationConfigurationError(
            "The configuration file {} does not exist".format(configuration_path)
        )
    try:
        configuration_xml = etree.parse(configuration_path)
    except etree.XMLSyntaxError as exc:
        raise OrchestrationConfigurationError("The configuration file is not valid XML: {}".format(exc))

    if validate_schema:
        _validate_with_lxml(configuration_xml)

    data_nodes = configuration_xml.xpath("/orchestrator_configuration/data")
    _warn_duplicate_fields(data_nodes)

    configuration_dir = os.path.dirname(os.path.abspath(configuration_path))
    for index, node in enumerate(data_nodes):
        _rule_from_node(node, index, configuration_dir=configuration_dir)

    priorities = defaultdict(list)
    for node in data_nodes:
        priorities[int(node.get("priority"))].append(node)
    for priority, priority_nodes in priorities.items():
        if len(priority_nodes) > 1:
            logger.warning(
                "Orchestration configuration contains %s data nodes with priority %s; XML order will be preserved.",
                len(priority_nodes),
                priority,
            )

    register_xpath_functions()
    return etree.XPathEvaluator(configuration_xml)
