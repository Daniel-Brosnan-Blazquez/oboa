#!/usr/bin/env python3
"""
Script for initializing OBOA environment.

module oboa
"""

import argparse
import os
import shlex
from subprocess import PIPE, Popen

from oboa.datamodel.functions import read_configuration


config = read_configuration()
db_configuration = config["DDBB_CONFIGURATION"]


def _script_path(script_name):
    """
    Return an absolute path to a bundled helper script.

    :param script_name: helper script filename
    :type script_name: str

    :return: absolute helper script path
    :rtype: str
    """
    return os.path.join(os.path.dirname(__file__), script_name)


def execute_command(command, success_message, check_error=True):
    """
    Execute a command and stop on failure.

    :param command: shell-style command string to execute
    :type command: str
    :param success_message: message printed when the command succeeds
    :type success_message: str
    :param check_error: exit when the command returns a non-zero status
    :type check_error: bool

    :return: None
    :rtype: None

    :raises SystemExit: when ``check_error`` is true and the command fails
    """
    command_split = shlex.split(command)
    program = Popen(command_split, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    output, error = program.communicate()
    if check_error and program.returncode != 0:
        print(
            "The execution of the command {} has ended unexpectedly with the following output: {} but the following error: {}".format(
                command,
                str(output.decode()),
                str(error.decode()),
            )
        )
        exit(-1)
    print(success_message)


def init(datamodel_path=None):
    """
    Initialize the OBOA DDBB using the generated datamodel SQL file.

    :param datamodel_path: optional path to the SQL datamodel
    :type datamodel_path: str or None

    :return: None
    :rtype: None

    :raises SystemExit: when the datamodel path is invalid or initialization
        command fails
    """
    if datamodel_path is not None:
        if not os.path.isfile(datamodel_path):
            print("The specified path to the datamodel file {} does not exist".format(datamodel_path))
            exit(-1)
    else:
        # Default path for the docker environment.
        datamodel_path = "/datamodel/oboa_data_model.sql"

    database_address = db_configuration["host"]
    database_port = db_configuration["port"]
    database_name = db_configuration["database"]

    command = "{} -h {} -p {} -d {} -f {}".format(
        shlex.quote(_script_path("oboa_init_ddbb.sh")),
        database_address,
        database_port,
        database_name,
        datamodel_path,
    )
    print("The OBOA database is going to be initialized using the datamodel SQL file {}...".format(datamodel_path))
    execute_command(command, "The OBOA database has been initialized successfully :-)")


def main():
    """
    Command-line entry point.

    :return: None
    :rtype: None

    :raises SystemExit: when argument parsing fails, initialization is declined,
        or initialization fails
    """
    args_parser = argparse.ArgumentParser(description="Initialize OBOA environment.")
    args_parser.add_argument("-f", dest="datamodel_path", type=str, nargs=1, help="path to the datamodel", required=False)
    args_parser.add_argument(
        "-y",
        "--accept_everything",
        help="Accept by default every request. Be careful: this drops all existing OBOA data.",
        action="store_true",
    )

    args = args_parser.parse_args()

    if not args.accept_everything:
        continue_flag = input(
            "\n"
            "Welcome to the OBOA initializer :-)\n"
            "You are about to initialize the DDBB of the orchestration engine.\n"
            "This operation will erase all the information stored related to OBOA, would you still want to continue? [Ny]"
        )

        if continue_flag != "y":
            print("No worries! The initialization is going to be aborted :-)")
            exit(0)

    datamodel_path = None
    if args.datamodel_path is not None:
        datamodel_path = args.datamodel_path[0]

    init(datamodel_path)
    exit(0)


if __name__ == "__main__":
    main()
