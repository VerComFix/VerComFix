import ast
from get_api_signatures import get_API_calls_from_funcnode

class StrictTopLevelFunctionExtractor:
    def __init__(self):
        self.top_level_functions = []
    
    def extract(self, file_path, package_version_dict, source_code=''):
        """提取不包含嵌套函数的顶级函数"""
        try:
            self.is_eval = True
            if not source_code:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source_code = f.read()
                self.is_eval = False
            self.file_path = file_path
            self.code = source_code
            self.deps = package_version_dict

            tree = ast.parse(source_code, filename=file_path)
            self._analyze_module(tree)
            return self.top_level_functions
            
        except Exception as e:
            print(f"错误: {e}")
            return []
    
    def _analyze_module(self, module_node):
        """分析模块节点，提取顶级函数"""
        for node in module_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not self._has_nested_functions(node):
                    func_info = self._extract_function_info(node)
                    if func_info: self.top_level_functions.append(func_info)
    
    def _has_nested_functions(self, func_node):
        """检查函数是否包含嵌套函数定义"""
        for child in ast.walk(func_node):
            # 跳过函数节点本身
            if child is func_node:
                continue
                
            # 如果找到任何函数定义节点，说明有嵌套函数
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return True
        
        return False
    
    def _extract_function_info(self, node):
        """提取函数详细信息"""
        head_offset = self._get_func_header_linenum(node)
        bg, ed = node.lineno+head_offset, getattr(node, 'end_lineno', -1)
        body_lines = ed-bg+1

        # 没有装饰器、body 为 5~20 行
        if self.is_eval: pass
        elif head_offset \
            or len(node.decorator_list)>0 \
            or node.args.vararg is not None or node.args.kwarg is not None\
            or ed == -1\
            or (body_lines<5 or body_lines>20):
            return None

        # 提取所有 func Call
        func_src   = ast.get_source_segment(self.code, node)
        tpl_calls = get_API_calls_from_funcnode(func_src, self.code, self.file_path, self.deps)

        if not tpl_calls: return None
        return {
            'api': tpl_calls[0]['api'],
            'file': self.file_path,
            'lineno': bg,
            'end_lineno': ed,
            'version': tpl_calls[0]['version'],
            'bg_off':  tpl_calls[0]['lineno'],
            'ed_off':  tpl_calls[0]['end_lineno'],
            'src':     ast.get_source_segment(self.code, node) if self.is_eval else ''
        }
    
    def _get_func_header_linenum(self, node):
        lines = ast.get_source_segment(self.code, node).split('\n')
        # 找到函数头的结束（通常是冒号所在行）
        for i, line in enumerate(lines):
            if line.strip().endswith(':'):
                return i + 1

def get_strict_top_level_functions(file_path, package_version_dict, source_code=''):
    """
    获取所有不包含嵌套函数的顶级函数
    """
    extractor = StrictTopLevelFunctionExtractor()
    return extractor.extract(file_path, package_version_dict, source_code)

def get_all_funcnode_from_sources(sources, package_version_dict):
    all_funcnodes = []
    for source in sources:
        try:
            func_calls = get_strict_top_level_functions(source, package_version_dict)
            all_funcnodes.extend(func_calls)
        except Exception as e:
            print(f"[ERROR] {source}: {e}")
            continue
    return all_funcnodes