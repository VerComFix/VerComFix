import ast, re, sys, os

from myTypes import CompletionType
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from task_construction.arg_validity_checker import ArgumentsAnalyser

class CodeHandler:
    @staticmethod
    def clean_gpt_response(response: str) -> str:
        match = re.search(r'```.*?\n(.*?)(?:```|$)', response, re.DOTALL)
        if match: return match.group(1).strip()
        else:     return response

    @staticmethod
    def clean_comments(code: str) -> str:
        inline_comment_pattern = r"(?<!#[^\'\"])(#.*)$"
        lines = []
        for line in  code.splitlines():
            if not line.strip().startswith("#"):
                lines.append(re.sub(inline_comment_pattern, '', line).rstrip())
    
        if lines and lines[0].strip() == '.': lines = lines[1:]
   
        return "\n".join(lines)

    @staticmethod
    def get_first_statement(code: str, remove_space: bool=False) -> str:
        def _unclosed(_stmt:str):
            if len(_stmt) == 0:                     return True
            
            _stmt = _stmt.splitlines()[-1]
            if _stmt.lstrip().startswith('@'):      return True

            if _stmt.count("(") > _stmt.count(")"): return True
            if _stmt.count("[") > _stmt.count("]"): return True
            if _stmt.count("{") > _stmt.count("}"): return True
            if _stmt.rstrip().endswith("\\"):       return True
            
            return False
        
        def _normalize(_line:str):
            if _line.lstrip().startswith('@'): return _line.lstrip()+'\n'
            _line = _line.strip().rstrip(" \\")     # 合并换行
            _line = re.sub(r"\s+", "", _line) if remove_space else re.sub(r"\s+", " ", _line) # 连续空格
            return _line

        lines = code.splitlines()

        if lines and lines[0].strip() == '.': lines.pop(0) 

        try:
            stmt = _normalize(lines.pop(0))
        except IndexError: # 只有注释，没有内容
            return ''
        while _unclosed(stmt) and lines: stmt += _normalize(lines.pop(0))

        return stmt
    
    @staticmethod
    def get_first_function(code: str) -> str | None:
        lines = code.splitlines()
        # 去掉函数定义前的内容
        while lines and not (
            lines[0].lstrip().startswith("def ") or lines[0].lstrip().startswith("async def")
        ): lines.pop(0)

        # 没有函数定义
        if not lines: return  None

        indent = len(re.search("^\s*", lines[0]).group(0))
        func = "\n".join(lines)
        func = re.split(r"\n {0,%d}[^\s#]" % indent, func, flags=re.M|re.S)[0]
        return func
    
def has_function_call(code_line: str):
    """使用 AST 分析判断代码行是否包含函数调用"""
    try:
        tree = ast.parse(code_line)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                return True
        return False
    except SyntaxError as e:
        if 'positional argument follows keyword argument' in str(e):
            return CompletionType.BCR
        return False

def extract_first_function_call(code_line):
    pattern = r'''
        (?:^|[^a-zA-Z0-9_\.])      # 前面不是字母数字下划线或点（或者是行首）
        (                           # 开始捕获组
            (?:                     # 非捕获组：匹配属性访问链
                [a-zA-Z_][a-zA-Z0-9_]*  # 标识符
                (?:\s*\.\s*[a-zA-Z_][a-zA-Z0-9_]*)*  # 可选的 .属性 链
            )
            \s*                     # 可选空白
            \(                      # 左括号
        )                           # 结束捕获组
    '''
    
    match = re.search(pattern, code_line, re.VERBOSE)
    return match.group(1)[:-1] if match else None

