# OBOA Development Plan

This plan describes how to develop the OBOA component from the requirements in
`OBOA_requirements.md`, using established component conventions for package
layout, configuration, database access, logging, command-line tooling, Docker,
and tests.

OBOA stands for Orchestrator for Business Operations Analysis. Its responsibility
is to poll an input directory, classify each received file with an orchestration
configuration, optionally run an executable data processor, archive the file
through ABOA, optionally delete the archived input file,
stage processor-backed files in a configurable internal processing directory, and
keep a PostgreSQL inventory of orchestrated files, configurations, and operation
history.

## 1. Target Architecture

Use this architecture for the first OBOA version:

- Package source under `src/oboa`.
- Keep code separated by concern: `datamodel`, `engine`, `processors`,
  `scripts`, `config`, `schemas`, database model artifacts, and `tests`.
- Use SQLAlchemy declarative models in `oboa.datamodel`, with `Base`,
  `Session`, and the SQLAlchemy engine initialized from `src/oboa/config/datamodel.json`.
- Use a high-level `Engine` class for mutation workflows: configuration loading,
  file orchestration, polling, processor execution, and ABOA archive delegation.
- Use a `Query` class for read-only inventory access and filtering.
- Run the polling loop as a daemon for production operation, with a foreground
  mode for Docker and test execution.
- Use project-wide rotating-file logging through `oboa.logging.Log`, with
  OBOA-specific environment variables and log file names.
- Validate XML configuration files with `lxml` and an XSD schema before accepting
  them.
- Install command line tools through `src/setup.py` `console_scripts`.
- Keep tests under `src/tests` using a database-lifecycle pattern: clear database
  tables in `setUp`, close sessions in `tearDown`, use fixture XML and scripts
  under `src/tests/inputs`, and assert JSON-friendly `jsonify()` outputs.

The first implementation should be a command-line component. REST APIs are not in
the OBOA requirements and should not be included in this development step.

## 2. Target Repository Layout

Create the following structure:

```text
oboa/
  AUTHORS
  Dockerfile.dev
  Dockerfile.github.dev
  README.md
  compose_dev.yml
  compose_github_dev.yml
  .github/
    workflows/
      oboa-testing.yml
  src/
    MANIFEST.in
    __init__.py
    setup.py
    oboa/
      __init__.py
      logging.py
      datamodel/
        __init__.py
        base.py
        errors.py
        functions.py
        orchestrated_files.py
      engine/
        __init__.py
        archive_client.py
        commands.py
        engine.py
        errors.py
        functions.py
        operators.py
        parsing.py
        query.py
      processors/
        __init__.py
        base_processor.py
    config/
      datamodel.json
      engine.json
      orchestrator_configuration.xml
    datamodel/
      oboa_data_model.dbm
      oboa_data_model.sql
    schemas/
      oboa_orchestrator_configuration.xsd
    scripts/
      __init__.py
      initialize_oboa_ddbb.sh
      oboa_configure.py
      oboa_init.py
      oboa_init_ddbb.sh
      oboa_daemon.py
      oboa_orchestrate.py
      oboa_poll.py
      oboa_query.py
      start_oboa.sh
    tests/
      inputs/
      test_aboa_integration.py
      test_cli.py
      test_configuration.py
      test_datamodel.py
      test_daemon.py
      test_engine.py
      test_functions.py
      test_logging.py
      test_polling.py
      test_processors.py
      test_query.py
```

`engine/archive_client.py` keeps OBOA's orchestration logic testable while the
default implementation delegates file storage to ABOA, as required by the
default orchestration flow.

### 2.1 ABOA Dependency

OBOA must declare and install ABOA as a runtime dependency because archiving
orchestrated files is delegated to ABOA by default.

- Add `aboa` to `src/setup.py` `install_requires` for packaged deployments.
- Pin the first implementation to the compatible archive package version, for
  example `aboa==0.1.0`, and update the pin intentionally when the archive API
  contract changes.
- In local Docker and CI environments, install the sibling ABOA package before
  OBOA when the dependency is not available from a package index.
- Keep the OBOA archive delegation behind `oboa.engine.archive_client.AboaArchiveClient`
  so unit tests can inject a fake client while production uses ABOA.
- Fail startup with a clear configuration or dependency error if `import aboa`
  is not available.

## 3. Configuration Files

### 3.1 Datamodel JSON

Create `src/oboa/config/datamodel.json` with the standard `DDBB_CONFIGURATION`
structure:

