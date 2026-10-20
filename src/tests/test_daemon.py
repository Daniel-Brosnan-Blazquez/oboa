"""
Tests for OBOA daemon helpers.
"""

import os
import signal
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("OBOA_LOG_PATH", "/tmp/oboa_log")

from oboa.engine.daemon import DaemonManager
from oboa.engine.errors import DaemonError


INPUTS = Path(__file__).parent / "inputs"


class TestDaemon(unittest.TestCase):
    """
    Daemon state tests that avoid forking.
    """

    def test_status_removes_stale_pid_file(self):
        """
        Treat stale PID files as stopped daemons and remove the file.
        """
        root = tempfile.mkdtemp(prefix="oboa_daemon_")
        pid_file = os.path.join(root, "oboa.pid")
        try:
            shutil.copy2(str(INPUTS / "stale_oboa.pid"), pid_file)
            manager = DaemonManager(pid_file)

            status = manager.status()

            assert status == {"running": False, "pid": None}
            assert not os.path.exists(pid_file)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_read_pid_handles_missing_and_invalid_pid_files(self):
        """
        Return None for PID files that are absent or not numeric.
        """
        root = tempfile.mkdtemp(prefix="oboa_daemon_")
        try:
            missing = os.path.join(root, "missing.pid")
            invalid = os.path.join(root, "invalid.pid")
            shutil.copy2(str(INPUTS / "invalid_oboa.pid"), invalid)

            assert DaemonManager(missing)._read_pid() is None
            assert DaemonManager(invalid)._read_pid() is None
            assert DaemonManager(None).pid_file == "/tmp/oboa.pid"
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pid_running_uses_signal_zero(self):
        """
        Check process liveness through ``os.kill(pid, 0)``.
        """
        manager = DaemonManager("/tmp/oboa.pid")
        with mock.patch("oboa.engine.daemon.os.kill") as kill:
            assert manager._pid_running(100) is True
        kill.assert_called_once_with(100, 0)

        with mock.patch("oboa.engine.daemon.os.kill", side_effect=OSError("missing")):
            assert manager._pid_running(100) is False

    def test_status_reports_running_pid(self):
        """
        Report a daemon as running when the PID file points to a live process.
        """
        root = tempfile.mkdtemp(prefix="oboa_daemon_")
        pid_file = os.path.join(root, "oboa.pid")
        try:
            with open(pid_file, "w", encoding="utf-8") as file_handler:
                file_handler.write("123")
            manager = DaemonManager(pid_file)

            with mock.patch.object(manager, "_pid_running", return_value=True):
                status = manager.status()

            assert status == {"running": True, "pid": 123}
            assert os.path.exists(pid_file)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_start_foreground_runs_engine_in_current_process(self):
        """
        Run foreground daemon mode without forking.
        """
        root = tempfile.mkdtemp(prefix="oboa_daemon_")
        pid_file = os.path.join(root, "oboa.pid")
        try:
            preflight_engine = mock.Mock()
            runtime_engine = mock.Mock()
            manager = DaemonManager(pid_file)

            with mock.patch.object(manager, "status", return_value={"running": False, "pid": None}):
                with mock.patch(
                    "oboa.engine.daemon.Engine",
                    side_effect=[preflight_engine, runtime_engine],
                ) as engine_class:
                    with mock.patch("oboa.engine.daemon.os.getpid", return_value=4321):
                        status = manager.start(
                            foreground=True,
                            polling_dir="/tmp/inbox",
                            polling_frequency=2,
                            configuration_path="orchestrator.xml",
                        )

            assert engine_class.call_count == 2
            preflight_engine.set_configuration_path.assert_called_once_with("orchestrator.xml")
            preflight_engine.validate_daemon_startup.assert_called_once_with(
                polling_dir="/tmp/inbox",
                pid_file=pid_file,
            )
            preflight_engine.close_session.assert_called_once_with()
            preflight_engine.run_daemon.assert_not_called()
            runtime_engine.set_configuration_path.assert_called_once_with("orchestrator.xml")
            runtime_engine.run_daemon.assert_called_once_with(
                polling_dir="/tmp/inbox",
                polling_frequency=2,
                pid_file=pid_file,
                foreground=True,
            )
            runtime_engine.close_session.assert_called_once_with()
            assert status == {"running": True, "pid": 4321}
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_start_rejects_already_running_daemon(self):
        """
        Reject a start request when the daemon is already running.
        """
        manager = DaemonManager("/tmp/oboa.pid")
        with mock.patch.object(manager, "status", return_value={"running": True, "pid": 123}):
            with self.assertRaises(DaemonError):
                manager.start()

    def test_start_rejects_unavailable_directories_before_forking(self):
        """
        Validate daemon directories before reporting a background daemon as started.
        """
        preflight_engine = mock.Mock()
        preflight_engine.validate_daemon_startup.side_effect = DaemonError("bad runtime dependency")
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch.object(manager, "status", return_value={"running": False, "pid": None}):
            with mock.patch("oboa.engine.daemon.Engine", return_value=preflight_engine):
                with mock.patch("oboa.engine.daemon.os.fork") as fork:
                    with self.assertRaises(DaemonError):
                        manager.start(polling_dir="/tmp/inbox")

        preflight_engine.validate_daemon_startup.assert_called_once_with(
            polling_dir="/tmp/inbox",
            pid_file="/tmp/oboa.pid",
        )
        preflight_engine.close_session.assert_called_once_with()
        fork.assert_not_called()
        preflight_engine.run_daemon.assert_not_called()

    def test_start_rejects_unavailable_database_before_forking(self):
        """
        Validate database readiness before reporting a background daemon as started.
        """
        preflight_engine = mock.Mock()
        preflight_engine.validate_daemon_startup.side_effect = DaemonError("database unavailable")
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch.object(manager, "status", return_value={"running": False, "pid": None}):
            with mock.patch("oboa.engine.daemon.Engine", return_value=preflight_engine):
                with mock.patch("oboa.engine.daemon.os.fork") as fork:
                    with self.assertRaises(DaemonError):
                        manager.start()

        preflight_engine.validate_daemon_startup.assert_called_once_with(
            polling_dir=None,
            pid_file="/tmp/oboa.pid",
        )
        preflight_engine.close_session.assert_called_once_with()
        fork.assert_not_called()
        preflight_engine.run_daemon.assert_not_called()

    def test_start_background_parent_returns_child_pid(self):
        """
        Return the child PID in the parent process after forking.
        """
        preflight_engine = mock.Mock()
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch.object(manager, "status", return_value={"running": False, "pid": None}):
            with mock.patch("oboa.engine.daemon.Engine", return_value=preflight_engine) as engine_class:
                with mock.patch("oboa.engine.daemon.os.fork", return_value=9876):
                    with mock.patch("oboa.engine.daemon.time.sleep") as sleep:
                        status = manager.start()

        sleep.assert_called_once_with(0.1)
        engine_class.assert_called_once_with()
        preflight_engine.validate_daemon_startup.assert_called_once_with(
            polling_dir=None,
            pid_file="/tmp/oboa.pid",
        )
        preflight_engine.close_session.assert_called_once_with()
        preflight_engine.run_daemon.assert_not_called()
        assert status == {"running": True, "pid": 9876}

    def test_start_background_child_runs_engine_and_exits(self):
        """
        Run the daemon body in the forked child process.
        """
        preflight_engine = mock.Mock()
        runtime_engine = mock.Mock()
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch.object(manager, "status", return_value={"running": False, "pid": None}):
            with mock.patch(
                "oboa.engine.daemon.Engine",
                side_effect=[preflight_engine, runtime_engine],
            ) as engine_class:
                with mock.patch("oboa.engine.daemon.os.fork", return_value=0):
                    with mock.patch("oboa.engine.daemon.os.setsid") as setsid:
                        with mock.patch("oboa.engine.daemon.os._exit", side_effect=RuntimeError("exit")):
                            with self.assertRaises(RuntimeError):
                                manager.start()

        assert engine_class.call_count == 2
        setsid.assert_called_once_with()
        preflight_engine.validate_daemon_startup.assert_called_once_with(
            polling_dir=None,
            pid_file="/tmp/oboa.pid",
        )
        preflight_engine.close_session.assert_called_once_with()
        preflight_engine.run_daemon.assert_not_called()
        runtime_engine.run_daemon.assert_called_once_with(
            polling_dir=None,
            polling_frequency=None,
            pid_file="/tmp/oboa.pid",
            foreground=True,
        )
        runtime_engine.close_session.assert_called_once_with()

    def test_stop_returns_when_not_running(self):
        """
        Treat stop requests for absent daemons as successful no-ops.
        """
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch.object(manager, "status", return_value={"running": False, "pid": None}):
            assert manager.stop() == {"running": False, "pid": None}

    def test_stop_sends_sigterm_and_removes_pid_file(self):
        """
        Send SIGTERM and remove the PID file once the daemon has stopped.
        """
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch.object(manager, "status", return_value={"running": True, "pid": 123}):
            with mock.patch.object(manager, "_pid_file_matches", side_effect=[True, True]):
                with mock.patch.object(manager, "_pid_running", side_effect=[False]):
                    with mock.patch.object(manager, "_remove_stale_pid_file") as remove_pid:
                        with mock.patch("oboa.engine.daemon.os.kill") as kill:
                            status = manager.stop()

        kill.assert_called_once_with(123, signal.SIGTERM)
        remove_pid.assert_called_once_with()
        assert status == {"running": False, "pid": None}

    def test_stop_returns_when_daemon_removes_pid_file(self):
        """
        Treat daemon-owned PID-file removal as a successful stop.
        """
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch.object(manager, "status", return_value={"running": True, "pid": 123}):
            with mock.patch.object(manager, "_pid_file_matches", return_value=False) as pid_matches:
                with mock.patch.object(manager, "_pid_running") as pid_running:
                    with mock.patch("oboa.engine.daemon.os.kill") as kill:
                        status = manager.stop()

        kill.assert_called_once_with(123, signal.SIGTERM)
        pid_matches.assert_called_once_with(123)
        pid_running.assert_not_called()
        assert status == {"running": False, "pid": None}

    def test_stop_handles_process_exit_before_sigterm(self):
        """
        Return stopped when the daemon exits before SIGTERM can be sent.
        """
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch.object(manager, "status", return_value={"running": True, "pid": 123}):
            with mock.patch.object(manager, "_pid_file_matches", return_value=True):
                with mock.patch.object(manager, "_remove_stale_pid_file") as remove_pid:
                    with mock.patch("oboa.engine.daemon.os.kill", side_effect=OSError("gone")):
                        status = manager.stop()

        remove_pid.assert_called_once_with()
        assert status == {"running": False, "pid": None}

    def test_stop_raises_when_daemon_does_not_stop(self):
        """
        Raise a daemon error when SIGTERM does not stop the process.
        """
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch.object(manager, "status", return_value={"running": True, "pid": 123}):
            with mock.patch.object(manager, "_pid_file_matches", return_value=True):
                with mock.patch.object(manager, "_pid_running", return_value=True):
                    with mock.patch("oboa.engine.daemon.os.kill"):
                        with mock.patch("oboa.engine.daemon.time.sleep"):
                            with self.assertRaises(DaemonError):
                                manager.stop()

    def test_restart_stops_then_starts(self):
        """
        Restart by delegating to stop before start.
        """
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch.object(manager, "stop") as stop:
            with mock.patch.object(manager, "start", return_value={"running": True, "pid": 321}) as start:
                status = manager.restart(
                    foreground=True,
                    polling_dir="/tmp/inbox",
                    polling_frequency=3,
                    configuration_path="orchestrator.xml",
                )

        stop.assert_called_once_with()
        start.assert_called_once_with(
            foreground=True,
            polling_dir="/tmp/inbox",
            polling_frequency=3,
            configuration_path="orchestrator.xml",
        )
        assert status == {"running": True, "pid": 321}

    def test_remove_stale_pid_file_ignores_remove_errors(self):
        """
        Ignore PID-file cleanup errors during stale status handling.
        """
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch("oboa.engine.daemon.os.path.exists", return_value=True):
            with mock.patch("oboa.engine.daemon.os.remove", side_effect=OSError("denied")):
                manager._remove_stale_pid_file()

    def test_remove_stale_pid_file_ignores_missing_files(self):
        """
        Treat absent stale PID files as cleanup no-ops.
        """
        manager = DaemonManager("/tmp/oboa.pid")

        with mock.patch("oboa.engine.daemon.os.path.exists", return_value=False):
            manager._remove_stale_pid_file()
