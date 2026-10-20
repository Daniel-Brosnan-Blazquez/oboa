"""
Engine definition for OBOA orchestration operations.
"""

import datetime
import hashlib
import os
import shutil
import signal
import time
import uuid

from sqlalchemy import text
from sqlalchemy.orm import scoped_session

from oboa.datamodel.orchestrated_files import (
    OrchestratedFile,
    OrchestrationConfiguration,
    OrchestrationOperation,
)
from oboa.datamodel.base import Session, engine as sqlalchemy_engine
from oboa.engine.archive_client import AboaArchiveClient
from oboa.engine.errors import (
    ArchiveDelegationError,
    DaemonError,
    OrchestrationConfigurationError,
    OrchestrationError,
    PollingError,
    ProcessorError,
)
from oboa.engine.functions import get_resources_path, parse_datetime, read_configuration
from oboa.engine.parsing import get_orchestrator_configuration
from oboa.engine.query import Query
from oboa.logging import Log
from oboa.processors.base_processor import execute_processor


logging = Log(name=__name__)
logger = logging.logger


exit_codes = {
    "OK": {"status": 0, "message": "The operation {} has finished correctly"},
    "CONFIGURATION_FAILED": {"status": 1, "message": "The configuration {} could not be loaded: {}"},
    "ABOA_DEPENDENCY_NOT_AVAILABLE": {"status": 2, "message": "ABOA could not be initialized: {}"},
    "POLLING_DIR_NOT_AVAILABLE": {"status": 3, "message": "The polling directory {} is not available"},
    "PROCESSING_DIR_NOT_AVAILABLE": {"status": 4, "message": "The processing directory {} is not available"},
    "FILE_DOES_NOT_EXIST": {"status": 5, "message": "The file {} does not exist"},
    "FILE_NOT_READY": {"status": 6, "message": "The file {} is not ready"},
    "PROCESSING_STAGE_FAILED": {"status": 7, "message": "The file {} could not be staged: {}"},
    "PROCESSOR_NOT_EXECUTABLE": {"status": 8, "message": "The processor {} is not executable"},
    "PROCESSOR_FAILED": {"status": 9, "message": "The processor {} failed: {}"},
    "ARCHIVE_FAILED": {"status": 10, "message": "The file {} could not be archived: {}"},
    "DAEMON_ALREADY_RUNNING": {"status": 11, "message": "The OBOA daemon is already running with PID {}"},
    "DAEMON_FAILED": {"status": 12, "message": "The OBOA daemon failed: {}"},
    "ORCHESTRATION_FAILED": {"status": 13, "message": "The orchestration of {} failed: {}"},
    "ERROR_DIR_NOT_AVAILABLE": {"status": 14, "message": "The error directory {} is not available"},
    "PID_DIR_NOT_AVAILABLE": {"status": 15, "message": "The PID-file directory {} is not available"},
}