```json
{
  "DDBB_CONFIGURATION": {
    "user": "oboa",
    "host": "localhost",
    "port": 5432,
    "database": "oboadb",
    "db_api": "postgresql",
    "pool_size": 100,
    "max_overflow": 100
  }
}
```

Support practical database overrides:

- `OBOA_DDBB_HOST`: override the configured host.

### 3.2 Engine JSON

Create `src/oboa/config/engine.json` with logging settings and the polling
configuration required by OBOA:

```json
{
  "LOG": {
    "LEVEL": "INFO",
    "MAX_BYTES": 50000000,
    "MAX_BACKUP": 30
  },
  "ORCHESTRATION": {
    "polling_dir": "/oboa_polling",
    "polling_frequency": 30,
    "delete_after_archive": true,
    "processing_dir": "/oboa_processing",
    "error_dir": "/oboa_error"
  },
  "DAEMON": {
    "pid_file": "/tmp/oboa.pid",
    "database_startup_attempts": 30,
    "database_startup_wait_seconds": 2
  }
}
```

`polling_dir` and `polling_frequency` are required by the requirements. The
`delete_after_archive` option controls whether successfully archived files are
removed from the input directory. The `processing_dir` option configures the
internal folder used to stage files that match an orchestration rule with a
configured data processor. The `error_dir` option configures the folder where
inputs are moved when the file has been accepted into OBOA inventory but cannot
be archived. Failed inputs use the date-based layout
`error_dir/<YEAR>/<MONTH>/<DAY>/<original_name>`, with a UUID suffix added to
the file name when needed to avoid overwriting an existing failed input.

Support environment overrides:

- `OBOA_RESOURCES_PATH`: directory containing OBOA JSON/XML resources.
- `OBOA_SCHEMAS_PATH`: directory containing OBOA XSD schemas.
- `OBOA_LOG_PATH`: directory where rotating logs are written.
- `OBOA_LOG_LEVEL`: override log level.
- `OBOA_STREAM_LOG`: enable stream logging.
- `OBOA_LOG_MAX_BYTES` and `OBOA_LOG_MAX_BACKUP`: override rotation settings.
- `OBOA_POLLING_DIR`: override `ORCHESTRATION.polling_dir`.
- `OBOA_POLLING_FREQUENCY`: override `ORCHESTRATION.polling_frequency`.
- `OBOA_DELETE_AFTER_ARCHIVE`: override `ORCHESTRATION.delete_after_archive`.
- `OBOA_PROCESSING_DIR`: override `ORCHESTRATION.processing_dir`.
- `OBOA_ERROR_DIR`: override `ORCHESTRATION.error_dir`.
- `OBOA_CONFIGURATION_PATH`: optional explicit XML configuration path.
- `OBOA_DAEMON_PID_FILE`: override `DAEMON.pid_file`.
- `OBOA_DAEMON_DATABASE_STARTUP_ATTEMPTS`: override
  `DAEMON.database_startup_attempts`.
- `OBOA_DAEMON_DATABASE_STARTUP_WAIT_SECONDS`: override
  `DAEMON.database_startup_wait_seconds`.
- `OBOA_DDBB_STARTUP_ATTEMPTS` and `OBOA_DDBB_STARTUP_WAIT_SECONDS`: accepted
  aliases for the daemon database readiness retry settings.

ABOA must also be configured in the runtime environment because OBOA delegates
the default archive flow to ABOA. In Docker and CI, set the ABOA resource,
schema, log, archive root, and database settings alongside the OBOA variables.

## 4. Data Model Plan

Design the PostgreSQL model in pgModeler and export both:

- `src/oboa/datamodel/oboa_data_model.dbm`
- `src/oboa/datamodel/oboa_data_model.sql`

Implement matching SQLAlchemy entities in
`oboa.datamodel.orchestrated_files`.

### 4.1 Core Tables

`orchestration_configurations`

- `orchestration_configuration_uuid`: text UUID primary key.
- `path`: text, source XML configuration path.
- `active_from`: timestamp, when this configuration became active.
- `active_until`: nullable timestamp, when this configuration was deactivated.
- `active`: boolean.
- `content`: text, raw XML content.

`orchestrated_files`

- `file_uuid`: text UUID primary key.
- `name`: text, original file name.
- `path`: text, original input path observed by OBOA.
- `file_group`: text, the assigned group. Use `file_group` in SQL/Python because
  `group` is a SQL keyword; expose `group` only if a CLI or JSON compatibility
  layer needs it.
- `reception_date`: timestamp, when OBOA first accepted the file for
  orchestration.
