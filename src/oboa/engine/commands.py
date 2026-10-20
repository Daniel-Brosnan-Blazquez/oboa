"""
Command line utilities for OBOA.
"""

import argparse
import json
import sys

from oboa.datamodel.base import Base, engine as sqlalchemy_engine
from oboa.engine.daemon import DaemonManager
from oboa.engine.engine import Engine
from oboa.engine.errors import DaemonError, OboaError
from oboa.engine.functions import parse_bool, read_configuration
from oboa.engine.query import Query
from oboa.logging import Log


logging = Log(name=__name__)
logger = logging.logger


def _print_json(payload):
    """
    Print a JSON payload to standard output.

    :param payload: JSON-serializable payload
    :type payload: object

    :return: None
    :rtype: None

    :raises TypeError: when the payload cannot be serialized as JSON
    """
    print(json.dumps(payload, indent=2, sort_keys=True))


def _jsonify_rows(rows):
    """
    Serialize query results to JSON-ready dictionaries.

    :param rows: list of model rows or grouped row dictionary
    :type rows: list or dict

    :return: JSON-ready list or grouped dictionary
    :rtype: list or dict
    """
    if isinstance(rows, dict):
        return {
            str(group): [row.jsonify() for row in group_rows]
            for group, group_rows in rows.items()
        }
    return [row.jsonify() for row in rows]


def _exit_with_error(parser, message):
    """
    Exit an argparse command with a formatted error message.

    :param parser: argument parser handling the command
    :type parser: argparse.ArgumentParser
    :param message: error message
    :type message: object

    :return: None
    :rtype: None

    :raises SystemExit: always exits through ``parser.exit``
    """
    parser.exit(status=1, message="error: {}\n".format(message))


def _add_common_execution_arguments(parser):
    """
    Add common orchestration execution arguments to a parser.

    :param parser: parser to mutate
    :type parser: argparse.ArgumentParser

    :return: None
    :rtype: None
    """
    parser.add_argument("--configuration", dest="configuration_path")
    parser.add_argument("--delete-after-archive", action="store_true", dest="delete_after_archive")
    parser.add_argument("--keep-input", action="store_true", dest="keep_input")
    parser.add_argument("--processing-dir", dest="processing_dir")


def _apply_runtime_overrides(args):
    """
    Apply command-line runtime overrides to engine configuration.

    :param args: parsed argparse namespace
    :type args: argparse.Namespace

    :return: engine configuration with overrides applied
    :rtype: dict

    :raises InputError: when boolean environment overrides are invalid
    """
    config = read_configuration()
    orchestration_config = config.setdefault("ORCHESTRATION", {})
    if getattr(args, "delete_after_archive", False):
        orchestration_config["delete_after_archive"] = True
    if getattr(args, "keep_input", False):
        orchestration_config["delete_after_archive"] = False
    if getattr(args, "processing_dir", None) is not None:
        orchestration_config["processing_dir"] = args.processing_dir
    return config


def oboa_init():
    """
    Initialize the OBOA database.

    :return: None
    :rtype: None

    :raises SystemExit: when argument parsing fails
    """
    parser = argparse.ArgumentParser(description="Initialize OBOA database.")
    parser.add_argument("-f", dest="datamodel_path", required=False)
    parser.add_argument("-y", "--accept_everything", action="store_true")
    args = parser.parse_args()
    if not args.accept_everything:
        answer = input(
            "This operation will create OBOA database tables and may overwrite existing schema state. Continue? [Ny]"
        )
        if answer != "y":
            print("Initialization aborted.")
            return
    Base.metadata.create_all(sqlalchemy_engine)
    _print_json({"initialized": True})


def oboa_configure():
    """
    Validate and activate an orchestration configuration.

    :return: None
    :rtype: None

    :raises SystemExit: when argument parsing fails or configuration fails
    """
    parser = argparse.ArgumentParser(description="Configure OBOA orchestration.")
    parser.add_argument("--configuration", required=False, dest="configuration_path")
    args = parser.parse_args()
    engine = Engine()
    try:
        if args.configuration_path is not None:
            engine.set_configuration_path(args.configuration_path)
        configuration = engine.configure_orchestrator()
        _print_json(configuration.jsonify())
    except OboaError as exc:
        _exit_with_error(parser, exc)
    finally:
        engine.close_session()


def oboa_orchestrate():
    """
    Orchestrate one explicit file.

    :return: None
    :rtype: None

    :raises SystemExit: when argument parsing or orchestration fails
    """
    parser = argparse.ArgumentParser(description="Orchestrate one file with OBOA.")
    parser.add_argument("-f", "--file", required=True, dest="file_path")
    _add_common_execution_arguments(parser)
    args = parser.parse_args()
    engine = Engine()
    try:
        engine.engine_configuration = _apply_runtime_overrides(args)
        if args.configuration_path is not None:
            engine.set_configuration_path(args.configuration_path)
        row = engine.orchestrate_file(args.file_path)
        _print_json(row.jsonify())
    except OboaError as exc:
        _exit_with_error(parser, exc)
    finally:
        engine.close_session()


