import pymysql, os, sys
from typing import List, Dict

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from global_config import DB_CONFIG_BASE, DB_NAME, DB_CONFIG

def create_database_if_not_exists():
    with pymysql.connect(**DB_CONFIG_BASE) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"""
                CREATE DATABASE IF NOT EXISTS {DB_NAME}
                CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci
            """)


def get_connection():
    return pymysql.connect(**DB_CONFIG)


def init_db():
    """初始化数据库表结构"""
    try:
        create_database_if_not_exists()
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS api_calls (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        api_name VARCHAR(1024) NOT NULL,
                        file_path TEXT NOT NULL,
                        lineno INT NOT NULL,
                        end_lineno INT NOT NULL,
                        version_type VARCHAR(32) DEFAULT NULL,
                        version VARCHAR(128) DEFAULT NULL,
                        UNIQUE KEY uniq_api_call (api_name(191), file_path(300), lineno)
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS func_task (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        api_name VARCHAR(1024) NOT NULL,
                        file_path TEXT NOT NULL,
                        lineno INT NOT NULL,
                        end_lineno INT NOT NULL,
                        version_type VARCHAR(32) DEFAULT NULL,
                        version VARCHAR(128) DEFAULT NULL,
                        bg_off INT NOT NULL,
                        ed_off INT NOT NULL,
                        UNIQUE KEY uniq_api_call (api_name(191), file_path(300), lineno)
                    )
                """)
    except Exception as e:
        print(f"数据库初始化失败: {e}")
        exit(0)

def classify_version_type(version_str: str) -> str:
    """根据版本字符串判断版本类型"""
    if not version_str or version_str.strip() == "":
        return "不明确"
    # 简单判断是否是范围版本（包含 >= <= < > 逗号）
    if any(op in version_str for op in [">=", "<=", ">", "<", ",", "~="]):
        return "范围"
    # 明确版本，比如 ==1.2.3 或 !=0.24.1
    if version_str.startswith("==") or version_str.startswith("!=") or version_str.startswith("~="):
        return "明确"
    # 其他情况归类为范围（保守处理）
    return "范围"

def save_api_calls(call_data: List[Dict]):
    """保存 API 调用记录到数据库，新增版本类型和版本字段"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for item in call_data:
                version_str = item.get("version", "") or ""
                version_type = classify_version_type(version_str)
                if version_type == '不明确': continue
                try:
                    cursor.execute(
                        """INSERT INTO api_calls 
                        (api_name, file_path, lineno, end_lineno, version_type, version)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            item["api"],
                            item["file"],
                            item["lineno"],
                            item["end_lineno"],
                            version_type,
                            version_str
                        )
                    )
                except pymysql.IntegrityError:
                    # 唯一约束冲突时忽略
                    continue

def save_func_info(func_info: List[Dict]):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for item in func_info:
                version_str = item.get("version", "") or ""
                version_type = classify_version_type(version_str)
                if version_type == '不明确': continue
                try:
                    cursor.execute(
                        """INSERT INTO func_task
                        (api_name, file_path, lineno, end_lineno, version_type, version, bg_off, ed_off)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            item["api"],
                            item["file"],
                            item["lineno"],
                            item["end_lineno"],
                            version_type,
                            version_str,
                            item['bg_off'],
                            item['ed_off'],
                        )
                    )
                except pymysql.IntegrityError:
                    # 唯一约束冲突时忽略
                    continue


def get_api_calls_by_file(file_path: str) -> List[Dict]:
    """根据文件路径获取 API 调用记录"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT api_name, lineno, end_lineno 
                FROM api_calls WHERE file_path = %s""",
                (file_path,)
            )
            results = cursor.fetchall()
            return [
                {
                    "api": row[0],
                    "file": file_path,
                    "lineno": row[1],
                    "end_lineno": row[2]
                }
                for row in results
            ]


# 初始化测试
if __name__ == "__main__":
    init_db()
    print("✅ MySQL 数据库和表结构初始化完成")