def extract_outermost_function_call(code_line):
    """
    提取一行代码中最外层的函数调用
    返回调用字符串和相关信息
    """
    def find_outermost_call(node):
        """递归查找最外层的函数调用"""
        if isinstance(node, ast.Module):
            if node.body:
                return find_outermost_call(node.body[0])
            return None
        
        elif isinstance(node, ast.Expr):
            return find_outermost_call(node.value)
        
        elif isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call):
                return node.value
            return find_outermost_call(node.value)
        
        elif isinstance(node, ast.AugAssign):
            return find_outermost_call(node.value)
        
        elif isinstance(node, ast.Return):
            return find_outermost_call(node.value)
        
        elif isinstance(node, ast.Call):
            return node
        
        for child in ast.iter_child_nodes(node):
            result = find_outermost_call(child)
            if result:
                return result
        
        return None

    def extract_function_name(func_node):
        """提取函数名称"""
        if isinstance(func_node, ast.Name):
            return func_node.id
        elif isinstance(func_node, ast.Attribute):
            if isinstance(func_node.value, ast.Name):
                return f"{func_node.value.id}.{func_node.attr}"
            else:
                return extract_nested_attribute(func_node)
        else:
            return "unknown"

    def extract_nested_attribute(node):
        """提取嵌套属性访问链"""
        if isinstance(node, ast.Attribute):
            prefix = extract_nested_attribute(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        elif isinstance(node, ast.Name):
            return node.id
        else:
            return "expression"

    try:
        tree = ast.parse(code_line)
        outermost_call = find_outermost_call(tree)
        
        if outermost_call: # 提取调用信息
            return \
                ast.unparse(outermost_call),\
                extract_function_name(outermost_call.func),\
                outermost_call
        return None
        
    except SyntaxError:
        return None

def analyze_GT_signature(signature):
    fqn, param_names, has_return = signature
    param_names = set(param_names)
    param_names.discard('self')
    return {
        'has_variable_args':    True if param_names & set(['args', 'kwargs']) else False,
        'optional_param_names': set(),
        'valid_keywords':       param_names,
        'has_return':           has_return,
        'return_type':          None
    }

def get_completion_type(
    gt_signature: tuple, 
    stmt: str, pred_FQN: str, gt_FQN: str, 
    is_line: bool=True,
):

    if not stmt: return CompletionType.EMPTY

    if not has_function_call(stmt):
        return CompletionType.OTHERS, 'No Function Call'
    
    try:
        call_string, _, pred_call_node = extract_outermost_function_call(stmt)
    except Exception as e:
        call_string, pred_call_node = '', None
    
    signature_info = analyze_GT_signature(gt_signature)
    if pred_FQN == gt_FQN:
        has_variable_args = signature_info['has_variable_args']
        if has_variable_args:
            return CompletionType.UNCERTAIN, 'have variable args'

        # arg count
        analyzer = ArgumentsAnalyser(call_string)
        try:
            pred_args = analyzer.extract_arguments_info(pred_call_node)
        except Exception:
            return CompletionType.UNCERTAIN, 'Cant not parse file'

        n_params = len(signature_info['valid_keywords'])
        n_positional, n_keywords = len(pred_args.get('positional_args', [])), len(pred_args.get('keyword_args', []))
        if (n_positional + n_keywords) > n_params:
            return CompletionType.BCR, 'Argument Count Error'

        optional_param_names = signature_info['optional_param_names']
        keyword_arg_names = set([item['keyword_name'] for item in pred_args.get('keyword_args', [])])
        n_keyword_required = len(keyword_arg_names - optional_param_names)
        if (n_keyword_required + n_positional) < (n_params - len(optional_param_names)):
            return CompletionType.BCR, 'Argument Count Error'
        
        valid_keywords = signature_info['valid_keywords']
        if len(keyword_arg_names - valid_keywords) > 0:
            return CompletionType.BCR, 'Invalid Keyword'
    
        if not is_line:
            is_return_val_match = True
            if not is_return_val_match:
                return CompletionType.BCR, 'Return Value Mismatch'
    else:
        is_in_knowledge = True
        if not is_in_knowledge:
            return CompletionType.OTHERS, 'Unkown Method'
        else:
            return CompletionType.BCR, 'Method Name Mismatch'
    return CompletionType.CR, ''

def get_cleaned_func(code_text: str) -> list:
    def is_balanced(code: str) -> bool:
        stack = []
        bracket_pairs = {'(': ')', '[': ']', '{': '}'}
        
        for char in code:
            if char in bracket_pairs:
                stack.append(char)
            elif char in bracket_pairs.values():
                if not stack or bracket_pairs[stack.pop()] != char:
                    return False
        return len(stack) == 0
        
    statements = []
    current_statement = []
    lines = code_text.split('\n')
    
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        
        if not stripped_line or stripped_line.startswith('#'):
            continue
            
        current_statement.append(line)
        current_code = ' '.join(current_statement)
        
        try:
            ast.parse(current_code)
            statements.append(current_code)
            current_statement = []
        except (SyntaxError, IndentationError):
            if (stripped_line.startswith(('def ', 'class ', 'if ', 'for ', 'while ', 'with ', 'try:', 'except ', 'finally:')) or
                stripped_line.endswith((':', '\\')) or
                any(stripped_line.startswith(keyword) for keyword in ['async def', 'async for', 'async with'])):
                continue
            else:
                if is_balanced(current_code):
                    statements.append(current_code)
                    current_statement = []
    
    if current_statement:
        last_line = ' '.join(current_statement)
        try:
            ast.parse('\n'.join(current_statement))
            statements.append(last_line)
        except SyntaxError:
            bracket_index = last_line.find('(')
            if bracket_index != -1:
                statements.append(f'{last_line[:bracket_index + 1]})')
        
    return '\n'.join(statements)

