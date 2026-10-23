"""Read registered tools and resources through FastMCP's public API.

FastMCP 2.x exposes ``get_tools()`` / ``get_resources()`` (dicts); 3.x replaced them
with ``list_tools()`` / ``list_resources()`` (lists) and dropped the private
``_tool_manager`` / ``_resource_manager`` registries the tests used to read.
"""

import asyncio

from fastmcp import FastMCP


def _registered(mcp: FastMCP, kind: str, key: str) -> dict:
    if hasattr(mcp, f"get_{kind}"):  # FastMCP 2.x
        items = asyncio.run(getattr(mcp, f"get_{kind}")())
        return {str(k): v.fn for k, v in items.items()}
    items = asyncio.run(getattr(mcp, f"list_{kind}")())  # FastMCP 3.x
    return {str(getattr(i, key)): i.fn for i in items}


def registered_tools(mcp: FastMCP) -> dict:
    """Map tool name to its function."""
    return _registered(mcp, "tools", "name")


def registered_resources(mcp: FastMCP) -> dict:
    """Map resource URI to its function."""
    return _registered(mcp, "resources", "uri")
