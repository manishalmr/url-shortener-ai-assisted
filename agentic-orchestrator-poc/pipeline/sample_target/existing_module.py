"""
A tiny pre-existing module standing in for 'the existing codebase' in the
Brownfield scenario - just enough real code for the pipeline's codebase-
reasoning step to inspect (grep for function names) rather than fabricate.
"""


def greet(name: str) -> str:
    return f"Hello, {name}!"


def add(a: int, b: int) -> int:
    return a + b
