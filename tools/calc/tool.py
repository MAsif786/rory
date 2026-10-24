"""Calculator: arithmetic, a few functions, and "15% of 200"."""
import ast
import math
import operator

from app.core.schemas import Input, UserError
from app.core.tool import Tool

tool = Tool("calc", title="Calculator", emoji="🧮", description="Do maths: 25*8, sqrt(144), 15% of 200")

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log10, "ln": math.log, "abs": abs,
         "round": round, "floor": math.floor, "ceil": math.ceil}
CONSTS = {"pi": math.pi, "e": math.e}
# strict patterns so ordinary sentences never look like maths: pure arithmetic that starts with a digit or "(",
# or an expression that uses a function and starts with a function, digit or "("
_FUNC = r"(?:sqrt|sin|cos|tan|log|ln|abs|round|floor|ceil)"
_PURE = r"(?=[\d(.])(?=.*[+*/^×÷%\-])[\d\s.+\-*/%^()×÷]{1,100}"
_WITH_FUNC = rf"(?=[\d(]|{_FUNC}\b)(?=.*\b{_FUNC}\b)(?=.*\d)[\w\s.+\-*/%^()×÷,]{{1,100}}"
EXPR = rf"(?:{_PURE}|{_WITH_FUNC})"
NUMBER = r"\d+(?:\.\d+)?"


def _eval(n):
    if isinstance(n, ast.Expression):
        return _eval(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.Name) and n.id in CONSTS:
        return CONSTS[n.id]
    if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
        return OPS[type(n.op)](_eval(n.operand))
    if isinstance(n, ast.BinOp) and type(n.op) in OPS:
        a, b = _eval(n.left), _eval(n.right)
        if isinstance(n.op, ast.Pow) and (abs(b) > 1000 or abs(a) > 1e6):
            raise UserError("🧮 That power is too big for me.")
        return OPS[type(n.op)](a, b)
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords:
        return FUNCS[n.func.id](*[_eval(a) for a in n.args])
    raise UserError("🧮 I only understand numbers, + - * / // % ** ( ) and sqrt/sin/cos/tan/log/ln/abs/round.")


def _fmt(result):
    if isinstance(result, float):
        result = round(result, 10)
        result = int(result) if result == int(result) and abs(result) < 1e15 else result
    return result


@tool.feature(
    "calc", description="Calculator", keywords=["calc", "calculate", "calculator"],
    phrases=["calc {expr}", "calculate {expr}", "compute {expr}", "what is {expr}", "what's {expr}", "whats {expr}",
             "how much is {expr}", "solve {expr}", "{expr}", "{expr} = ?", "{expr} ="],
    examples=["25*8", "what is 12 + 30", "sqrt(144)"],
    inputs={"expr": Input(required=True, pattern=EXPR, ask="🧮 What should I calculate? (e.g. *25*8*)")})
async def calc(ctx, expr):
    try:
        result = _eval(ast.parse(expr.replace("^", "**").replace("×", "*").replace("÷", "/"), mode="eval"))
    except UserError:
        raise
    except ZeroDivisionError:
        raise UserError("🧮 Division by zero. Nice try.") from None
    except (SyntaxError, ValueError, TypeError, OverflowError):
        raise UserError("🧮 I couldn't compute that.") from None
    return f"🧮 {expr} = *{_fmt(result)}*"


@tool.feature(
    "percent", description="Percentage of a number (15% of 200)",
    phrases=["{pct}% of {n}", "{pct} percent of {n}", "{pct} per cent of {n}", "what is {pct}% of {n}", "what is {pct} percent of {n}"],
    examples=["15% of 200", "what is 20 percent of 50"],
    inputs={"pct": Input(type="float", required=True, pattern=NUMBER), "n": Input(type="float", required=True, pattern=NUMBER)})
async def percent(ctx, pct, n):
    return f"🧮 {pct:g}% of {n:g} = *{_fmt(pct / 100 * n)}*"
