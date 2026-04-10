from langchain_core.tools import tool
import ast
import operator
import math


ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

ALLOWED_FUNCTIONS = {
    'abs': abs,
    'round': round,
    'min': min,
    'max': max,
    'sqrt': math.sqrt,
    'sin': math.sin,
    'cos': math.cos,
    'tan': math.tan,
    'log': math.log,
    'log10': math.log10,
    'exp': math.exp,
    'floor': math.floor,
    'ceil': math.ceil,
}

ALLOWED_CONSTANTS = {
    'pi': math.pi,
    'e': math.e,
}


def _safe_eval(expression: str) -> float:
    """
    安全地计算数学表达式
    
    params:
        expression: 数学表达式字符串
    
    return:
        计算结果
    
    raises:
        ValueError: 如果表达式包含不允许的操作
    """
    try:
        tree = ast.parse(expression, mode='eval')
        
        def _eval(node):
            if isinstance(node, ast.Constant):
                return node.value
            elif isinstance(node, ast.Num):
                return node.n
            elif isinstance(node, ast.Name):
                if node.id in ALLOWED_CONSTANTS:
                    return ALLOWED_CONSTANTS[node.id]
                raise ValueError(f"未知的常量: {node.id}")
            elif isinstance(node, ast.BinOp):
                if type(node.op) not in ALLOWED_OPERATORS:
                    raise ValueError(f"不支持的操作符: {type(node.op).__name__}")
                left = _eval(node.left)
                right = _eval(node.right)
                return ALLOWED_OPERATORS[type(node.op)](left, right)
            elif isinstance(node, ast.UnaryOp):
                if type(node.op) not in ALLOWED_OPERATORS:
                    raise ValueError(f"不支持的操作符: {type(node.op).__name__}")
                operand = _eval(node.operand)
                return ALLOWED_OPERATORS[type(node.op)](operand)
            elif isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name):
                    raise ValueError("只允许调用简单函数")
                if node.func.id not in ALLOWED_FUNCTIONS:
                    raise ValueError(f"不支持的函数: {node.func.id}")
                args = [_eval(arg) for arg in node.args]
                return ALLOWED_FUNCTIONS[node.func.id](*args)
            else:
                raise ValueError(f"不支持的表达式类型: {type(node).__name__}")
        
        result = _eval(tree.body)
        return result
    
    except ZeroDivisionError:
        raise ValueError("除零错误")
    except Exception as e:
        raise ValueError(f"计算错误: {str(e)}")


@tool
def calculate(expression: str) -> str:
    """
    计算数学表达式
    
    params:
        expression: 数学表达式（支持加减乘除、幂运算、数学函数等）
    
    return:
        计算结果
    
    示例:
        - 基本运算: "2 + 3 * 4"
        - 幂运算: "2 ** 10"
        - 数学函数: "sqrt(16)", "sin(pi/2)"
        - 常量: "pi * 2", "e ** 2"
    """
    try:
        expression = expression.strip()
        
        if not expression:
            return "错误：表达式不能为空"
        
        result = _safe_eval(expression)
        
        if isinstance(result, float):
            if result.is_integer():
                result = int(result)
            else:
                result = round(result, 10)
        
        return f"计算结果：{expression} = {result}"
    
    except ValueError as e:
        return f"计算错误：{str(e)}"
    except Exception as e:
        return f"未知错误：{str(e)}"


@tool
def calculate_percentage(value: float, percentage: float) -> str:
    """
    计算百分比
    
    params:
        value: 基础数值
        percentage: 百分比（如 20 表示 20%）
    
    return:
        百分比计算结果
    
    示例:
        calculate_percentage(100, 20) -> 计算 100 的 20%
    """
    try:
        result = value * (percentage / 100)
        return f"{value} 的 {percentage}% = {result}"
    except Exception as e:
        return f"计算错误：{str(e)}"


@tool
def calculate_average(numbers: str) -> str:
    """
    计算平均值
    
    params:
        numbers: 数字列表，用逗号分隔（如 "1, 2, 3, 4, 5"）
    
    return:
        平均值
    
    示例:
        calculate_average("1, 2, 3, 4, 5") -> 计算 1,2,3,4,5 的平均值
    """
    try:
        num_list = [float(x.strip()) for x in numbers.split(',')]
        if not num_list:
            return "错误：数字列表不能为空"
        
        average = sum(num_list) / len(num_list)
        return f"{num_list} 的平均值 = {average}"
    except ValueError:
        return "错误：请输入有效的数字列表，用逗号分隔"
    except Exception as e:
        return f"计算错误：{str(e)}"
