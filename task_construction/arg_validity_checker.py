"""
ArgumentsAnalyser: 用于分析 Function Call 中的实参、提取实参中涉及的 variable name
GlobalVariableDefFinder: 获取所有的 intra-file dependency 变量名
"""

import ast
from typing import Dict, List, Any, Set

class ArgumentsAnalyser():
    def __init__(self, source_code: str):
        self.source_code = source_code

    def extract_arguments_info(self, call_node: ast.Call) -> Dict[str, List[Dict]]:
        """
        提取函数调用的参数信息，区分不同类型（Python 3.10+）
        """
        arguments_info = {
            'positional_args': [],
            'keyword_args': []
        }
        
        # 处理位置参数
        for i, arg in enumerate(call_node.args):
            arg_info = self.analyze_argument(arg, f'arg_{i}')
            arguments_info['positional_args'].append(arg_info)
        
        # 处理关键字参数
        for kw_arg in call_node.keywords:
            arg_info = self.analyze_argument(kw_arg.value, kw_arg.arg)
            arguments_info['keyword_args'].append({
                'keyword_name': kw_arg.arg,
                **arg_info
            })
        
        return arguments_info

    def analyze_argument(self, arg_node: ast.AST, arg_name: str = '') -> Dict[str, Any]:
        """
        分析单个参数节点，区分字符串、变量名等类型
        """    
        try:
            src = ast.get_source_segment(self.source_code, arg_node)
        except UnicodeDecodeError as e:
            src = ''
    
        arg_info = {
            'name': arg_name,
            'node_type': type(arg_node).__name__,
            'value_type': 'unknown',
            'value': None,
            'source': src,
            'is_string': False,
            'is_variable': False,
            'is_number': False,
            'is_boolean': False,
            'is_none': False,
            'is_literal': False,
            'is_expression': False
        }
        
        # 处理常量值
        if isinstance(arg_node, ast.Constant):
            arg_info['value'] = arg_node.value
            arg_info['value_type'] = type(arg_node.value).__name__
            
            if isinstance(arg_node.value, str):
                arg_info['is_string'] = True
                arg_info['is_literal'] = True
            elif isinstance(arg_node.value, (int, float, complex)):
                arg_info['is_number'] = True
                arg_info['is_literal'] = True
            elif isinstance(arg_node.value, bool):
                arg_info['is_boolean'] = True
                arg_info['is_literal'] = True
            elif arg_node.value is None:
                arg_info['is_none'] = True
                arg_info['is_literal'] = True
        
        # 处理变量名
        elif isinstance(arg_node, ast.Name):
            arg_info['value'] = arg_node.id
            arg_info['value_type'] = 'variable'
            arg_info['is_variable'] = True
        
        # 处理属性访问
        elif isinstance(arg_node, ast.Attribute):
            arg_info['value'] = ast.get_source_segment(self.source_code, arg_node)
            arg_info['value_type'] = 'attribute'
            arg_info['is_expression'] = True
        
        # 处理列表
        elif isinstance(arg_node, ast.List):
            elements = [self.analyze_argument(el, self.source_code) for el in arg_node.elts]
            arg_info['value'] = elements
            arg_info['value_type'] = 'list'
            arg_info['is_expression'] = True
        
        # 处理字典
        elif isinstance(arg_node, ast.Dict):
            dict_value = {}
            for key, value in zip(arg_node.keys, arg_node.values):
                key_info = self.analyze_argument(key, self.source_code) if key else {'value': None}
                value_info = self.analyze_argument(value, self.source_code)
                dict_value[key_info.get('value', 'None')] = value_info
            arg_info['value'] = dict_value
            arg_info['value_type'] = 'dict'
            arg_info['is_expression'] = True
        
        # 处理其他表达式
        else:
            arg_info['value'] = ast.get_source_segment(self.source_code, arg_node)
            arg_info['value_type'] = 'expression'
            arg_info['is_expression'] = True
        
        return arg_info

    def get_varnames_in_args(self, call_node: ast.Call, args: List = []) -> Set[str]:
        """获取实参中的所有变量名"""
        if not args: args = self.extract_arguments_info(call_node)
        todos = args.get('keyword_args', []) + args.get('positional_args', [])

        var_names = set()
        for item in todos:
            if item['value_type'] == 'variable':
                var_names.add(item['value'])
        return var_names

class GlobalVariableDefFinder(ast.NodeVisitor):
    """
    一个访问者，用于查找在模块全局作用域中定义的所有变量名。
    它会忽略函数和类内部定义的变量。
    """
    def __init__(self):
        super().__init__()
        self.defined_vars = set()

    def visit_Assign(self, node):

        for target in node.targets:
            if isinstance(target, ast.Name):
                self.defined_vars.add(target.id)
            elif isinstance(target, ast.Tuple):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        self.defined_vars.add(elt.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if isinstance(node.target, ast.Name):
            self.defined_vars.add(node.target.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.defined_vars.add(node.name)

    def visit_AsyncFunctionDef(self, node):
        self.defined_vars.add(node.name)

    def visit_ClassDef(self, node):
        self.defined_vars.add(node.name)

    def visit_For(self, node):
        if isinstance(node.target, ast.Name):
            self.defined_vars.add(node.target.id)
        elif isinstance(node.target, ast.Tuple):
            for elt in node.target.elts:
                if isinstance(elt, ast.Name):
                    self.defined_vars.add(elt.id)
        self.generic_visit(node)

    def visit_With(self, node):
        for item in node.items:
            if item.optional_vars:
                if isinstance(item.optional_vars, ast.Name):
                    self.defined_vars.add(item.optional_vars.id)
                elif isinstance(item.optional_vars, ast.Tuple):
                    for elt in item.optional_vars.elts:
                        if isinstance(elt, ast.Name):
                            self.defined_vars.add(elt.id)
        self.generic_visit(node)

    def visit_NamedExpr(self, node):
        if isinstance(node.target, ast.Name):
            self.defined_vars.add(node.target.id)
        self.generic_visit(node)

    """忽略 inter file dependencies"""
    def visit_Import(self, node): return
    def visit_ImportFrom(self, node): return

