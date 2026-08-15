# """
# formulas.py — deterministic formula engine for CriterionEvidence.

# A criterion data-label (header) becomes a computed field by carrying a formula:

#     {"key": "annual_cost", "label": "Annual cost", "type": "number",
#      "formula": "unit_cost * quantity * coverage", "round": 4}

# References
# ----------
# * bare name            -> another field on the SAME evidence row
#                           (raw input OR another computed field on that row).
#                           A formula that references its OWN key reads the row's
#                           raw (pre-compute) input, not its own computed slot, so
#                           self-derived fields (coverage -> coverage%) are allowed
#                           and are NOT treated as circular.
# * ref("Crit", "key"[, default])
#                        -> value of `key` on the SAME target's row for another
#                           criterion. Missing target / field falls back to
#                           `default` (0).

# Arithmetic only, no eval, no I/O, whitelisted functions — stays on the
# deterministic side of the model wall and is therefore auditable.
# """
# import ast
# import math
# import operator


# class FormulaError(Exception):
#     pass


# _BIN = {
#     ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
#     ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
#     ast.Mod: operator.mod, ast.Pow: operator.pow,
# }
# _UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
# _CMP = {
#     ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
#     ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
# }
# _FUNCS = {
#     "min": lambda *a: min(a), "max": lambda *a: max(a),
#     "abs": lambda x: abs(x), "round": lambda x, n=0: round(float(x), int(n)),
#     "sqrt": lambda x: math.sqrt(x), "floor": lambda x: float(math.floor(x)),
#     "ceil": lambda x: float(math.ceil(x)), "pow": lambda a, b: float(a) ** float(b),
#     "log": lambda x, b=math.e: math.log(x, b), "log10": lambda x: math.log10(x),
#     "exp": lambda x: math.exp(x), "sum": lambda *a: float(sum(a)),
#     "iif": lambda c, a, b: a if c else b,
# }
# DEFAULT_ROUND = 4


# def _num(v):
#     if isinstance(v, bool):
#         return 1.0 if v else 0.0
#     if isinstance(v, (int, float)):
#         return float(v)
#     if v is None:
#         raise FormulaError("value is empty")
#     s = str(v).strip().replace(",", "")
#     if s == "":
#         raise FormulaError("value is empty")
#     try:
#         return float(s)
#     except ValueError:
#         raise FormulaError(f'"{v}" is not a number')


# def _eval(node, resolve, ref_func):
#     if isinstance(node, ast.Constant):
#         if isinstance(node.value, bool):
#             return 1.0 if node.value else 0.0
#         if isinstance(node.value, (int, float)):
#             return float(node.value)
#         if isinstance(node.value, str):
#             return node.value
#         raise FormulaError("unsupported literal")
#     if isinstance(node, ast.Name):
#         return resolve(node.id)
#     if isinstance(node, ast.BinOp):
#         op = _BIN.get(type(node.op))
#         if not op:
#             raise FormulaError("unsupported operator")
#         return op(_eval(node.left, resolve, ref_func), _eval(node.right, resolve, ref_func))
#     if isinstance(node, ast.UnaryOp):
#         op = _UNARY.get(type(node.op))
#         if not op:
#             raise FormulaError("unsupported unary operator")
#         return op(_eval(node.operand, resolve, ref_func))
#     if isinstance(node, ast.BoolOp):
#         vals = [_eval(v, resolve, ref_func) for v in node.values]
#         r = vals[0]
#         for v in vals[1:]:
#             r = (r and v) if isinstance(node.op, ast.And) else (r or v)
#         return r
#     if isinstance(node, ast.Compare):
#         left = _eval(node.left, resolve, ref_func)
#         for op, comp in zip(node.ops, node.comparators):
#             right = _eval(comp, resolve, ref_func)
#             f = _CMP.get(type(op))
#             if not f:
#                 raise FormulaError("unsupported comparison")
#             if not f(left, right):
#                 return 0.0
#             left = right
#         return 1.0
#     if isinstance(node, ast.IfExp):
#         return (_eval(node.body, resolve, ref_func)
#                 if _eval(node.test, resolve, ref_func)
#                 else _eval(node.orelse, resolve, ref_func))
#     if isinstance(node, ast.Call):
#         if not isinstance(node.func, ast.Name):
#             raise FormulaError("unsupported call")
#         args = [_eval(a, resolve, ref_func) for a in node.args]
#         if node.func.id == "ref":
#             return ref_func(*args)
#         fn = _FUNCS.get(node.func.id)
#         if not fn:
#             raise FormulaError(f'unknown function "{node.func.id}"')
#         return fn(*args)
#     raise FormulaError("unsupported expression")


