# OBOA Orchestration Operations Flow

This document describes the operational flows of OBOA, the Orchestrator for
Business Operations Analysis. It focuses on how OBOA starts, configures
orchestration rules, polls input files, delegates archiving, optionally executes
processors, and records the resulting inventory and audit information.

## 1. Operational Scope

OBOA is a command-line and daemon-oriented component. Its main responsibility is
to observe an input folder, classify files with an XML orchestration
configuration, archive each file through ABOA, optionally stage and process files
that require additional handling, and persist the full operation history in a
PostgreSQL database.

The main operational entry points are:

- `oboa_init`: initialize the OBOA database tables.
- `oboa_configure`: validate and activate an orchestration XML configuration.
- `oboa_orchestrate`: orchestrate one explicit file.
- `oboa_poll`: scan the configured input folder once or continuously.
- `oboa_daemon`: start, stop, restart, or inspect the daemon process.
- `oboa_query`: query the persisted OBOA inventory.

## 2. Runtime Configuration Flow

OBOA reads its runtime configuration from packaged JSON resources, with
environment variables used for deployment-time overrides.

```text
Start command
  -> read engine configuration
  -> read datamodel configuration when database access is needed
  -> apply environment overrides
  -> execute the requested operation
```

Engine configuration includes:

- `polling_dir`: input folder scanned by the polling flow.
- `polling_frequency`: delay between daemon polling iterations.
- `delete_after_archive`: whether a successfully archived input is removed from
  the input folder.
- `processing_dir`: internal folder used to stage files that have a configured
  data processor.
- `error_dir`: internal folder used to move files that were accepted into OBOA
  inventory but could not be archived. Failed files are stored under
  `error_dir/<YEAR>/<MONTH>/<DAY>/<original_name>`, with a UUID suffix added
  when a file with the same name already exists for that day.
- `pid_file`: daemon PID file path.
- `database_startup_attempts`: how many database readiness checks daemon startup
  performs before failing.
- `database_startup_wait_seconds`: delay between daemon database readiness
  checks.

Database configuration uses PostgreSQL and supports the deployment host override
through `OBOA_DDBB_HOST`.

## 3. Database Initialization Flow

The initialization flow creates the inventory schema needed by OBOA.

```text
Operator runs oboa_init
  -> command asks for confirmation unless -y is supplied
  -> SQLAlchemy metadata creates OBOA tables
  -> command prints JSON result
```

The inventory is composed of:

- `orchestration_configurations`: active and historical XML configuration
  versions.
- `orchestrated_files`: file inventory rows created during orchestration.
- `orchestration_operations`: failed operation audit rows for configure, poll,
  orchestrate, archive, and process events.

## 4. Configuration Activation Flow

The configuration flow validates the XML orchestration rules and marks the
accepted configuration as active.

```text
Operator runs oboa_configure
  -> load XML configuration path
  -> validate XML against OBOA XSD
  -> reject reserved group "unknown"
  -> reject invalid priorities
  -> reject non-executable processors
  -> compare XML checksum with active configuration
  -> reuse active row when content is unchanged
  -> deactivate previous active rows when content changed
  -> create new active orchestration_configurations row
  -> record configure operation
```

Rules are defined as:

```xml
<orchestrator_configuration>
  <data group="example" priority="1">
    <data_mask>*.txt</data_mask>
    <data_processor>/path/to/processor.sh</data_processor>
  </data>
</orchestrator_configuration>
```

Priority starts at `1`, where `1` is the highest priority. `data_processor` is
optional. A rule with `data_processor` requires an executable script.

The group value `unknown` is reserved by OBOA and cannot be configured. OBOA uses
that group internally when a file does not match any rule.

## 5. Daemon Lifecycle Flow

OBOA is intended to run as a daemon for continuous operation.

```text
Operator runs oboa_daemon start
  -> read daemon pid_file from CLI or configuration
  -> check existing PID file
  -> reject start if the PID is running
  -> validate runtime folders
  -> retry database readiness check until PostgreSQL accepts SELECT 1
  -> fail cleanly if database readiness retry budget is exhausted
  -> run in foreground when requested
  -> otherwise fork and start polling in the child process
```

