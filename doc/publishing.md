# Publishing OBOA to PyPI

OBOA's distribution name is `oboa`. Package metadata and the release version
live in `pyproject.toml`. Follow these steps to build, install, and publish a
release on PyPI.

## Validate a release locally

Use a virtual environment with Python 3.9 or newer, such as the environment
inside the development container. From the repository root:

```bash
python3 -m pip install build twine
python3 -m build
python3 -m twine check --strict dist/*
```

Use a fresh `dist/` directory for each build. The default `python3 -m build`
builds the wheel from the source distribution, checking that the source archive
contains everything needed to rebuild it. Twine validates the metadata and
README rendering.

Install each artifact in a separate clean environment outside the source tree,
then run the installed distribution checker. Activate the environment so its
console commands are on `PATH`:

```bash
python3 -m pip install /path/to/oboa/dist/oboa-0.1.0-py3-none-any.whl
python3 -m pip check
python3 /path/to/oboa/tools/check_distribution.py
```

Repeat in another clean environment using `oboa-0.1.0.tar.gz`. Replace `0.1.0`
in these examples with the version being released.

The installed checker verifies the version, license metadata, README, bundled
JSON/XML/XSD/SQL/pgModeler/shell resources, and all six console commands. It also
checks that the initializer resolves its bundled SQL file and executable helper,
using a mock so no database is initialized. Command help checks use a temporary
directory and the packaged configuration defaults.

The publishing workflow performs both installations on Python 3.9 and 3.12,
runs the checker, and executes the configuration, function, and logging tests.

## Publish a release

1. Update `[project].version` in `pyproject.toml` for subsequent releases. Each
   PyPI release needs a new version. The installed package's `oboa.__version__`
   reads the version from its distribution metadata.
2. Commit and push the release changes. Confirm the packaging and integration
   workflows pass.
3. Create and publish a GitHub release whose tag is exactly `v` followed by the
   package version, for example `v0.1.0`, targeting the validated commit.
4. The `oboa-publish.yml` workflow checks the tag against the package version,
   builds the wheel and source distribution, validates their metadata, and
   tests their installations. Its final job uploads those same artifacts to
   PyPI through the `pypi` environment.
5. Verify the release at [OBOA on PyPI](https://pypi.org/project/oboa/) and install
   it in a fresh environment with `python3 -m pip install oboa==0.1.0`.

Pushes, pull requests, and manual workflow runs only build and validate; a
published GitHub release triggers the upload. GitHub prereleases also upload,
so use a PEP 440 prerelease version such as `0.2.0rc1` and tag `v0.2.0rc1` when
publishing a release candidate.

## Manual upload

To upload directly to PyPI, complete the local validation above and configure
your PyPI API token locally, then run:

```bash
python3 -m twine upload dist/*
```