- `archived`: boolean, true when ABOA archive delegation succeeds.
- `processed`: boolean, true when no processor is configured or the configured
  executable processor exits successfully.
- `orchestration_configuration_uuid`: nullable FK to
  `orchestration_configurations`. Unknown files can still point to the active
  configuration that failed to match them.

`orchestration_operations`

- `operation_uuid`: text UUID primary key.
- `operation`: text. Initial values: `configure`, `poll`, `orchestrate`,
  `process`, and `archive`.
- `time_stamp`: timestamp.
- `status`: integer status code.
- `message`: nullable text.
- `file_uuid`: nullable FK to `orchestrated_files`.

OBOA should persist only failed operations. Successful configuration,
orchestration, archive, and processing outcomes are represented by the current
state of the configuration and file inventory tables, while the operation table
is the durable failure audit trail.

### 4.2 Model Conventions

- Use SQLAlchemy classes with explicit `__tablename__`, typed columns,
  constructors, relationships, and `jsonify()` methods.
- Use helper functions such as `_isoformat()` and `_stringify()` so
  CLI output can print JSON directly.
- Keep database access centralized through `oboa.datamodel.base.Session`.
- Keep database configuration reading in `oboa.datamodel.functions`.
- Add indexes for common filters: `name`, `path`, `file_group`,
  `reception_date`, `archived`, `processed`, `operation`, `time_stamp`, `status`,
  and `file_uuid`.
- Keep UUIDs as text for simple SQLAlchemy/PostgreSQL serialization and
  consistent CLI output.
- Add `Query.clear_db()` for tests and initialization workflows, deleting tables
  in reverse metadata order.

## 5. XML Configuration Plan

OBOA accepts orchestration configuration XML with this required shape:

```xml
<orchestrator_configuration>
  <data group="documents" priority="1">
    <data_mask>*.pdf</data_mask>
    <data_processor>/opt/oboa/processors/process_document.sh</data_processor>
  </data>
  <data group="images" priority="2">
    <data_mask>*.png</data_mask>
  </data>
</orchestrator_configuration>
```

### 5.1 XSD Rules

Create `src/oboa/schemas/oboa_orchestrator_configuration.xsd` with these rules:

- Root element is `orchestrator_configuration`.
- It contains zero or more `data` elements.
- Each `data` element requires:
  - `group`: non-empty string.
  - `priority`: positive integer, starting from 1.
- Each `data` element contains:
  - `data_mask`: non-empty string.
  - `data_processor`: optional string.

Runtime validation must add rules that are difficult or noisy in XSD:

- Reject `group="unknown"`.
- Validate that any configured `data_processor` is an existing executable file.
- Parse priorities as integers and evaluate them in ascending order.
- Preserve XML source order for entries with the same priority, but log a warning
  because equal priority can make operations harder to reason about.
- Warn when several `data` entries define the same group or data mask.

### 5.2 Parser Module

Implement `oboa.engine.parsing.get_orchestrator_configuration()` as the
configuration entry point:

- Check that the file exists.
- Parse with `lxml.etree.parse`.
- Validate against `oboa_orchestrator_configuration.xsd`.
- Run the runtime validation rules.
- Normalize relative `data_processor` paths directly in the parsed XML nodes.
- Register the OBOA XPath extension functions.
- Return an `lxml.etree.XPathEvaluator` for the parsed XML configuration. The
  engine must work with the returned XML elements directly; it must not create a
  parallel rule-dictionary structure for orchestration.

## 6. Orchestration Engine Plan

Implement `oboa.engine.engine.Engine` as the main mutation interface.

### 6.1 Public Methods

- `set_configuration_path(configuration_path)`: set the XML configuration used by
  orchestration operations.
- `configure_orchestrator(configuration_path=None)`: validate XML, store a new
  active `OrchestrationConfiguration` row when the content changes, and
  deactivate the previous active row.
- `poll_once(polling_dir=None)`: scan the polling directory once and orchestrate
  every ready regular file.
- `run_polling_loop(polling_dir=None, polling_frequency=None)`: call
  `poll_once()` repeatedly, sleeping for the configured frequency between
  iterations.
- `run_daemon(polling_dir=None, polling_frequency=None, pid_file=None,
  foreground=False)`: run the polling loop as a managed daemon process or as a
  foreground long-running process.
- `orchestrate_file(file_path, reception_date=None)`: classify, stage processor
  inputs, archive, process, inventory, and record failures for one file.
- `prepare_processing_file(file_path, orchestrated_file)`: hard-link or copy a
  processor-backed file into the configured internal processing directory.