Foreground mode:

```text
start foreground
  -> install SIGTERM and SIGINT handlers
  -> write current PID to pid_file
  -> run polling loop
  -> remove pid_file on exit
```

Background mode:

```text
start background
  -> fork process
  -> parent returns child PID
  -> child creates a new session
  -> child runs foreground daemon flow
```

Stop and restart:

```text
stop
  -> read PID file
  -> return stopped when no live PID exists
  -> send SIGTERM to live PID
  -> wait until process disappears or pid_file is removed/changed by the daemon
  -> remove stale PID file only when it still points to the stopped PID

restart
  -> stop
  -> start with supplied runtime options
```

Status:

```text
status
  -> read PID file
  -> return running when PID exists
  -> remove stale PID file when PID is not running
  -> return stopped otherwise
```

## 6. Polling Flow

Polling scans the input folder and orchestrates stable files according to
configuration priority.

```text
poll_once
  -> resolve polling_dir from argument or configuration
  -> verify directory exists and is readable
  -> list entries by name
  -> ignore hidden files
  -> ignore temporary files ending with .tmp, .lock, .part, or ~
  -> ignore non-files
  -> verify file readiness using stable size and mtime
  -> load active orchestration configuration when ready files exist
  -> match each ready file against configured rules
  -> sort matched files by priority and XML order
  -> sort unmatched files after matched files
  -> orchestrate each ready file
  -> record poll operation
```

If a file changes while being checked, OBOA records a `FILE_NOT_READY` poll
operation and skips it for the current pass.

If a ready file cannot be orchestrated, OBOA logs the error and continues with
the next ready file. This keeps one problematic file from stopping the polling
pass.

## 7. Priority Flow

Priority is evaluated before orchestration starts for a polling pass.

```text
ready files
  -> load configuration rules sorted by priority and XML order
  -> for each file, find first rule whose data_mask matches the basename
  -> matched files get key: matched, priority, XML order, file name
  -> unmatched files get key: unmatched, file name
  -> orchestrate in sorted order
```

This means:

- Matching files are processed before unknown files.
- Lower priority numbers are processed first.
- When two rules have the same priority, their XML order is preserved.
- Files that do not match any rule are still orchestrated under group
  `unknown`.

## 8. Single File Orchestration Flow

The single-file flow is used by both `oboa_orchestrate` and the polling flow.

```text
orchestrate_file(file_path)
  -> record reception date
  -> reject missing input file
  -> load active XML configuration
  -> match file against configuration rules
  -> assign configured group or "unknown"
  -> decide whether a processor is configured
  -> create orchestrated_files row
  -> stage file for processing when processor exists
  -> archive original file through ABOA
  -> mark file archived
  -> optionally delete original input after successful archive
  -> execute processor when configured
  -> mark file processed on processor success
  -> record processor failure without undoing archive success
  -> return orchestrated_files row
```

The `processed` flag is initialized as:

- `true` when no processor is configured.
- `false` when a processor is configured and still needs to run.

## 9. Archive Delegation Flow

ABOA is the default archive provider used by OBOA.

```text
archive file
  -> initialize archive client when not injected
  -> create archive metadata
  -> include OBOA file_group in metadata
  -> call ABOA archive_file
  -> pass delete_after_archive flag to archive provider
  -> close downstream archive session
```

When archive delegation succeeds:

- OBOA marks `orchestrated_files.archived` as `true`.
- OBOA deletes the original input file only when `delete_after_archive` is true
  and the file still exists.

When archive delegation fails:

- OBOA keeps the file inventory row.
- OBOA leaves `archived` as `false`.
- OBOA records an `archive` operation with failure status.
- OBOA moves the original input to
  `error_dir/<YEAR>/<MONTH>/<DAY>/<original_name>` when the file is still
  present in the polling entry point.
