#!/usr/bin/env python3
"""
Script wrapper for the OBOA configure command.
"""

from oboa.engine.commands import oboa_configure


def main():
    """
    Execute the OBOA configure command.

    :return: None
    :rtype: None

    :raises SystemExit: when command parsing or execution fails
    """
    oboa_configure()


if __name__ == "__main__":
    main()