- `close_session()`: close the SQLAlchemy session.
- `get_exit_codes()` and `get_exit_code(name)`: expose a copy of the engine
  status-code table.

### 6.2 Exit Codes

Define an `exit_codes` dictionary in `engine.py`:

- `OK`: status `0`.
- `CONFIGURATION_FAILED`: invalid or missing XML configuration.
- `ABOA_DEPENDENCY_NOT_AVAILABLE`: ABOA cannot be imported or initialized.
- `POLLING_DIR_NOT_AVAILABLE`: polling directory missing or unreadable.
- `PROCESSING_DIR_NOT_AVAILABLE`: processing directory missing, not writable, or
  impossible to create.
- `FILE_DOES_NOT_EXIST`: file disappeared before orchestration.
- `FILE_NOT_READY`: file is not stable enough to process.
- `PROCESSING_STAGE_FAILED`: file could not be hard-linked or copied to the
  processing directory.
- `PROCESSOR_NOT_EXECUTABLE`: configured processor is not executable.
- `PROCESSOR_FAILED`: processor exited non-zero or timed out.
- `ARCHIVE_FAILED`: ABOA archive delegation failed.
- `DAEMON_ALREADY_RUNNING`: daemon PID file points to a running process.
- `DAEMON_FAILED`: daemon startup, shutdown, or runtime management failed.
- `ORCHESTRATION_FAILED`: unexpected orchestration failure.

Use non-zero status codes in `orchestration_operations` and all status codes for
CLI exits.

### 6.3 Polling Behavior

`poll_once()` should:

- Resolve `polling_dir` from the method argument, environment override, or
  `engine.json`.
- Reject missing or unreadable polling directories.
- Scan regular files in the polling directory non-recursively for the first
  version.
- Ignore hidden files and temporary lock files.
- Check file readiness before orchestration. A file is ready when its size and
  modification time remain stable across a short check window.
- Process files in deterministic path/name order.
- Skip files that already have an `orchestrated_files` row with the same path and
  `archived=True`, unless the file still exists because the previous archive
  delete step failed. In that case, record an operation and retry archive cleanup.
- Apply `delete_after_archive` only after ABOA archive success. Files that fail
  after they have been accepted into OBOA inventory must be moved out of the
  input directory into the configured `error_dir` so polling does not orchestrate
  the same failed file repeatedly.

`run_polling_loop()` should:

- Log loop start and stop.
- Sleep for `polling_frequency` seconds between scans.
- Keep running after per-file failures, because one bad file should not block the
  entire polling directory.
- Exit cleanly on `KeyboardInterrupt`.

### 6.4 Daemon Behavior

OBOA shall run as a daemon for production operation.

- Implement daemon lifecycle helpers in `oboa.engine.daemon` or
  `oboa.engine.commands`.
- Provide `oboa_daemon start`, `oboa_daemon stop`, `oboa_daemon restart`, and
  `oboa_daemon status`.
- Store the daemon PID in `DAEMON.pid_file`, overridable with
  `OBOA_DAEMON_PID_FILE` and CLI `--pid-file`.
- Reject a second daemon start when the PID file points to a running OBOA process.
- Before forking or entering foreground mode, validate required runtime folders
  and wait for the OBOA PostgreSQL database to accept connections. If the
  database remains unavailable after the configured retry budget, fail startup
  with a controlled `DaemonError`.
- Remove stale PID files when the recorded process no longer exists.
- Handle `SIGTERM` and `SIGINT` by finishing the current file operation when
  possible, closing database sessions, closing the ABOA client, removing the PID
  file, and exiting cleanly.
- Keep a foreground mode for containers and tests. `start_oboa.sh` should run the
  same daemon loop in foreground so Docker can supervise the process directly.
- Log daemon start, stop, restart, status checks, signal handling, and unexpected
  loop failures.

### 6.5 File Classification

`orchestrate_file()` should:

- Load and persist the active orchestration configuration before matching files.
- Match the input file name against `data_mask` values using the lxml XPath
  evaluator and the registered `match(data_mask, $file_name)` function.
- Evaluate matching XML `data` elements by ascending `priority`, preserving XML
  order for equal priorities.
- Assign the first matching rule's `group`.
- Assign `unknown` when no rule matches. Unknown files must still be archived
  through ABOA and must not run any data processor.
- Create an `OrchestratedFile` row before processor or archive execution so
  failures are traceable.
