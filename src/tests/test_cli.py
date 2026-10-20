"""
Tests for OBOA CLI commands.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("OBOA_LOG_PATH", "/tmp/oboa_log")

from oboa.engine import commands
from oboa.engine.commands import (
    _apply_runtime_overrides,
    _build_bool_filter,
    _build_order_by,
    _build_text_filter,
    _jsonify_rows,
    oboa_configure,
    oboa_daemon,
    oboa_init,
    oboa_orchestrate,
    oboa_poll,
    oboa_query,
)
from oboa.engine.errors import DaemonError, OrchestrationError
from oboa.engine.functions import default_resources_path


class JsonRow():
    """
    Minimal JSON-ready row for CLI output tests.
    """

    def __init__(self, payload):
        """
        Store the JSON payload returned by the row.
        """
        self.payload = payload

    def jsonify(self):
        """
        Return the configured JSON payload.
        """
        return self.payload


class TestCli(unittest.TestCase):
    """
    CLI smoke tests.
    """

    def setUp(self):
        """
        Preserve the caller's argv while tests exercise CLI wrappers.
        """
        self.argv = sys.argv[:]

    def tearDown(self):
        """
        Restore argv after each CLI test.
        """
        sys.argv = self.argv

    def test_init_prints_json(self):
        """
        Print the JSON success payload for non-interactive initialization.
        """
        sys.argv = ["oboa_init", "-y"]
        stdout = io.StringIO()
        with mock.patch("oboa.engine.commands.Base.metadata.create_all") as create_all:
            with contextlib.redirect_stdout(stdout):
                oboa_init()
        create_all.assert_called_once_with(commands.sqlalchemy_engine)
        assert json.loads(stdout.getvalue()) == {"initialized": True}

    def test_init_aborts_without_confirmation(self):
        """
        Leave the schema untouched when the interactive prompt is declined.
        """
        sys.argv = ["oboa_init"]
        stdout = io.StringIO()
        with mock.patch("builtins.input", return_value="n"):
            with mock.patch("oboa.engine.commands.Base.metadata.create_all") as create_all:
                with contextlib.redirect_stdout(stdout):
                    oboa_init()
        create_all.assert_not_called()
        assert "aborted" in stdout.getvalue().lower()

    def test_init_accepts_interactive_confirmation(self):
        """
        Initialize the schema when the operator confirms the prompt.
        """
        sys.argv = ["oboa_init"]
        stdout = io.StringIO()
        with mock.patch("builtins.input", return_value="y"):
            with mock.patch("oboa.engine.commands.Base.metadata.create_all") as create_all:
                with contextlib.redirect_stdout(stdout):
                    oboa_init()

        create_all.assert_called_once_with(commands.sqlalchemy_engine)
        assert json.loads(stdout.getvalue()) == {"initialized": True}

    def test_jsonify_rows_serializes_grouped_results(self):
        """
        Serialize grouped query results as JSON-ready dictionaries.
        """
        assert _jsonify_rows({"texts": [JsonRow({"name": "sample.txt"})]}) == {
            "texts": [{"name": "sample.txt"}]
        }

    def test_apply_runtime_overrides_sets_orchestration_options(self):
        """
        Merge command-line execution overrides into the engine configuration.
        """
        args = mock.Mock(
            delete_after_archive=True,
            keep_input=False,
            processing_dir="/tmp/oboa_cli_processing",
        )
        with mock.patch.dict(os.environ, {"OBOA_RESOURCES_PATH": default_resources_path()}):
            config = _apply_runtime_overrides(args)

        assert config["ORCHESTRATION"]["delete_after_archive"] is True
        assert config["ORCHESTRATION"]["processing_dir"] == "/tmp/oboa_cli_processing"

        args.keep_input = True
        with mock.patch.dict(os.environ, {"OBOA_RESOURCES_PATH": default_resources_path()}):
            config = _apply_runtime_overrides(args)

        assert config["ORCHESTRATION"]["delete_after_archive"] is False

    def test_cli_filter_builders_return_none_without_values(self):
        """
        Leave optional query filters unset when callers do not provide values.
        """
        args = mock.Mock(order_by=None, descending=False)

        assert _build_text_filter(None) is None
        assert _build_bool_filter(None) is None
        assert _build_order_by(args) is None

    def test_configure_prints_configuration_json_and_closes_engine(self):
        """
        Configure OBOA through the CLI and print the activated configuration.
        """
        sys.argv = ["oboa_configure", "--configuration", "orchestrator.xml"]
        engine = mock.Mock()
        engine.configure_orchestrator.return_value = JsonRow({"configured": True})
        stdout = io.StringIO()

        with mock.patch("oboa.engine.commands.Engine", return_value=engine):
            with contextlib.redirect_stdout(stdout):
                oboa_configure()

        engine.set_configuration_path.assert_called_once_with("orchestrator.xml")
        engine.configure_orchestrator.assert_called_once_with()
        engine.close_session.assert_called_once_with()
        assert json.loads(stdout.getvalue()) == {"configured": True}

    def test_configure_exits_with_error_and_closes_engine(self):
        """
        Convert configuration failures into CLI error exits.
        """
        sys.argv = ["oboa_configure"]
        engine = mock.Mock()
        engine.configure_orchestrator.side_effect = OrchestrationError("bad config")

        with mock.patch("oboa.engine.commands.Engine", return_value=engine):
            with self.assertRaises(SystemExit) as captured:
                oboa_configure()

        assert captured.exception.code == 1
        engine.close_session.assert_called_once_with()

    def test_orchestrate_prints_orchestrated_file_json(self):
        """
        Orchestrate an explicit file through the CLI.
        """
        sys.argv = [
            "oboa_orchestrate",
            "--file",
            "sample.txt",
            "--configuration",
            "orchestrator.xml",
            "--processing-dir",
            "/tmp/processing",
        ]
        engine = mock.Mock()
        engine.orchestrate_file.return_value = JsonRow({"name": "sample.txt"})
        stdout = io.StringIO()

        with mock.patch("oboa.engine.commands.Engine", return_value=engine):
            with mock.patch.dict(os.environ, {"OBOA_RESOURCES_PATH": default_resources_path()}):
                with contextlib.redirect_stdout(stdout):
                    oboa_orchestrate()

        engine.set_configuration_path.assert_called_once_with("orchestrator.xml")
        engine.orchestrate_file.assert_called_once_with("sample.txt")
        engine.close_session.assert_called_once_with()
        assert json.loads(stdout.getvalue()) == {"name": "sample.txt"}

    def test_orchestrate_exits_on_engine_errors(self):
        """
        Convert orchestration failures into CLI error exits.
        """
        sys.argv = ["oboa_orchestrate", "--file", "missing.txt"]
        engine = mock.Mock()
        engine.orchestrate_file.side_effect = OrchestrationError("missing")

        with mock.patch("oboa.engine.commands.Engine", return_value=engine):
            with mock.patch.dict(os.environ, {"OBOA_RESOURCES_PATH": default_resources_path()}):
                with self.assertRaises(SystemExit) as captured:
                    oboa_orchestrate()

        assert captured.exception.code == 1
        engine.close_session.assert_called_once_with()

    def test_poll_once_prints_polled_rows(self):
        """
        Poll once and serialize the produced rows.
        """
        sys.argv = [
            "oboa_poll",
            "--once",
            "--polling-dir",
            "/tmp/inbox",
            "--configuration",
            "orchestrator.xml",
        ]
        engine = mock.Mock()
        engine.poll_once.return_value = [JsonRow({"name": "sample.txt"})]
        stdout = io.StringIO()

        with mock.patch("oboa.engine.commands.Engine", return_value=engine):
            with mock.patch.dict(os.environ, {"OBOA_RESOURCES_PATH": default_resources_path()}):
                with contextlib.redirect_stdout(stdout):
                    oboa_poll()

        engine.set_configuration_path.assert_called_once_with("orchestrator.xml")
        engine.poll_once.assert_called_once_with(polling_dir="/tmp/inbox")
        engine.close_session.assert_called_once_with()
        assert json.loads(stdout.getvalue()) == [{"name": "sample.txt"}]

    def test_poll_loop_uses_runtime_options(self):
        """
        Run the CLI polling loop with directory and frequency overrides.
        """
        sys.argv = [
            "oboa_poll",
            "--polling-dir",
            "/tmp/inbox",
            "--polling-frequency",
            "0.5",
            "--keep-input",
        ]
        engine = mock.Mock()

        with mock.patch("oboa.engine.commands.Engine", return_value=engine):
            with mock.patch.dict(os.environ, {"OBOA_RESOURCES_PATH": default_resources_path()}):
                oboa_poll()

        engine.run_polling_loop.assert_called_once_with(
            polling_dir="/tmp/inbox",
            polling_frequency=0.5,
        )
        assert engine.engine_configuration["ORCHESTRATION"]["delete_after_archive"] is False
        engine.close_session.assert_called_once_with()

    def test_poll_exits_on_invalid_runtime_override(self):
        """
        Report invalid runtime override values through the CLI error path.
        """
        sys.argv = ["oboa_poll", "--once"]
        engine = mock.Mock()
        with mock.patch("oboa.engine.commands.Engine", return_value=engine):
            with mock.patch.dict(os.environ, {
                "OBOA_RESOURCES_PATH": default_resources_path(),
                "OBOA_DELETE_AFTER_ARCHIVE": "sometimes",
            }):
                with self.assertRaises(SystemExit) as captured:
                    oboa_poll()

        assert captured.exception.code == 1
        engine.close_session.assert_called_once_with()

    def test_daemon_start_stop_and_restart_print_json(self):
        """
        Dispatch daemon lifecycle actions to the daemon manager.
        """
        actions = {
            "start": ("start", {"pid": 10, "running": True}),
            "stop": ("stop", {"pid": None, "running": False}),
            "restart": ("restart", {"pid": 11, "running": True}),
        }
        for action, (method_name, payload) in actions.items():
            with self.subTest(action=action):
                manager = mock.Mock()
                getattr(manager, method_name).return_value = payload
                sys.argv = [
                    "oboa_daemon",
                    action,
                    "--pid-file",
                    "/tmp/oboa.pid",
                    "--foreground",
                    "--polling-dir",
                    "/tmp/inbox",
                    "--polling-frequency",
                    "1.5",
                    "--configuration",
                    "orchestrator.xml",
                ]
                stdout = io.StringIO()

                with mock.patch("oboa.engine.commands.DaemonManager", return_value=manager):
                    with mock.patch.dict(os.environ, {"OBOA_RESOURCES_PATH": default_resources_path()}):
                        with contextlib.redirect_stdout(stdout):
                            oboa_daemon()

                if action == "stop":
                    getattr(manager, method_name).assert_called_once_with()
                else:
                    getattr(manager, method_name).assert_called_once_with(
                        foreground=True,
                        polling_dir="/tmp/inbox",
                        polling_frequency=1.5,
                        configuration_path="orchestrator.xml",
                    )
                assert json.loads(stdout.getvalue()) == payload

    def test_daemon_errors_exit_with_status_one(self):
        """
        Convert daemon lifecycle failures into CLI error exits.
        """
        manager = mock.Mock()
        manager.start.side_effect = DaemonError("already running")
        sys.argv = ["oboa_daemon", "start", "--pid-file", "/tmp/oboa.pid"]

        with mock.patch("oboa.engine.commands.DaemonManager", return_value=manager):
            with mock.patch.dict(os.environ, {"OBOA_RESOURCES_PATH": default_resources_path()}):
                with self.assertRaises(SystemExit) as captured:
                    oboa_daemon()

        assert captured.exception.code == 1

    def test_daemon_ignores_unreachable_action_from_patched_parser(self):
        """
        Cover the defensive fall-through after argparse choices are bypassed.
        """
        args = mock.Mock(
            action="noop",
            pid_file="/tmp/oboa.pid",
            foreground=False,
            polling_dir=None,
            polling_frequency=None,
            configuration_path=None,
        )
        manager = mock.Mock()
        sys.argv = ["oboa_daemon", "noop"]

        with mock.patch("oboa.engine.commands.argparse.ArgumentParser.parse_args", return_value=args):
            with mock.patch("oboa.engine.commands.DaemonManager", return_value=manager):
                with mock.patch.dict(os.environ, {"OBOA_RESOURCES_PATH": default_resources_path()}):
                    oboa_daemon()

        manager.status.assert_not_called()
        manager.start.assert_not_called()
        manager.stop.assert_not_called()
        manager.restart.assert_not_called()

    def test_query_dispatches_files_configurations_and_operations(self):
        """
        Dispatch each query entity to the expected query interface method.
        """
        cases = [
            (
                [
                    "oboa_query",
                    "--files",
                    "--uuid",
                    "file-1",
                    "--uuid",
                    "file-2",
                    "--name",
                    "sample",
                    "--file-group",
                    "texts",
                    "--archived",
                    "true",
                    "--processed",
                    "false",
                    "--selection",
                    "last",
                    "--order-by",
                    "name",
                    "--descending",
                    "--group-by",
                    "group",
                    "--limit",
                    "5",
                    "--offset",
                    "2",
                ],
                "get_orchestrated_files",
            ),
            (
                ["oboa_query", "--configurations", "--path", "orchestrator", "--active", "false"],
                "get_orchestration_configurations",
            ),
            (
                ["oboa_query", "--operations", "--operation", "archive", "--status", "0"],
                "get_orchestration_operations",
            ),
        ]
        for argv, method_name in cases:
            with self.subTest(argv=argv):
                query = mock.Mock()
                getattr(query, method_name).return_value = [JsonRow({"ok": True})]
                sys.argv = argv
                stdout = io.StringIO()

                with mock.patch("oboa.engine.commands.Query", return_value=query):
                    with contextlib.redirect_stdout(stdout):
                        oboa_query()

                getattr(query, method_name).assert_called_once()
                query.close_session.assert_called_once_with()
                assert json.loads(stdout.getvalue()) == [{"ok": True}]

                if method_name == "get_orchestrated_files":
                    kwargs = getattr(query, method_name).call_args.kwargs
                    assert kwargs["file_uuids"] == {"filter": ["file-1", "file-2"], "op": "in"}
                    assert kwargs["processed"] == {"filter": False, "op": "=="}
                    assert kwargs["order_by"] == {"field": "name", "descending": True}
                    assert kwargs["group_by"] == "group"
                    assert kwargs["selection"] == "last"
                    assert kwargs["limit"] == 5
                    assert kwargs["offset"] == 2

    def test_query_exits_on_invalid_boolean_filter(self):
        """
        Report invalid query filter values through the CLI error path.
        """
        query = mock.Mock()
        sys.argv = ["oboa_query", "--files", "--archived", "sometimes"]

        with mock.patch("oboa.engine.commands.Query", return_value=query):
            with self.assertRaises(SystemExit) as captured:
                oboa_query()

        assert captured.exception.code == 1
        query.close_session.assert_called_once_with()

    def test_daemon_status_prints_json(self):
        """
        Report missing daemon PID files as a JSON stopped status.
        """
        root = tempfile.mkdtemp(prefix="oboa_cli_")
        try:
            pid_file = os.path.join(root, "missing.pid")
            sys.argv = ["oboa_daemon", "status", "--pid-file", pid_file]
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                oboa_daemon()
            assert json.loads(stdout.getvalue()) == {"pid": None, "running": False}
        finally:
            shutil.rmtree(root, ignore_errors=True)