# def _name_ids(tree):
#     return {n.id for n in ast.walk(tree)
#             if isinstance(n, ast.Name) and n.id not in _FUNCS and n.id != "ref"}


# def _toposort(deps):
#     order, temp, perm, cyc = [], set(), set(), set()

#     def visit(n):
#         if n in perm:
#             return
#         if n in temp:
#             cyc.add(n)
#             return
#         temp.add(n)
#         for m in deps.get(n, ()):
#             if m in deps:
#                 visit(m)
#         temp.discard(n)
#         perm.add(n)
#         order.append(n)

#     for n in deps:
#         visit(n)
#     return order, cyc


# def field_refs(expr):
#     try:
#         return _name_ids(ast.parse(expr, mode="eval"))
#     except SyntaxError:
#         return set()


# def criterion_refs(expr):
#     try:
#         tree = ast.parse(expr, mode="eval")
#     except SyntaxError:
#         return set()
#     out = set()
#     for n in ast.walk(tree):
#         if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "ref"
#                 and n.args and isinstance(n.args[0], ast.Constant)
#                 and isinstance(n.args[0].value, str)):
#             out.add(n.args[0].value)
#     return out


# def validate_formula(expr):
#     """None if safe & parseable, else an error message."""
#     if not (expr or "").strip():
#         return "empty formula"
#     try:
#         tree = ast.parse(expr, mode="eval")
#     except SyntaxError as e:
#         return f"syntax error: {e.msg}"
#     banned = (ast.Attribute, ast.Subscript, ast.Lambda, ast.Dict, ast.List,
#               ast.Set, ast.Starred, ast.Await, ast.Yield, ast.NamedExpr)
#     for n in ast.walk(tree):
#         if isinstance(n, banned):
#             return "unsupported syntax"
#         if isinstance(n, ast.Call) and not isinstance(n.func, ast.Name):
#             return "unsupported call"
#     return None


# def compute_row(headers, data, ref_func, default_round=DEFAULT_ROUND):
#     """
#     Compute every formula field on one evidence row, in local dependency order.
#     Returns (new_data, errors). Formula keys are always overwritten; a field
#     that errors is set to None and reported in `errors`.

#     A formula referencing its own key resolves from `original` (the pre-compute
#     row data), so self-derived fields are permitted and the self-edge is dropped
#     from the dependency graph rather than flagged as circular.
#     """
#     fheaders = {h["key"]: h for h in headers if isinstance(h, dict) and h.get("formula")}
#     fkeys = set(fheaders)

#     deps, parsed = {}, {}
#     for k, h in fheaders.items():
#         try:
#             tree = ast.parse(h["formula"], mode="eval")
#             parsed[k] = tree
#             deps[k] = (_name_ids(tree) & fkeys) - {k}       # formula→formula edges, minus self
#         except SyntaxError as e:
#             parsed[k] = e
#             deps[k] = set()

#     order, cyc = _toposort(deps)
#     result = dict(data or {})
#     original = dict(data or {})
#     errors = {}

#     for k in order:
#         if k in cyc:
#             errors[k] = "circular reference"
#             result[k] = None
#             continue
#         h = fheaders[k]
#         tree = parsed[k]
#         if isinstance(tree, SyntaxError):
#             errors[k] = f"syntax error: {tree.msg}"
#             result[k] = None
#             continue
#         rnd = h.get("round")
#         rnd = default_round if rnd in (None, "") else int(rnd)

#         def resolve(name, _r=result, _self=k, _orig=original):
#             if name == _self:
#                 return _num(_orig.get(name)) if name in _orig else 0.0
#             if name in _r:
#                 return _num(_r[name])
#             raise FormulaError(f'unknown field "{name}"')

#         try:
#             val = _eval(tree.body, resolve, ref_func)
#             result[k] = round(float(val), rnd)
#         except FormulaError as e:
#             errors[k] = str(e); result[k] = None
#         except ZeroDivisionError:
#             errors[k] = "division by zero"; result[k] = None
#         except Exception as e: 
#             errors[k] = f"error: {e}"; result[k] = None

#     return result, errors


"""
formulas.py — deterministic formula engine for CriterionEvidence.

A criterion data-label (header) becomes a computed field by carrying a formula:

    {"key": "annual_cost", "label": "Annual cost", "type": "number",
     "formula": "unit_cost * quantity * coverage", "round": 4}

References
----------
* bare name            -> another field on the SAME evidence row
                          (raw input OR another computed field on that row).
                          A formula that references its OWN key reads the row's
                          raw (pre-compute) input, not its own computed slot, so
                          self-derived fields (coverage -> coverage%) are allowed
                          and are NOT treated as circular.

                          Field keys may begin with a digit (e.g.
                          5_year_projections); such bare names are masked to a
                          valid identifier for parsing, then un-masked on the
                          tree so the rest of the engine sees the real key.
* ref("Crit", "key"[, default])
                       -> value of `key` on the SAME target's row for another
                          criterion. Missing target / field falls back to
                          `default` (0).

No-data discipline
------------------
An empty input or a non-finite result (NaN / ±Inf) is preserved as no-data
(None -> "—"), never coerced to 0. Rounding is only applied to finite values.

Arithmetic only, no eval, no I/O, whitelisted functions — stays on the
deterministic side of the model wall and is therefore auditable.
"""
import ast
import math
import operator