- When the matching rule has a `data_processor`, stage the file under
  `processing_dir/<file_uuid>/<original_name>` before archive delegation. Prefer
  a POSIX hard link so storage is cheap when the polling and processing
  directories are on the same filesystem; fall back to `shutil.copy2()` when hard
  linking is not possible.
- Archive the original input path through ABOA. If
  `delete_after_archive` is enabled, allow ABOA or the OBOA cleanup step to
  delete the input file only after archive success.
- If archive delegation fails, move the original input to
  `error_dir/<YEAR>/<MONTH>/<DAY>/<original_name>`, leave `archived=False`, and
  record the archive failure. If the destination file already exists, append a
  UUID suffix to the file name before moving the failed input.
- Run the configured data processor against the staged processing path, not the
  input path. This preserves a processor-readable payload even when the input file
  has been deleted from the polling directory.
- Use `processed=True` when no processor is configured, because there is no
  pending processor work.
- Update `processed` and `archived` independently so partial failures are visible.

### 6.6 Processor Execution

OBOA processors are executable scripts, not importable Python modules.

Implement processor helpers in `oboa.processors.base_processor` or
`oboa.engine.functions`:

- Validate executable scripts with `os.path.isfile()` and `os.access(path, os.X_OK)`.
- Ensure `processing_dir` exists and is writable before staging processor-backed
  files.
- Stage processor-backed files into a deterministic per-file subdirectory under
  the configured processing directory.
- Attempt `os.link()` first; if the hard-link operation fails because of
  cross-device boundaries, permissions, or unsupported filesystems, use
  `shutil.copy2()` as the fallback.
- Execute scripts with `subprocess.run()`.
- Pass the staged processing path as the first argument.
- Provide useful environment variables to the processor:
  - `OBOA_FILE_UUID`
  - `OBOA_FILE_PATH`: staged processing path, kept for processor convenience.
  - `OBOA_INPUT_PATH`: original input path observed in the polling directory.
  - `OBOA_PROCESSING_PATH`: staged processing path.
  - `OBOA_FILE_NAME`
  - `OBOA_FILE_GROUP`
  - `OBOA_CONFIGURATION_UUID`
- Capture stdout and stderr.
- Treat exit code `0` as success.
- Treat any non-zero exit code, timeout, or execution exception as a processor
  failure.
- Store a `process` operation row only for failures.
- Processor failure must not undo a successful archive. It should leave the
  staged processing payload in place for inspection or a later reprocessing
  workflow.

Do not require processor output to update OBOA metadata in the first version,
because the OBOA requirements only require `processed` state and processor
execution. Processor metadata extraction can be planned later if requirements
expand.

### 6.7 ABOA Archive Delegation

Implement `oboa.engine.archive_client.AboaArchiveClient` as the default archive
client:

- Import `aboa.engine.engine.Engine`.
- Instantiate an ABOA `Engine`.
- Call `archive_file()` with the input file path, the OBOA group metadata, and
  the configured delete-after-archive behavior.
- If ABOA cannot delete the input file itself, delete the input file from the
  polling directory after confirmed archive success when `delete_after_archive`
  is enabled.
- Close the ABOA engine session in all paths.
- Convert ABOA domain exceptions into OBOA `ArchiveDelegationError` or
  `OrchestrationError` exceptions.

`Engine` should accept an optional archive client in its constructor for tests:

```python
engine = Engine(archive_client=FakeArchiveClient())
```

This keeps OBOA unit tests focused and allows a separate integration test to
verify the real ABOA call path.

The OBOA file UUID is independent from the ABOA archive UUID. The first version
does not need to persist ABOA archive identifiers because the OBOA requirements
only require OBOA's own `file_uuid`, archive state, processor state, group, path,
configuration, and operation history.

## 7. Query Plan

Implement `oboa.engine.query.Query` as the read interface for OBOA inventory.

### 7.1 Orchestrated File Filters

Support filters for:

- `file_uuids`
- `names`
- `paths`
- `file_group`
- `reception_date_filters`
- `archived`
- `processed`
- `orchestration_configuration_uuids`

Use structured filter dictionaries:

```python
{"filter": "S2%", "op": "like"}
{"filter": ["documents", "images"], "op": "in"}
{"date": "2026-07-01T00:00:00", "op": ">="}
{"filter": True, "op": "=="}
```

### 7.2 Configuration Filters

Support filters for:

- `orchestration_configuration_uuids`
- `paths`
- `contents`
- `active`
- `active_from_date_filters`
- `active_until_date_filters`

### 7.3 Operation Filters

Support filters for:

