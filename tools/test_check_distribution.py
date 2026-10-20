"""Regression tests for release validation and installed console launchers."""

from importlib.metadata import PackagePath
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from check_distribution import RESOURCES, check_contents, check_metadata, resolve_console_script


class DistributionValidationTests(unittest.TestCase):
    """Reject incomplete artifacts and releases with mismatched tags."""

    metadata = b"""Metadata-Version: 2.4
Name: oboa
Version: 0.1.0
Requires-Python: >=3.9
License-Expression: MIT
Description-Content-Type: text/markdown
Requires-Dist: aboa==0.2.0
Project-URL: Repository, https://github.com/Daniel-Brosnan-Blazquez/oboa

# OBOA
"""

    def test_release_metadata_accepts_matching_tag(self):
        self.assertEqual(check_metadata(self.metadata, "v0.1.0")["Version"], "0.1.0")

    def test_release_metadata_rejects_mismatched_tag(self):
        with self.assertRaisesRegex(SystemExit, "Release tag must match v0.1.0"):
            check_metadata(self.metadata, "v9.9.9")

    def test_release_metadata_rejects_missing_required_fields(self):
        for field in (
            b"Version: 0.1.0\n", b"License-Expression: MIT\n",
            b"Requires-Python: >=3.9\n", b"Requires-Dist: aboa==0.2.0\n",
        ):
            with self.subTest(field=field), self.assertRaises(SystemExit):
                check_metadata(self.metadata.replace(field, b""), "")

    def test_release_metadata_rejects_another_project(self):
        with self.assertRaisesRegex(SystemExit, "Unexpected distribution name"):
            check_metadata(self.metadata.replace(b"Name: oboa", b"Name: other"), "")

    def test_contents_require_resources_in_wheel_and_source_archive(self):
        for prefix in ("", "oboa-0.1.0/src/"):
            names = {prefix + "oboa/" + resource for resource in RESOURCES}
            with self.subTest(prefix=prefix):
                check_contents(names, prefix)
                names.remove(prefix + "oboa/" + RESOURCES[0])
                with self.assertRaisesRegex(SystemExit, "Missing resource"):
                    check_contents(names, prefix)

    def test_contents_reject_test_output_and_python_caches(self):
        names = {"oboa/" + resource for resource in RESOURCES}
        for artifact in (
            "tests/test_engine.py", "oboa/__pycache__/engine.pyc",
            ".pytest_cache/README.md", ".coverage", "oboa/engine.pyc",
        ):
            with self.subTest(artifact=artifact):
                with self.assertRaisesRegex(SystemExit, "Development artifact"):
                    check_contents(names | {artifact}, "")


class ConsoleScriptTests(unittest.TestCase):
    """
    Verify launcher discovery across supported installation locations.
    """

    def setUp(self):
        """
        Create an isolated package layout and mock script search locations.
        """
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packages = self.root / "lib" / "python3.12" / "site-packages"
        self.packages.mkdir(parents=True)
        self.command = "oboa_init.py"
        self.distribution = Mock()
        self.distribution.files = [PackagePath("oboa/scripts/" + self.command)]
        self.distribution.locate_file.side_effect = lambda file: self.packages / file
        self.addCleanup(patch.stopall)
        self.default_scripts = self.root / "system-bin"
        patch("check_distribution.sysconfig.get_path", return_value=str(self.default_scripts)).start()
        self.which = patch("check_distribution.shutil.which", return_value=None).start()

    def launcher(self, folder):
        """
        Create an executable launcher fixture in ``folder`` and return its path.
        """
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / self.command
        path.write_text("#!/usr/bin/env python3\n")
        path.chmod(0o755)
        return path

    def test_user_install_uses_recorded_launcher_when_not_on_path(self):
        """
        Find a recorded user launcher while ignoring a matching package module.
        """
        launcher = self.launcher(self.root / "bin")
        self.distribution.files.append(PackagePath("../../../bin/" + self.command))
        # A package module has the same basename but is not a console launcher.
        self.launcher(self.packages / "oboa" / "scripts")
        self.assertEqual(resolve_console_script(self.command, self.distribution), launcher)

    def test_virtual_environment_uses_its_scripts_directory(self):
        """
        Find a launcher in the interpreter's scripts directory without PATH.
        """
        launcher = self.launcher(self.default_scripts)
        self.assertEqual(resolve_console_script(self.command, self.distribution), launcher)

    def test_target_install_finds_bin_inside_distribution_root(self):
        """
        Find a target installation's launcher in its local ``bin`` directory.
        """
        launcher = self.launcher(self.packages / "bin")
        self.assertEqual(resolve_console_script(self.command, self.distribution), launcher)

    def test_custom_launcher_can_be_found_on_path(self):
        """
        Use PATH when the launcher is absent from the other search locations.
        """
        launcher = self.launcher(self.root / "custom-bin")
        self.which.return_value = str(launcher)
        self.assertEqual(resolve_console_script(self.command, self.distribution), launcher)

    def test_missing_or_non_executable_launcher_has_actionable_error(self):
        """
        Reject a non-executable launcher with a clear installation error.
        """
        launcher = self.launcher(self.default_scripts)
        launcher.chmod(0o644)
        with self.assertRaisesRegex(SystemExit, "Installed console command oboa_init.py was not found"):
            resolve_console_script(self.command, self.distribution)


if __name__ == "__main__":
    unittest.main()
