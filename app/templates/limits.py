"""A Jinja2 sandbox that bounds the work and the memory a template can cause.

Jinja's sandbox stops a template from reaching Python internals, not from burning CPU or memory: loops and macro
recursion multiply, strings double, and `range`, `*` and `**` take arbitrary sizes. Everything here is deterministic
(no signals, threads or timers), so it behaves the same in validation and in requests:

- one work budget per render, charged for loop iterations, calls, filters, comparisons and slices, by the nested size
  of what they are given and the size of what they produce;
- collections and strings above `max_value_size` and renders above `max_output_size` are refused, as are integers
  wider than `MAX_BITS`, huge sizes handed to the functions that pad or repeat, and replacements that would blow up;
- constructs that multiply work without being needed for subscriptions are refused when the template is compiled.

Memory is only bounded per value, not in total; a container memory limit remains the backstop.
"""

import contextvars
import functools
import re
from collections.abc import Callable, Mapping

from jinja2 import nodes
from jinja2.exceptions import TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment, SecurityError
from jinja2.visitor import NodeTransformer

# A loop iteration or a call costs about as much as touching eight items of a collection.
ITERATION_COST = CALL_COST = 8
SIZED = (str, bytes, list, tuple, dict, set, frozenset)
FORBIDDEN = {
    nodes.Import: "import",
    nodes.FromImport: "import",
    nodes.Include: "include",
    nodes.Extends: "extends",
    nodes.Block: "block",
    nodes.CallBlock: "call blocks",
}
# The numbers that size a result in a format string: `%-10.5s` and `{:>10.5}`.
# `*` takes the number from the arguments, and a nested field (`{:{}}`) does too, so neither can be checked here.
# The patterns are written to match in linear time: no optional part can start where another one stops.
PERCENT_SPEC = re.compile(r"%(?:\([^)%]*\))?[-#0 +]*(\d+|\*)?(?:\.(\d+|\*)?)?")
FIELD_SPEC = re.compile(r"\{[^{}:]*:([^{}]*)\}")
NESTED_FIELD = re.compile(r"\{[^{}:]*:[^{}]*\{")
DIGITS = re.compile(r"\d+")

# Integers are capped by width, which keeps any arithmetic on them cheap while leaving room for timestamps and byte
# counts. The functions that turn a number into a size are named, and are given at most `max_value_size`.
MAX_BITS = 64
SIZING = frozenset({"center", "ljust", "rjust", "zfill", "expandtabs", "indent", "to_bytes"})
# Filters that cost more than their input's size suggests, as a multiple of it (the yaml dumper is pure Python).
FILTER_WEIGHT = {"yaml": 50}

# Filters that run in Python cost about 0.3 µs per unit: roughly one per list item or four per string character
# (measured on 100k-item inputs: sort ~120k units, wordwrap ~43k, urlize ~23k; the rest run in C and cost less).
# Lists are charged by their items wherever they are passed; text, which weight() prices much lower, is charged here.
TEXT_CHARS_PER_UNIT = 4

# Remaining work and emitted characters of the render in progress. Without a default, a render that skipped `render_limited` fails loudly.
_remaining: contextvars.ContextVar[list[int]] = contextvars.ContextVar("template_work_remaining")


def _internal(func: Callable) -> Callable:
    """Marks the hooks the rewritten template calls itself, which must not be charged as calls."""
    func._internal = True  # type: ignore[attr-defined]
    return func


def _hook(name: str, *args: nodes.Expr) -> nodes.Call:
    # EnvironmentAttribute cannot be shadowed by a template variable, unlike a Name.
    return nodes.Call(nodes.EnvironmentAttribute(name), list(args), [], None, None)


class _Rewrite(NodeTransformer):
    def visit_For(self, node: nodes.For) -> nodes.For:
        if node.recursive:
            raise TemplateSyntaxError("recursive loops are not allowed in templates", node.lineno)
        node = self.generic_visit(node)
        node.iter = _hook("limit_iterable", node.iter)
        return node

    def _guard(self, node: nodes.Expr) -> nodes.Call:
        return _hook("guard", self.generic_visit(node))

    # The operations that build bigger values out of the ones they are given.
    visit_Concat = visit_Add = visit_Mul = visit_Mod = visit_Pow = _guard

    def visit_Getitem(self, node: nodes.Getitem) -> nodes.Expr:
        node = self.generic_visit(node)
        return _hook("guard", node) if isinstance(node.arg, nodes.Slice) else node

    def visit_Compare(self, node: nodes.Compare) -> nodes.Compare:
        # `in` and `==` walk what they compare.
        node = self.generic_visit(node)
        node.expr = _hook("charge_operand", node.expr)
        for operand in node.ops:
            operand.expr = _hook("charge_operand", operand.expr)
        return node


