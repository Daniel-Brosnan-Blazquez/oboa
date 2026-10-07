#!/usr/bin/env python3
"""
Script wrapper for the OBOA daemon command.
"""

from oboa.engine.commands import oboa_daemon


def main():
    """
    Execute the OBOA daemon command.

    :return: None
    :rtype: None

    :raises SystemExit: when command parsing or execution fails
    """
    oboa_daemon()


if __name__ == "__main__":
    main()
