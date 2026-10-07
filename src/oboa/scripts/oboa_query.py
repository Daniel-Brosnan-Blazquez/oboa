#!/usr/bin/env python3
"""
Script wrapper for the OBOA query command.
"""

from oboa.engine.commands import oboa_query


def main():
    """
    Execute the OBOA query command.

    :return: None
    :rtype: None

    :raises SystemExit: when command parsing or execution fails
    """
    oboa_query()


if __name__ == "__main__":
    main()
