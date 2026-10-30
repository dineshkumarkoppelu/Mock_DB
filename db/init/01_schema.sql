-- CRM schema. Runs once, on first start of an empty data volume.

CREATE TABLE IF NOT EXISTS sales_people (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    region      TEXT NOT NULL,
    joined_on   DATE NOT NULL,
    active      BOOLEAN NOT NULL,
    capacity    INTEGER NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clients (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    industry    TEXT NOT NULL,
    size        TEXT NOT NULL,
    region      TEXT NOT NULL,
    created_on  DATE NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deals (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    value               BIGINT NOT NULL,
    status              TEXT NOT NULL,
    stage               TEXT NOT NULL,
    created_at          DATE NOT NULL,
    qualified_at        DATE,
    proposal_at         DATE,
    negotiation_at      DATE,
    expected_close_date DATE NOT NULL,
    closed_at           DATE,
    domain              TEXT NOT NULL,
    client_id           TEXT NOT NULL REFERENCES clients (id),
    owner_id            TEXT,              -- nullable, no FK (rep may exist only in Neo4j)
    inserted_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS activities (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    date            DATE NOT NULL,
    outcome         TEXT NOT NULL,
    deal_id         TEXT NOT NULL,         -- no FK
    sales_person_id TEXT NOT NULL,         -- no FK
    inserted_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_deals_client      ON deals(client_id);
CREATE INDEX IF NOT EXISTS idx_deals_owner       ON deals(owner_id);
CREATE INDEX IF NOT EXISTS idx_activities_deal   ON activities(deal_id);
CREATE INDEX IF NOT EXISTS idx_activities_person ON activities(sales_person_id);

-- change notifications
CREATE OR REPLACE FUNCTION crm_notify_change() RETURNS trigger AS $$
DECLARE
    changed RECORD;
BEGIN
    IF current_setting('application_name', true) = 'crm-app' THEN
        RETURN NULL;
    END IF;
    IF TG_OP = 'DELETE' THEN changed := OLD; ELSE changed := NEW; END IF;
    PERFORM pg_notify(
        'crm_changes',
        json_build_object('table', TG_TABLE_NAME, 'op', TG_OP, 'id', changed.id)::text
    );
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- one trigger per table: sales_people, clients, deals, activities
CREATE OR REPLACE TRIGGER crm_sales_people_notify
    AFTER INSERT OR UPDATE OR DELETE ON sales_people
    FOR EACH ROW EXECUTE FUNCTION crm_notify_change();

CREATE OR REPLACE TRIGGER crm_clients_notify
    AFTER INSERT OR UPDATE OR DELETE ON clients
    FOR EACH ROW EXECUTE FUNCTION crm_notify_change();

CREATE OR REPLACE TRIGGER crm_deals_notify
    AFTER INSERT OR UPDATE OR DELETE ON deals
    FOR EACH ROW EXECUTE FUNCTION crm_notify_change();

CREATE OR REPLACE TRIGGER crm_activities_notify
    AFTER INSERT OR UPDATE OR DELETE ON activities
    FOR EACH ROW EXECUTE FUNCTION crm_notify_change();
