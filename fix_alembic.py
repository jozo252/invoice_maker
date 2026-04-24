import sqlite3
from pathlib import Path

DB_PATH = Path("instance/invoices.db")  # uprav, ak používaš inú DB

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("PRAGMA table_info(clients)")
print("Pred úpravou:")
for col in cur.fetchall():
    print(col)

# SQLite nevie priamo ALTER COLUMN nullable.
# Najjednoduchšie bezpečné riešenie: ak nechceš prestavať tabuľku,
# tak pred vložením nikdy neposielaj None do bic.
conn.close()