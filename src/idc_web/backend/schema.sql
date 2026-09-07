-- IDC Patrol PostgreSQL Schema
-- SRV-01 physical schema aligned with SDD v1.2 logical model

CREATE TABLE audit_log (
	id SERIAL NOT NULL,
	ts TIMESTAMP WITH TIME ZONE,
	actor VARCHAR(100),
	action VARCHAR(100),
	target VARCHAR(200),
	detail TEXT,
	prev_hash VARCHAR(64),
	hash VARCHAR(64),
	PRIMARY KEY (id)
);

CREATE TABLE patrol_runs (
	id SERIAL NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE,
	ended_at TIMESTAMP WITH TIME ZONE,
	map_id VARCHAR(100),
	coverage FLOAT,
	status VARCHAR(50),
	PRIMARY KEY (id)
);

CREATE TABLE persons (
	id SERIAL NOT NULL,
	name VARCHAR(100),
	org VARCHAR(100),
	consent_id VARCHAR(100),
	embedding BYTEA,
	registered_at TIMESTAMP WITH TIME ZONE,
	revoked_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id)
);

CREATE TABLE robots (
	id VARCHAR(64) NOT NULL,
	name VARCHAR(100),
	last_seen TIMESTAMP WITH TIME ZONE,
	battery FLOAT,
	state VARCHAR(50),
	x FLOAT,
	y FLOAT,
	yaw FLOAT,
	PRIMARY KEY (id)
);

CREATE TABLE zones (
	id VARCHAR(16) NOT NULL,
	name VARCHAR(100),
	polygon_json TEXT,
	allowed_from TIME WITHOUT TIME ZONE,
	allowed_to TIME WITHOUT TIME ZONE,
	min_persons INTEGER,
	max_dwell_sec INTEGER,
	allowed_person_ids TEXT,
	PRIMARY KEY (id)
);

CREATE TABLE auth_events (
	id SERIAL NOT NULL,
	person_id INTEGER,
	door_id VARCHAR(100),
	ts TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id)
);

CREATE TABLE racks (
	id VARCHAR(16) NOT NULL,
	aruco_id INTEGER,
	x FLOAT,
	y FLOAT,
	yaw FLOAT,
	zone_id VARCHAR(16),
	baseline_door VARCHAR(50),
	baseline_led VARCHAR(50),
	PRIMARY KEY (id),
	UNIQUE (aruco_id),
	FOREIGN KEY(zone_id) REFERENCES zones (id)
);

CREATE TABLE waypoints (
	id SERIAL NOT NULL,
	run_id INTEGER,
	robot_id VARCHAR(64),
	seq INTEGER,
	x FLOAT,
	y FLOAT,
	yaw FLOAT,
	rack_id VARCHAR(16),
	visited_at TIMESTAMP WITH TIME ZONE,
	result VARCHAR(100),
	PRIMARY KEY (id),
	FOREIGN KEY(run_id) REFERENCES patrol_runs (id),
	FOREIGN KEY(robot_id) REFERENCES robots (id),
	FOREIGN KEY(rack_id) REFERENCES racks (id)
);

CREATE TABLE events (
	id SERIAL NOT NULL,
	run_id INTEGER,
	type VARCHAR(50),
	severity INTEGER,
	zone_id VARCHAR(16),
	rack_id VARCHAR(16),
	robot_id VARCHAR(64),
	x FLOAT,
	y FLOAT,
	first_ts TIMESTAMP WITH TIME ZONE,
	last_ts TIMESTAMP WITH TIME ZONE,
	status VARCHAR(50),
	acked_by VARCHAR(100),
	acked_at TIMESTAMP WITH TIME ZONE,
	detail_json TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(run_id) REFERENCES patrol_runs (id),
	FOREIGN KEY(zone_id) REFERENCES zones (id),
	FOREIGN KEY(rack_id) REFERENCES racks (id),
	FOREIGN KEY(robot_id) REFERENCES robots (id)
);

CREATE TABLE evidence (
	id SERIAL NOT NULL,
	event_id INTEGER,
	robot_id VARCHAR(64),
	ts TIMESTAMP WITH TIME ZONE,
	path_blurred TEXT,
	path_encrypted TEXT,
	sha256 VARCHAR(64),
	x FLOAT,
	y FLOAT,
	yaw FLOAT,
	PRIMARY KEY (id),
	FOREIGN KEY(event_id) REFERENCES events (id)
);
