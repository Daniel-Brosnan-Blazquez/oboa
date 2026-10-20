-- ** Database generated with pgModeler (PostgreSQL Database Modeler).
-- ** pgModeler version: 1.2.3
-- ** PostgreSQL version: 18.0
-- ** Project Site: pgmodeler.io
-- ** Model Author: ---
-- object: oboa | type: ROLE --
-- DROP ROLE IF EXISTS oboa;
CREATE ROLE oboa WITH 
	INHERIT
	LOGIN;
-- ddl-end --


-- ** Database creation must be performed outside a multi lined SQL file. 
-- ** These commands were put in this file only as a convenience.

-- object: oboadb | type: DATABASE --
-- DROP DATABASE IF EXISTS oboadb;
CREATE DATABASE oboadb;
-- ddl-end --


-- object: oboa | type: SCHEMA --
-- DROP SCHEMA IF EXISTS oboa CASCADE;
CREATE SCHEMA oboa;
-- ddl-end --
ALTER SCHEMA oboa OWNER TO oboa;
-- ddl-end --

SET search_path TO pg_catalog,public,oboa;
-- ddl-end --

-- object: oboa.orchestration_configurations | type: TABLE --
-- DROP TABLE IF EXISTS oboa.orchestration_configurations CASCADE;
CREATE TABLE oboa.orchestration_configurations (
	orchestration_configuration_uuid text NOT NULL,
	path text NOT NULL,
	active_from timestamp NOT NULL,
	active_until timestamp,
	active bool NOT NULL,
	content text NOT NULL,
	CONSTRAINT orchestration_configurations_pk PRIMARY KEY (orchestration_configuration_uuid)
);
-- ddl-end --
ALTER TABLE oboa.orchestration_configurations OWNER TO oboa;
-- ddl-end --

-- object: oboa.orchestrated_files | type: TABLE --
-- DROP TABLE IF EXISTS oboa.orchestrated_files CASCADE;
CREATE TABLE oboa.orchestrated_files (
	file_uuid text NOT NULL,
	name text NOT NULL,
	path text NOT NULL,
	file_group text NOT NULL,
	reception_date timestamp NOT NULL,
	archived bool NOT NULL,
	processed bool NOT NULL,
	orchestration_configuration_uuid text,
	CONSTRAINT orchestrated_files_pk PRIMARY KEY (file_uuid)
);
-- ddl-end --
ALTER TABLE oboa.orchestrated_files OWNER TO oboa;
-- ddl-end --

-- object: orchestrated_files_orchestration_configurations_fk | type: CONSTRAINT --
-- ALTER TABLE oboa.orchestrated_files DROP CONSTRAINT IF EXISTS orchestrated_files_orchestration_configurations_fk CASCADE;
ALTER TABLE oboa.orchestrated_files ADD CONSTRAINT orchestrated_files_orchestration_configurations_fk FOREIGN KEY (orchestration_configuration_uuid)
REFERENCES oboa.orchestration_configurations (orchestration_configuration_uuid) MATCH FULL
ON DELETE SET NULL ON UPDATE CASCADE;
-- ddl-end --

-- object: oboa.orchestration_operations | type: TABLE --
-- DROP TABLE IF EXISTS oboa.orchestration_operations CASCADE;
CREATE TABLE oboa.orchestration_operations (
	operation_uuid text NOT NULL,
	operation text NOT NULL,
	time_stamp timestamp NOT NULL,
	status integer NOT NULL,
	message text,
	file_uuid text,
	CONSTRAINT orchestration_operations_pk PRIMARY KEY (operation_uuid)
);
-- ddl-end --
ALTER TABLE oboa.orchestration_operations OWNER TO oboa;
-- ddl-end --

-- object: orchestration_operations_orchestrated_files_fk | type: CONSTRAINT --
-- ALTER TABLE oboa.orchestration_operations DROP CONSTRAINT IF EXISTS orchestration_operations_orchestrated_files_fk CASCADE;
ALTER TABLE oboa.orchestration_operations ADD CONSTRAINT orchestration_operations_orchestrated_files_fk FOREIGN KEY (file_uuid)
REFERENCES oboa.orchestrated_files (file_uuid) MATCH FULL
ON DELETE SET NULL ON UPDATE CASCADE;
-- ddl-end --

