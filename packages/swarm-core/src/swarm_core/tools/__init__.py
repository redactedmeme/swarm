"""Tool implementations dispatched by the terminal (`/tool ...` verbs).

Modules here are loaded by name at call time, so this package is imported for
its location as much as its contents — keep `__init__.py` present so
`swarm_core.tools.__file__` resolves (a namespace package reports None, which
breaks callers that derive a directory from it).
"""
