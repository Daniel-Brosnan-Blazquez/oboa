"""
Tests for OBOA logging.
"""

import logging
import os
import shutil
import tempfile
import unittest
from unittest import mock


from oboa.engine.functions import default_resources_path
from oboa.logging import Log, RotatingFileHandlerAllUsers


class TestLogging(unittest.TestCase):
    """
    Logging configuration tests.
    """

    def cleanup_logger(self, name):
        """
        Remove handlers from a test logger after inspection.
        """
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def test_log_file_is_created(self):
        """
        Create a log file in the configured OBOA log directory.
        """
        log_dir = tempfile.mkdtemp(prefix="oboa_log_")
        previous = os.environ.get("OBOA_LOG_PATH")
        os.environ["OBOA_LOG_PATH"] = log_dir
        logger_name = "oboa.tests.logging.created"
        self.addCleanup(self.cleanup_logger, logger_name)
        try:
            logger = Log(name=logger_name, log_name="test.log").logger
            logger.info("hello")
            assert os.path.exists(os.path.join(log_dir, "test.log"))
        finally:
            if previous is None:
                os.environ.pop("OBOA_LOG_PATH", None)
            else:
                os.environ["OBOA_LOG_PATH"] = previous
            shutil.rmtree(log_dir, ignore_errors=True)

    def test_environment_logging_options_configure_handlers_and_level(self):
        """
        Apply environment log level, stream logging, and rotation settings.
        """
        log_dir = tempfile.mkdtemp(prefix="oboa_log_")
        logger_name = "oboa.tests.logging.environment"
        self.addCleanup(self.cleanup_logger, logger_name)
        self.addCleanup(shutil.rmtree, log_dir, True)
        env = {
            "OBOA_RESOURCES_PATH": default_resources_path(),
            "OBOA_LOG_PATH": log_dir,
            "OBOA_LOG_LEVEL": "DEBUG",
            "OBOA_STREAM_LOG": "1",
            "OBOA_LOG_MAX_BYTES": "123",
            "OBOA_LOG_MAX_BACKUP": "2",
        }

        with mock.patch.dict(os.environ, env):
            logger = Log(name=logger_name, log_name="environment.log").logger

        stream_handlers = [
            handler for handler in logger.handlers
            if type(handler) == logging.StreamHandler
        ]
        file_handlers = [
            handler for handler in logger.handlers
            if type(handler) == RotatingFileHandlerAllUsers
        ]
        assert logger.level == logging.DEBUG
        assert len(stream_handlers) == 1
        assert len(file_handlers) == 1
        assert file_handlers[0].maxBytes == 123
        assert file_handlers[0].backupCount == 2

        with mock.patch.dict(os.environ, env):
            logger_again = Log(name=logger_name, log_name="environment.log").logger

        assert logger_again is logger
        assert [
            handler for handler in logger.handlers
            if type(handler) == RotatingFileHandlerAllUsers
        ] == file_handlers

    def test_default_logger_name_and_custom_debugp_level(self):
        """
        Support the default logger name and custom DEBUGP logging level.
        """
        log_dir = tempfile.mkdtemp(prefix="oboa_log_")
        logger_name = "oboa.logging"
        self.addCleanup(self.cleanup_logger, logger_name)
        self.addCleanup(shutil.rmtree, log_dir, True)
        env = {
            "OBOA_RESOURCES_PATH": default_resources_path(),
            "OBOA_LOG_PATH": log_dir,
            "OBOA_LOG_LEVEL": "DEBUGP",
        }

        with mock.patch.dict(os.environ, env):
            logger = Log(log_name="default.log").logger

        assert logger.name == logger_name
        with self.assertLogs(logger_name, level="DEBUGP") as captured:
            logger.debugp("custom level message")
        assert any("custom level message" in message for message in captured.output)

        logger.setLevel(logging.CRITICAL)
        logger.debugp("disabled custom level message")

    def test_rollover_relaxes_permissions_on_new_log_file(self):
        """
        Keep rotated log files writable by all users.
        """
        log_dir = tempfile.mkdtemp(prefix="oboa_log_")
        self.addCleanup(shutil.rmtree, log_dir, True)
        path = os.path.join(log_dir, "rollover.log")
        handler = RotatingFileHandlerAllUsers(path, maxBytes=1, backupCount=1)
        self.addCleanup(handler.close)

        handler.emit(logging.makeLogRecord({"msg": "before rollover", "levelno": logging.INFO}))
        handler.doRollover()

        assert os.path.exists(path)
        assert os.stat(path).st_mode & 0o777 == 0o666
