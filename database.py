import lancedb
import os

DB_PATH = "./lancedb_data"

def get_lancedb_connection():
    """Initializes and returns the LanceDB connection."""
    os.makedirs(DB_PATH, exist_ok=True)
    return lancedb.connect(DB_PATH)