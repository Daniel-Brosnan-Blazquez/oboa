"""
Tests for OBOA integration with the ABOA archive interface.
"""

import builtins
import os
import shutil
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("OBOA_LOG_PATH", "/tmp/oboa_log")

from oboa.engine.archive_client import AboaArchiveClient
from oboa.engine.errors import AboaDependencyError, ArchiveDelegationError


INPUTS = Path(__file__).parent / "inputs"
ABOA_TEST_RESOURCES = INPUTS / "aboa_resources"
ABOA_TEST_ARCHIVE_ROOT = Path("/tmp/oboa_test_aboa_archive")


class MockAboaEngine():
    """
    Test double for the ABOA engine interface used by OBOA.
    """

    instances = []
    archive_result = {"archived": True}
    archive_error = None
    close_error = None

    def __init__(self):
        """
        Record each mock engine instance created by the adapter.
        """
        self.archive_calls = []
        self.closed = False
        MockAboaEngine.instances.append(self)

    def archive_file(self, *args, **kwargs):
        """
        Capture archive calls and optionally simulate an archive failure.
        """
        self.archive_calls.append((args, kwargs))
        if MockAboaEngine.archive_error is not None:
            raise MockAboaEngine.archive_error
        return MockAboaEngine.archive_result

    def close_session(self):
        """
        Capture session closure and optionally simulate a close failure.
        """
        self.closed = True
        if MockAboaEngine.close_error is not None:
            raise MockAboaEngine.close_error


