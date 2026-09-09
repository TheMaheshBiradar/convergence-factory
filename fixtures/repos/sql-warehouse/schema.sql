-- Data warehouse (team-data): owns the customers table.
CREATE TABLE IF NOT EXISTS customers (
    id   INTEGER PRIMARY KEY,
    name TEXT,
    active BOOLEAN DEFAULT TRUE
);

CREATE VIEW active_customers AS
    SELECT id, name FROM customers WHERE active = TRUE;
