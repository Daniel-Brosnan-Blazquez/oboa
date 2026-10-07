"""
Tests for OBOA engine orchestration.
"""

import datetime
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("OBOA_LOG_PATH", "/tmp/oboa_log")

from oboa.datamodel.base import Base, engine as sqlalchemy_engine
from oboa.datamodel.orchestrated_files import OrchestratedFile
from oboa.engine.engine import Engine
from oboa.engine.errors import (
    ArchiveDelegationError,
    DaemonError,
    OrchestrationConfigurationError,
    OrchestrationError,
    PollingError,
    ProcessorError,
)
from oboa.engine.parsing import get_orchestrator_configuration
from oboa.engine.query import Query


INPUTS = Path(__file__).parent / "inputs"


class MockArchiveClient():
    """
    Mock archive client for engine tests.
    """

    def __init__(self, delete=False, fail=False):
        """
        Configure whether the mock archive deletes inputs or raises failures.
        """
        self.delete = delete
        self.fail = fail
        self.calls = []
        self.closed = False

    def archive_file(self, file_path, file_group=None, delete_after_archive=False):
        """
        Record archive parameters and optionally emulate archive side effects.
        """
        self.calls.append((file_path, file_group, delete_after_archive))
        if self.fail:
            raise RuntimeError("archive failed")
        if self.delete and delete_after_archive and os.path.exists(file_path):
            os.remove(file_path)

    def close(self):
        """
        Match the archive-client interface used by ``Engine.close_session``.
        """
        self.closed = True


