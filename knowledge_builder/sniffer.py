import ast
import os
import re
import sys
import json
from packaging.version import parse as parse_version
from db import *

def get_keywords(node):
    args = node.args
    arg_names = []
    defaults = args.defaults
    for arg in args.args:
        arg_names += [arg.arg]
    has_return = any(isinstance(n, ast.Return) for n in ast.walk(node))
    # return (arg_names, len(defaults))
    return (arg_names, int(has_return))

class ClassVisitor(ast.NodeVisitor):
    def __init__(self):
        self.result = {} 
    def visit_FunctionDef(self, node): 
        kw_names = get_keywords(node)
        self.result[node.name] = kw_names
        return node
    
class SourceVisitor(ast.NodeVisitor):
    def __init__(self):
        self.result = {}
    def visit_FunctionDef(self, node):
        kw_names = get_keywords(node)
        self.result[node.name] = kw_names
        return node
    def visit_ClassDef(self, node):
        visitor = ClassVisitor()
        visitor.visit(node)
        self.result[node.name] = visitor.result
        return node


class Tree:
    def __init__(self, name):
        self.name = name
        self.children = []
        self.parent = None
        self.cargo = {}
        self.source = ''
        self.ast = None
    def __str__(self):
        return str(self.name)

def parse_import(tree):
    module_item_dict = {}
    try:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module is None and node.level not in module_item_dict:
                    module_item_dict[node.level] = []
                elif node.module not in module_item_dict:
                   module_item_dict[node.module] = []
                items = [nn.__dict__ for nn in node.names]
                for d in items:
                    if node.module is None:
                        module_item_dict[node.level].append(d['name'])
                    else:
                        module_item_dict[node.module].append(d['name'])

        return module_item_dict
    except(AttributeError):
        return None
 
def gen_AST(filename):
    try:
        source = open(filename).read()
        tree = ast.parse(source, mode='exec')
        return tree
    except (SyntaxError,UnicodeDecodeError,):  # to avoid non-python code
        pass
        return None
def parse_pyx(filename):
    lines = open(filename).readlines()
    all_func_names = []
    for line in lines:
        names = re.findall('def ([\s\S]*?)\(', str(line))
        if len(names)>0:
            all_func_names.append(names[0])

def extract_class(filename):
    try:
        print(filename)
        source = open(filename).read()
        tree = ast.parse(source, mode='exec')
        visitor = SourceVisitor()
        visitor.visit(tree)
        print('testing')
        return visitor.result, tree
    except Exception as e:  # to avoid non-python code
        # fail passing python3 
        if filename[-3:] == 'pyx':
            parse_pyx(filename)
        return {}, None  # return empty 

def extract_class_from_source(source):
    try:
        tree = ast.parse(source, mode='exec')
        visitor = SourceVisitor()
        visitor.visit(tree)
        return visitor.result, tree
    except Exception as e:  # to avoid non-python code
        #if filename[-3:] == 'pyx':
        #    #print(filename)
        #    parse_pyx(filename)
        print(e)
        return {}, None# return empty 

def build_dir_tree(node):
    if node.name in ['test', 'tests', 'testing']:
        return 
    if os.path.isdir(node.name) is True:
        os.chdir(node.name)
        items  = os.listdir('.')
        for item in items:
            child_node = Tree(item)
            child_node.parent =  node
            build_dir_tree(child_node)
            node.children.append(child_node)
        os.chdir('..')
    else:
        # this is a file
        if node.name.endswith('.py'):
            source = open(node.name, 'rb').read()
            node.source = source.decode("utf-8", errors="ignore")
            res, tree = extract_class_from_source(node.source)
            node.cargo = res
            node.ast = tree

def leaf2root(node):
    tmp_node = node
    path_to_root = []
    # not init.py
    while tmp_node is not None:
        path_to_root.append(tmp_node.name)
        tmp_node = tmp_node.parent
    if node.name == '__init__.py':
        path_to_root = path_to_root[1:]
        path_name = ".".join(reversed(path_to_root))
        return path_name
    else:
        path_name = ".".join(reversed(path_to_root[1:]))
        path_name = "{}.{}".format(path_name, node.name.split('.')[0])
        return path_name

def find_child_by_name(node, name):
    for ch in node.children:
        if ch.name == name:
            return ch
    return None
def find_node_by_name(nodes, name):
    for node in nodes:
        if node.name == name or node.name.rstrip('.py')== name:
            return node
    return None
