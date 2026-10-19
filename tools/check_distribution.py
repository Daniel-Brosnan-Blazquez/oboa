"""Check an installed distribution without a source checkout or database."""

import os
from importlib.metadata import distribution
from pathlib import Path
import shlex
import subprocess
import tempfile
from unittest import mock

import oboa
from oboa.engine import functions
from oboa.engine.parsing import get_orchestrator_configuration
from oboa.scripts import oboa_init


def main():
    package = distribution("oboa")
    assert package.version == oboa.__version__
    assert package.metadata["License-Expression"] == "MIT"
    assert package.metadata["Requires-Python"] == ">=3.9"
    assert package.read_text("METADATA").count("# OBOA") >= 1
    files = [str(path) for path in package.files]
    assert not any(path.startswith("tests/") for path in files)
    assert any(path.endswith("/licenses/LICENSE") for path in files)
    assert any(path.endswith("/licenses/AUTHORS") for path in files)

    root = Path(oboa.__file__).parent
    resources = (
        "config/datamodel.json", "config/engine.json",
        "config/orchestrator_configuration.xml",
        "schemas/oboa_orchestrator_configuration.xsd",
        "datamodel/oboa_data_model.sql", "datamodel/oboa_data_model.dbm",
        "scripts/initialize_oboa_ddbb.sh", "scripts/start_oboa.sh",
        "scripts/oboa_init_ddbb.sh",
    )
    for resource in resources:
        assert (root / resource).is_file(), resource
    assert functions.read_configuration()["ORCHESTRATION"]
    get_orchestrator_configuration(str(root / "config/orchestrator_configuration.xml"))

    # The pip-installed initializer must resolve its SQL and helper locally.
    with mock.patch.object(oboa_init, "execute_command") as execute:
        oboa_init.init()
    command = shlex.split(execute.call_args.args[0])
    assert Path(command[0]) == root / "scripts/oboa_init_ddbb.sh"
    assert os.access(command[0], os.X_OK)
    assert Path(command[-1]) == root / "datamodel/oboa_data_model.sql"

    scripts = {entry.name for entry in package.entry_points if entry.group == "console_scripts"}
    assert scripts == {
        "oboa_init.py", "oboa_configure.py", "oboa_orchestrate.py",
        "oboa_poll.py", "oboa_daemon.py", "oboa_query.py",
    }
    with tempfile.TemporaryDirectory(prefix="oboa-package-check-") as directory:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        for variable in ("OBOA_RESOURCES_PATH", "OBOA_SCHEMAS_PATH"):
            environment.pop(variable, None)
        environment["OBOA_LOG_PATH"] = directory
        for script in sorted(scripts):
            subprocess.run(
                [script, "--help"], check=True, cwd=directory,
                env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
    print("Installed OBOA {}: resources, initializer, and six commands passed".format(package.version))


if __name__ == "__main__":
    main()