- `operation_uuids`
- `operations`
- `time_stamp_filters`
- `status_filters`
- `messages`
- `file_uuids`

### 7.4 Selection, Ordering, and Pagination

Support these selection features:

- `order_by`: dictionary with `field` and `descending`.
- `group_by`: group result rows by a valid metadata field.
- `selection`: `all`, `first`, or `last`.
- `limit`: maximum rows.
- `offset`: skipped rows.

Validate every public field against explicit field maps. Do not build SQLAlchemy
queries with `eval`.

## 8. Command Line API Plan

Install command wrappers under `src/oboa/scripts` and command implementations under
`oboa.engine.commands`.

### 8.1 Commands

`oboa_init`

- Initialize the OBOA database from `src/oboa/datamodel/oboa_data_model.sql`.
- Provide `-f` for the datamodel path and `-y` for destructive confirmation.

`oboa_configure`

- Validate and activate an orchestration configuration XML.
- Option: `--configuration /path/to/orchestrator_configuration.xml`.
- Print the active configuration row as JSON.

`oboa_orchestrate`

- Orchestrate one explicit file.
- Option: `--file /path/to/file`.
- Optional: `--configuration /path/to/orchestrator_configuration.xml`.
- Optional: `--delete-after-archive` and `--keep-input` to override the runtime
  input-deletion behavior for this execution.
- Optional: `--processing-dir /path/to/internal/processing` to override the
  internal processing directory for this execution.
- Print the orchestrated file row as JSON.

`oboa_poll`

- Run the poller.
- Options:
  - `--once`: scan once and exit.
  - `--polling-dir /path/to/input`.
  - `--polling-frequency SECONDS`.
  - `--configuration /path/to/orchestrator_configuration.xml`.
  - `--delete-after-archive` or `--keep-input`.
  - `--processing-dir /path/to/internal/processing`.
- Print JSON results for `--once`; log loop activity for continuous mode.

`oboa_daemon`

- Run OBOA as a managed daemon.
- Subcommands:
  - `start`: start the daemon and write the PID file.
  - `stop`: stop the daemon gracefully.
  - `restart`: stop and start the daemon.
  - `status`: report whether the daemon is running.
- Options:
  - `--pid-file /path/to/oboa.pid`.
  - `--foreground`: run the daemon loop in the current process for Docker and
    tests.
  - `--polling-dir /path/to/input`.
  - `--polling-frequency SECONDS`.
  - `--configuration /path/to/orchestrator_configuration.xml`.

`oboa_query`

- Query orchestrated files, configurations, or operations.
- Options:
  - `--files`
  - `--configurations`
  - `--operations`
  - shared filters for each entity group.
  - `--order-by`, `--descending`, `--group-by`, `--selection`, `--limit`,
    and `--offset`.

### 8.2 CLI Conventions

- Use `argparse`.
- Print JSON to stdout using `json.dumps(..., indent=2, sort_keys=True)`.
- Convert expected domain errors into clean `parser.exit(...)` messages without
  tracebacks.
- Close engine/query sessions in `finally`.
- Keep command wrapper scripts tiny:

```python
from oboa.engine.commands import oboa_daemon

def main():
    oboa_daemon()
```

## 9. Docker and CI Plan

Use the standard development and GitHub Docker pattern.

### 9.1 Development Compose

Create `compose_dev.yml` with:

- `oboa_db`: PostgreSQL/PostGIS container.
- `oboa`: OBOA container built from `Dockerfile.dev`.
- A bind mount from the repository root to `/oboa`.
- Environment variables for OBOA resource, schema, log, and polling paths.
- A writable processing directory mounted or created for files staged before
  data-processor execution.
- ABOA runtime variables and dependency installation, because OBOA's default
  archive client delegates file storage to ABOA.

Use a separate OBOA database from ABOA. When running integration tests with the
real archive flow, initialize both databases.

### 9.2 Dockerfile.dev

Use the Rocky Linux 9 development image style:

- Create the `boa` user.
- Install Python, PostgreSQL client/development packages, and build tools.
- Install Python dependencies into `/usr/local/python-packages`.
- Set `PYTHONPATH=/oboa/src:/usr/local/python-packages`.
- Set `PATH` to include OBOA scripts and installed console scripts.
- Create runtime folders such as `/log`, `/resources_path`, `/schemas`,
  `/datamodel`, `/oboa_polling`, and `/oboa_processing`.
- Install or mount ABOA so the default archive client can import it.

### 9.3 GitHub CI

Create `.github/workflows/oboa-testing.yml`:

