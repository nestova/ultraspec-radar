"""Tracerfy skip-trace provider — retrieves owner phone numbers and email
addresses for property addresses via the Tracerfy MCP server.

Tracerfy is used ONLY for skip tracing (contact lookup), not for property
data.  The fixture provider supplies anchors and parcels; Tracerfy enriches
candidate parcel owners with contact info on demand.
"""

from __future__ import annotations

import logging
import os

from app.models import OwnerContact
from app.providers.attom import MissingCredentialsError
from app.providers.mcp_client import MCPClient

logger = logging.getLogger(__name__)

MCP_URL_TEMPLATE = "https://mcp.tracerfy.com/u/{token}/mcp"


class TracerfyProvider:
    """Skip-trace provider backed by the Tracerfy MCP ``trace_lookup`` tool."""

    name = "tracerfy"

    def __init__(self, token: str | None = None) -> None:
        token = token or os.getenv("TRACERFY_API_KEY")
        if not token:
            raise MissingCredentialsError(
                "TRACERFY_API_KEY is not set. Generate a connector token in your "
                "Tracerfy profile → Connect via MCP and add it as TRACERFY_API_KEY."
            )
        if token.startswith("http"):
            server_url = token
        else:
            server_url = MCP_URL_TEMPLATE.format(token=token)
        self._client = MCPClient(server_url)

    def skip_trace(self, address: str, city: str, state: str, zip_code: str = "") -> OwnerContact:
        """Skip trace a single property address; returns owner phones and emails."""
        logger.info("Tracerfy skip trace: %s, %s, %s", address, city, state)
        result = self._client.call_tool("trace_lookup", {
            "address": address,
            "city": city,
            "state": state,
            "zip_code": zip_code,
        })
        return self._parse_result(result)

    @staticmethod
    def _parse_result(result: object) -> OwnerContact:
        """Parse the Tracerfy trace_lookup response into an OwnerContact."""
        if isinstance(result, dict):
            return OwnerContact(
                owner_name=result.get("owner_name") or result.get("name"),
                phones=_as_list(result.get("phones") or result.get("phone_numbers")),
                emails=_as_list(result.get("emails") or result.get("email_addresses")),
            )
        # Non-dict result means no hit — return empty contact
        return OwnerContact()


def _as_list(value: object) -> list[str]:
    """Coerce a string or list into a list of strings."""
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str) and value:
        return [value]
    return []