-- object: idx_orchestration_configurations_path | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestration_configurations_path CASCADE;
CREATE INDEX idx_orchestration_configurations_path ON oboa.orchestration_configurations
USING btree
(
	path
);
-- ddl-end --

-- object: idx_orchestration_configurations_active_from | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestration_configurations_active_from CASCADE;
CREATE INDEX idx_orchestration_configurations_active_from ON oboa.orchestration_configurations
USING btree
(
	active_from
);
-- ddl-end --

-- object: idx_orchestration_configurations_active_until | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestration_configurations_active_until CASCADE;
CREATE INDEX idx_orchestration_configurations_active_until ON oboa.orchestration_configurations
USING btree
(
	active_until
);
-- ddl-end --

-- object: idx_orchestration_configurations_active | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestration_configurations_active CASCADE;
CREATE INDEX idx_orchestration_configurations_active ON oboa.orchestration_configurations
USING btree
(
	active
);
-- ddl-end --

-- object: idx_orchestrated_files_name | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestrated_files_name CASCADE;
CREATE INDEX idx_orchestrated_files_name ON oboa.orchestrated_files
USING btree
(
	name
);
-- ddl-end --

-- object: idx_orchestrated_files_path | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestrated_files_path CASCADE;
CREATE INDEX idx_orchestrated_files_path ON oboa.orchestrated_files
USING btree
(
	path
);
-- ddl-end --

-- object: idx_orchestrated_files_file_group | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestrated_files_file_group CASCADE;
CREATE INDEX idx_orchestrated_files_file_group ON oboa.orchestrated_files
USING btree
(
	file_group
);
-- ddl-end --

-- object: idx_orchestrated_files_reception_date | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestrated_files_reception_date CASCADE;
CREATE INDEX idx_orchestrated_files_reception_date ON oboa.orchestrated_files
USING btree
(
	reception_date
);
-- ddl-end --

-- object: idx_orchestrated_files_archived | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestrated_files_archived CASCADE;
CREATE INDEX idx_orchestrated_files_archived ON oboa.orchestrated_files
USING btree
(
	archived
);
-- ddl-end --

-- object: idx_orchestrated_files_processed | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestrated_files_processed CASCADE;
CREATE INDEX idx_orchestrated_files_processed ON oboa.orchestrated_files
USING btree
(
	processed
);
-- ddl-end --

-- object: idx_orchestrated_files_orchestration_configuration_uuid | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestrated_files_orchestration_configuration_uuid CASCADE;
CREATE INDEX idx_orchestrated_files_orchestration_configuration_uuid ON oboa.orchestrated_files
USING btree
(
	orchestration_configuration_uuid
);
-- ddl-end --

-- object: idx_orchestration_operations_operation | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestration_operations_operation CASCADE;
CREATE INDEX idx_orchestration_operations_operation ON oboa.orchestration_operations
USING btree
(
	operation
);
-- ddl-end --

-- object: idx_orchestration_operations_time_stamp | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestration_operations_time_stamp CASCADE;
CREATE INDEX idx_orchestration_operations_time_stamp ON oboa.orchestration_operations
USING btree
(
	time_stamp
);
-- ddl-end --

-- object: idx_orchestration_operations_status | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestration_operations_status CASCADE;
CREATE INDEX idx_orchestration_operations_status ON oboa.orchestration_operations
USING btree
(
	status
);
-- ddl-end --

-- object: idx_orchestration_operations_file_uuid | type: INDEX --
-- DROP INDEX IF EXISTS oboa.idx_orchestration_operations_file_uuid CASCADE;
CREATE INDEX idx_orchestration_operations_file_uuid ON oboa.orchestration_operations
USING btree
(
	file_uuid
);
-- ddl-end --


