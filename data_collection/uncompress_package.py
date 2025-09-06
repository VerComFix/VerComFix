import os
from pathlib import Path
import shutil
import tempfile
import logging
from packaging.version import parse as parse_version
from concurrent.futures import ThreadPoolExecutor, as_completed

log_file = 'unpack_log.txt'
logging.basicConfig(
    filename=log_file,
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger()

def get_packages_path_order_by_time(packages_dir):
    # logger.info(f"扫描目录（按时间）: {packages_dir}")
    packages_list = os.listdir(packages_dir)
    if packages_list:
        packages_list = sorted(packages_list, key=lambda x: os.path.getmtime(os.path.join(packages_dir, x)))
        return packages_list
    return []

def get_packages_path_order_by_name(packages_dir):
    # logger.info(f"扫描目录（按版本）: {packages_dir}")
    packages_list = os.listdir(packages_dir)

    def extract_version(folder_name):
        parts = folder_name.rsplit('-', 1)
        if len(parts) == 2:
            return parse_version(parts[1])
        return parse_version("0.0.0")  # fallback

    if packages_list:
        packages_list = sorted(packages_list, key=extract_version)
        return packages_list

    return []

def unpack_single_package(project_path, packages_dir, ff):
    src_file = project_path / ff
    version_folder_name = ff.replace('.zip', '').replace('.tar.gz', '')
    dest_dir = packages_dir / version_folder_name

    if dest_dir.exists():
        logger.info(f"{ff} 已存在，跳过")
        return

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            shutil.unpack_archive(str(src_file), tmpdir)
            top_level_items = list(Path(tmpdir).iterdir())

            if len(top_level_items) == 1 and top_level_items[0].is_dir():
                shutil.move(str(top_level_items[0]), dest_dir)
            else:
                dest_dir.mkdir()
                for item in top_level_items:
                    if item.is_dir():
                        shutil.copytree(item, dest_dir / item.name)
                    else:
                        shutil.copy2(item, dest_dir / item.name)

        logger.info(f"成功解压: {ff}")
    except Exception as e:
        logger.error(f"解压失败 {ff}: {e}")

def main():
    tasks = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for f in os.listdir(projects):
            project_path = Path(projects) / f
            packages_dir = Path(packages) / f
            packages_dir.mkdir(parents=True, exist_ok=True)

            if project_path.is_dir():
                for ff in get_packages_path_order_by_time(project_path):
                    future = executor.submit(unpack_single_package, project_path, packages_dir, ff)
                    tasks.append(future)

        # 等待所有任务完成
        for future in as_completed(tasks):
            future.result()

    logger.info("全部解压完成！")

if __name__ == '__main__':
    current_folder = Path(__file__).resolve().parent
    projects = current_folder.parent / 'projects'
    packages = current_folder.parent / 'packages'
    main()
