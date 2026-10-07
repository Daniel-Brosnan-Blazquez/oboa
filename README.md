# OBOA

Orchestrator for Business Operations Analysis.

OBOA polls an input directory, matches files against orchestration XML rules,
delegates archiving to ABOA, optionally stages files for executable data
processors, and keeps a PostgreSQL inventory of configurations, files, and
operations.

## Runtime Configuration

Required OBOA paths:

- `OBOA_RESOURCES_PATH`: directory with `datamodel.json`, `engine.json`, and
  `orchestrator_configuration.xml`.
- `OBOA_SCHEMAS_PATH`: directory with `oboa_orchestrator_configuration.xsd`.
- `OBOA_LOG_PATH`: rotating log output directory.

Useful overrides:

- `OBOA_POLLING_DIR`: input directory to poll.
- `OBOA_POLLING_FREQUENCY`: daemon polling frequency in seconds.
- `OBOA_DELETE_AFTER_ARCHIVE`: whether archived input files are deleted.
- `OBOA_PROCESSING_DIR`: internal folder where processor-backed files are
  hard-linked or copied before the input can be deleted.
- `OBOA_ERROR_DIR`: internal folder where failed orchestrated inputs are moved
  when they cannot be archived or staged. Failed files are stored as
  `<OBOA_ERROR_DIR>/YEAR/MONTH/DAY/file`.
- `OBOA_DAEMON_PID_FILE`: daemon PID file.
- `OBOA_DDBB_HOST`: PostgreSQL host override.
- `OBOA_DAEMON_DATABASE_STARTUP_ATTEMPTS`: number of database readiness checks
  before daemon startup fails.
- `OBOA_DAEMON_DATABASE_STARTUP_WAIT_SECONDS`: delay between database readiness
  checks. `OBOA_DDBB_STARTUP_ATTEMPTS` and `OBOA_DDBB_STARTUP_WAIT_SECONDS` are
  also accepted.

ABOA must also be configured because OBOA archives through ABOA by default.

## XML Configuration

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

`data_processor` is optional. The group `unknown` is reserved for files that do
not match any rule.

## Command Line

```bash
oboa_init.py -y
oboa_configure.py --configuration /path/to/orchestrator_configuration.xml
oboa_orchestrate.py --file /input/file.txt
oboa_poll.py --once --polling-dir /input
oboa_daemon.py start --foreground
oboa_daemon.py status
oboa_query.py --files --name "%.txt"
```

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e "src[tests]"
```

Docker Compose maps the OBOA container user to the host user through
`UID_HOST_USER` and `GID_HOST_USER`:

```bash
UID_HOST_USER=$(id -u) GID_HOST_USER=$(id -g) docker compose -f compose_dev.yml up --build
```

OBOA uses PostgreSQL for its inventory. For local runs outside Compose, point
the component to a PostgreSQL host and the local configuration folders:

```bash
export OBOA_DDBB_HOST="localhost"
export OBOA_RESOURCES_PATH="$PWD/src/oboa/config"
export OBOA_SCHEMAS_PATH="$PWD/src/oboa/schemas"
export OBOA_LOG_PATH="/tmp/oboa_log"
```
