"""
XPath extension functions for OBOA orchestration configuration matching.
"""

import fnmatch

from lxml import etree


def _xpath_match(context, source_mask, file_name):
    """
    XPath extension function to match file names against configured masks.

    :param context: lxml XPath extension context
    :type context: object
    :param source_mask: mask node, node list, or string
    :type source_mask: object
    :param file_name: file name supplied by the XPath caller
    :type file_name: object

    :return: True when any mask matches the file name
    :rtype: bool
    """
    if isinstance(file_name, list):
        file_name = file_name[0] if file_name else ""
    masks = source_mask if isinstance(source_mask, list) else [source_mask]
    for mask in masks:
        if hasattr(mask, "text"):
            mask = mask.text
        if mask is not None and fnmatch.fnmatch(str(file_name), str(mask)):
            return True
    return False


def register_xpath_functions():
    """
    Register OBOA XPath extension functions with lxml.

    :return: None
    :rtype: None
    """
    xpath_namespace = etree.FunctionNamespace(None)
    xpath_namespace["match"] = _xpath_match
