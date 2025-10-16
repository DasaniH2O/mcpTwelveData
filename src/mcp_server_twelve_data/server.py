from typing import Type, TypeVar, Literal, Optional
import httpx
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP, Context
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
import re

from .common import vector_db_exists
from .doc_tool import register_doc_tool, register_http_doctool
from .doc_tool_remote import register_doc_tool_remote
from .key_provider import extract_twelve_data_apikey
from .tools import register_all_tools
from .u_tool import register_u_tool, register_http_utool
from .u_tool_remote import register_u_tool_remote
import asyncio
from starlette.responses import JSONResponse

def serve(
    api_base: str,
    transport: Literal["stdio", "sse", "streamable-http"],
    twelve_data_apikey: Optional[str],
    number_of_tools: int,
    u_tool_open_ai_api_key: Optional[str],
    u_tool_oauth2: bool
) -> None:
    server = FastMCP(
        "mcp-twelve-data",
        host="0.0.0.0",
        port="8000",
    )

    P = TypeVar('P', bound=BaseModel)
    R = TypeVar('R', bound=BaseModel)

    def resolve_path_params(endpoint: str, params_dict: dict) -> str:
        def replacer(match):
            key = match.group(1)
            if key not in params_dict:
                raise ValueError(f"Missing path parameter: {key}")
            return str(params_dict.pop(key))
        return re.sub(r"{(\w+)}", replacer, endpoint)

    async def _call_endpoint(
        endpoint: str,
        params: P,
        response_model: Type[R],
        ctx: Context
    ) -> R:
        params.apikey = extract_twelve_data_apikey(
            twelve_data_apikey=twelve_data_apikey,
            transport=transport,
            ctx=ctx
        )

        params_dict = params.model_dump(exclude_none=True)
        resolved_endpoint = resolve_path_params(endpoint, params_dict)

        async with httpx.AsyncClient(
            trust_env=False,
            headers={
                "accept": "application/json",
                "user-agent": "python-httpx/0.24.0"
            },
        ) as client:
            resp = await client.get(
                f"{api_base}/{resolved_endpoint}",
                params=params_dict
            )
            resp.raise_for_status()
            resp_json = resp.json()

            if isinstance(resp_json, dict):
                status = resp_json.get("status")
                if status == "error":
                    code = resp_json.get('code')
                    raise HTTPException(
                        status_code=code,
                        detail=f"Failed to perform request,"
                               f" code = {code}, message = {resp_json.get('message')}"
                    )

            return response_model.model_validate(resp_json)

    if u_tool_oauth2 or u_tool_open_ai_api_key is not None:
        # we will not publish large vector db, without it server will work in remote mode
        if vector_db_exists():
            register_all_tools(server=server, _call_endpoint=_call_endpoint)
            u_tool = register_u_tool(
                server=server,
                open_ai_api_key_from_args=u_tool_open_ai_api_key,
                transport=transport
            )
            doc_tool = register_doc_tool(
                server=server,
                open_ai_api_key_from_args=u_tool_open_ai_api_key,
                transport=transport
            )
        else:
            u_tool = register_u_tool_remote(
                server=server,
                twelve_data_apikey=twelve_data_apikey,
                open_ai_api_key_from_args=u_tool_open_ai_api_key,
                transport=transport,
            )
            doc_tool = register_doc_tool_remote(
                server=server,
                twelve_data_apikey=twelve_data_apikey,
                open_ai_api_key_from_args=u_tool_open_ai_api_key,
                transport=transport,
            )
        register_http_utool(
            transport=transport,
            u_tool=u_tool,
            server=server,
        )
        register_http_doctool(
            transport=transport,
            server=server,
            doc_tool=doc_tool,
        )

    else:
        register_all_tools(server=server, _call_endpoint=_call_endpoint)
        all_tools = server._tool_manager._tools
        server._tool_manager._tools = dict(list(all_tools.items())[:number_of_tools])

    @server.custom_route("/health", ["GET"])
    async def health(_: Request):
        return JSONResponse({"status": "ok"})
    # Relay that auto-retries once on "Session terminated"
    @server.custom_route("/mcp_retry", ["POST"])
    async def mcp_retry(request: Request):
        """
        A small wrapper around the built-in /mcp endpoint that:
          - forwards the original JSON-RPC body
          - if it gets -32600 "Session terminated", it re-initializes and replays once
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": "parse-error",
                 "error": {"code": -32700, "message": "Invalid JSON"}},
                status_code=200
            )

        # Forward headers we need (Authorization + Accept are important for Streamable HTTP)
        fwd_headers = {
            "Authorization": request.headers.get("Authorization", ""),
            "Content-Type": "application/json",
            "Accept": request.headers.get("Accept", "application/json, text/event-stream"),
        }

        async def call_mcp(payload):
            async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                r = await client.post(
                    "http://127.0.0.1:8000/mcp",  # call the local MCP endpoint
                    headers=fwd_headers,
                    json=payload
                )
                # Return raw JSON (even on error)
                try:
                    return r.json()
                except Exception:
                    return {"jsonrpc": "2.0", "id": "relay-error",
                            "error": {"code": -32603, "message": "Relay parse error"}}

        # 1) First attempt
        out = await call_mcp(body)
        err = (out or {}).get("error", {})
        msg = (err.get("message") or "")

        if err.get("code") == -32600 and "Session terminated" in msg:
            # 2) Re-initialize then retry once
            await asyncio.sleep(0.8)  # tiny backoff
            init = {
                "jsonrpc": "2.0",
                "id": "relay-init",
                "method": "initialize",
                "params": {
                    "clientInfo": {"name": "relay", "version": "1.0.0"},
                    "protocolVersion": "2024-11-05"
                }
            }
            _ = await call_mcp(init)

            out = await call_mcp(body)

        return JSONResponse(out, status_code=200)

    server.run(transport=transport)
