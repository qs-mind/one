"""The agent engine: One's thin layer over PydanticAI.

Only this package imports `pydantic_ai`, and inside it only the connector files, `agents.py`,
`tools.py` (the toolset adapter) and `runner.py`. Everything else, and every caller outside the
package, uses One's own types from `qsone.engine.types`.
"""