def oboa_poll():
    """
    Poll the configured input directory.

    :return: None
    :rtype: None

    :raises SystemExit: when argument parsing or polling fails
    """
    parser = argparse.ArgumentParser(description="Poll OBOA input directory.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--polling-dir", dest="polling_dir")
    parser.add_argument("--polling-frequency", type=float, dest="polling_frequency")
    _add_common_execution_arguments(parser)
    args = parser.parse_args()
    engine = Engine()
    try:
        engine.engine_configuration = _apply_runtime_overrides(args)
        if args.configuration_path is not None:
            engine.set_configuration_path(args.configuration_path)
        if args.once:
            rows = engine.poll_once(polling_dir=args.polling_dir)
            _print_json(_jsonify_rows(rows))
        else:
            engine.run_polling_loop(
                polling_dir=args.polling_dir,
                polling_frequency=args.polling_frequency,
            )
    except OboaError as exc:
        _exit_with_error(parser, exc)
    finally:
        engine.close_session()


def oboa_daemon():
    """
    Manage the OBOA daemon.

    :return: None
    :rtype: None

    :raises SystemExit: when argument parsing or daemon management fails
    """
    parser = argparse.ArgumentParser(description="Manage OBOA daemon.")
    parser.add_argument("action", choices=["start", "stop", "restart", "status"])
    parser.add_argument("--pid-file", dest="pid_file")
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("--polling-dir", dest="polling_dir")
    parser.add_argument("--polling-frequency", type=float, dest="polling_frequency")
    parser.add_argument("--configuration", dest="configuration_path")
    args = parser.parse_args()
    config = read_configuration()
    pid_file = args.pid_file or config.get("DAEMON", {}).get("pid_file") or "/tmp/oboa.pid"
    manager = DaemonManager(pid_file)
    try:
        if args.action == "status":
            _print_json(manager.status())
        elif args.action == "start":
            _print_json(manager.start(
                foreground=args.foreground,
                polling_dir=args.polling_dir,
                polling_frequency=args.polling_frequency,
                configuration_path=args.configuration_path,
            ))
        elif args.action == "stop":
            _print_json(manager.stop())
        elif args.action == "restart":
            _print_json(manager.restart(
                foreground=args.foreground,
                polling_dir=args.polling_dir,
                polling_frequency=args.polling_frequency,
                configuration_path=args.configuration_path,
            ))
    except DaemonError as exc:
        _exit_with_error(parser, exc)


def _build_text_filter(value):
    """
    Build a text ``like`` filter descriptor.

    :param value: text filter value
    :type value: str or None

    :return: filter descriptor or None
    :rtype: dict or None
    """
    if value is None:
        return None
    return {"filter": value, "op": "like"}


def _build_bool_filter(value):
    """
    Build an equality boolean filter descriptor.

    :param value: boolean-like value
    :type value: str or bool or None

    :return: filter descriptor or None
    :rtype: dict or None

    :raises InputError: when the value is not a valid boolean
    """
    if value is None:
        return None
    return {"filter": parse_bool(value), "op": "=="}


def _build_order_by(args):
    """
    Build an ordering descriptor from parsed CLI arguments.

    :param args: parsed argparse namespace
    :type args: argparse.Namespace

    :return: ordering descriptor or None
    :rtype: dict or None
    """
    if args.order_by is None:
        return None
    return {"field": args.order_by, "descending": args.descending}


def oboa_query():
    """
    Query OBOA inventory tables.

    :return: None
    :rtype: None

    :raises SystemExit: when argument parsing or query validation fails
    """
    parser = argparse.ArgumentParser(description="Query OBOA inventory.")
    entity = parser.add_mutually_exclusive_group(required=True)
    entity.add_argument("--files", action="store_true")
    entity.add_argument("--configurations", action="store_true")
    entity.add_argument("--operations", action="store_true")
    parser.add_argument("--uuid", action="append", dest="uuids")
    parser.add_argument("--name")
    parser.add_argument("--path")
    parser.add_argument("--file-group")
    parser.add_argument("--operation")
    parser.add_argument("--status", type=int)
    parser.add_argument("--active")
    parser.add_argument("--archived")
    parser.add_argument("--processed")
    parser.add_argument("--selection", choices=["all", "first", "last"], default="all")
    parser.add_argument("--order-by", dest="order_by")
    parser.add_argument("--descending", action="store_true")
    parser.add_argument("--group-by", dest="group_by")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--offset", type=int)
    args = parser.parse_args()
    query = Query()
    order_by = _build_order_by(args)
    try:
        common = {
            "order_by": order_by,
            "group_by": args.group_by,
            "selection": args.selection,
            "limit": args.limit,
            "offset": args.offset,
        }
        if args.files:
            rows = query.get_orchestrated_files(
                file_uuids={"filter": args.uuids, "op": "in"} if args.uuids else None,
                names=_build_text_filter(args.name),
                paths=_build_text_filter(args.path),
                file_group=_build_text_filter(args.file_group),
                archived=_build_bool_filter(args.archived),
                processed=_build_bool_filter(args.processed),
                **common
            )
        elif args.configurations:
            rows = query.get_orchestration_configurations(
                orchestration_configuration_uuids={"filter": args.uuids, "op": "in"} if args.uuids else None,
                paths=_build_text_filter(args.path),
                active=_build_bool_filter(args.active),
                **common
            )
        else:
            rows = query.get_orchestration_operations(
                operation_uuids={"filter": args.uuids, "op": "in"} if args.uuids else None,
                operations=_build_text_filter(args.operation),
                status_filters=[{"number": args.status, "op": "=="}] if args.status is not None else None,
                **common
            )
        _print_json(_jsonify_rows(rows))
    except OboaError as exc:
        _exit_with_error(parser, exc)
    finally:
        query.close_session()
