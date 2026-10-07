"""
Daemon lifecycle helpers for OBOA.
"""

import os
import signal
import time

from oboa.engine.engine import Engine
from oboa.engine.errors import DaemonError


class DaemonManager():
    """
    Manage OBOA daemon start, stop, restart, and status operations.
    """

    def __init__(self, pid_file):
        """
        Create a daemon manager for a PID file.

        :param pid_file: path where the daemon PID is stored
        :type pid_file: str

        :return: None
        :rtype: None
        """
        self.pid_file = pid_file or "/tmp/oboa.pid"

    def status(self):
        """
        Return daemon status.

        :return: dictionary with ``running`` and ``pid`` keys
        :rtype: dict
        """
        pid = self._read_pid()
        if pid is None:
            return {"running": False, "pid": None}
        if self._pid_running(pid):
            return {"running": True, "pid": pid}
        self._remove_stale_pid_file()
        return {"running": False, "pid": None}

    def start(self, foreground=False, polling_dir=None, polling_frequency=None,
              configuration_path=None):
        """
        Start the OBOA daemon.

        :param foreground: run the polling loop in the current process
        :type foreground: bool
        :param polling_dir: optional polling directory override
        :type polling_dir: str or None
        :param polling_frequency: optional polling frequency override in seconds
        :type polling_frequency: int or float or None
        :param configuration_path: optional orchestration configuration path
        :type configuration_path: str or None

        :return: dictionary with ``running`` and ``pid`` keys
        :rtype: dict

        :raises DaemonError: when the daemon is already running or a required
            runtime directory is unavailable
        """
        status = self.status()
        if status["running"]:
            raise DaemonError("The OBOA daemon is already running with PID {}".format(status["pid"]))

        engine = self._make_engine(configuration_path)
        try:
            engine.validate_daemon_startup(
                polling_dir=polling_dir,
                pid_file=self.pid_file,
            )
        except DaemonError:
            raise
        except Exception as exc:
            raise DaemonError("The OBOA daemon failed: {}".format(exc)) from exc
        finally:
            engine.close_session()

        if foreground:
            runtime_engine = self._make_engine(configuration_path)
            try:
                runtime_engine.run_daemon(
                    polling_dir=polling_dir,
                    polling_frequency=polling_frequency,
                    pid_file=self.pid_file,
                    foreground=True,
                )
            finally:
                runtime_engine.close_session()
            return {"running": True, "pid": os.getpid()}

        pid = os.fork()
        if pid > 0:
            time.sleep(0.1)
            return {"running": True, "pid": pid}

        os.setsid()
        runtime_engine = self._make_engine(configuration_path)
        try:
            runtime_engine.run_daemon(
                polling_dir=polling_dir,
                polling_frequency=polling_frequency,
                pid_file=self.pid_file,
                foreground=True,
            )
        finally:
            runtime_engine.close_session()
        os._exit(0)

    def stop(self):
        """
        Stop the OBOA daemon.

        :return: dictionary with ``running`` and ``pid`` keys
        :rtype: dict

        :raises DaemonError: when the daemon does not stop within the timeout
        """
        status = self.status()
        if not status["running"]:
            return {"running": False, "pid": None}
        pid = status["pid"]
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            if self._pid_file_matches(pid):
                self._remove_stale_pid_file()
            return {"running": False, "pid": None}
        for _ in range(50):
            if not self._pid_file_matches(pid):
                return {"running": False, "pid": None}
            if not self._pid_running(pid):
                if self._pid_file_matches(pid):
                    self._remove_stale_pid_file()
                return {"running": False, "pid": None}
            time.sleep(0.1)
        if not self._pid_file_matches(pid):
            return {"running": False, "pid": None}
        raise DaemonError("The OBOA daemon with PID {} did not stop".format(pid))

    def restart(self, foreground=False, polling_dir=None, polling_frequency=None,
                configuration_path=None):
        """
        Restart the daemon.

        :param foreground: run the polling loop in the current process
        :type foreground: bool
        :param polling_dir: optional polling directory override
        :type polling_dir: str or None
        :param polling_frequency: optional polling frequency override in seconds
        :type polling_frequency: int or float or None
        :param configuration_path: optional orchestration configuration path
        :type configuration_path: str or None

        :return: dictionary with ``running`` and ``pid`` keys
        :rtype: dict

        :raises DaemonError: when stop or start fails
        """
        self.stop()
        return self.start(
            foreground=foreground,
            polling_dir=polling_dir,
            polling_frequency=polling_frequency,
            configuration_path=configuration_path,
        )

    def _make_engine(self, configuration_path=None):
        """
        Create an engine configured with the requested orchestration XML.

        :param configuration_path: optional orchestration configuration path
        :type configuration_path: str or None

        :return: configured engine instance
        :rtype: oboa.engine.engine.Engine
        """
        engine = Engine()
        if configuration_path is not None:
            engine.set_configuration_path(configuration_path)
        return engine

    def _read_pid(self):
        """
        Read the PID file.

        :return: PID value, or None when the file is absent or invalid
        :rtype: int or None
        """
        if not os.path.exists(self.pid_file):
            return None
        try:
            with open(self.pid_file, encoding="utf-8") as file_handler:
                return int(file_handler.read().strip())
        except (OSError, ValueError):
            return None

    def _pid_running(self, pid):
        """
        Check whether a PID is currently running.

        :param pid: process ID to inspect
        :type pid: int

        :return: True when the process exists
        :rtype: bool
        """
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _pid_file_matches(self, pid):
        """
        Check whether the PID file still points to the expected daemon process.

        :param pid: expected process ID
        :type pid: int

        :return: True when the PID file exists and still contains ``pid``
        :rtype: bool
        """
        return self._read_pid() == pid

    def _remove_stale_pid_file(self):
        """
        Remove a stale PID file if it exists.

        :return: None
        :rtype: None
        """
        try:
            if os.path.exists(self.pid_file):
                os.remove(self.pid_file)
        except OSError:
            pass