class FormulaError(Exception):
    pass


_BIN = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_CMP = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
    ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
}
_FUNCS = {
    "min": lambda *a: min(a), "max": lambda *a: max(a),
    "abs": lambda x: abs(x), "round": lambda x, n=0: round(float(x), int(n)),
    "sqrt": lambda x: math.sqrt(x), "floor": lambda x: float(math.floor(x)),
    "ceil": lambda x: float(math.ceil(x)), "pow": lambda a, b: float(a) ** float(b),
    "log": lambda x, b=math.e: math.log(x, b), "log10": lambda x: math.log10(x),
    "exp": lambda x: math.exp(x), "sum": lambda *a: float(sum(a)),
    "iif": lambda c, a, b: a if c else b,
}
DEFAULT_ROUND = 4


def _num(v):
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        raise FormulaError("value is empty")
    s = str(v).strip().replace(",", "")
    if s == "":
        raise FormulaError("value is empty")
    try:
        return float(s)
    except ValueError:
        raise FormulaError(f'"{v}" is not a number')


# ── digit-led identifier support ───────────────────────────────────────────
_ALIAS_PREFIX = "_f_"


def _mask_numeric_idents(expr):
    """Rewrite bare identifiers that begin with a digit (e.g. 5_year_projections)
    into valid Python identifiers so ast.parse accepts them, mirroring the JS
    tokenizer. Numbers (incl. 1e-5) and string literals are left untouched.
    Returns (masked_expr, {alias: original})."""
    out, alias = [], {}
    i, n = 0, len(expr)
    while i < n:
        c = expr[i]
        if c in "\"'":                                     # string literal — copy verbatim
            j = i + 1
            while j < n and expr[j] != c:
                j += 1
            out.append(expr[i:min(j + 1, n)]); i = j + 1; continue
        if c.isdigit() or (c == "." and i + 1 < n and expr[i + 1].isdigit()):
            j = i
            while j < n and (expr[j].isdigit() or expr[j] == "."):
                j += 1
            # exponent notation: 1e-5, 2.3E+4, 6e9
            if j < n and expr[j] in "eE" and (
                (j + 1 < n and expr[j + 1].isdigit())
                or (j + 2 < n and expr[j + 1] in "+-" and expr[j + 2].isdigit())
            ):
                j += 1
                if j < n and expr[j] in "+-":
                    j += 1
                while j < n and expr[j].isdigit():
                    j += 1
            if j < n and (expr[j].isalpha() or expr[j] == "_"):   # digit-led identifier
                k = i
                while k < n and (expr[k].isalnum() or expr[k] == "_"):
                    k += 1
                name = expr[i:k]
                a = _ALIAS_PREFIX + name
                alias[a] = name
                out.append(a); i = k; continue
            out.append(expr[i:j]); i = j; continue
        out.append(c); i += 1
    return "".join(out), alias


def _parse_formula(expr, mode="eval"):
    """ast.parse with digit-led field keys masked, then un-masked on the tree
    so the rest of the engine sees the real key names. Raises SyntaxError just
    like ast.parse, so existing except-guards still catch genuine errors."""
    masked, alias = _mask_numeric_idents(expr)
    tree = ast.parse(masked, mode=mode)
    if alias:
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in alias:
                node.id = alias[node.id]
    return tree


