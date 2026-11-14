#!/bin/bash
# Runs once, the first time the postgres volume is created.
# Creates one database per microservice, each owned by its own user.
# Passwords come from environment variables (see .env.example) — never hard-code them.
set -euo pipefail

create_service_db() {
  local db="$1" user="$2" password="$3"
  echo "Creating database ${db} owned by ${user}"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -v db="$db" -v user="$user" -v password="$password" <<'SQL'
CREATE USER :"user" WITH PASSWORD :'password';
CREATE DATABASE :"db" OWNER :"user";
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
SQL
}

create_service_db target_db       "$TARGET_DB_USER"       "$TARGET_DB_PASSWORD"
create_service_db monitoring_db   "$MONITORING_DB_USER"   "$MONITORING_DB_PASSWORD"
create_service_db incident_db     "$INCIDENT_DB_USER"     "$INCIDENT_DB_PASSWORD"
create_service_db notification_db "$NOTIFICATION_DB_USER" "$NOTIFICATION_DB_PASSWORD"
