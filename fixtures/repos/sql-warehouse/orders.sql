-- Orders table with a foreign key to customers (exercises the FK graph),
-- plus a table nothing references (exercises orphan-table detection).
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    total_cents INTEGER
);

CREATE TABLE IF NOT EXISTS audit_log_deprecated (
    id   INTEGER PRIMARY KEY,
    note TEXT
);
