-- Least-privilege Postgres roles, one per consolidated domain.
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
-- Table lists below match main/static.py's domain[7], domain[8], domain[9]
-- at the time this was written - if you add tables to a domain there,
-- add the matching GRANT here too.

-- ============================================================
-- agent1-service-property-deals -> domain[7]
-- ============================================================
CREATE ROLE app_property_deals WITH LOGIN PASSWORD 'CHANGE_ME_property_deals';

GRANT SELECT ON TABLE
    developers, projects, buildings, units,
    deals, deals_units, deals_projects, deals_customers, deals_directors, deals_agents
TO app_property_deals;

-- Its own history table (created by agent_common.history_repo on startup,
-- so this GRANT needs to run *after* the service has started at least
-- once and created history_property_deals - or pre-create the table
-- yourself using the CREATE TABLE in agent_common/history_repo.py).
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE history_property_deals TO app_property_deals;
GRANT USAGE, SELECT ON SEQUENCE history_property_deals_id_seq TO app_property_deals;

-- ============================================================
-- agent2-service-people -> domain[8]
-- ============================================================
CREATE ROLE app_people WITH LOGIN PASSWORD 'CHANGE_ME_people';

GRANT SELECT ON TABLE
    employees, directors_employees, hos_employee, teams, agents_employee,
    customers, customerrequesttrackers, customers_deals
TO app_people;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE history_people TO app_people;
GRANT USAGE, SELECT ON SEQUENCE history_people_id_seq TO app_people;

-- ============================================================
-- agent3-service-sales-payments -> domain[9]
-- ============================================================
CREATE ROLE app_sales_payments WITH LOGIN PASSWORD 'CHANGE_ME_sales_payments';

GRANT SELECT ON TABLE
    bookings, paymentlinks, projects, buildings, units, employees, agents_employee, customers, brokers,
    paymentsplits, payments, paymentplandetails, onlinepaymenttransactions,
    installmentplans, instalmentadjusted, paymenttermitems, paymentterms,
    projectpaymentplans, projectpaymentterms
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
ALTER ROLE app_property_deals SET statement_timeout = '30s';
ALTER ROLE app_people SET statement_timeout = '30s';
ALTER ROLE app_sales_payments SET statement_timeout = '30s';
ALTER ROLE app_orchestrator SET statement_timeout = '30s';

-- ============================================================
-- Wiring these into docker-compose.yml (not done automatically - this
-- requires the roles above to actually exist first):
--
-- Each service currently shares one env_file (./env/.env.app) with one
-- PG_USER/PG_PASSWORD for all 4 services. To use these roles, override
-- PG_USER/PG_PASSWORD per service in docker/docker-compose.yml, e.g.:
--
--   agent-property-deals:
--     environment:
--       PG_USER: app_property_deals
--       PG_PASSWORD: CHANGE_ME_property_deals
--     env_file:
--       - ./env/.env.app
--
-- (docker-compose merges `environment:` on top of `env_file:`, so this
-- overrides just those two vars per service without duplicating the rest
-- of .env.app.) Do the same for agent-people, agent-sales-payments, and
-- agents-service with their respective roles.
-- ============================================================
