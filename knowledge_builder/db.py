import pymysql
from typing import List, Tuple
import json
import os, sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from global_config import DB_CONFIG_BASE, DB_NAME, DB_CONFIG


def create_database_if_not_exists():
    """连接到MySQL，自动创建数据库（如果不存在）"""
    with pymysql.connect(**DB_CONFIG_BASE) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"""
                CREATE DATABASE IF NOT EXISTS {DB_NAME}
                CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci
            """)


def get_connection():
    """获取连接到目标数据库的连接"""
    return pymysql.connect(**DB_CONFIG)


def init_db():
    """初始化数据库表结构"""
    try:
        create_database_if_not_exists()

        with get_connection() as conn:
            with conn.cursor() as cursor:
                # 建 top_level 表（避免 TEXT 参与 UNIQUE）
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS top_level (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        package_name VARCHAR(255) NOT NULL,
                        package_version VARCHAR(255) NOT NULL,
                        top_level VARCHAR(1024) NOT NULL,
                        version_id INT DEFAULT 0,
                        UNIQUE KEY uniq_top_level (package_name(100), package_version(100), top_level(191))
                    )
                """)
                # 建 api_signatures 表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS api_signatures (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        package_name VARCHAR(255) NOT NULL,
                        package_version VARCHAR(255) NOT NULL,
                        api_name VARCHAR(1024) NOT NULL,
                        parameters TEXT,
                        has_return TINYINT(1) NOT NULL,
                        UNIQUE KEY uniq_api (package_name(100), package_version(100), api_name(191))
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS differences (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        package_version INT NOT NULL,
                        package_name VARCHAR(255) NOT NULL,
                        version_id INT NOT NULL,
                        api_name TEXT NOT NULL,
                        param_list TEXT,
                        has_return BOOLEAN,
                        diff CHAR(1) NOT NULL,
                        FOREIGN KEY (package_version) REFERENCES top_level(id) ON DELETE CASCADE
                    )
                """)

                # 建索引（必须用 SHOW 判断，不支持 IF NOT EXISTS）
                cursor.execute("SHOW INDEX FROM api_signatures WHERE Key_name = 'idx_api_signatures_pkg_ver'")
                if cursor.fetchone() is None:
                    cursor.execute("CREATE INDEX idx_api_signatures_pkg_ver ON api_signatures(package_name(100), package_version(100))")

                cursor.execute("SHOW INDEX FROM api_signatures WHERE Key_name = 'idx_api_signatures_name'")
                if cursor.fetchone() is None:
                    cursor.execute("CREATE INDEX idx_api_signatures_name ON api_signatures(api_name(191))")
    except Exception as e:
        print(f"数据库初始化失败: {e}")
    

def is_exist(sql, params=()):
    """检查记录是否存在"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone() is not None


def insert_many(sql_list):
    """批量执行INSERT语句"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for sql in sql_list:
                try:
                    cursor.execute(sql)
                except pymysql.IntegrityError:
                    pass


def save_api_signatures(package_name: str, version: str, signatures: List[Tuple[str, List[str], bool]]):
    """保存API签名到数据库"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for api_name, params, has_return in signatures:
                try:
                    cursor.execute(
                        """INSERT INTO api_signatures 
                        (package_name, package_version, api_name, parameters, has_return)
                        VALUES (%s, %s, %s, %s, %s)""",
                        (package_name, version, api_name, json.dumps(params), 1 if has_return else 0)
                    )
                except pymysql.IntegrityError:
                    continue


def get_api_signatures(package_name: str, version: str = None):
    """获取指定包和版本的API签名"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if version:
                cursor.execute(
                    """SELECT api_name, parameters, has_return 
                    FROM api_signatures 
                    WHERE package_name=%s AND package_version=%s""",
                    (package_name, version)
                )
            else:
                cursor.execute(
                    """SELECT api_name, parameters, has_return 
                    FROM api_signatures 
                    WHERE package_name=%s""",
                    (package_name,)
                )

            results = []
            for api_name, params_json, has_return in cursor.fetchall():
                params = json.loads(params_json) if params_json else []
                results.append((api_name, params, bool(has_return)))
            return results


# 初始化数据库（首次导入时自动创建表）
if __name__ == "__main__":
    init_db()
    print("✅ MySQL 数据库和表结构初始化完成")