class Engine():
    """
    Class for managing OBOA orchestration mutations.
    """

    def __init__(self, session=None, archive_client=None):
        """
        Initialize an OBOA engine instance.

        :param session: optional SQLAlchemy session supplied by callers or tests
        :type session: sqlalchemy.orm.session.Session or None
        :param archive_client: optional archive delegation client
        :type archive_client: object or None

        :return: None
        :rtype: None
        """
        if session is None:
            scoped = scoped_session(Session)
            self.session = scoped()
        else:
            self.session = session
        self.query = Query(session=self.session)
        self.engine_configuration = read_configuration()
        self.configuration_path = os.environ.get("OBOA_CONFIGURATION_PATH")
        self.configuration_xpath = None
        self.archive_client = archive_client
        self._should_stop = False
        self._failed_input_moves = []

    def get_exit_codes(self):
        """
        Return the engine exit-code table.

        :return: copy of the exit-code table keyed by code name
        :rtype: dict
        """
        return {key: dict(value) for key, value in exit_codes.items()}

    def get_exit_code(self, name):
        """
        Return one exit-code descriptor.

        :param name: exit-code key
        :type name: str

        :return: copy of the exit-code descriptor
        :rtype: dict

        :raises KeyError: when the exit-code key is unknown
        """
        return self.get_exit_codes()[name]

    def set_configuration_path(self, configuration_path):
        """
        Set the orchestration configuration path used by this engine.

        :param configuration_path: XML orchestration configuration path
        :type configuration_path: str

        :return: None
        :rtype: None
        """
        self.configuration_path = configuration_path

    def close_session(self):
        """
        Close archive-client resources and the SQLAlchemy session.

        :return: None
        :rtype: None
        """
        try:
            if self.archive_client is not None and hasattr(self.archive_client, "close"):
                self.archive_client.close()
        finally:
            self.session.close()

    def configure_orchestrator(self, configuration_path=None):
        """
        Validate and activate an orchestration configuration.

        :param configuration_path: XML configuration path, or None to use the
            engine default
        :type configuration_path: str or None

        :return: active orchestration configuration row
        :rtype: oboa.datamodel.orchestrated_files.OrchestrationConfiguration

        :raises OrchestrationConfigurationError: when the configuration cannot
            be read, parsed, or validated
        """
        try:
            configuration = self._load_orchestration_configuration(configuration_path)
        except Exception as exc:
            self._record_operation("configure", exit_codes["CONFIGURATION_FAILED"]["status"], str(exc))
            raise OrchestrationConfigurationError(str(exc)) from exc

        return configuration

    def poll_once(self, polling_dir=None):
        """
        Scan the polling directory once and orchestrate ready files.

        Ready files are sorted by their matching configuration priority before
        orchestration. Files without a matching rule are processed after matched
        files.

        :param polling_dir: directory to scan, or None to use engine config
        :type polling_dir: str or None

        :return: orchestrated-file rows produced during this polling pass
        :rtype: list

        :raises PollingError: when the polling directory is unavailable
        :raises OrchestrationConfigurationError: when ready files exist but the
            orchestration configuration cannot be parsed
        """
        polling_dir = polling_dir or self._orchestration_config("polling_dir")
        logger.info("Polling OBOA input directory {}".format(polling_dir))
        if not os.path.isdir(polling_dir) or not os.access(polling_dir, os.R_OK):
            message = exit_codes["POLLING_DIR_NOT_AVAILABLE"]["message"].format(polling_dir)
            self._record_operation("poll", exit_codes["POLLING_DIR_NOT_AVAILABLE"]["status"], message)
            raise PollingError(message)

        polled_files = []
        ready_files = []
        for name in sorted(os.listdir(polling_dir)):
            file_path = os.path.join(polling_dir, name)
            if not self._pollable_file(name, file_path):
                continue
            polled_files.append(file_path)
            if not self._is_file_ready(file_path):
                self._record_operation(
                    "poll",
                    exit_codes["FILE_NOT_READY"]["status"],
                    exit_codes["FILE_NOT_READY"]["message"].format(file_path),
                )
                continue
            ready_files.append(file_path)
        logger.info("Polled OBOA input files: {}".format(polled_files))

        configuration_xpath = None
        if ready_files:
            try:
                self._load_orchestration_configuration(self.configuration_path)
                configuration_xpath = self.configuration_xpath
            except OrchestrationConfigurationError as exc:
                self._record_operation("configure", exit_codes["CONFIGURATION_FAILED"]["status"], str(exc))
                raise
        ordered_files = sorted(
            ready_files,
            key=lambda file_path: self._polling_priority_key(file_path, configuration_xpath),
        )
        logger.info("Sorted OBOA input files: {}".format(ordered_files))

        results = []
        for file_path in ordered_files:
            try:
                results.append(self.orchestrate_file(file_path))
            except Exception as exc:
                logger.error("Could not orchestrate {}: {}".format(file_path, exc))
                self._log_failed_input_moves(file_path)
                continue
        return results

    def run_polling_loop(self, polling_dir=None, polling_frequency=None, max_iterations=None):
        """
        Run the polling loop until interrupted.

        :param polling_dir: optional polling directory override
        :type polling_dir: str or None
        :param polling_frequency: optional polling frequency in seconds
        :type polling_frequency: int or float or None
        :param max_iterations: optional maximum number of polling iterations
        :type max_iterations: int or None

        :return: None
        :rtype: None

        Polling-pass failures are logged and retried on the next iteration.
        """
        polling_frequency = polling_frequency or self._orchestration_config("polling_frequency")
        iterations = 0
        logger.info("Starting OBOA polling loop")
        try:
            while not self._should_stop:
                try:
                    self.poll_once(polling_dir=polling_dir)
                except Exception as exc:
                    try:
                        self.session.rollback()
                    except Exception as rollback_exc:
                        logger.warning(
                            "Could not rollback OBOA session after polling iteration failure: {}".format(
                                rollback_exc,
                            )
                        )
                    logger.error("OBOA polling iteration failed: {}".format(exc))
                iterations += 1
                if max_iterations is not None and iterations >= max_iterations:
                    break
                time.sleep(float(polling_frequency))
        except KeyboardInterrupt:
            logger.info("OBOA polling loop interrupted")
        finally:
            logger.info("OBOA polling loop stopped")

    def run_daemon(self, polling_dir=None, polling_frequency=None, pid_file=None,
                   foreground=False, max_iterations=None):
        """
        Run OBOA as a long-running daemon process.

        :param polling_dir: optional polling directory override
        :type polling_dir: str or None
        :param polling_frequency: optional polling frequency in seconds
        :type polling_frequency: int or float or None
        :param pid_file: PID file path, or None to use engine config
        :type pid_file: str or None
        :param foreground: run in the current process when True
        :type foreground: bool
        :param max_iterations: optional maximum number of polling iterations
        :type max_iterations: int or None

        :return: None
        :rtype: None

        :raises DaemonError: when background daemonization is requested through
            this method
        """
        pid_file = pid_file or self.engine_configuration.get("DAEMON", {}).get("pid_file") or "/tmp/oboa.pid"
        self.validate_daemon_startup(polling_dir=polling_dir, pid_file=pid_file)
        self._install_signal_handlers(pid_file)
        if foreground:
            self._write_pid_file(pid_file)
            try:
                self.run_polling_loop(
                    polling_dir=polling_dir,
                    polling_frequency=polling_frequency,
                    max_iterations=max_iterations,
                )
            finally:
                self._remove_pid_file(pid_file)
            return
        raise DaemonError("Background daemonization is handled by oboa.engine.daemon.DaemonManager")

    def validate_daemon_startup(self, polling_dir=None, pid_file=None):
        """
        Validate daemon filesystem and database dependencies before startup.

        :param polling_dir: optional polling directory override
        :type polling_dir: str or None
        :param pid_file: optional PID file path override
        :type pid_file: str or None

        :return: resolved daemon directory paths keyed by role
        :rtype: dict

        :raises DaemonError: when a required directory or database connection is
            unavailable
        """
        directories = self.validate_daemon_directories(
            polling_dir=polling_dir,
            pid_file=pid_file,
        )
        self.wait_for_database()
        return directories

    def validate_daemon_directories(self, polling_dir=None, pid_file=None):
        """
        Validate the filesystem directories required before daemon startup.

        The input polling directory must already exist because it is the daemon
        entry point. Internal processing, error, and PID-file directories are
        created when possible and then checked for the required permissions.

        :param polling_dir: optional polling directory override
        :type polling_dir: str or None
        :param pid_file: optional PID file path override
        :type pid_file: str or None

        :return: resolved daemon directory paths keyed by role
        :rtype: dict

        :raises DaemonError: when any required directory is missing,
            not a directory, cannot be created, or lacks required permissions
        """
        orchestration_config = self.engine_configuration.get("ORCHESTRATION", {})
        polling_dir = polling_dir or orchestration_config.get("polling_dir")
        processing_dir = orchestration_config.get("processing_dir")
        error_dir = orchestration_config.get("error_dir", "/oboa_error")
        pid_file = pid_file or self.engine_configuration.get("DAEMON", {}).get("pid_file") or "/tmp/oboa.pid"
        pid_dir = os.path.dirname(os.path.abspath(pid_file)) or "."

        polling_dir = self._ensure_daemon_directory(
            polling_dir,
            exit_codes["POLLING_DIR_NOT_AVAILABLE"]["message"].format(polling_dir),
            create=False,
            access_mode=os.R_OK | os.W_OK | os.X_OK,
        )
        processing_dir = self._ensure_daemon_directory(
            processing_dir,
            exit_codes["PROCESSING_DIR_NOT_AVAILABLE"]["message"].format(processing_dir),
            create=True,
            access_mode=os.W_OK | os.X_OK,
        )
        error_dir = self._ensure_daemon_directory(
            error_dir,
            exit_codes["ERROR_DIR_NOT_AVAILABLE"]["message"].format(error_dir),
            create=True,
            access_mode=os.W_OK | os.X_OK,
        )
        pid_dir = self._ensure_daemon_directory(
            pid_dir,
            exit_codes["PID_DIR_NOT_AVAILABLE"]["message"].format(pid_dir),
            create=True,
            access_mode=os.W_OK | os.X_OK,
        )
        return {
            "polling_dir": polling_dir,
            "processing_dir": processing_dir,
            "error_dir": error_dir,
            "pid_dir": pid_dir,
        }

    def wait_for_database(self, attempts=None, wait_seconds=None):
        """
        Wait until the OBOA database accepts connections.

        :param attempts: optional number of connection attempts
        :type attempts: int or None
        :param wait_seconds: optional delay between attempts
        :type wait_seconds: int or float or None

        :return: True when the database is ready
        :rtype: bool

        :raises DaemonError: when the database remains unavailable after all
            attempts or the retry configuration is invalid
        """
        daemon_config = self.engine_configuration.get("DAEMON", {})
        attempts = attempts if attempts is not None else daemon_config.get("database_startup_attempts", 1)
        wait_seconds = (
            wait_seconds
            if wait_seconds is not None
            else daemon_config.get("database_startup_wait_seconds", 0)
        )
        try:
            attempts = int(attempts)
            wait_seconds = float(wait_seconds)
        except (TypeError, ValueError) as exc:
            raise DaemonError("The OBOA database startup retry configuration is invalid") from exc
        if attempts < 1:
            raise DaemonError("The OBOA database startup attempts must be greater than zero")
        if wait_seconds < 0:
            raise DaemonError("The OBOA database startup wait seconds must not be negative")

        last_exception = None
        try:
            for attempt in range(1, attempts + 1):
                try:
                    connection = sqlalchemy_engine.connect()
                    try:
                        connection.execute(text("SELECT 1"))
                    finally:
                        connection.close()
                    if attempt > 1:
                        logger.info("OBOA database is ready after {} attempts".format(attempt))
                    return True
                except Exception as exc:
                    last_exception = exc
                    logger.warning(
                        "OBOA database is not ready (attempt {}/{}): {}".format(
                            attempt,
                            attempts,
                            exc,
                        )
                    )
                    if attempt < attempts:
                        time.sleep(wait_seconds)
            raise DaemonError(
                "The OBOA database is not available after {} attempt(s): {}".format(
                    attempts,
                    last_exception,
                )
            )
        finally:
            sqlalchemy_engine.dispose()

    def orchestrate_file(self, file_path, reception_date=None):
        """
        Orchestrate one file.

        :param file_path: path to the input file
        :type file_path: str
        :param reception_date: optional reception timestamp
        :type reception_date: str or datetime.datetime or None

        :return: orchestrated-file inventory row
        :rtype: oboa.datamodel.orchestrated_files.OrchestratedFile

        :raises OrchestrationError: when the input file does not exist or cannot
            be staged for processing
        :raises OrchestrationConfigurationError: when the active configuration
            cannot be loaded
        :raises ArchiveDelegationError: when archive delegation fails
        """
        logger.info("Orchestration request received for file {}".format(file_path))
        self._clear_failed_input_moves(file_path)
        reception_date = parse_datetime(reception_date) or datetime.datetime.utcnow()
        if not os.path.exists(file_path):
            message = exit_codes["FILE_DOES_NOT_EXIST"]["message"].format(file_path)
            self._record_operation("orchestrate", exit_codes["FILE_DOES_NOT_EXIST"]["status"], message)
            raise OrchestrationError(message)

        try:
            configuration = self._load_orchestration_configuration(self.configuration_path)
        except OrchestrationConfigurationError as exc:
            self._record_operation("configure", exit_codes["CONFIGURATION_FAILED"]["status"], str(exc))
            raise
        rule = self._match_rule(file_path, self.configuration_xpath)
        file_group = "unknown" if rule is None else rule.get("group")
        processor = None if rule is None else self._configuration_node_text(
            rule,
            "data_processor",
            empty_as_none=True,
        )
        processed = processor is None

        orchestrated_file = OrchestratedFile(
            uuid.uuid4(),
            os.path.basename(file_path),
            file_path,
            file_group,
            reception_date,
            archived=False,
            processed=processed,
            orchestration_configuration=configuration,
        )
        self.session.add(orchestrated_file)
        self.session.commit()

        processing_path = None
        if processor is not None:
            try:
                processing_path = self.prepare_processing_file(file_path, orchestrated_file)
            except Exception as exc:
                message = exit_codes["PROCESSING_STAGE_FAILED"]["message"].format(file_path, exc)
                message = self._move_failed_input_and_extend_message(
                    file_path,
                    orchestrated_file,
                    message,
                )
                self._record_operation(
                    "process",
                    exit_codes["PROCESSING_STAGE_FAILED"]["status"],
                    message,
                    orchestrated_file,
                )
                raise OrchestrationError(message) from exc

        try:
            self._archive_file(file_path, file_group)
            orchestrated_file.archived = True
            self.session.commit()
        except Exception as exc:
            message = exit_codes["ARCHIVE_FAILED"]["message"].format(file_path, exc)
            message = self._move_failed_input_and_extend_message(
                file_path,
                orchestrated_file,
                message,
            )
            self._record_operation(
                "archive",
                exit_codes["ARCHIVE_FAILED"]["status"],
                message,
                orchestrated_file,
            )
            raise ArchiveDelegationError(message) from exc

        if self._delete_after_archive() and os.path.exists(file_path):
            os.remove(file_path)

        if processor is not None:
            try:
                execute_processor(
                    processor,
                    processing_path,
                    orchestrated_file,
                    configuration_uuid=configuration.orchestration_configuration_uuid,
                )
                orchestrated_file.processed = True
                self.session.commit()
            except ProcessorError as exc:
                orchestrated_file.processed = False
                self.session.commit()
                self._record_operation("process", exit_codes["PROCESSOR_FAILED"]["status"], str(exc), orchestrated_file)

        return orchestrated_file

    def prepare_processing_file(self, file_path, orchestrated_file):
        """
        Hard-link or copy a processor-backed file into the processing directory.

        :param file_path: source input file path
        :type file_path: str
        :param orchestrated_file: inventory row for the source file
        :type orchestrated_file: oboa.datamodel.orchestrated_files.OrchestratedFile

        :return: staged processing file path
        :rtype: str

        :raises OrchestrationError: when the processing directory cannot be
            created or written
        """
        processing_dir = self._orchestration_config("processing_dir")
        try:
            os.makedirs(processing_dir, exist_ok=True)
        except OSError as exc:
            raise OrchestrationError(
                exit_codes["PROCESSING_DIR_NOT_AVAILABLE"]["message"].format(processing_dir)
            ) from exc
        if not os.access(processing_dir, os.W_OK):
            raise OrchestrationError(
                exit_codes["PROCESSING_DIR_NOT_AVAILABLE"]["message"].format(processing_dir)
            )

        target_dir = os.path.join(processing_dir, str(orchestrated_file.file_uuid))
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, orchestrated_file.name)
        if os.path.exists(target_path):
            os.remove(target_path)
        try:
            os.link(file_path, target_path)
        except OSError:
            shutil.copy2(file_path, target_path)
        return target_path

    def move_to_error_folder(self, file_path, orchestrated_file):
        """
        Move a failed input out of the polling entry point.

        Failed inputs are stored under ``error_dir/YEAR/MONTH/DAY/file``.

        :param file_path: source input file path
        :type file_path: str
        :param orchestrated_file: inventory row for the source file
        :type orchestrated_file: oboa.datamodel.orchestrated_files.OrchestratedFile

        :return: moved error-file path, or None when the source no longer exists
        :rtype: str or None

        :raises OrchestrationError: when the error directory cannot be created
            or written
        """
        if not os.path.exists(file_path):
            return None

        error_dir = self.engine_configuration.get("ORCHESTRATION", {}).get(
            "error_dir",
            "/oboa_error",
        ) or "/oboa_error"
        error_dir = str(error_dir)
        try:
            os.makedirs(error_dir, exist_ok=True)
        except OSError as exc:
            raise OrchestrationError(
                "The OBOA error directory {} is not available".format(error_dir)
            ) from exc
        if not os.access(error_dir, os.W_OK | os.X_OK):
            raise OrchestrationError(
                "The OBOA error directory {} is not available".format(error_dir)
            )

        target_path = self._build_error_path(
            error_dir,
            datetime.datetime.utcnow(),
            orchestrated_file.name,
        )
        shutil.move(file_path, target_path)
        self._failed_input_moves.append({"source": file_path, "target": target_path})
        return target_path

    def _log_failed_input_moves(self, file_path):
        """
        Log failed-input moves recorded during a polling orchestration failure.

        :param file_path: source input path whose move events should be logged
        :type file_path: str

        :return: None
        :rtype: None
        """
        moves = self._clear_failed_input_moves(file_path)
        for move in moves:
            logger.error(
                "Moved failed OBOA input file {} to {}".format(
                    move["source"],
                    move["target"],
                )
            )

    def _clear_failed_input_moves(self, file_path):
        """
        Remove and return recorded failed-input moves for one source file.

        :param file_path: source input path
        :type file_path: str

        :return: move descriptors for the source file
        :rtype: list
        """
        moves = [
            move for move in self._failed_input_moves
            if move["source"] == file_path
        ]
        self._failed_input_moves = [
            move for move in self._failed_input_moves
            if move["source"] != file_path
        ]
        return moves

    def _build_error_path(self, error_dir, error_date, file_name):
        """
        Build a collision-safe failed-input path below the error directory.

        :param error_dir: configured error folder
        :type error_dir: str
        :param error_date: timestamp used for YEAR/MONTH/DAY folders
        :type error_date: datetime.datetime
        :param file_name: original input file name
        :type file_name: str

        :return: destination error-file path
        :rtype: str

        :raises OSError: when the date-based destination directory cannot be
            created
        """
        directory = os.path.join(
            error_dir,
            error_date.strftime("%Y"),
            error_date.strftime("%m"),
            error_date.strftime("%d"),
        )
        os.makedirs(directory, exist_ok=True)
        destination_path = os.path.join(directory, file_name)
        if not os.path.exists(destination_path):
            return destination_path

        base, extension = os.path.splitext(file_name)
        return os.path.join(directory, "{}_{}{}".format(base, uuid.uuid4(), extension))

    def _move_failed_input_and_extend_message(self, file_path, orchestrated_file, message):
        """
        Move a failed input to the error folder and append the outcome to a message.

        :param file_path: source input file path
        :type file_path: str
        :param orchestrated_file: inventory row for the source file
        :type orchestrated_file: oboa.datamodel.orchestrated_files.OrchestratedFile
        :param message: base failure message
        :type message: str

        :return: failure message extended with the error-folder outcome
        :rtype: str
        """
        try:
            error_path = self.move_to_error_folder(file_path, orchestrated_file)
        except Exception as exc:
            logger.error(
                "Could not move failed OBOA input file {} to the error folder: {}".format(
                    file_path,
                    exc,
                )
            )
            return "{}. The file could not be moved to the error folder: {}".format(message, exc)
        if error_path is None:
            return "{}. The file was no longer present in the entry point".format(message)
        return "{}. The file was moved to {}".format(message, error_path)

    def _load_orchestration_configuration(self, configuration_path=None):
        """
        Load and activate the OBOA orchestration configuration.

        :param configuration_path: optional XML orchestration configuration path.
            When omitted, ``orchestrator_configuration.xml`` is loaded from the
            OBOA resources path.
        :type configuration_path: str or None

        :return: active orchestration configuration row
        :rtype: oboa.datamodel.orchestrated_files.OrchestrationConfiguration

        :raises OrchestrationConfigurationError: when the configuration cannot
            be loaded, parsed, validated, or persisted
        """
        try:
            if configuration_path is None:
                configuration_path = os.path.join(
                    get_resources_path(),
                    "orchestrator_configuration.xml",
                )
            logger.info("Loading OBOA orchestration configuration {}".format(configuration_path))
            configuration_xpath = get_orchestrator_configuration(configuration_path)
            configuration = self._activate_orchestration_configuration(configuration_path)
            self.configuration_xpath = configuration_xpath
            self.configuration_path = configuration_path
            return configuration
        except Exception as exc:
            self.session.rollback()
            raise OrchestrationConfigurationError(exc) from exc

    def _activate_orchestration_configuration(self, configuration_path):
        """
        Ensure the supplied XML configuration path is the active configuration.

        A new history row is created only when the active configuration checksum
        differs from the checksum of the XML content at the supplied path.

        :param configuration_path: source XML orchestration configuration path
        :type configuration_path: str

        :return: active orchestration configuration row
        :rtype: oboa.datamodel.orchestrated_files.OrchestrationConfiguration
        """
        with open(configuration_path, "r", encoding="utf-8") as configuration_file:
            configuration_content = configuration_file.read()
        active_configuration = self.query.get_active_orchestration_configuration()
        configuration_checksum = self._configuration_checksum(configuration_content)
        if active_configuration is not None and (
                self._configuration_checksum(active_configuration.content) == configuration_checksum
        ):
            return active_configuration

        now = datetime.datetime.utcnow()
        active_configurations = self.session.query(OrchestrationConfiguration).filter(
            OrchestrationConfiguration.active == True
        ).all()
        for configuration in active_configurations:
            configuration.active = False
            configuration.active_until = now

        configuration = OrchestrationConfiguration(
            uuid.uuid4(),
            configuration_path,
            now,
            configuration_content,
        )
        self.session.add(configuration)
        self.session.commit()
        return configuration

    def _configuration_checksum(self, configuration_content):
        """
        Calculate a SHA-256 checksum for orchestration configuration text.

        :param configuration_content: raw XML orchestration configuration content
        :type configuration_content: str

        :return: hexadecimal SHA-256 checksum
        :rtype: str
        """
        return hashlib.sha256(configuration_content.encode("utf-8")).hexdigest()

    def _archive_file(self, file_path, file_group):
        """
        Delegate one file to the configured archive client.

        :param file_path: input file path
        :type file_path: str
        :param file_group: matched orchestration group
        :type file_group: str

        :return: archive-client return value
        :rtype: object

        :raises AboaDependencyError: when the default ABOA client cannot be
            initialized
        :raises ArchiveDelegationError: when archive delegation fails
        """
        if self.archive_client is None:
            self.archive_client = AboaArchiveClient()
        return self.archive_client.archive_file(
            file_path,
            file_group=file_group,
            delete_after_archive=self._delete_after_archive(),
        )

    def _orchestration_config(self, name):
        """
        Return one orchestration configuration value.

        :param name: orchestration configuration key
        :type name: str

        :return: configured value
        :rtype: object

        :raises KeyError: when the configuration key is missing
        """
        return self.engine_configuration.get("ORCHESTRATION", {})[name]

    def _delete_after_archive(self):
        """
        Return whether archived inputs should be deleted.

        :return: delete-after-archive flag
        :rtype: bool

        :raises KeyError: when the option is missing from engine configuration
        """
        return bool(self._orchestration_config("delete_after_archive"))

    def _match_rule(self, file_path, configuration_xpath):
        """
        Match an input file against XML orchestration rules.

        :param file_path: input file path
        :type file_path: str
        :param configuration_xpath: parsed orchestration configuration evaluator
        :type configuration_xpath: lxml.etree.XPathEvaluator or None

        :return: matching rule, or None when no rule matches
        :rtype: lxml.etree._Element or None
        """
        if configuration_xpath is None:
            return None
        name = os.path.basename(file_path)
        matching_rules = configuration_xpath(
            "/orchestrator_configuration/data[match(data_mask, $file_name)]",
            file_name=name,
        )
        if len(matching_rules) == 0:
            return None
        return sorted(matching_rules, key=self._rule_priority_key)[0]

    def _polling_priority_key(self, file_path, configuration_xpath):
        """
        Build the sort key used to process polled files by priority.

        :param file_path: ready input file path
        :type file_path: str
        :param configuration_xpath: parsed orchestration configuration evaluator
        :type configuration_xpath: lxml.etree.XPathEvaluator or None

        :return: tuple ordering matched files before unmatched files by priority
        :rtype: tuple
        """
        rule = self._match_rule(file_path, configuration_xpath)
        name = os.path.basename(file_path)
        if rule is None:
            return (1, 0, 0, name)
        priority, order = self._rule_priority_key(rule)
        return (0, priority, order, name)

    def _rule_priority_key(self, rule):
        """
        Build a priority key for one XML orchestration rule node.

        :param rule: XML ``data`` rule node
        :type rule: lxml.etree._Element

        :return: tuple containing configured priority and XML order
        :rtype: tuple
        """
        return (int(rule.get("priority")), self._rule_order(rule))

    def _rule_order(self, rule):
        """
        Return one XML rule node's position in document order.

        :param rule: XML ``data`` rule node
        :type rule: lxml.etree._Element

        :return: zero-based element position under its parent
        :rtype: int
        """
        parent = rule.getparent()
        if parent is None:
            return 0
        return parent.index(rule)

    def _configuration_node_text(self, configuration_node, child_name, empty_as_none=False):
        """
        Return stripped child text from an orchestration XML node.

        :param configuration_node: XML orchestration configuration node
        :type configuration_node: lxml.etree._Element
        :param child_name: child element name to read
        :type child_name: str
        :param empty_as_none: return None instead of an empty string when True
        :type empty_as_none: bool

        :return: stripped child text, or None when requested for empty values
        :rtype: str or None
        """
        text_value = configuration_node.xpath("string({})".format(child_name)).strip()
        if empty_as_none and text_value == "":
            return None
        return text_value

    def _pollable_file(self, name, file_path):
        """
        Check whether a directory entry should be considered for polling.

        :param name: directory entry name
        :type name: str
        :param file_path: absolute or joined file path
        :type file_path: str

        :return: True when the entry is a regular, non-temporary visible file
        :rtype: bool
        """
        if name.startswith("."):
            return False
        if name.endswith((".tmp", ".lock", ".part", "~")):
            return False
        return os.path.isfile(file_path)

    def _is_file_ready(self, file_path):
        """
        Check whether a file appears stable enough to orchestrate.

        :param file_path: input file path
        :type file_path: str

        :return: True when size and modification time are stable
        :rtype: bool
        """
        try:
            first = os.stat(file_path)
            time.sleep(0.05)
            second = os.stat(file_path)
        except OSError:
            return False
        return first.st_size == second.st_size and first.st_mtime == second.st_mtime

    def _record_operation(self, operation, status, message=None, orchestrated_file=None):
        """
        Persist a failed orchestration operation audit row.

        :param operation: operation name
        :type operation: str
        :param status: numeric operation status
        :type status: int
        :param message: optional operation message
        :type message: str or None
        :param orchestrated_file: optional related orchestrated-file row
        :type orchestrated_file: oboa.datamodel.orchestrated_files.OrchestratedFile or None

        :return: persisted operation row, or None for successful statuses
        :rtype: oboa.datamodel.orchestrated_files.OrchestrationOperation or None
        """
        if int(status) == exit_codes["OK"]["status"]:
            return None
        row = OrchestrationOperation(
            uuid.uuid4(),
            operation,
            datetime.datetime.utcnow(),
            status,
            message=message,
            orchestrated_file=orchestrated_file,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def _ensure_daemon_directory(self, directory_path, message, create=False, access_mode=os.W_OK):
        """
        Ensure one daemon directory exists and has the required permissions.

        :param directory_path: directory path to validate
        :type directory_path: str
        :param message: error message used when validation fails
        :type message: str
        :param create: create the directory when it is missing
        :type create: bool
        :param access_mode: permission bits passed to ``os.access``
        :type access_mode: int

        :return: validated directory path
        :rtype: str

        :raises DaemonError: when the directory is unavailable
        """
        if directory_path is None or str(directory_path).strip() == "":
            raise DaemonError(message)
        directory_path = str(directory_path)
        try:
            if create:
                os.makedirs(directory_path, exist_ok=True)
        except (OSError, TypeError) as exc:
            raise DaemonError(message) from exc
        if not os.path.isdir(directory_path) or not os.access(directory_path, access_mode):
            raise DaemonError(message)
        return directory_path

    def _write_pid_file(self, pid_file):
        """
        Write the current process ID to a PID file.

        :param pid_file: PID file path
        :type pid_file: str

        :return: None
        :rtype: None

        :raises OSError: when the PID file cannot be written
        """
        with open(pid_file, "w", encoding="utf-8") as file_handler:
            file_handler.write(str(os.getpid()))

    def _remove_pid_file(self, pid_file):
        """
        Remove a PID file if present.

        :param pid_file: PID file path
        :type pid_file: str

        :return: None
        :rtype: None
        """
        try:
            if os.path.exists(pid_file):
                os.remove(pid_file)
        except OSError:
            logger.warning("Could not remove PID file {}".format(pid_file))

    def _install_signal_handlers(self, pid_file):
        """
        Install signal handlers that request daemon shutdown.

        :param pid_file: PID file removed during signal handling
        :type pid_file: str

        :return: None
        :rtype: None
        """
        def handle_signal(signum, frame):
            """
            Request daemon shutdown after receiving a signal.

            :param signum: received signal number
            :type signum: int
            :param frame: current stack frame
            :type frame: frame

            :return: None
            :rtype: None
            """
            logger.info("OBOA received signal {}".format(signum))
            self._should_stop = True
            self._remove_pid_file(pid_file)

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)