def go_to_that_node(root, cur_node, visit_path):
    route_node_names = visit_path.split('.')
    route_length = len(route_node_names)
    tmp_node = None
    # go to the siblings of the current node
    tmp_node =  find_node_by_name(cur_node.parent.children, route_node_names[0])
    if tmp_node is not None:
        for i in range(1,route_length):
            tmp_node =  find_node_by_name(tmp_node.children, route_node_names[i])
            if tmp_node is None:
                break
    # from the topmost 
    elif route_node_names[0] == root.name:
        tmp_node = root
        for i in range(1,route_length):
            tmp_node =  find_node_by_name(tmp_node.children, route_node_names[i])
            if tmp_node is None:
                break
        return tmp_node
    # from its parent 
    elif route_node_names[0] == cur_node.parent.name:
        tmp_node = cur_node.parent
        for i in range(1,route_length):
            tmp_node =  find_node_by_name(tmp_node.children, route_node_names[i])
            if tmp_node is None:
                break

    # we are still in the directory
    if tmp_node is not None and tmp_node.name.endswith('.py') is not True:
       tmp_node =  find_node_by_name(tmp_node.children, '__init__.py')

    return tmp_node

def tree_infer_levels(root_node):
    API_name_lst = []
    leaf_stack = []
    working_queue = []
    working_queue.append(root_node)

    # bfs to search all I leafs
    while len(working_queue)>0:
        tmp_node = working_queue.pop(0)
        if tmp_node.name.endswith('.py') == True:
            leaf_stack.append(tmp_node)
        working_queue.extend(tmp_node.children)

    # visit all elements from the stack
    for node in leaf_stack[::-1]:
        # private modules
        if node.name!='__init__.py' and node.name[0]=='_':
            continue
        module_item_dict = parse_import(node.ast)
        if module_item_dict is None:
            continue
        for k, v in module_item_dict.items():
            if k is None or isinstance(k, int):
                continue
            dst_node = go_to_that_node(root_node, node, k)
            if dst_node is not None:
                if v[0] =='*':
                  for k_ch, v_ch in dst_node.cargo.items():
                      node.cargo[k_ch] = v_ch
                  k_ch_all = list(dst_node.cargo.keys())
                else:
                    for api in v:
                        if api in dst_node.cargo:
                            node.cargo[api]= dst_node.cargo[api]
            else:
                pass

    for node in leaf_stack:
        # get visit path 
        API_prefix = leaf2root(node) 
        node_API_lst = make_API_full_name(node.cargo, API_prefix)
        API_name_lst.extend(node_API_lst)

    return API_name_lst

def make_API_full_name(meta_data, API_prefix):
    API_lst = []
    for k, v in meta_data.items():
        if k[0] == '_':
            continue  # 忽略私有函数或类
        if isinstance(v, tuple):
            # v = (参数列表, 是否有返回值)
            API_name = "{}.{},{},{}".format(API_prefix, k, ";".join(v[0]), v[1])
            API_lst.append(API_name)
        elif isinstance(v, dict):
            # 类的 __init__
            if '__init__' in v:
                args = v['__init__']
                API_name = "{}.{},{},{}".format(API_prefix, k, ";".join(args[0]), args[1])
                API_lst.append(API_name)
            else:
                args = ([], 0)  # 默认无参数无返回值
                API_name = "{}.{},{},{}".format(API_prefix, k, ";".join(args[0]), args[1])
                API_lst.append(API_name)

            # 类中其他方法
            for f_name, args in v.items():
                if f_name[0] != '_':
                    API_name = "{}.{}.{},{},{}".format(API_prefix, k, f_name, ";".join(args[0]), args[1])
                    API_lst.append(API_name)

    return API_lst

def search_targets(root_dir, targets):
     entry_points = []
     for root, dirs, files in os.walk(root_dir):
         n_found = 0
         for t in targets:
             if t in dirs :
                entry_points.append(os.path.join(root, t))
                n_found += 1
             elif t+'.py' in files:
                 entry_points.append(os.path.join(root, t+'.py'))
                 n_found += 1
         if n_found == len(targets):
             return entry_points
     return None


def process_source_package(path, l_name):
    """
    path: 解压后的源码目录
    l_name: 库的顶层目录名，例如 numpy、torch
    返回 entry_points：可能的入口模块路径
    """
    all_items = os.listdir(path)
    top_levels = []

    # 尝试根据 l_name 或 setup.py 中的提示找到顶层目录
    for item in all_items:
        if item == l_name or item.startswith(l_name.replace("-", "_")):
            top_levels.append(item)
        elif item.endswith(".py") and item.rstrip(".py") == l_name:
            top_levels.append(item)

    if not top_levels:
        # fallback：使用所有目录
        top_levels = [item for item in all_items if os.path.isdir(os.path.join(path, item))]

    entry_points = search_targets(path, top_levels)
    return entry_points

def process_single_module(module_path):
    API_name_lst = []
    # process other modules !!!
    if os.path.isfile(module_path):
        name_segments =  os.path.basename(module_path).rstrip('.py*') # .py and .pyx
        # process a single file module
        res, tree = extract_class(module_path)
        node_API_lst = make_API_full_name(res, name_segments)
        API_name_lst.extend(node_API_lst)
    else:
        first_name = os.path.basename(module_path)
        working_dir = os.path.dirname(module_path)
        path = []
        cwd = os.getcwd() # save current working dir
        os.chdir(working_dir)
        root_node = Tree(first_name)
        build_dir_tree(root_node)
        API_name_lst = tree_infer_levels(root_node)
        os.chdir(cwd) # go back cwd
    return API_name_lst