class TestEngine(unittest.TestCase):
    """
    Engine behavior tests.
    """

    def setUp(self):
        """
        Prepare an isolated polling and processing workspace.
        """
        Base.metadata.create_all(sqlalchemy_engine)
        query = Query()
        query.clear_db()
        query.close_session()
        self.root = Path(tempfile.mkdtemp(prefix="oboa_engine_"))
        self.polling_dir = self.root / "polling"
        self.processing_dir = self.root / "processing"
        self.error_dir = self.root / "error"
        self.polling_dir.mkdir()
        self.processing_dir.mkdir()
        self.error_dir.mkdir()

    def tearDown(self):
        """
        Remove temporary filesystem state, leaving database rows inspectable.
        """
        shutil.rmtree(str(self.root), ignore_errors=True)

    def copy_input(self, name):
        """
        Copy a persistent fixture into the temporary polling directory.
        """
        path = self.polling_dir / name
        shutil.copy2(str(INPUTS / name), str(path))
        return path

    def error_files(self, name):
        """
        Return failed inputs stored under the date-based error folder layout.
        """
        pattern = "[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]/{}".format(name)
        return list(self.error_dir.glob(pattern))

    def make_engine(self, archive_client, configuration):
        """
        Build an engine with test-local folders and configuration XML.
        """
        engine = Engine(archive_client=archive_client)
        engine.set_configuration_path(str(configuration))
        engine.engine_configuration["ORCHESTRATION"]["polling_dir"] = str(self.polling_dir)
        engine.engine_configuration["ORCHESTRATION"]["processing_dir"] = str(self.processing_dir)
        engine.engine_configuration["ORCHESTRATION"]["error_dir"] = str(self.error_dir)
        engine.engine_configuration["ORCHESTRATION"]["polling_frequency"] = 0.1
        return engine

    def test_orchestrate_stages_processor_file_and_deletes_input_after_archive(self):
        """
        Stage processor-backed inputs before deleting the archived source.
        """
        input_file = self.copy_input("sample.txt")
        archive_client = MockArchiveClient(delete=False)
        engine = self.make_engine(
            archive_client,
            INPUTS / "orchestrator_texts_with_processor.xml",
        )

        row = engine.orchestrate_file(str(input_file))

        assert row.file_group == "texts"
        assert row.archived is True
        assert row.processed is True
        assert not input_file.exists()
        staged_files = list(self.processing_dir.glob("{}/sample.txt".format(row.file_uuid)))
        assert len(staged_files) == 1
        assert staged_files[0].read_text(encoding="utf-8") == (
            INPUTS / "sample.txt"
        ).read_text(encoding="utf-8")
        assert archive_client.calls[0][1] == "texts"
        assert engine.query.get_orchestration_operations() == []
        engine.close_session()

    def test_default_archive_client_receives_group_and_delete_flag(self):
        """
        Use the default archive client path when no archive client is injected.
        """
        input_file = self.copy_input("sample.txt")
        archive_client = MockArchiveClient(delete=False)
        engine = self.make_engine(
            None,
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with mock.patch(
            "oboa.engine.engine.AboaArchiveClient",
            return_value=archive_client,
        ) as archive_client_class:
            row = engine.orchestrate_file(str(input_file))

        archive_client_class.assert_called_once_with()
        assert engine.archive_client is archive_client
        assert archive_client.calls == [(str(input_file), "texts", True)]
        assert row.archived is True
        assert not input_file.exists()
        engine.close_session()

    def test_unknown_file_is_archived_without_processor(self):
        """
        Archive unmatched inputs under the unknown group without staging.
        """
        input_file = self.copy_input("sample.bin")
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        row = engine.orchestrate_file(str(input_file))

        assert row.file_group == "unknown"
        assert row.archived is True
        assert row.processed is True
        assert list(self.processing_dir.iterdir()) == []
        engine.close_session()

    def test_archive_failure_records_unarchived_row(self):
        """
        Preserve the OBOA row and move the input to the error folder on archive failure.
        """
        input_file = self.copy_input("sample.txt")
        engine = self.make_engine(
            MockArchiveClient(fail=True),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with self.assertRaises(ArchiveDelegationError):
            engine.orchestrate_file(str(input_file))

        rows = engine.query.get_orchestrated_files(names={"filter": "sample.txt", "op": "like"})
        assert rows[0].archived is False
        operations = engine.query.get_orchestration_operations()
        assert [operation.operation for operation in operations] == ["archive"]
        assert not input_file.exists()
        # Failed inputs are moved into the archive-style date layout.
        error_files = self.error_files("sample.txt")
        assert len(error_files) == 1
        assert "moved to {}".format(error_files[0]) in operations[0].message
        engine.close_session()

    def test_configure_orchestrator_reuses_same_configuration_content(self):
        """
        Avoid creating duplicate active configuration rows for same XML content.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        first = engine.configure_orchestrator(
            str(INPUTS / "orchestrator_texts_without_processor.xml")
        )
        second = engine.configure_orchestrator(
            str(INPUTS / "orchestrator_texts_without_processor.xml")
        )
        rows = engine.query.get_orchestration_configurations()

        assert first.orchestration_configuration_uuid == second.orchestration_configuration_uuid
        assert len(rows) == 1
        assert rows[0].active is True
        assert engine.query.get_orchestration_operations() == []
        engine.close_session()

    def test_configure_orchestrator_deactivates_previous_configuration(self):
        """
        Keep only the newest distinct configuration content active.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        first = engine.configure_orchestrator(
            str(INPUTS / "orchestrator_texts_without_processor.xml")
        )
        second = engine.configure_orchestrator(str(INPUTS / "orchestrator_valid.xml"))
        rows = engine.query.get_orchestration_configurations()
        active_rows = [row for row in rows if row.active]
        inactive_rows = [row for row in rows if not row.active]

        assert len(rows) == 2
        assert [row.orchestration_configuration_uuid for row in active_rows] == [
            second.orchestration_configuration_uuid
        ]
        assert [row.orchestration_configuration_uuid for row in inactive_rows] == [
            first.orchestration_configuration_uuid
        ]
        assert inactive_rows[0].active_until is not None
        assert engine.query.get_orchestration_operations() == []
        engine.close_session()

    def test_exit_codes_and_session_close_helpers(self):
        """
        Return defensive exit-code copies and close archive-client resources.
        """
        archive_client = MockArchiveClient()
        engine = self.make_engine(
            archive_client,
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        exit_code = engine.get_exit_code("OK")
        exit_code["status"] = 99
        engine.close_session()

        assert engine.get_exit_code("OK")["status"] == 0
        assert archive_client.closed is True

    def test_engine_accepts_injected_session_and_archive_client_without_close(self):
        """
        Use caller-supplied sessions and tolerate archive clients without close hooks.
        """
        session = mock.Mock()
        archive_client = object()

        engine = Engine(session=session, archive_client=archive_client)
        engine.close_session()

        assert engine.session is session
        session.close.assert_called_once_with()

    def test_orchestrate_rejects_missing_files_and_invalid_configurations(self):
        """
        Reject inputs and configurations that cannot be loaded.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        with self.assertRaises(OrchestrationError):
            engine.orchestrate_file(str(self.polling_dir / "missing.txt"))

        input_file = self.copy_input("sample.txt")
        engine.set_configuration_path(str(INPUTS / "missing_orchestrator.xml"))
        with self.assertRaises(OrchestrationConfigurationError):
            engine.orchestrate_file(str(input_file))
        engine.close_session()

    def test_orchestrate_records_staging_failure_for_processor_backed_files(self):
        """
        Record a processing-stage failure when a matched file cannot be staged.
        """
        input_file = self.copy_input("sample.txt")
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_with_processor.xml",
        )

        with mock.patch.object(engine, "prepare_processing_file", side_effect=OSError("stage failed")):
            with self.assertRaises(OrchestrationError):
                engine.orchestrate_file(str(input_file))

        rows = engine.query.get_orchestrated_files(names={"filter": "sample.txt", "op": "like"})
        assert rows[0].processed is False
        assert not input_file.exists()
        # Staging failures also leave the polling entry point through the error layout.
        error_files = self.error_files("sample.txt")
        assert len(error_files) == 1
        engine.close_session()

    def test_orchestrate_records_processor_failure_without_failing_archive(self):
        """
        Keep archived rows visible when the downstream processor fails.
        """
        input_file = self.copy_input("sample.txt")
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_with_processor.xml",
        )

        with mock.patch("oboa.engine.engine.execute_processor", side_effect=ProcessorError("processor failed")):
            row = engine.orchestrate_file(str(input_file))

        assert row.archived is True
        assert row.processed is False
        engine.close_session()

    def test_poll_once_rejects_unavailable_directories(self):
        """
        Reject polling directories that cannot be read.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        polling_dir = str(self.root / "missing")

        with self.assertLogs("oboa.engine.engine", level="INFO") as captured:
            with self.assertRaises(PollingError):
                engine.poll_once(polling_dir=polling_dir)

        assert any(polling_dir in message for message in captured.output)
        engine.close_session()

    def test_poll_once_records_not_ready_files_and_continues_after_errors(self):
        """
        Skip unstable files and continue when a ready file fails orchestration.
        """
        self.copy_input("sample.txt")
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with mock.patch.object(engine, "_is_file_ready", return_value=False):
            assert engine.poll_once(polling_dir=str(self.polling_dir)) == []

        with mock.patch.object(engine, "_is_file_ready", return_value=True):
            with mock.patch.object(engine, "orchestrate_file", side_effect=OrchestrationError("boom")):
                assert engine.poll_once(polling_dir=str(self.polling_dir)) == []
        engine.close_session()

    def test_poll_once_logs_polled_and_sorted_files(self):
        """
        Show raw polled files and priority-sorted files in every polling pass.
        """
        low_priority = self.copy_input("a_low_priority.bin")
        high_priority = self.copy_input("z_high_priority.txt")
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_valid.xml",
        )

        with mock.patch.object(engine, "_is_file_ready", return_value=True):
            with mock.patch.object(engine, "orchestrate_file", side_effect=lambda file_path: file_path):
                with self.assertLogs("oboa.engine.engine", level="INFO") as captured:
                    assert engine.poll_once(polling_dir=str(self.polling_dir)) == [
                        str(high_priority),
                        str(low_priority),
                    ]

        polled_log = next(
            message for message in captured.output
            if "Polled OBOA input files:" in message
        )
        sorted_log = next(
            message for message in captured.output
            if "Sorted OBOA input files:" in message
        )
        assert polled_log.index(str(low_priority)) < polled_log.index(str(high_priority))
        assert sorted_log.index(str(high_priority)) < sorted_log.index(str(low_priority))
        engine.close_session()

    def test_poll_once_logs_failed_input_move_after_orchestration_error(self):
        """
        Log failed input movement as an error after the orchestration failure.
        """
        input_file = self.copy_input("sample.txt")
        engine = self.make_engine(
            MockArchiveClient(fail=True),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with mock.patch.object(engine, "_is_file_ready", return_value=True):
            with self.assertLogs("oboa.engine.engine", level="ERROR") as captured:
                assert engine.poll_once(polling_dir=str(self.polling_dir)) == []

        orchestration_log = next(
            index for index, message in enumerate(captured.output)
            if "Could not orchestrate {}".format(input_file) in message
        )
        move_log = next(
            index for index, message in enumerate(captured.output)
            if "Moved failed OBOA input file {}".format(input_file) in message
        )
        assert orchestration_log < move_log
        assert captured.output[move_log].startswith("ERROR:oboa.engine.engine:")
        assert len(self.error_files("sample.txt")) == 1
        engine.close_session()

    def test_poll_once_records_configuration_failure_for_ready_files(self):
        """
        Record configuration failures encountered after ready files are detected.
        """
        self.copy_input("sample.txt")
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with mock.patch.object(engine, "_is_file_ready", return_value=True):
            with mock.patch.object(
                engine,
                "_load_orchestration_configuration",
                side_effect=OrchestrationConfigurationError("bad configuration"),
            ):
                with self.assertRaises(OrchestrationConfigurationError):
                    engine.poll_once(polling_dir=str(self.polling_dir))
        engine.close_session()

    def test_run_polling_loop_stops_after_max_iterations_and_keyboard_interrupt(self):
        """
        Stop polling loops on iteration limits and keyboard interrupts.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with mock.patch.object(engine, "poll_once") as poll_once:
            with mock.patch("oboa.engine.engine.time.sleep") as sleep:
                engine.run_polling_loop(polling_dir=str(self.polling_dir), polling_frequency=0.1, max_iterations=2)

        assert poll_once.call_count == 2
        sleep.assert_called_once_with(0.1)

        with mock.patch.object(engine, "poll_once", side_effect=KeyboardInterrupt):
            engine.run_polling_loop(polling_dir=str(self.polling_dir), polling_frequency=0.1)
        engine.close_session()

    def test_run_polling_loop_logs_iteration_errors_and_continues(self):
        """
        Keep the daemon loop alive when one polling iteration fails.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with mock.patch.object(engine, "poll_once", side_effect=[RuntimeError("database down"), None]) as poll_once:
            with mock.patch.object(engine.session, "rollback") as rollback:
                with mock.patch("oboa.engine.engine.time.sleep") as sleep:
                    with self.assertLogs("oboa.engine.engine", level="ERROR") as captured:
                        engine.run_polling_loop(
                            polling_dir=str(self.polling_dir),
                            polling_frequency=0.1,
                            max_iterations=2,
                        )

        assert poll_once.call_count == 2
        rollback.assert_called_once_with()
        sleep.assert_called_once_with(0.1)
        assert any("OBOA polling iteration failed: database down" in message for message in captured.output)
        engine.close_session()

    def test_run_polling_loop_exits_when_stop_is_already_requested(self):
        """
        Exit a polling loop without polling when shutdown is already requested.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        engine._should_stop = True

        with mock.patch.object(engine, "poll_once") as poll_once:
            engine.run_polling_loop(polling_dir=str(self.polling_dir), polling_frequency=0.1)

        poll_once.assert_not_called()
        engine.close_session()

    def test_run_daemon_foreground_writes_and_removes_pid_file(self):
        """
        Manage the PID file while running in foreground daemon mode.
        """
        pid_file = self.root / "oboa.pid"
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with mock.patch.object(engine, "validate_daemon_startup") as validate_startup:
            with mock.patch.object(engine, "_install_signal_handlers") as install_handlers:
                with mock.patch.object(engine, "run_polling_loop") as polling_loop:
                    engine.run_daemon(
                        polling_dir=str(self.polling_dir),
                        polling_frequency=0.2,
                        pid_file=str(pid_file),
                        foreground=True,
                        max_iterations=1,
                    )

        validate_startup.assert_called_once_with(
            polling_dir=str(self.polling_dir),
            pid_file=str(pid_file),
        )
        install_handlers.assert_called_once_with(str(pid_file))
        polling_loop.assert_called_once_with(
            polling_dir=str(self.polling_dir),
            polling_frequency=0.2,
            max_iterations=1,
        )
        assert not pid_file.exists()
        with mock.patch.object(engine, "validate_daemon_startup"):
            with mock.patch.object(engine, "_install_signal_handlers"):
                with self.assertRaises(DaemonError):
                    engine.run_daemon(foreground=False)
        engine.close_session()

    def test_validate_daemon_startup_checks_directories_and_database(self):
        """
        Check daemon directories and database readiness before startup.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        directories = {"polling_dir": str(self.polling_dir)}

        with mock.patch.object(engine, "validate_daemon_directories", return_value=directories) as validate_dirs:
            with mock.patch.object(engine, "wait_for_database") as wait_database:
                result = engine.validate_daemon_startup(
                    polling_dir=str(self.polling_dir),
                    pid_file="/tmp/oboa.pid",
                )

        validate_dirs.assert_called_once_with(
            polling_dir=str(self.polling_dir),
            pid_file="/tmp/oboa.pid",
        )
        wait_database.assert_called_once_with()
        assert result == directories
        engine.close_session()

    def test_validate_daemon_directories_creates_internal_folders(self):
        """
        Create daemon-owned internal folders before the polling loop starts.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        processing_dir = self.root / "created_processing"
        error_dir = self.root / "created_error"
        pid_file = self.root / "pid" / "oboa.pid"
        engine.engine_configuration["ORCHESTRATION"]["processing_dir"] = str(processing_dir)
        engine.engine_configuration["ORCHESTRATION"]["error_dir"] = str(error_dir)

        directories = engine.validate_daemon_directories(
            polling_dir=str(self.polling_dir),
            pid_file=str(pid_file),
        )

        assert directories["polling_dir"] == str(self.polling_dir)
        assert directories["processing_dir"] == str(processing_dir)
        assert directories["error_dir"] == str(error_dir)
        assert directories["pid_dir"] == str(pid_file.parent)
        assert processing_dir.is_dir()
        assert error_dir.is_dir()
        assert pid_file.parent.is_dir()
        engine.close_session()

    def test_validate_daemon_directories_rejects_unavailable_error_folder(self):
        """
        Fail daemon startup when the configured error folder is unavailable.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        error_path = self.root / "error_file"
        error_path.write_text("not a directory", encoding="utf-8")
        engine.engine_configuration["ORCHESTRATION"]["error_dir"] = str(error_path)

        with self.assertRaises(DaemonError) as captured:
            engine.validate_daemon_directories(polling_dir=str(self.polling_dir))

        assert "error directory" in str(captured.exception)
        engine.close_session()

    def test_validate_daemon_directories_rejects_missing_polling_folder(self):
        """
        Require the polling entry point to exist before daemon startup.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with self.assertRaises(DaemonError) as captured:
            engine.validate_daemon_directories(polling_dir=str(self.root / "missing_polling"))

        assert "polling directory" in str(captured.exception)
        engine.close_session()

    def test_ensure_daemon_directory_rejects_unavailable_paths(self):
        """
        Convert low-level directory creation and access failures into daemon errors.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with mock.patch("oboa.engine.engine.os.makedirs", side_effect=OSError("denied")):
            with self.assertRaises(DaemonError):
                engine._ensure_daemon_directory(
                    str(self.root / "new_dir"),
                    "directory failed",
                    create=True,
                )
        with mock.patch("oboa.engine.engine.os.path.isdir", return_value=True):
            with mock.patch("oboa.engine.engine.os.access", return_value=False):
                with self.assertRaises(DaemonError):
                    engine._ensure_daemon_directory(
                        str(self.polling_dir),
                        "directory failed",
                    )
        engine.close_session()

    def test_wait_for_database_retries_until_ready(self):
        """
        Retry database readiness checks until PostgreSQL accepts connections.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        connection = mock.Mock()

        with mock.patch(
            "oboa.engine.engine.sqlalchemy_engine.connect",
            side_effect=[RuntimeError("starting"), connection],
        ) as connect:
            with mock.patch("oboa.engine.engine.sqlalchemy_engine.dispose") as dispose:
                with mock.patch("oboa.engine.engine.time.sleep") as sleep:
                    assert engine.wait_for_database(attempts=2, wait_seconds=0.1) is True

        assert connect.call_count == 2
        dispose.assert_called_once_with()
        sleep.assert_called_once_with(0.1)
        connection.execute.assert_called_once()
        connection.close.assert_called_once_with()
        engine.close_session()

    def test_wait_for_database_raises_after_retry_budget(self):
        """
        Report a controlled daemon error when the database remains unavailable.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with mock.patch("oboa.engine.engine.sqlalchemy_engine.connect", side_effect=RuntimeError("down")):
            with mock.patch("oboa.engine.engine.sqlalchemy_engine.dispose") as dispose:
                with mock.patch("oboa.engine.engine.time.sleep") as sleep:
                    with self.assertRaises(DaemonError) as captured:
                        engine.wait_for_database(attempts=2, wait_seconds=0)

        assert "database is not available" in str(captured.exception)
        dispose.assert_called_once_with()
        sleep.assert_called_once_with(0.0)
        engine.close_session()

    def test_wait_for_database_rejects_invalid_retry_configuration(self):
        """
        Reject invalid daemon database retry configuration before sleeping.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        with self.assertRaises(DaemonError):
            engine.wait_for_database(attempts=0, wait_seconds=0)
        with self.assertRaises(DaemonError):
            engine.wait_for_database(attempts=1, wait_seconds=-1)
        with self.assertRaises(DaemonError):
            engine.wait_for_database(attempts="invalid", wait_seconds=0)
        engine.close_session()

    def test_signal_handler_requests_stop_and_removes_pid_file(self):
        """
        Install signal handlers that mark the engine for shutdown.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        pid_file = str(self.root / "oboa.pid")

        with mock.patch("oboa.engine.engine.signal.signal") as signal_mock:
            with mock.patch.object(engine, "_remove_pid_file") as remove_pid:
                engine._install_signal_handlers(pid_file)
                handler = signal_mock.call_args_list[0].args[1]
                handler(15, None)

        assert engine._should_stop is True
        remove_pid.assert_called_once_with(pid_file)
        engine.close_session()

    def test_remove_pid_file_ignores_missing_files_and_warns_on_errors(self):
        """
        Treat absent PID files as no-ops and warn when removal fails.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        missing_pid = str(self.root / "missing.pid")

        engine._remove_pid_file(missing_pid)
        with mock.patch("oboa.engine.engine.os.path.exists", return_value=True):
            with mock.patch("oboa.engine.engine.os.remove", side_effect=OSError("denied")):
                with self.assertLogs("oboa.engine.engine", level="WARNING") as captured:
                    engine._remove_pid_file(missing_pid)

        assert any("Could not remove PID file" in message for message in captured.output)
        engine.close_session()

    def test_prepare_processing_file_rejects_unavailable_processing_dir(self):
        """
        Reject processing directories that cannot be created or written.
        """
        input_file = self.copy_input("sample.txt")
        row = OrchestratedFile(
            "file-uuid",
            "sample.txt",
            str(input_file),
            "texts",
            datetime.datetime.utcnow(),
        )
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_with_processor.xml",
        )

        with mock.patch("oboa.engine.engine.os.makedirs", side_effect=OSError("denied")):
            with self.assertRaises(OrchestrationError):
                engine.prepare_processing_file(str(input_file), row)

        with mock.patch("oboa.engine.engine.os.access", return_value=False):
            with self.assertRaises(OrchestrationError):
                engine.prepare_processing_file(str(input_file), row)
        engine.close_session()

    def test_prepare_processing_file_copies_when_hard_link_fails(self):
        """
        Fall back to copying staged processor input when hard-linking fails.
        """
        input_file = self.copy_input("sample.txt")
        row = OrchestratedFile(
            "file-uuid",
            "sample.txt",
            str(input_file),
            "texts",
            datetime.datetime.utcnow(),
        )
        target_dir = self.processing_dir / row.file_uuid
        target_dir.mkdir()
        (target_dir / row.name).write_text("old", encoding="utf-8")
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_with_processor.xml",
        )

        with mock.patch("oboa.engine.engine.os.link", side_effect=OSError("cross-device")):
            staged = engine.prepare_processing_file(str(input_file), row)

        assert Path(staged).read_text(encoding="utf-8") == input_file.read_text(encoding="utf-8")
        engine.close_session()

    def test_build_error_path_uses_date_layout_and_avoids_collisions(self):
        """
        Build error paths as ``error_dir/YEAR/MONTH/DAY/file`` without overwrites.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        error_date = datetime.datetime(2026, 8, 8, 1, 2, 3)

        first_path = Path(engine._build_error_path(str(self.error_dir), error_date, "sample.txt"))
        first_path.write_text("already failed", encoding="utf-8")
        second_path = Path(engine._build_error_path(str(self.error_dir), error_date, "sample.txt"))

        assert first_path == self.error_dir / "2026" / "08" / "08" / "sample.txt"
        assert second_path.parent == first_path.parent
        assert second_path.name.startswith("sample_")
        assert second_path.suffix == ".txt"
        assert second_path != first_path
        engine.close_session()

    def test_configuration_loading_default_path_and_failure_paths(self):
        """
        Load default configurations and record failures through configure.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        configuration = mock.Mock()

        with mock.patch("oboa.engine.engine.get_resources_path", return_value="/tmp/resources"):
            with mock.patch("oboa.engine.engine.get_orchestrator_configuration"):
                with mock.patch.object(engine, "_activate_orchestration_configuration", return_value=configuration) as activate:
                    loaded = engine._load_orchestration_configuration()

        activate.assert_called_once_with("/tmp/resources/orchestrator_configuration.xml")
        assert loaded is configuration
        assert engine.configuration_path == "/tmp/resources/orchestrator_configuration.xml"

        with mock.patch.object(engine, "_load_orchestration_configuration", side_effect=ValueError("bad")):
            with self.assertRaises(OrchestrationConfigurationError):
                engine.configure_orchestrator()
        operations = engine.query.get_orchestration_operations()
        assert [operation.operation for operation in operations] == ["configure"]
        engine.close_session()

    def test_record_operation_ignores_success_statuses(self):
        """
        Persist only failed operations in the operation audit table.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )

        assert engine._record_operation("poll", engine.get_exit_code("OK")["status"], "success") is None

        assert engine.query.get_orchestration_operations() == []
        engine.close_session()

    def test_engine_private_file_helpers_cover_matching_and_readiness(self):
        """
        Cover matching, priority, pollable-file, readiness, and checksum helpers.
        """
        engine = self.make_engine(
            MockArchiveClient(),
            INPUTS / "orchestrator_texts_without_processor.xml",
        )
        configuration_xpath = get_orchestrator_configuration(INPUTS / "orchestrator_valid.xml")
        text_rule = engine._match_rule("/tmp/sample.txt", configuration_xpath)
        binary_rule = engine._match_rule("/tmp/sample.bin", configuration_xpath)

        assert text_rule.get("group") == "high"
        assert binary_rule.get("group") == "low"
        assert engine._match_rule("/tmp/sample.csv", configuration_xpath) is None
        assert engine._polling_priority_key("/tmp/sample.txt", configuration_xpath) == (0, 1, 1, "sample.txt")
        assert engine._polling_priority_key("/tmp/sample.csv", configuration_xpath) == (1, 0, 0, "sample.csv")
        assert engine._configuration_node_text(text_rule, "data_processor") == str(
            (INPUTS / "processor_success.sh").resolve()
        )
        assert engine._configuration_node_text(binary_rule, "data_processor", empty_as_none=True) is None
        assert engine._pollable_file(".hidden.txt", str(INPUTS / ".hidden.txt")) is False
        assert engine._pollable_file("skip.tmp", str(INPUTS / "skip.tmp")) is False
        assert engine._pollable_file("inputs", str(INPUTS)) is False
        assert engine._configuration_checksum("hello") == engine._configuration_checksum("hello")
        assert engine._delete_after_archive() is True
        assert engine._orchestration_config("processing_dir") == str(self.processing_dir)

        with mock.patch("oboa.engine.engine.os.stat", side_effect=OSError("gone")):
            assert engine._is_file_ready(str(INPUTS / "sample.txt")) is False

        first = mock.Mock(st_size=1, st_mtime=1)
        second = mock.Mock(st_size=2, st_mtime=1)
        with mock.patch("oboa.engine.engine.os.stat", side_effect=[first, second]):
            with mock.patch("oboa.engine.engine.time.sleep"):
                assert engine._is_file_ready(str(INPUTS / "sample.txt")) is False
        engine.close_session()
