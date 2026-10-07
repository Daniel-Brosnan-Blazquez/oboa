#!/usr/bin/env python3
"""
Script wrapper for the OBOA orchestrate command.
"""

from oboa.engine.commands import oboa_orchestrate


def main():
    """
    Execute the OBOA orchestrate command.

    :return: None
    :rtype: None

    :raises SystemExit: when command parsing or execution fails
    """
    oboa_orchestrate()


if __name__ == "__main__":
    main()
