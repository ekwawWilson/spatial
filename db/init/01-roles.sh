#!/bin/bash
# Runs once, when the database volume is first created.
# Creates the non-superuser application role. Superusers bypass row-level
# security, so the running app must never connect as the owner role.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
  CREATE EXTENSION IF NOT EXISTS postgis;

  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${APP_DB_USER}') THEN
      CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${APP_DB_PASSWORD}'
        NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
  END
  \$\$;

  GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${APP_DB_USER};
  GRANT USAGE ON SCHEMA public TO ${APP_DB_USER};

  -- Tables and sequences created later by migrations (run as the owner role)
  -- are usable by the app role automatically.
  ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_DB_USER};
  ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO ${APP_DB_USER};
SQL