class TestAboaIntegration(unittest.TestCase):
    """
    Verify the OBOA adapter uses the ABOA archive interface correctly.
    """

    def setUp(self):
        """
        Install a mock ABOA package tree for adapter unit tests.
        """
        self.original_modules = self.snapshot_aboa_modules()
        self.install_mock_aboa(MockAboaEngine)
        MockAboaEngine.instances = []
        MockAboaEngine.archive_result = {"archived": True}
        MockAboaEngine.archive_error = None
        MockAboaEngine.close_error = None

    def tearDown(self):
        """
        Restore any real ABOA modules that were loaded before the test.
        """
        self.restore_original_aboa_modules()

    def snapshot_aboa_modules(self):
        """
        Remember loaded ABOA modules so mocked imports do not leak between tests.
        """
        return {
            name: module
            for name, module in sys.modules.items()
            if name == "aboa" or name.startswith("aboa.")
        }

    def clear_aboa_modules(self):
        """
        Remove all loaded ABOA modules from the Python import cache.
        """
        for name in list(sys.modules):
            if name == "aboa" or name.startswith("aboa."):
                sys.modules.pop(name, None)

    def restore_original_aboa_modules(self):
        """
        Put the import cache back the way it was before the test.
        """
        self.clear_aboa_modules()
        for name, module in self.original_modules.items():
            sys.modules[name] = module

    def install_mock_aboa(self, engine_class):
        """
        Create the minimal module hierarchy imported by ``AboaArchiveClient``.
        """
        self.clear_aboa_modules()
        # The adapter imports from aboa.engine.engine, so the mock must mirror
        # that package structure instead of replacing only the top-level module.
        aboa_module = types.ModuleType("aboa")
        engine_package = types.ModuleType("aboa.engine")
        engine_module = types.ModuleType("aboa.engine.engine")
        engine_module.Engine = engine_class
        aboa_module.engine = engine_package
        engine_package.engine = engine_module
        sys.modules["aboa"] = aboa_module
        sys.modules["aboa.engine"] = engine_package
        sys.modules["aboa.engine.engine"] = engine_module

    def real_aboa_environment(self):
        """
        Build the environment used by the optional real ABOA integration test.
        """
        return {
            "ABOA_RESOURCES_PATH": str(ABOA_TEST_RESOURCES),
            "ABOA_DDBB_HOST": os.environ.get(
                "ABOA_DDBB_HOST",
                os.environ.get("OBOA_DDBB_HOST", "localhost"),
            ),
            "ABOA_LOG_PATH": os.environ.get("ABOA_LOG_PATH", "/tmp/oboa_log"),
            "ABOA_DEFAULT_ARCHIVE_PATH": str(ABOA_TEST_ARCHIVE_ROOT),
        }

    def import_real_aboa_engine_or_skip(self):
        """
        Import the actual ABOA engine, skipping when it is not installed.
        """
        self.clear_aboa_modules()
        try:
            from aboa.engine.engine import Engine as RealAboaEngine
        except Exception as exc:
            self.skipTest("ABOA package is not available in this environment: {}".format(exc))
        return RealAboaEngine

    def prepare_real_aboa_database_or_skip(self):
        """
        Create and clear ABOA tables for an optional real integration run.
        """
        try:
            from aboa.datamodel.base import Base as AboaBase
            from aboa.datamodel.base import engine as aboa_sqlalchemy_engine
            from aboa.engine.query import Query as AboaQuery
        except Exception as exc:
            self.skipTest("ABOA database interface is not available: {}".format(exc))

        query = None
        try:
            # Keep setup deterministic, but do not clean up afterward so a
            # completed integration run remains inspectable.
            AboaBase.metadata.create_all(aboa_sqlalchemy_engine)
            query = AboaQuery()
            query.clear_db()
        except Exception as exc:
            self.skipTest("ABOA database is not available: {}".format(exc))
        finally:
            if query is not None:
                query.close_session()
        return AboaQuery

    def prepare_oboa_database_or_skip(self):
        """
        Create and clear OBOA tables for an optional real integration run.
        """
        try:
            from oboa.datamodel.base import Base as OboaBase
            from oboa.datamodel.base import engine as oboa_sqlalchemy_engine
            from oboa.engine.engine import Engine as OboaEngine
            from oboa.engine.query import Query as OboaQuery
        except Exception as exc:
            self.skipTest("OBOA database interface is not available: {}".format(exc))

        query = None
        try:
            # Keep setup deterministic, but do not clean up afterward so a
            # completed integration run remains inspectable.
            OboaBase.metadata.create_all(oboa_sqlalchemy_engine)
            query = OboaQuery()
            query.clear_db()
        except Exception as exc:
            self.skipTest("OBOA database is not available: {}".format(exc))
        finally:
            if query is not None:
                query.close_session()
        return OboaEngine, OboaQuery

    def test_archive_client_calls_aboa_archive_file_with_group_metadata(self):
        """
        Pass the OBOA file group to ABOA as archive metadata.
        """
        path = str(INPUTS / "sample.txt")
        client = AboaArchiveClient()

        result = client.archive_file(path, file_group="texts", delete_after_archive=True)

        aboa_engine = MockAboaEngine.instances[0]
        assert result == {"archived": True}
        assert aboa_engine.archive_calls == [
            ((path,), {"metadata": {"file_group": "texts"}, "delete": True})
        ]
        assert aboa_engine.closed is True

    def test_archive_client_calls_aboa_archive_file_without_group_metadata(self):
        """
        Archive through ABOA with empty metadata when no group is supplied.
        """
        path = str(INPUTS / "sample.txt")
        client = AboaArchiveClient()

        result = client.archive_file(path, delete_after_archive=False)

        aboa_engine = MockAboaEngine.instances[0]
        assert result == {"archived": True}
        assert aboa_engine.archive_calls == [
            ((path,), {"metadata": {}, "delete": False})
        ]
        assert aboa_engine.closed is True

    def test_archive_client_closes_aboa_session_when_archive_fails(self):
        """
        Close the ABOA session even when the archive operation fails.
        """
        path = str(INPUTS / "sample.txt")
        MockAboaEngine.archive_error = RuntimeError("archive failed")
        client = AboaArchiveClient()

        with self.assertRaises(ArchiveDelegationError):
            client.archive_file(path, file_group="texts")

        aboa_engine = MockAboaEngine.instances[0]
        assert aboa_engine.closed is True

    def test_archive_client_ignores_aboa_close_session_failure_after_success(self):
        """
        Preserve archive success when only the downstream close operation fails.
        """
        path = str(INPUTS / "sample.txt")
        MockAboaEngine.close_error = RuntimeError("close failed")
        client = AboaArchiveClient()

        result = client.archive_file(path, file_group="texts")

        aboa_engine = MockAboaEngine.instances[0]
        assert result == {"archived": True}
        assert aboa_engine.closed is True

    def test_archive_client_reports_missing_aboa_dependency(self):
        """
        Convert a missing ABOA import into OBOA's dependency error.
        """
        original_import = builtins.__import__
        self.clear_aboa_modules()

        def import_without_aboa(name, globals=None, locals=None, fromlist=(), level=0):
            """
            Raise an import error only for the ABOA engine dependency.
            """
            if name == "aboa.engine.engine":
                raise ImportError("missing aboa")
            return original_import(name, globals, locals, fromlist, level)

        with mock.patch("builtins.__import__", side_effect=import_without_aboa):
            with self.assertRaises(AboaDependencyError):
                AboaArchiveClient()

    def test_oboa_orchestrates_file_using_actual_aboa_when_available(self):
        """
        Orchestrate through OBOA while using real ABOA as archive provider.
        """
        file_name = "aboa_archive_success.txt"
        input_file = INPUTS / file_name

        with mock.patch.dict(os.environ, self.real_aboa_environment()):
            self.import_real_aboa_engine_or_skip()
            AboaQuery = self.prepare_real_aboa_database_or_skip()
            OboaEngine, OboaQuery = self.prepare_oboa_database_or_skip()
            # Start with an empty archive root so the payload assertion proves
            # this OBOA orchestration pass triggered the downstream archive.
            shutil.rmtree(str(ABOA_TEST_ARCHIVE_ROOT), ignore_errors=True)

            engine = OboaEngine()
            try:
                engine.set_configuration_path(
                    str(INPUTS / "orchestrator_texts_without_processor.xml")
                )
                # Keep the persistent input fixture available for repeated test
                # runs; ABOA still stores its own managed archive payload.
                engine.engine_configuration["ORCHESTRATION"]["delete_after_archive"] = False
                orchestrated_file = engine.orchestrate_file(str(input_file))
                orchestrated_file_uuid = str(orchestrated_file.file_uuid)
            finally:
                engine.close_session()

            oboa_query = OboaQuery()
            try:
                orchestrated_files = oboa_query.get_orchestrated_files(
                    file_uuids={"filter": [orchestrated_file_uuid], "op": "in"},
                )
            finally:
                oboa_query.close_session()

            aboa_query = AboaQuery()
            try:
                archived_files = aboa_query.get_archived_files(
                    names={"filter": [file_name], "op": "in"},
                    selection="last",
                )
            finally:
                aboa_query.close_session()

        assert len(orchestrated_files) == 1
        orchestrated_file = orchestrated_files[0]
        assert orchestrated_file.name == file_name
        assert orchestrated_file.file_group == "texts"
        assert orchestrated_file.archived is True
        assert orchestrated_file.processed is True
        assert input_file.exists()
        assert len(archived_files) == 1
        archived_file = archived_files[0]
        assert archived_file.file_group == "texts"
        assert archived_file.available is True
        assert archived_file.physically_available is True
        assert os.path.exists(archived_file.path)
        assert os.path.commonpath([
            str(ABOA_TEST_ARCHIVE_ROOT),
            archived_file.path,
        ]) == str(ABOA_TEST_ARCHIVE_ROOT)
        assert "texts" in Path(archived_file.path).parts
        assert Path(archived_file.path).read_text(
            encoding="utf-8"
        ) == input_file.read_text(encoding="utf-8")
