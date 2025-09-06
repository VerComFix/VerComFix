import os

# download dir
GITHUB_CODE_DOWNLOAD_BASE_DIR = '../data/repos'

# result base dir
RESULT_BASE_DIR = '../data'

# DB connection
DB_NAME = os.getenv("MYSQL_DATABASE", "api_signatures")
DB_CONFIG_BASE = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "******"),
    "charset": "utf8mb4",
    "autocommit": True
}
DB_CONFIG = {
    **DB_CONFIG_BASE,
    "database": DB_NAME
}
