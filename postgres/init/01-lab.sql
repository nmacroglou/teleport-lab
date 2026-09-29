-- Runs once, on the first start of an empty database volume.

CREATE DATABASE labdb;
\connect labdb

CREATE TABLE servers (
  id   serial PRIMARY KEY,
  name text NOT NULL,
  role text NOT NULL,
  env  text NOT NULL
);

INSERT INTO servers (name, role, env) VALUES
  ('teleport',       'auth + proxy', 'lab'),
  ('linux-server-1', 'ssh node',     'lab'),
  ('whoami',         'web app',      'lab'),
  ('postgres',       'database',     'lab');

-- Read-only login used through Teleport (no password: cert auth only).
CREATE ROLE labreader LOGIN;
ALTER ROLE labreader SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE labdb TO labreader;
GRANT USAGE ON SCHEMA public TO labreader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO labreader;
