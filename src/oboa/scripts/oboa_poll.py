#!/usr/bin/env python3
"""
Script wrapper for the OBOA poll command.
"""

from oboa.engine.commands import oboa_poll


def main():
    """
    Execute the OBOA poll command.

    :return: None
    :rtype: None

    :raises SystemExit: when command parsing or execution fails
    """
    oboa_poll()


if __name__ == "__main__":
    main()