```yaml
name: "OBOA testing"
on:
  push:
    branches:
      - "*"
jobs:
  tests:
    name: "Integration Test"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: "Set up environment"
        run: GITHUB_BRANCH=${{ github.ref_name }} REPOSITORY_URI=${{ github.server_url }}/${{ github.repository }} docker compose -f compose_github_dev.yml up -d --wait
      - name: "Test OBOA"
        run: docker exec oboa bash -c "/scripts/initialize_oboa_ddbb.sh; cd /oboa/src; py.test -vv tests/"
```

Add ABOA initialization to the test command once real ABOA integration tests are
enabled in CI.

## 10. Test Plan

Use pytest to run unittest-style tests.

### 10.1 Datamodel Tests

Cover:

- `OrchestrationConfiguration.jsonify()`.
- `OrchestratedFile.jsonify()`.
- `OrchestrationOperation.jsonify()`.
- Optional value serialization.
- Persistence of relationships.
- `Query.clear_db()`.

### 10.2 Configuration Tests

Cover:

- Valid XML returns ordered rules.
- `priority="1"` is highest priority.
- Same-priority rules preserve XML order and log a warning.
- Missing configuration file is rejected.
- Malformed XML is rejected.
- XSD-invalid XML is rejected.
- `group="unknown"` is rejected.
- Missing required `group`, `priority`, or `data_mask` is rejected.
- Non-positive priority is rejected.
- Non-executable `data_processor` is rejected.
- Duplicate groups or masks are warned.
- Configured `processing_dir` can be resolved from `engine.json`, environment,
  or CLI override.

### 10.3 Engine and Polling Tests

Cover:

- `orchestrate_file()` creates an inventory row.
- Matching data mask assigns the configured group.
- No matching data mask assigns `unknown`.
- Unknown files are still archived through the archive client.
- Processor success sets `processed=True`.
- No processor sets `processed=True`.
- Processor failure sets `processed=False`, records a failed `process`
  operation, and does not undo a successful archive.
- Processor-backed files are staged under the configured processing directory.
- Staging uses a hard link when possible and falls back to copy when hard linking
  fails.
- Data processors receive the staged processing path instead of the input path.
- ABOA archive success sets `archived=True`.
- ABOA archive failure sets `archived=False`, records an `archive` failure, and
  moves the input file to the configured error folder under
  `YEAR/MONTH/DAY/file`.
- `delete_after_archive=True` removes the input file only after archive success.
- `delete_after_archive=False` keeps the input file after archive success.
- A processor-backed file remains available in the internal processing directory
  after the input file is deleted.
- Polling scans deterministic file order.
- Polling ignores hidden/temp files.
- Polling skips files that are not ready.
- Polling continues after a per-file failure.
- Continuous loop sleeps by `polling_frequency` and exits on interrupt.

Use a fake archive client for most engine tests. Add a focused
`test_aboa_integration.py` that initializes ABOA and verifies the default client
can archive a file through the real ABOA engine.

### 10.4 Query Tests

Cover:

- Text filters.
- Date filters.
- Boolean filters.
- Numeric operation status filters.
- Ordering.
- Grouping.
- `first`, `last`, and `all`.
- Limit and offset.
- Invalid filters and invalid field names.

### 10.5 CLI Tests

Cover:

- Clean error handling without tracebacks.
- `oboa_configure` prints active configuration JSON.
- `oboa_orchestrate` prints orchestrated file JSON.
- `oboa_poll --once` prints a JSON list of orchestrated files.
- `oboa_daemon status` reports stopped and running states.
- `oboa_daemon --foreground` runs the same polling loop without forking.
- `oboa_daemon start` waits for database readiness and fails cleanly when the
  database is still unavailable after the retry budget.
- `oboa_query --files`, `--configurations`, and `--operations`.
- CLI session cleanup after success and failure.

### 10.6 Daemon Tests

Cover:

- Daemon start creates a PID file.
- Daemon start rejects an already running daemon.
- Stale PID files are removed and replaced.
- Daemon stop sends a graceful signal and removes the PID file.
- Signal handling closes database sessions and the ABOA client.
- Foreground mode can be exercised in tests without double-forking.

### 10.7 Logging Tests

Cover:

- Default log file creation.
- `OBOA_LOG_LEVEL` override.
- `OBOA_STREAM_LOG` behavior.
- Rotation settings from `engine.json` or environment.

## 11. Implementation Phases

### Phase 1: Skeleton and Runtime Configuration

- Add package layout, setup metadata, script wrappers, config files, and schema
  placeholders.
