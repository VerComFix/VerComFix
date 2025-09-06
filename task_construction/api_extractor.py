import os, re
from get_api_signatures import get_all_call_apis_from_sources
from version_resolver import get_all_dependencies
from func_extractor import get_all_funcnode_from_sources
from db import save_api_calls, save_func_info

# Target TPLs (lib names)
TPLs = set()
with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data_collection', 'rank.txt'), 'r' , encoding='utf-8') as f:
    for line in f:
        TPLs.add(line.split('@@')[-1][:-1])

def get_py_files(project_dir):
    exclude_pattern = re.compile(r'^(setup.*|conftest\.py)$')
    py_files = []
        
    offset = len(project_dir) + 1
    for root, _, files in os.walk(project_dir):
        skip = False
        relative_dir = root[offset:]
        for dir_name in relative_dir.split(os.sep):
            if dir_name.startswith('.') or dir_name.startswith('__'):
                skip = True
                break
        if skip: continue

        for file in files:
            if file.endswith('.py') and not exclude_pattern.match(file):
                py_files.append(os.path.join(root, file))
    return py_files

def normalize_api_prefix(api_name):
    """
    例如将 'numpy.array' -> 'numpy'
    将 'sklearn.linear_model.LogisticRegression' -> 'sklearn'
    """
    return api_name.split('.')[0]

def build_package_version_dict(dep_list):
    """
    [('numpy', '==1.21.0'), ('pandas', ''), ('torch', '>=1.8')]
    ->
    {
        'numpy': '==1.21.0',
        'pandas': '',
        'torch': '>=1.8'
    }
    """
    return {name.lower(): version for name, version in dep_list}

def enrich_apis_with_versions(apis, package_version_dict):
    enriched = []
    for item in apis:
        prefix = normalize_api_prefix(item['api']).lower()
        version = package_version_dict.get(prefix, None)
        enriched.append({
            "api": item["api"],
            "file": item["file"],
            "lineno": item["lineno"],
            "end_lineno": item["end_lineno"],
            "version": version
        })
    return enriched

def print_results(results):
    print(f"{'API 限定名':40} {'文件路径':40} {'起始行号':8} {'结束行号':8} {'版本信息'}")
    print('-' * 100)
    for item in results:
        print(f"{item['api']:<40} {item['file']:<40} {item['lineno']:<8} {item['end_lineno']:<8} {item['version'] or 'N/A'}")

def extract_repo_api(project_dir):
    print(f"[INFO] 提取依赖版本信息...")
    deps = get_all_dependencies(project_dir)
    if len(deps) == 0: return
    dep_dict = build_package_version_dict(deps)
    
    cnt_lib = len(set(dep_dict.keys()) & TPLs)
    if cnt_lib <= 5: return

    print(f"[INFO] 提取源代码文件...")
    py_files = get_py_files(project_dir)

    print(f"[INFO] 提取 API 调用...")
    apis = get_all_call_apis_from_sources(py_files, dep_dict)

    print(f"[INFO] 保存到数据库...")
    save_api_calls(apis)

"""处理 Function-Level Task"""
def extract_repo_func(project_dir):
    print(f"[INFO] 提取依赖版本信息...")
    deps = get_all_dependencies(project_dir)
    if len(deps) == 0: return
    dep_dict = build_package_version_dict(deps)
    
    cnt_lib = len(set(dep_dict.keys()) & TPLs)
    if cnt_lib <= 5: return

    print(f"[INFO] 提取源代码文件...")
    py_files = get_py_files(project_dir)

    print(f"[INFO] 提取包含 TPL 调用 的 Function 定义 ...")
    funcs = get_all_funcnode_from_sources(py_files, dep_dict)

    print(f"[INFO] 保存到数据库...")
    save_func_info(funcs)
