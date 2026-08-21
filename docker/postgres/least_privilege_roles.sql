-- Least-privilege Postgres roles, one per deployed agent.
--
-- Mounted into the pgvector container's docker-entrypoint-initdb.d, so
-- it runs once when the data volume is first created. On an existing
-- database, run it by hand as a superuser instead.
--
-- This is the control that makes the application-layer SQL validation
-- survivable. sql_validation.py parses every query and rejects tables
-- outside a domain, but it is still application code: a parser bug or an
-- unanticipated construct is always possible. A role that physically
-- cannot see another domain's tables turns that from a breach into an
-- error message.
--
-- These roles are only usable because each service carries its own
-- PG_USER/PG_PASSWORD in docker-compose.yml. A single shared env file
-- means a single database user, and then none of the separation below
-- exists.

\set ON_ERROR_STOP on

-- ============================================================
-- Nobody gets anything by default.
-- ============================================================
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO PUBLIC;

-- ============================================================
-- History tables.
--
-- Created here rather than by the application, so that no agent role
-- needs CREATE on the schema. An agent can write its own history and
-- read nothing else.
--
-- vector(1024) must match EMBEDDING_MODEL_SIZE in .env.app. It is the
-- width of text-embedding-v3 today and of bge-m3 later, so self-hosting
-- the embedding model needs no reindexing.
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;

DO $$
DECLARE
    history_table text;
BEGIN
    FOREACH history_table IN ARRAY ARRAY['history_orchestrator', 'history_hr', 'history_crm']
    LOOP
        EXECUTE format($fmt$
            CREATE TABLE IF NOT EXISTS %I (
              id BIGSERIAL PRIMARY KEY,
              session_id TEXT NOT NULL,
              turn_id UUID NOT NULL,
              event_type TEXT NOT NULL,
              payload JSONB NOT NULL DEFAULT '{}'::jsonb,
              duration_seconds NUMERIC,
              valid BOOLEAN,
              reason TEXT,
              embed_user_query vector(1024),
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_%I_session_created ON %I(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_%I_turn ON %I(turn_id, event_type);
            CREATE INDEX IF NOT EXISTS idx_%I_examples ON %I(event_type, valid, created_at);
        $fmt$, history_table,
              history_table, history_table,
              history_table, history_table,
              history_table, history_table);
    END LOOP;
END
$$;

-- ============================================================
-- HR agent -> the organization tables only.
-- ============================================================
CREATE ROLE app_hr WITH LOGIN PASSWORD 'CHANGE_ME_hr';

GRANT SELECT ON TABLE
    employees, directors_employees, hos_employee, teams, agents_employee
TO app_hr;

GRANT SELECT, INSERT, UPDATE ON TABLE history_hr TO app_hr;
GRANT USAGE, SELECT ON SEQUENCE history_hr_id_seq TO app_hr;

-- ============================================================
-- CRM agent -> the customer tables only.
-- ============================================================
CREATE ROLE app_crm WITH LOGIN PASSWORD 'CHANGE_ME_crm';

GRANT SELECT ON TABLE
    customers, customerrequesttrackers, customers_deals
TO app_crm;

GRANT SELECT, INSERT, UPDATE ON TABLE history_crm TO app_crm;
GRANT USAGE, SELECT ON SEQUENCE history_crm_id_seq TO app_crm;

-- ============================================================
-- Orchestrator -> its own history and nothing else.
--
-- It reaches data only by delegating to an agent, so it needs no SELECT
-- on any business table. An earlier orchestrator ran SQL directly, with
-- no table allowlist of its own, which made every domain boundary below
-- it optional.
-- ============================================================
CREATE ROLE app_orchestrator WITH LOGIN PASSWORD 'CHANGE_ME_orchestrator';

GRANT SELECT, INSERT, UPDATE ON TABLE history_orchestrator TO app_orchestrator;
GRANT USAGE, SELECT ON SEQUENCE history_orchestrator_id_seq TO app_orchestrator;

-- ============================================================
-- No agent may delete its own audit trail.
--
-- DELETE is deliberately withheld above: an agent that can rewrite its
-- own history has no audit trail. Data retention runs as a separate,
-- scheduled job under a different role.
-- ============================================================

-- ============================================================
-- A server-side ceiling on query time, independent of the client-side
-- timeout in the application.
-- ============================================================
ALTER ROLE app_hr           SET statement_timeout = '30s';
ALTER ROLE app_crm          SET statement_timeout = '30s';
ALTER ROLE app_orchestrator SET statement_timeout = '30s';

-- ============================================================
-- Row-level security goes here once authentication is in place.
--
-- With RLS_ENABLED=true the application sets app.user_id on every
-- connection before running a statement, so a policy shaped like:
--
--   ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
--   CREATE POLICY employees_visible_to_caller ON employees
--     FOR SELECT TO app_hr
--     USING (department = current_setting('app.user_id', true));
--
-- puts the decision in the database, where a prompt injection cannot
-- reach it. Until such policies exist, leave RLS_ENABLED=false.
-- ============================================================
