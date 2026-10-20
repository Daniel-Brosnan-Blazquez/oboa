"""
Logging definition for OBOA.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from oboa.engine.functions import get_log_path, read_configuration


class RotatingFileHandlerAllUsers(RotatingFileHandler):
    """
    Rotating file handler that keeps new log files writable by all users.
    """

    def doRollover(self):
        """
        Rotate the log file and relax permissions on the new file.

        :return: None
        :rtype: None

        :raises OSError: when chmod fails
        """
        RotatingFileHandler.doRollover(self)
        os.chmod(self.baseFilename, 0o666)


class Log():
    """
    Configure and expose an OBOA logger.
    """

    def __init__(self, name=None, log_name="oboa_engine.log"):
        """
        Initialize an OBOA logger wrapper.

        :param name: logger name, defaulting to this module
        :type name: str or None
        :param log_name: rotating log file name
        :type log_name: str

        :return: None
        :rtype: None
        """
        self.log_name = log_name
        self._add_new_level("DEBUGP", 15)
        self.define_logging_configuration(name)

    def define_logging_configuration(self, name=None):
        """
        Configure handlers, formatter, and log level.

        :param name: logger name, defaulting to this module
        :type name: str or None

        :return: None
        :rtype: None

        :raises OboaLogPathNotAvailable: when the configured log path cannot be
            created
        :raises KeyError: when required logging configuration keys are missing
        :raises AttributeError: when the configured log level is unknown
        """
        if name is None:
            name = __name__
        config = read_configuration()
        log_path = get_log_path()
        self.logger = logging.getLogger(name)
        if "OBOA_LOG_LEVEL" in os.environ:
            self.logger.setLevel(getattr(logging, os.environ["OBOA_LOG_LEVEL"]))
        else:
            self.logger.setLevel(getattr(logging, config["LOG"]["LEVEL"]))

        formatter = logging.Formatter(
            "%(levelname)s\t; (%(asctime)s.%(msecs)03d) ; %(name)s(%(lineno)d) [%(process)d] -> %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

        stream_handlers = [
            handler for handler in self.logger.handlers
            if type(handler) == logging.StreamHandler
        ]
        if "OBOA_STREAM_LOG" in os.environ and len(stream_handlers) < 1:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)

        max_bytes = int(os.environ.get("OBOA_LOG_MAX_BYTES", config["LOG"]["MAX_BYTES"]))
        max_backup = int(os.environ.get("OBOA_LOG_MAX_BACKUP", config["LOG"]["MAX_BACKUP"]))
        os.makedirs(log_path, exist_ok=True)

        file_handlers = [
            handler for handler in self.logger.handlers
            if type(handler) == RotatingFileHandlerAllUsers
        ]
        if len(file_handlers) < 1:
            file_handler = RotatingFileHandlerAllUsers(
                os.path.join(log_path, self.log_name),
                maxBytes=max_bytes,
                backupCount=max_backup,
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def _add_new_level(self, name, level):
        """
        Add a custom logging level to the logging module.

        :param name: logging level name
        :type name: str
        :param level: numeric logging level
        :type level: int

        :return: None
        :rtype: None
        """
        logging.addLevelName(level, name)

        def log_for_level(self, message, *args, **kwargs):
            """
            Log a message using the custom level.

            :param message: log message
            :type message: str
            :param args: positional formatting arguments
            :type args: tuple
            :param kwargs: keyword arguments passed to ``Logger._log``
            :type kwargs: dict

            :return: None
            :rtype: None
            """
            if self.isEnabledFor(level):
                self._log(level, message, args, **kwargs)

        setattr(logging, name, level)
        setattr(logging.getLoggerClass(), name.lower(), log_for_level)