- OBOA raises an archive delegation error to the caller.

## 10. Processor Staging and Execution Flow

Files with a configured data processor are staged in the internal processing
folder before the original input is archived and optionally deleted.

```text
processor-backed file
  -> resolve processing_dir from engine configuration
  -> create processing_dir when needed
  -> verify processing_dir is writable
  -> create per-file folder named with file_uuid
  -> stage file as processing_dir/file_uuid/original_name
  -> prefer hard link
  -> fall back to copy when hard link is not possible
  -> archive original file
  -> delete original input when configured
  -> execute processor with staged file path
```

The processor receives OBOA context through environment variables:

- `OBOA_FILE_UUID`
- `OBOA_FILE_PATH`
- `OBOA_INPUT_PATH`
- `OBOA_PROCESSING_PATH`
- `OBOA_FILE_NAME`
- `OBOA_FILE_GROUP`
- `OBOA_CONFIGURATION_UUID`

When staging fails, OBOA records a processing-stage failure and stops the
orchestration for that file before archive delegation. The original input is
moved to the configured error folder so the polling loop does not retry the same
failed file endlessly.

When processor execution fails after archive success, OBOA records the process
failure and leaves the archived file visible in the inventory with
`processed=false`.

## 11. Operation Audit Flow

OBOA records operation rows only for failed operational events. Successful
configuration, polling, archive, and processing outcomes are reflected by the
state of `orchestration_configurations` and `orchestrated_files`, without
creating `orchestration_operations` rows.

```text
failed operation event
  -> build operation_uuid
  -> assign operation name
  -> assign timestamp
  -> assign non-zero numeric status
  -> attach message
  -> attach file_uuid when related to a file
  -> commit orchestration_operations row
```

Initial operation names are:

- `configure`
- `poll`
- `orchestrate`
- `archive`
- `process`

The audit trail is intentionally durable. Test cleanup should not remove rows at
teardown, so operators can inspect database state after test runs or manual
execution.

## 12. Query Flow

The query API reads OBOA inventory data without mutating operational state.

```text
oboa_query
  -> parse requested entity: files, configurations, or operations
  -> build text, boolean, numeric, and date filters
  -> validate filter descriptors
  -> apply ordering
  -> apply limit and offset
  -> apply selection: all, first, or last
  -> optionally group results
  -> serialize rows as JSON
```

Supported query targets:

- Files: `orchestrated_files`
- Configurations: `orchestration_configurations`
- Operations: `orchestration_operations`

The query layer exposes `jsonify()` output so command-line callers receive
stable JSON payloads.

## 13. Error Handling Flow

OBOA prefers explicit failure recording before raising errors to callers.

```text
failure detected
  -> record operation when the failure is operationally relevant
  -> roll back database session when configuration activation fails
  -> raise a typed OBOA exception
  -> command-line wrapper exits with status 1 and an error message
```

Common failure paths:

- Polling directory is unavailable.
- File does not exist.
- File is not ready.
- XML configuration is missing, malformed, or schema-invalid.
- Rule uses reserved group `unknown`.
- Rule priority is invalid.
- Processor path is not executable.
- Processing directory is unavailable.
- Archive delegation fails.
- Processor execution fails.
- Daemon is already running or cannot stop.

## 14. End-to-End Daemon Flow

The complete production flow is:

```text
container or operator starts OBOA daemon
  -> daemon validates PID state
  -> daemon starts polling loop
  -> polling loop scans input folder every polling_frequency seconds
  -> ready files are ordered by orchestration priority
  -> each file is registered in inventory
  -> processor-backed files are staged internally
  -> original files are archived through ABOA
  -> original files are deleted when configured
  -> processors run against staged internal files
  -> OBOA records failed operations only
  -> query API exposes files, configurations, and failure history
```

This flow ensures OBOA can continuously orchestrate files, preserve traceability
in PostgreSQL, keep archive responsibility delegated to ABOA, and protect
processor-backed workflows from losing their inputs when input-folder cleanup is
enabled.
