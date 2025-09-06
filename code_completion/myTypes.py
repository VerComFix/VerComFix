from enum import Enum, auto

# 下面是和 API Stability Check 相关的类型定义
class APIShiftType(Enum):
    METHOD_NAME = "method_name"
    PARAMETERS  = "parameters"
    RETURN_TYPE = "return_type"

# 下面是和版本约束相关的类型定义
class VersionConstrainType(Enum):
    OMITTED       = "omitted"
    PINNED        = "pinned"
    RANGE         = "range"
    UNCONSTRAINED = "unconstrained"

def cstr_2_ctype(constrain_str):
    if constrain_str.startswith('=='):   return VersionConstrainType.PINNED
    elif constrain_str.startswith('~~'): return VersionConstrainType.UNCONSTRAINED
    else:                                return VersionConstrainType.RANGE

class VersionDetail:
    def __init__(self, version: str, version_type: VersionConstrainType):
        self.version = version
        self.type    = version_type
        return

class VersionConstrains:
    def __init__(self):
        self.data = {}
        return
    
    def add(self, version: str, version_type: VersionConstrainType):
        if version not in self.data:
            self.data[version] = VersionDetail(version, version_type)
        return
    
    def get(self, version: str) -> VersionDetail:
        return self.data.get(version, None)
    
class CompletionType(Enum):
    CR        = auto()
    BCR       = auto()
    UNCERTAIN = auto()
    OTHERS    = auto()
    EMPTY     = auto()
