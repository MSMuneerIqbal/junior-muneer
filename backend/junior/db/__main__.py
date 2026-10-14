"""Create or upgrade the database:  python -m junior.db"""

from junior.db.engine import init_db
from junior.logging_setup import setup_logging

setup_logging()
init_db()
