import os

from db import is_exist, insert_many
from pathlib import Path
from packaging.version import parse as parse_version

def search_egg_dir(package_dir):
    for parent_dir, dir_names, file_names in os.walk(package_dir):
        for dir_name in dir_names:
            if str(dir_name).endswith('.egg-info'):
                return os.path.join(parent_dir, dir_name, 'top_level.txt')
    return ''


def get_packages_version_order_by_time(package_name, packages_dir):
    try:
        packages_list = os.listdir(packages_dir)
        if packages_list:
            packages_list = sorted(packages_list, key=lambda x: os.path.getmtime(os.path.join(packages_dir, x)))
            version_list = []
            for package in packages_list:
                if package.endswith('.tar.gz'):
                    package = package.replace('.tar.gz', '')
                if package.endswith('.zip'):
                    package = package.replace('.zip', '')

                version_list.append(package.replace(package_name + '-', ''))

            return version_list
    except Exception as e:
        print(e)
        return []


def get_packages_version_order_by_name(package_name, packages_dir):
    try:
        packages_list = os.listdir(packages_dir)
        version_list = []

        for package in packages_list:
            version = package
            if version.endswith('.tar.gz'):
                version = version.replace('.tar.gz', '')
            elif version.endswith('.zip'):
                version = version.replace('.zip', '')

            if version.startswith(package_name + '-'):
                version_str = version.replace(package_name + '-', '')
                version_list.append(version_str)

        version_list.sort(key=lambda v: parse_version(v))
        return version_list

    except Exception as e:
        print(e)
        return []

def read_file(path):
    try:
        file = open(path, "r")
        data = file.read().splitlines()
        return data
    except Exception as e:
        print(e)


def get_top_level_from_sources(package_dir):
    top_level = []
    top_level_file = search_egg_dir(package_dir)
    if top_level_file:
        top_level = read_file(top_level_file)
    return top_level


def main():
    for package_name in os.listdir(packages_path):
        # all_version_list = get_packages_version_order_by_time(package_name, str(projects_path) +'/' + package_name + '/')
        all_version_list = get_packages_version_order_by_name(package_name, str(projects_path) +'/' + package_name + '/')
        for version in all_version_list:
            print("handle version : " + version)
            if is_exist(
                    "SELECT 1 FROM top_level WHERE package_name='%s' AND package_version='%s'" % (
                            package_name, version)) > 0:
                print("%s - %s exist" % (package_name, version))
                continue

            package_dir = str(projects_path) +'/' + package_name + '/' + package_name + '-' + version + '/'
            top_levels = get_top_level_from_sources(package_dir)
            if not top_levels:
                top_levels.append(package_name)

            sql_list = []
            for top_level in top_levels:
                sql_list.append(
                    "INSERT INTO top_level(package_name,package_version,top_level) VALUES('%s','%s','%s')" % (
                        package_name, version, top_level))
            insert_many(sql_list)


if __name__ == '__main__':
    current_folder = Path(__file__).resolve().parent
    projects_path = current_folder.parent / 'projects'
    packages_path = current_folder.parent / 'packages'
    main()
