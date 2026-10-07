"""
Tests for OBOA polling.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("OBOA_LOG_PATH", "/tmp/oboa_log")

from oboa.datamodel.base import Base, engine as sqlalchemy_engine
from oboa.engine.engine import Engine
from oboa.engine.query import Query
from tests.test_engine import MockArchiveClient


INPUTS = Path(__file__).parent / "inputs"


class TestPolling(unittest.TestCase):
    """
    Polling behavior tests.
    """

    def setUp(self):
        """
        Prepare an isolated polling directory for each polling test.
        """
        Base.metadata.create_all(sqlalchemy_engine)
        query = Query()
        query.clear_db()
        query.close_session()
        self.root = Path(tempfile.mkdtemp(prefix="oboa_polling_"))
        self.polling_dir = self.root / "polling"
        self.processing_dir = self.root / "processing"
        self.polling_dir.mkdir()
        self.processing_dir.mkdir()
        self.configuration = INPUTS / "orchestrator_texts_without_processor.xml"

    def tearDown(self):
        """
        Remove temporary files created for the polling pass.
        """
        shutil.rmtree(str(self.root), ignore_errors=True)

    def copy_input(self, name):
        """
        Copy a persistent input fixture into the polled folder.
        """
        shutil.copy2(str(INPUTS / name), str(self.polling_dir / name))

    def test_poll_once_ignores_hidden_and_temp_files(self):
        """
        Process only visible, stable files during one polling pass.
        """
        self.copy_input(".hidden.txt")
        self.copy_input("skip.tmp")
        self.copy_input("sample.txt")
        engine = Engine(archive_client=MockArchiveClient())
        engine.set_configuration_path(str(self.configuration))
        engine.engine_configuration["ORCHESTRATION"]["processing_dir"] = str(self.processing_dir)

        rows = engine.poll_once(polling_dir=str(self.polling_dir))

        assert [row.name for row in rows] == ["sample.txt"]
        engine.close_session()

    def test_poll_once_orchestrates_files_by_configured_priority(self):
        """
        Orchestrate matched files according to XML rule priority.
        """
        self.copy_input("a_low_priority.bin")
        self.copy_input("z_high_priority.txt")
        archive_client = MockArchiveClient()
        engine = Engine(archive_client=archive_client)
        engine.set_configuration_path(str(INPUTS / "orchestrator_valid.xml"))
        engine.engine_configuration["ORCHESTRATION"]["processing_dir"] = str(self.processing_dir)

        rows = engine.poll_once(polling_dir=str(self.polling_dir))

        assert [row.name for row in rows] == ["z_high_priority.txt", "a_low_priority.bin"]
        assert [call[1] for call in archive_client.calls] == ["high", "low"]
        assert engine.query.get_orchestration_operations() == []
        engine.close_session()