def normalize_name(name):
    return name.replace("_", "-").lower()

def extract_version(folder_name, lib_name):
    """
    从文件夹名如 pandas-0.13.1 中提取版本号（确保前缀匹配）。
    返回版本字符串或 None。
    """
    lib_name_norm = normalize_name(lib_name)
    if normalize_name(folder_name).startswith(lib_name_norm + "-"):
        return folder_name[len(lib_name)+1:]  # +1 去除连字符
    return None

def get_diff_from_all_version_apis(all_version_apis):
    if not all_version_apis:
        return {}

    diff = {}
    version_keys = list(all_version_apis.keys())
    first_version = version_keys[0]

    def to_hashable(api):
        return (api[0], tuple(api[1]), api[2])  # 限定名, 参数, 返回标志

    base_apis = {to_hashable(api) for api in all_version_apis[first_version]}
    diff[first_version] = {api: '=' for api in base_apis}

    for version in version_keys[1:]:
        current_apis = {to_hashable(api) for api in all_version_apis[version]}
        result = {}

        for api in base_apis - current_apis:
            result[api] = '-'  # 被删除
        for api in current_apis - base_apis:
            result[api] = '+'  # 新增

        diff[version] = result
        base_apis = current_apis

    return diff

def save_package_version_apis_diff(package_name, all_diff):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            version_id_counter = 0
            for version, apis in all_diff.items():
                # 获取 top_level 记录
                cursor.execute("""
                    SELECT id, version_id FROM top_level
                    WHERE package_name=%s AND package_version=%s
                    LIMIT 1
                """, (package_name, version))
                result = cursor.fetchone()
                if not result:
                    print(f"Warning: No top_level entry found for {package_name} {version}")
                    continue
                top_level_id, version_id = result

                # 这里可选择是否更新 version_id（如果你想同步 version_id）
                cursor.execute("""
                    UPDATE top_level SET version_id=%s WHERE id=%s
                """, (version_id_counter, top_level_id))

                sql_list = []
                for api_signature, diff_flag in apis.items():
                    api_name, params, has_return = api_signature
                    param_str = ', '.join(params)
                    sql_list.append((
                        top_level_id,
                        package_name,
                        version_id_counter,
                        api_name,
                        param_str,
                        has_return,
                        diff_flag
                    ))

                if not sql_list:
                    sql_list.append((top_level_id, package_name, version_id_counter, '', '', False, '='))

                cursor.executemany("""
                    INSERT INTO differences(
                        package_version, package_name, version_id,
                        api_name, param_list, has_return, diff
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, sql_list)

                conn.commit()
                version_id_counter += 1


def main():
    root_dir = "packages"
    all_packages = os.listdir(root_dir)

    for lib_name in all_packages:
        lib_path = os.path.join(root_dir, lib_name)
        if not os.path.isdir(lib_path):
            continue

        version_dirs = []
        for fname in os.listdir(lib_path):
            version = extract_version(fname, lib_name)
            if version:
                version_dirs.append((version, os.path.join(lib_path, fname)))

        # 按语义版本排序
        version_dirs.sort(key=lambda x: parse_version(x[0]))

        for version, v_dir in version_dirs:
            print(f"Processing {v_dir}")

            if is_exist("SELECT 1 FROM api_signatures WHERE package_name=%s AND package_version=%s",
                        (lib_name, version)):
                print(f"{lib_name} - {version} already exists in database")
                continue

            entry_points = process_source_package(v_dir, lib_name)
            if entry_points is None:
                continue

            version_api_list = []

            for ep in entry_points:
                API_name_lst = process_single_module(ep)
                if API_name_lst is None:
                    continue

                for api_full_str in API_name_lst:
                    parts = api_full_str.split(",")
                    api_qualname = parts[0]
                    params = parts[1].split(";") if parts[1] else []
                    has_return = int(parts[2])
                    version_api_list.append([api_qualname, params, has_return])

            save_api_signatures(lib_name, version, version_api_list)
            print(f"Saved {len(version_api_list)} APIs for {lib_name}-{version} to database")

        # 版本差异对比与存储
        if version_dirs:
            all_version_apis = {}
            for version, _ in version_dirs:
                version_apis = get_api_signatures(lib_name, version)
                all_version_apis[version] = version_apis

            api_diff = get_diff_from_all_version_apis(all_version_apis)
            save_package_version_apis_diff(lib_name, api_diff)
            print(f"Saved API diff for {lib_name}")

if __name__ == '__main__':
    main()