- Add logging module and resource-path helpers.
- Add Docker/compose files using the standard component pattern.

### Phase 2: Database Inventory

- Design the model in pgModeler.
- Export `oboa_data_model.dbm` and `oboa_data_model.sql`.
- Implement SQLAlchemy entities and query session setup.
- Add datamodel tests.

### Phase 3: XML Configuration

- Implement XSD validation.
- Implement runtime validation for `unknown` group and executable processors.
- Persist active configuration history.
- Add configuration tests.

### Phase 4: Query API

- Implement explicit query field maps and filter builders.
- Add ordering, grouping, selection, limit, and offset.
- Add query tests.

### Phase 5: Engine and Polling

- Implement file readiness checks, matching, inventory writes, operation writes,
  processing-directory staging, input deletion after archive, processor
  execution, and polling.
- Add engine and polling tests with a fake archive client.

### Phase 6: ABOA Integration

- Implement `AboaArchiveClient`.
- Add real integration tests using the ABOA package and initialized ABOA
  database.
- Ensure Docker/CI initializes both OBOA and ABOA when integration tests run.

### Phase 7: CLI and Documentation

- Implement all command-line entry points.
- Add CLI tests.
- Update README with quick start, runtime configuration, XML examples, and command
  examples.

## 12. Requirement Traceability

- Requirement 1: `Engine.poll_once()` and `Engine.run_polling_loop()` poll the
  configured input directory.
- Requirement 2: `AboaArchiveClient` delegates the default archive flow to ABOA,
  and `src/setup.py`, Docker, and CI install ABOA as an OBOA runtime dependency.
- Requirements 3 and 4: SQLAlchemy/PostgreSQL inventory configured through
  `datamodel.json`.
- Requirement 5: pgModeler artifacts stored in `src/oboa/datamodel`.
- Requirement 6: PostgreSQL tables `orchestration_configurations`,
  `orchestrated_files`, and `orchestration_operations`.
- Requirement 7: `OrchestratedFile` entity includes file UUID, name, path, group,
  reception date, archived state, processed state, and configuration FK.
- Requirement 8: `OrchestrationConfiguration` entity includes path, active dates,
  active flag, and content.
- Requirement 9: `OrchestrationOperation` entity includes operation, timestamp,
  status, message, and file UUID.
- Requirement 10: Console scripts provide the command line API.
- Requirement 11: `orchestrator_configuration.xml` and parsing code implement the
  XML configuration API.
- Requirement 12: XSD validation is enforced by `oboa.engine.parsing`.
- Requirement 13: unmatched files are assigned group `unknown` and still archived.
- Requirement 14: runtime configuration validation rejects group `unknown`.
- Requirement 15: runtime configuration validation requires processors to be
  executable scripts.
- Requirement 16: tests cover datamodel, configuration, engine, polling,
  processor execution, ABOA integration, query, CLI, daemon behavior, functions,
  and logging.
- Requirement 17: package structure, logging, SQLAlchemy setup, command wrappers,
  Docker/CI, and tests follow standard component conventions.
- Requirement 18: `engine.json`, environment overrides, and poller methods expose
  `polling_dir` and `polling_frequency`.
- Requirement 19: `delete_after_archive` controls input deletion after archive,
  while processor-backed files are hard-linked or copied to the internal
  processing directory before the input can be removed.
- Requirement 20: `processing_dir`, `OBOA_PROCESSING_DIR`, and CLI overrides
  configure the internal folder used for further processing.
- Requirement 21: `oboa_daemon`, `Engine.run_daemon()`, PID handling, signal
  handling, and foreground Docker mode provide daemon execution.

## 13. Definition of Done

- `python -m pip install -e "src[tests]"` installs OBOA.
- `oboa_init -y` initializes the OBOA database from the exported SQL model.
- `oboa_configure --configuration <xml>` validates and activates a configuration.
- `oboa_poll --once` orchestrates ready files from the configured polling
  directory.
- Files matching configuration rules get the configured group.
- Files not matching any configuration get group `unknown`.
- Unknown group is rejected in configuration XML.
- Configured processors must be executable scripts.
- `delete_after_archive` can remove archived input files from the polling
  directory.
- Processor-backed files are staged into the configured internal processing
  directory by hard link or copy before input deletion can happen.
- Real ABOA delegation archives files successfully in an integration test.
- OBOA can run as a daemon with start, stop, restart, status, PID-file handling,
  signal handling, and foreground container mode.
- All tests pass with coverage over the implemented component code.
- README documents setup, environment variables, XML configuration, and CLI usage.