def _eval(node, resolve, ref_func):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return 1.0 if node.value else 0.0
        if isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node.value, str):
            return node.value
        raise FormulaError("unsupported literal")
    if isinstance(node, ast.Name):
        return resolve(node.id)
    if isinstance(node, ast.BinOp):
        op = _BIN.get(type(node.op))
        if not op:
            raise FormulaError("unsupported operator")
        return op(_eval(node.left, resolve, ref_func), _eval(node.right, resolve, ref_func))
    if isinstance(node, ast.UnaryOp):
        op = _UNARY.get(type(node.op))
        if not op:
            raise FormulaError("unsupported unary operator")
        return op(_eval(node.operand, resolve, ref_func))
    if isinstance(node, ast.BoolOp):
        vals = [_eval(v, resolve, ref_func) for v in node.values]
        r = vals[0]
        for v in vals[1:]:
            r = (r and v) if isinstance(node.op, ast.And) else (r or v)
        return r
    if isinstance(node, ast.Compare):
        left = _eval(node.left, resolve, ref_func)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, resolve, ref_func)
            f = _CMP.get(type(op))
            if not f:
                raise FormulaError("unsupported comparison")
            if not f(left, right):
                return 0.0
            left = right
        return 1.0
    if isinstance(node, ast.IfExp):
        return (_eval(node.body, resolve, ref_func)
                if _eval(node.test, resolve, ref_func)
                else _eval(node.orelse, resolve, ref_func))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FormulaError("unsupported call")
        args = [_eval(a, resolve, ref_func) for a in node.args]
        if node.func.id == "ref":
            return ref_func(*args)
        fn = _FUNCS.get(node.func.id)
        if not fn:
            raise FormulaError(f'unknown function "{node.func.id}"')
        return fn(*args)
    raise FormulaError("unsupported expression")


def _name_ids(tree):
    return {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id not in _FUNCS and n.id != "ref"}


def _toposort(deps):
    order, temp, perm, cyc = [], set(), set(), set()

    def visit(n):
        if n in perm:
            return
        if n in temp:
            cyc.add(n)
            return
        temp.add(n)
        for m in deps.get(n, ()):
            if m in deps:
                visit(m)
        temp.discard(n)
        perm.add(n)
        order.append(n)

    for n in deps:
        visit(n)
    return order, cyc


def field_refs(expr):
    try:
        return _name_ids(_parse_formula(expr))
    except SyntaxError:
        return set()


def criterion_refs(expr):
    try:
        tree = _parse_formula(expr)
    except SyntaxError:
        return set()
    out = set()
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "ref"
                and n.args and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)):
            out.add(n.args[0].value)
    return out


def validate_formula(expr):
    """None if safe & parseable, else an error message."""
    if not (expr or "").strip():
        return "empty formula"
    try:
        tree = _parse_formula(expr)
    except SyntaxError as e:
        return f"syntax error: {e.msg}"
    banned = (ast.Attribute, ast.Subscript, ast.Lambda, ast.Dict, ast.List,
              ast.Set, ast.Starred, ast.Await, ast.Yield, ast.NamedExpr)
    for n in ast.walk(tree):
        if isinstance(n, banned):
            return "unsupported syntax"
        if isinstance(n, ast.Call) and not isinstance(n.func, ast.Name):
            return "unsupported call"
    return None


def compute_row(headers, data, ref_func, default_round=DEFAULT_ROUND):
    """
    Compute every formula field on one evidence row, in local dependency order.
    Returns (new_data, errors). Formula keys are always overwritten; a field
    that errors — including a non-finite (NaN / ±Inf) result — is set to None
    and reported in `errors`. None means "no data" ("—"), and is never coerced
    to 0.

    A formula referencing its own key resolves from `original` (the pre-compute
    row data), so self-derived fields are permitted and the self-edge is dropped
    from the dependency graph rather than flagged as circular.
    """
    fheaders = {h["key"]: h for h in headers if isinstance(h, dict) and h.get("formula")}
    fkeys = set(fheaders)

    deps, parsed = {}, {}
    for k, h in fheaders.items():
        try:
            tree = _parse_formula(h["formula"])
            parsed[k] = tree
            deps[k] = (_name_ids(tree) & fkeys) - {k}       # formula→formula edges, minus self
        except SyntaxError as e:
            parsed[k] = e
            deps[k] = set()

    order, cyc = _toposort(deps)
    result = dict(data or {})
    original = dict(data or {})
    errors = {}

    for k in order:
        if k in cyc:
            errors[k] = "circular reference"
            result[k] = None
            continue
        h = fheaders[k]
        tree = parsed[k]
        if isinstance(tree, SyntaxError):
            errors[k] = f"syntax error: {tree.msg}"
            result[k] = None
            continue
        rnd = h.get("round")
        rnd = default_round if rnd in (None, "") else int(rnd)

        def resolve(name, _r=result, _self=k, _orig=original):
            if name == _self:
                return _num(_orig.get(name)) if name in _orig else 0.0
            if name in _r:
                return _num(_r[name])
            raise FormulaError(f'unknown field "{name}"')

        try:
            val = float(_eval(tree.body, resolve, ref_func))
            if not math.isfinite(val):        # NaN / ±Inf → no-data ("—"), never 0
                errors[k] = "not a number"; result[k] = None
            else:
                result[k] = round(val, rnd)
        except FormulaError as e:
            errors[k] = str(e); result[k] = None
        except ZeroDivisionError:
            errors[k] = "division by zero"; result[k] = None
        except Exception as e:
            errors[k] = f"error: {e}"; result[k] = None

    return result, errors