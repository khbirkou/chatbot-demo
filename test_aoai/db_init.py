import sqlite3
from pathlib import Path

DB_PATH = Path("greenmow.db")

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS mower_models (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  brand TEXT NOT NULL,
  product_line TEXT NOT NULL,
  model_name TEXT NOT NULL,
  tagline TEXT,
  description TEXT
);

CREATE TABLE IF NOT EXISTS model_specs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model_id INTEGER NOT NULL,
  component TEXT NOT NULL,
  details TEXT,
  testing_focus TEXT,
  FOREIGN KEY(model_id) REFERENCES mower_models(id)
);
"""

# Optional: Demo-Daten (nur wenn mower_models noch leer ist)
SEED_SQL = """
INSERT INTO mower_models (brand, product_line, model_name, tagline, description)
VALUES
('Evergreen Connect', 'Smart Mowers', 'TerraMow T-3', 'The Essential',
 'Entry-level model for smaller lawns. Focus: reliability, basic navigation, connectivity.'),
('Evergreen Connect', 'Smart Mowers', 'TerraMow T-5', 'The Navigator',
 'Mid-range model with improved navigation and better battery performance.'),
('Evergreen Connect', 'Smart Mowers', 'TerraMow T-7 Vision', 'The Visionary',
 'Advanced model with enhanced perception and obstacle handling.');

INSERT INTO model_specs (model_id, component, details, testing_focus)
VALUES
(1, 'Battery Capacity', '2.0 Ah (Amp-hours)', 'Verify runtime and recharge time.'),
(1, 'Connectivity', 'Wi-Fi (2.4GHz only)', 'Stability under network congestion; reconnect behavior.'),
(1, 'Key Feature', 'App-based Scheduling', 'Reliability of scheduling and stop/start behavior.'),

(2, 'Battery Capacity', '3.2 Ah (Amp-hours)', 'Longer runtime vs. entry model; recharge time under load.'),
(2, 'Navigation System', 'Enhanced GNSS + IMU', 'Path accuracy; drift over time; boundary adherence.'),

(3, 'Perception', 'Vision-assisted obstacle detection', 'Detection precision; false positives/negatives; low light behavior.'),
(3, 'Terrain Handling', 'All-terrain wheels', 'Traction on slopes; wet grass performance; stability.');
"""

def main():
    print(f"Using DB: {DB_PATH.resolve()}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Schema anlegen
    cur.executescript(SCHEMA_SQL)
    conn.commit()

    # Seed nur, wenn leer
    cur.execute("SELECT COUNT(*) AS c FROM mower_models")
    count = cur.fetchone()["c"]

    if count == 0:
        cur.executescript(SEED_SQL)
        conn.commit()
        print("Seed inserted: mower_models + model_specs filled.")
    else:
        print(f"Seed skipped: mower_models already has {count} rows.")

    # Kurzer Check: Tabellen anzeigen
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [r["name"] for r in cur.fetchall()]
    print("Tables:", tables)

    conn.close()
    print("DB init complete.")

if __name__ == "__main__":
    main()