class LimitedSandboxEnvironment(SandboxedEnvironment):
    # Also stops Jinja from folding these on constants at compile time, before any limit applies.
    intercepted_binops = frozenset({"*", "**", "%"})

    def __init__(self, *, budget: int, max_value_size: int, max_output_size: int, **kwargs):
        super().__init__(**kwargs)
        self.budget = budget
        self.max_value_size = max_value_size
        self.max_output_size = max_output_size
        del self.globals["lipsum"]
        self.globals["range"] = self._range
        # markupsafe's striptags cuts tags out of the string one by one: quadratic in the number of tags.
        self.filters.pop("striptags", None)
        self.finalize = self._count_output
        self.add_filters(dict(self.filters))
        # Jinja tests (`is in`, `is sameas`, ...) are plain callables too, found through a separate dict that
        # add_filters doesn't touch; `is in` walks a sequence exactly like the `in` operator, so it needs the
        # same charge or it bypasses visit_Compare's charge_operand entirely.
        for name, func in dict(self.tests).items():
            self.tests[name] = self._limited_filter(name, func)

    def add_filters(self, filters: Mapping[str, Callable]) -> None:
        for name, func in filters.items():
            self.filters[name] = self._limited_filter(name, func)

    # -- accounting

    def charge(self, units: int) -> None:
        remaining = _remaining.get()
        remaining[0] -= units
        if remaining[0] < 0:
            raise SecurityError(f"template is too heavy: it exceeds the limit of {self.budget:,} units of work")

    def _count_output(self, value):
        """Counts everything `{{ }}` emits, also inside `{% set %}` blocks and macros, which render_limited
        does not see because their output is joined before it reaches the top level."""
        if isinstance(value, SIZED):
            state = _remaining.get()
            state[1] += len(value)
            if state[1] > self.max_output_size:
                raise SecurityError(f"output is too large: more than {self.max_output_size:,} characters")
        return value

    def charge_text(self, value: object) -> None:
        if isinstance(value, str | bytes):
            self.charge(len(value) // TEXT_CHARS_PER_UNIT)

    def weight(self, value: object, limit: int) -> int:
        """Nested size of `value`, giving up once it exceeds `limit`. Strings count by length."""
        total, stack = 0, [value]
        while stack and total <= limit:
            item = stack.pop()
            if isinstance(item, str | bytes):
                total += 1 + len(item) // 64
            elif isinstance(item, dict):
                total += len(item)
                stack.extend(item.keys())
                stack.extend(item.values())
            elif isinstance(item, list | tuple | set | frozenset):
                total += len(item)
                stack.extend(item)
            else:
                total += 1
        return total

    def charge_value(self, value: object) -> None:
        if isinstance(value, SIZED):
            self.charge(self.weight(value, _remaining.get()[0]))

    def check_arguments(self, args: tuple, kwargs: Mapping, name: str | None = None) -> None:
        for key, arg in (*((None, arg) for arg in args), *kwargs.items()):
            if key in ("_loop_vars", "_block_vars"):  # passed by Jinja itself
                continue
            if (
                isinstance(arg, int)
                and not isinstance(arg, bool)
                and (arg.bit_length() > MAX_BITS or (name in SIZING and abs(arg) > self.max_value_size))
            ):
                raise SecurityError(f"number {arg} is too large")
            self.charge_value(arg)

    def check_growth(self, name: str | None, receiver: object, args: tuple) -> None:
        """Refuses `replace` and `join` calls whose result would be too large, before it is built."""
        if not isinstance(receiver, str):
            return
        if name == "replace" and len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
            old, new = args[0], args[1]
            occurrences = receiver.count(old) if old else len(receiver) + 1
            grown = len(receiver) + occurrences * (len(new) - len(old))
        elif name == "join" and args and isinstance(args[0], list | tuple):
            grown = len(receiver) * len(args[0])
        else:
            return
        if grown > self.max_value_size:
            raise SecurityError(f"value is too large: more than {self.max_value_size:,} characters")

    def check_format_string(self, text: object) -> None:
        if isinstance(text, bytes):
            text = text.decode(errors="replace")
        if not isinstance(text, str):
            return
        numbers = [number for spec in PERCENT_SPEC.findall(text) for number in spec]
        numbers += [number for spec in FIELD_SPEC.findall(text) for number in DIGITS.findall(spec)]
        if "*" in numbers or NESTED_FIELD.search(text):
            raise SecurityError("sizes taken from arguments are not allowed in format strings")
        if any(number and (len(number) > 9 or int(number) > self.max_value_size) for number in numbers):
            raise SecurityError("number in format string is too large")

    @_internal
    def guard(self, value):
        """Refuses a value that is too large and charges for the size of one that is not.

        Numbers are capped rather than charged: a chain of `*`/`**`/`+`/`%` can only grow a value by one guarded
        step at a time, so capping the width of each step's result keeps any one of them cheap to compute.
        """
        if isinstance(value, int | float) and not isinstance(value, bool):
            if isinstance(value, int) and value.bit_length() > MAX_BITS:
                raise SecurityError(f"number is too large: more than {MAX_BITS} bits")
            return value
        if isinstance(value, SIZED):
            size = len(value)
            if size > self.max_value_size:
                raise SecurityError(f"value is too large: more than {self.max_value_size:,} items")
            self.charge(size // 64 + 1 if isinstance(value, str | bytes) else size)
        return value

    @_internal
    def charge_operand(self, value):
        self.charge_value(value)
        return value

    @_internal
    def limit_iterable(self, iterable):
        for item in iterable:
            self.charge(ITERATION_COST)
            yield item

    # -- hooks of the sandbox

    def _range(self, *args):
        result = range(*args)
        if len(result) > self.max_value_size:
            raise SecurityError(f"number {len(result)} is too large")
        self.charge(len(result))
        return result

    def _limited_filter(self, name: str, func: Callable) -> Callable:
        # pass_context / pass_environment filters get Jinja's own object before the value they filter
        skipped = 1 if getattr(func, "jinja_pass_arg", None) is not None else 0

        @functools.wraps(func)  # keeps the pass_context and pass_environment marks
        def wrapper(*args, **kwargs):
            self.check_arguments(args, kwargs, name)
            if len(args) > skipped:
                self.charge_text(args[skipped])
                self.check_growth(name, args[skipped], args[skipped + 1 :])
                if name == "join" and len(args) > skipped + 1:  # the separator is the second argument
                    self.check_growth(name, args[skipped + 1], args[skipped : skipped + 1])
            if name == "format" and args:
                self.check_format_string(args[0])
            if name in FILTER_WEIGHT and len(args) > skipped:
                self.charge((FILTER_WEIGHT[name] - 1) * self.weight(args[skipped], _remaining.get()[0]))
            self.charge(CALL_COST)
            return self.guard(func(*args, **kwargs))

        return wrapper

    def call(self, context, obj, /, *args, **kwargs):
        if getattr(getattr(obj, "__func__", None), "_internal", False):
            return obj(*args)  # no sandbox checks or pass-arg dispatch: Jinja only adds `_loop_vars` and `_block_vars`
        self.charge(CALL_COST)
        name = getattr(obj, "__name__", None)
        self.check_arguments(args, kwargs, name)
        receiver = getattr(obj, "__self__", None)
        self.charge_value(receiver)  # the receiver of a method, e.g. list.count
        self.check_growth(name, receiver, args)
        return self.guard(super().call(context, obj, *args, **kwargs))

    def call_binop(self, context, operator, left, right):
        if operator == "**" and isinstance(right, int | float) and abs(right) > 1000:
            raise SecurityError("exponent is too large")
        if operator == "*":
            for sequence, count in ((left, right), (right, left)):
                if (
                    isinstance(sequence, SIZED)
                    and isinstance(count, int)
                    and len(sequence) * max(count, 0) > self.max_value_size
                ):
                    raise SecurityError("repetition is too large")
        if operator == "%":
            self.check_format_string(left)
        return super().call_binop(context, operator, left, right)

    def wrap_str_format(self, value):
        wrapper = super().wrap_str_format(value)
        if wrapper is not None:  # `"...".format` or `format_map`, checked when it is accessed
            self.check_format_string(value.__self__)
        return wrapper

    def _parse(self, source, name, filename):
        tree = super()._parse(source, name, filename)
        for node in tree.find_all(tuple(FORBIDDEN)):
            raise TemplateSyntaxError(
                f"{FORBIDDEN[type(node)]} is not allowed in templates", node.lineno, name, filename
            )
        return _Rewrite().visit(tree)

    def render_limited(self, template, context: Mapping) -> str:
        """Renders a template of this environment within its budget and output limit."""
        token = _remaining.set([self.budget, 0])
        try:
            parts, size = [], 0
            for chunk in template.generate(context):
                size += len(chunk)
                if size > self.max_output_size:
                    raise SecurityError(f"output is too large: more than {self.max_output_size:,} characters")
                parts.append(chunk)
            return "".join(parts)
        finally:
            _remaining.reset(token)
