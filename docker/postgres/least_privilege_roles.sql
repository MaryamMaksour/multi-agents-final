-- Least-privilege Postgres roles, one per sub-agent provider.
--
-- Defense in depth for the SQL validation in agent_common/sql_validation.py:
-- that check parses every query's AST and rejects anything outside a
-- domain's table list, but it's still application code. A role that
-- physically cannot see another domain's tables means an app-layer bug
-- (or a future tool that forgets to validate) still can't cross domains.
--
-- Run this once against the live database (as a superuser / the owning
-- role), then point each service's PG_USER/PG_PASSWORD at its own role -
-- see the notes at the bottom for wiring that into docker-compose.
--
-- Table lists below match main/static.py's domain[1], domain[2], domain[3],
-- domain[7] at the time this was written - if you add tables to a domain
-- there, add the matching GRANT here too.

-- ============================================================
-- agent1-service-property -> domain[1]
-- ============================================================
CREATE ROLE app_property WITH LOGIN PASSWORD 'CHANGE_ME_property';

GRANT SELECT ON TABLE
    developers, projects, buildings, units
TO app_property;

-- Its own history table (created by agent_common.history_repo on startup,
-- so this GRANT needs to run *after* the service has started at least
-- once and created history_property - or pre-create the table yourself
-- using the CREATE TABLE in agent_common/history_repo.py).
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE history_property TO app_property;
GRANT USAGE, SELECT ON SEQUENCE history_property_id_seq TO app_property;

-- ============================================================
-- agent2-service-hr -> domain[2]
-- ============================================================
CREATE ROLE app_hr WITH LOGIN PASSWORD 'CHANGE_ME_hr';

GRANT SELECT ON TABLE
    employees, directors_employees, hos_employee, teams, agents_employee
TO app_hr;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE history_hr TO app_hr;
GRANT USAGE, SELECT ON SEQUENCE history_hr_id_seq TO app_hr;

-- ============================================================
-- agent3-service-crm -> domain[3]
-- ============================================================
CREATE ROLE app_crm WITH LOGIN PASSWORD 'CHANGE_ME_crm';

GRANT SELECT ON TABLE
    customers, customerrequesttrackers, customers_deals
TO app_crm;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE history_crm TO app_crm;
GRANT USAGE, SELECT ON SEQUENCE history_crm_id_seq TO app_crm;

-- ============================================================
-- agent4-service-sales-payments -> domain[7]
-- ============================================================
CREATE ROLE app_sales_payments WITH LOGIN PASSWORD 'CHANGE_ME_sales_payments';

GRANT SELECT ON TABLE
    agents_employee, bookings, brokers, buildings, customers, employees,
    installmentplans, instalmentadjusted, onlinepaymenttransactions,
    paymentlinks, paymentplandetails, payments, paymentsplits,
    paymenttermitems, paymentterms, projectpaymentplans, projectpaymentterms,
    projects, units
TO app_sales_payments;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE history_sales_payments TO app_sales_payments;
GRANT USAGE, SELECT ON SEQUENCE history_sales_payments_id_seq TO app_sales_payments;

-- ============================================================
-- agents-service (orchestrator) -> its own history table only.
-- The orchestrator no longer runs SQL against business tables at all
-- (db_execute/execute_next_cursor were removed from it - see the audit),
-- so it needs no SELECT grants on domain tables, only its own history.
-- ============================================================
CREATE ROLE app_orchestrator WITH LOGIN PASSWORD 'CHANGE_ME_orchestrator';

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE history_orchestrator TO app_orchestrator;
GRANT USAGE, SELECT ON SEQUENCE history_orchestrator_id_seq TO app_orchestrator;

-- ============================================================
-- Optional: a Postgres-level guard against runaway queries, on top of
-- the app-layer MAX_OFFSET/limit<=100 checks in agent_common/tools.py.
-- ============================================================
ALTER ROLE app_property SET statement_timeout = '30s';
ALTER ROLE app_hr SET statement_timeout = '30s';
ALTER ROLE app_crm SET statement_timeout = '30s';
ALTER ROLE app_sales_payments SET statement_timeout = '30s';
ALTER ROLE app_orchestrator SET statement_timeout = '30s';

-- ============================================================
-- Wiring these into docker-compose.yml (not done automatically - this
-- requires the roles above to actually exist first):
--
-- Each service currently shares one env_file (./env/.env.app) with one
-- PG_USER/PG_PASSWORD for all 5 services. To use these roles, override
-- PG_USER/PG_PASSWORD per service in docker/docker-compose.yml, e.g.:
--
--   agent-property:
--     environment:
--       PG_USER: app_property
--       PG_PASSWORD: CHANGE_ME_property
--     env_file:
--       - ./env/.env.app
--
-- (docker-compose merges `environment:` on top of `env_file:`, so this
-- overrides just those two vars per service without duplicating the rest
-- of .env.app.) Do the same for agent-hr, agent-crm, agent-sales-payments,
-- and agents-service with their respective roles.
-- ============================================================
