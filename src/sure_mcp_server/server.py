"""Sure MCP Server - Main server implementation."""

import os
import logging
import json
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastMCP server
# Host/port/path only matter for HTTP-based transports (sse, streamable-http);
# they're ignored for stdio. Default host is 0.0.0.0 so the server is reachable
# when run in a container (e.g. on Unraid) rather than bound to localhost only.
mcp = FastMCP(
    "Sure MCP Server",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8000")),
    streamable_http_path=os.getenv("MCP_PATH", "/mcp"),
)


# Sure's API paginates index endpoints with Pagy and caps per_page at 100.
MAX_PER_PAGE = 100


def get_api_url() -> str:
    """Get the Sure API base URL."""
    url = os.getenv("SURE_API_URL")
    if not url:
        raise RuntimeError("❌ SURE_API_URL not configured. Set it in your environment.")
    return url.rstrip("/")


def get_auth_header() -> Dict[str, str]:
    """Get authentication header for API requests."""
    api_key = os.getenv("SURE_API_KEY")
    access_token = os.getenv("SURE_ACCESS_TOKEN")

    if api_key:
        return {"X-Api-Key": api_key}
    elif access_token:
        return {"Authorization": f"Bearer {access_token}"}
    else:
        raise RuntimeError("❌ No authentication configured. Set SURE_API_KEY or SURE_ACCESS_TOKEN.")


def get_client() -> httpx.Client:
    """Get configured HTTP client for Sure API."""
    timeout = int(os.getenv("SURE_TIMEOUT", "30"))
    verify_ssl = os.getenv("SURE_VERIFY_SSL", "true").lower() == "true"

    return httpx.Client(
        base_url=get_api_url(),
        timeout=timeout,
        verify=verify_ssl,
        headers=get_auth_header()
    )


def handle_response(response: httpx.Response) -> Any:
    """Handle API response and raise appropriate errors."""
    if response.status_code == 401:
        raise RuntimeError("❌ Authentication failed. Check your API key.")
    elif response.status_code == 403:
        raise RuntimeError("❌ Permission denied. Check API key scopes.")
    elif response.status_code == 404:
        raise RuntimeError("❌ Resource not found.")
    elif response.status_code == 429:
        raise RuntimeError("❌ Rate limited. Please wait and try again.")
    elif response.status_code >= 400:
        raise RuntimeError(f"❌ API error {response.status_code}: {response.text}")

    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return response.text


@mcp.tool()
def setup_authentication() -> str:
    """Get instructions for setting up authentication with Sure."""
    return """🔐 Sure MCP Server - Setup Instructions

1️⃣ Start your Sure Docker instance:
   cd /path/to/sure
   docker compose up -d

2️⃣ Log into Sure at http://localhost:3000

3️⃣ Go to Settings > API Key and generate a new key

4️⃣ Add to your Claude Desktop config:
   "env": {
     "SURE_API_URL": "http://localhost:3000",
     "SURE_API_KEY": "your-api-key-here"
   }

5️⃣ Restart Claude Desktop

✅ Start using Sure tools:
   • get_accounts - View all accounts
   • get_transactions - Recent transactions
   • get_categories - Transaction categories
   • sync_accounts - Trigger account sync"""


@mcp.tool()
def check_auth_status() -> str:
    """Check if authentication is configured for Sure API."""
    try:
        api_url = os.getenv("SURE_API_URL")
        api_key = os.getenv("SURE_API_KEY")
        access_token = os.getenv("SURE_ACCESS_TOKEN")

        status = ""

        if api_url:
            status += f"✅ API URL: {api_url}\n"
        else:
            status += "❌ SURE_API_URL not configured\n"

        if api_key:
            status += "✅ API Key configured\n"
        elif access_token:
            status += "✅ Access Token configured\n"
        else:
            status += "❌ No authentication configured (SURE_API_KEY or SURE_ACCESS_TOKEN)\n"

        status += "\n💡 Try get_accounts to test the connection."

        return status
    except Exception as e:
        return f"Error checking auth status: {str(e)}"


@mcp.tool()
def check_connection() -> str:
    """Test connection to Sure API."""
    try:
        with get_client() as client:
            response = client.get("/api/v1/usage")
            data = handle_response(response)

            return f"✅ Connected to Sure API\n{json.dumps(data, indent=2, default=str)}"
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        return f"❌ Connection failed: {str(e)}"


@mcp.tool()
def get_accounts() -> str:
    """Get all financial accounts from Sure."""
    try:
        with get_client() as client:
            response = client.get("/api/v1/accounts")
            data = handle_response(response)

            # Handle paginated response
            accounts = data.get("accounts") or data.get("data") or data
            if isinstance(accounts, dict):
                accounts = accounts.get("accounts", [])

            logger.info(f"✅ Retrieved {len(accounts) if isinstance(accounts, list) else 'unknown'} accounts")
            return json.dumps(accounts, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get accounts: {e}")
        return f"Error getting accounts: {str(e)}"


@mcp.tool()
def get_transactions(
    limit: int = 25,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_ids: Optional[str] = None,
    category_ids: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    fetch_all: bool = False,
) -> str:
    """
    Get transactions from Sure.

    Results are newest-first. The API caps a page at 100, so a query matching
    more than that is split across pages - use `page` to step through them, or
    `fetch_all=True` to retrieve every match in one call.

    Args:
        limit: Number of transactions per page (default: 25, max: 100)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        account_ids: Comma-separated account IDs to filter by
        category_ids: Comma-separated category IDs to filter by
        search: Search term to filter transactions
        page: Which page to retrieve (1-based, default: 1)
        fetch_all: Retrieve every matching transaction across all pages
    """
    try:
        with get_client() as client:
            params: Dict[str, Any] = {
                "per_page": MAX_PER_PAGE if fetch_all else min(limit, MAX_PER_PAGE)
            }

            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            if account_ids:
                params["account_ids"] = account_ids
            if category_ids:
                params["category_ids"] = category_ids
            if search:
                params["search"] = search

            transactions: List[Any] = []
            current_page = 1 if fetch_all else max(page, 1)

            while True:
                params["page"] = current_page
                response = client.get("/api/v1/transactions", params=params)
                data = handle_response(response)

                batch = data.get("transactions") or data.get("data") or data
                if isinstance(batch, dict):
                    batch = batch.get("transactions", [])
                if not isinstance(batch, list):
                    # Unrecognised shape - return whatever came back rather than looping.
                    return json.dumps(batch, indent=2, default=str)

                transactions.extend(batch)

                pagination = data.get("pagination") if isinstance(data, dict) else None

                if not fetch_all:
                    total_pages = (pagination or {}).get("total_pages", 1)
                    if total_pages > current_page:
                        logger.warning(
                            f"⚠️  Page {current_page} of {total_pages} - "
                            f"{(pagination or {}).get('total_count')} transactions match. "
                            f"Use page=N or fetch_all=True to get the rest."
                        )
                    break

                if not pagination:
                    break
                if pagination.get("page", current_page) >= pagination.get("total_pages", current_page):
                    break
                current_page += 1

            logger.info(f"✅ Retrieved {len(transactions)} transactions")
            return json.dumps(transactions, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get transactions: {e}")
        return f"Error getting transactions: {str(e)}"


@mcp.tool()
def get_transaction(transaction_id: str) -> str:
    """
    Get a single transaction by ID.

    Args:
        transaction_id: The ID of the transaction
    """
    try:
        with get_client() as client:
            response = client.get(f"/api/v1/transactions/{transaction_id}")
            data = handle_response(response)

            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get transaction: {e}")
        return f"Error getting transaction: {str(e)}"


@mcp.tool()
def create_transaction(
    account_id: str,
    amount: float,
    name: str,
    date: str,
    category_id: Optional[str] = None,
    notes: Optional[str] = None,
    nature: Optional[str] = None,
) -> str:
    """
    Create a new transaction in Sure.

    Args:
        account_id: The account ID to add the transaction to
        amount: Transaction amount (use nature to specify income/expense)
        name: Transaction name/payee
        date: Transaction date in YYYY-MM-DD format
        category_id: Optional category ID
        notes: Optional notes
        nature: Optional "income" or "expense" to set amount sign
    """
    try:
        with get_client() as client:
            payload: Dict[str, Any] = {
                "account_id": account_id,
                "amount": amount,
                "name": name,
                "date": date,
            }

            if category_id:
                payload["category_id"] = category_id
            if notes:
                payload["notes"] = notes
            if nature:
                payload["nature"] = nature

            response = client.post(
                "/api/v1/transactions",
                json={"transaction": payload}
            )
            data = handle_response(response)

            logger.info(f"✅ Created transaction")
            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to create transaction: {e}")
        return f"Error creating transaction: {str(e)}"


@mcp.tool()
def update_transaction(
    transaction_id: str,
    amount: Optional[float] = None,
    name: Optional[str] = None,
    date: Optional[str] = None,
    category_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """
    Update an existing transaction in Sure.

    Args:
        transaction_id: The ID of the transaction to update
        amount: New transaction amount
        name: New transaction name/payee
        date: New transaction date in YYYY-MM-DD format
        category_id: New category ID
        notes: New notes
    """
    try:
        with get_client() as client:
            payload: Dict[str, Any] = {}

            if amount is not None:
                payload["amount"] = amount
            if name is not None:
                payload["name"] = name
            if date is not None:
                payload["date"] = date
            if category_id is not None:
                payload["category_id"] = category_id
            if notes is not None:
                payload["notes"] = notes

            response = client.patch(
                f"/api/v1/transactions/{transaction_id}",
                json={"transaction": payload}
            )
            data = handle_response(response)

            logger.info(f"✅ Updated transaction {transaction_id}")
            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to update transaction: {e}")
        return f"Error updating transaction: {str(e)}"


@mcp.tool()
def delete_transaction(transaction_id: str) -> str:
    """
    Delete a transaction from Sure.

    Args:
        transaction_id: The ID of the transaction to delete
    """
    try:
        with get_client() as client:
            response = client.delete(f"/api/v1/transactions/{transaction_id}")
            data = handle_response(response)

            logger.info(f"✅ Deleted transaction {transaction_id}")
            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to delete transaction: {e}")
        return f"Error deleting transaction: {str(e)}"


@mcp.tool()
def get_categories() -> str:
    """
    Get all transaction categories from Sure.

    Walks every page, so the full category list is returned rather than just
    the API's first page of 25.
    """
    try:
        with get_client() as client:
            categories: List[Any] = []
            page = 1

            while True:
                response = client.get(
                    "/api/v1/categories",
                    params={"page": page, "per_page": MAX_PER_PAGE},
                )
                data = handle_response(response)

                batch = data.get("categories") or data.get("data") or data
                if isinstance(batch, dict):
                    batch = batch.get("categories", [])
                if not isinstance(batch, list):
                    # Unrecognised shape - return whatever came back rather than looping.
                    return json.dumps(batch, indent=2, default=str)

                categories.extend(batch)

                pagination = data.get("pagination") if isinstance(data, dict) else None
                if not pagination:
                    break
                if pagination.get("page", page) >= pagination.get("total_pages", page):
                    break
                page += 1

            logger.info(f"✅ Retrieved {len(categories)} categories")
            return json.dumps(categories, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get categories: {e}")
        return f"Error getting categories: {str(e)}"


@mcp.tool()
def get_category(category_id: str) -> str:
    """
    Get a single category by ID.

    Args:
        category_id: The ID of the category
    """
    try:
        with get_client() as client:
            response = client.get(f"/api/v1/categories/{category_id}")
            data = handle_response(response)

            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get category: {e}")
        return f"Error getting category: {str(e)}"


@mcp.tool()
def create_category(
    name: str,
    color: Optional[str] = None,
    icon: Optional[str] = None,
    parent_id: Optional[str] = None,
) -> str:
    """
    Create a new transaction category in Sure.

    Args:
        name: The category name
        color: Optional hex color, e.g. "#0d9488"
        icon: Optional Lucide icon name, e.g. "trending-up" (Sure suggests one if omitted)
        parent_id: Optional parent category ID to create this as a subcategory
    """
    try:
        with get_client() as client:
            payload: Dict[str, Any] = {"name": name}

            if color:
                payload["color"] = color
            if icon:
                payload["icon"] = icon
            if parent_id:
                payload["parent_id"] = parent_id

            response = client.post(
                "/api/v1/categories",
                json={"category": payload}
            )
            data = handle_response(response)

            logger.info(f"✅ Created category {name}")
            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to create category: {e}")
        return f"Error creating category: {str(e)}"


@mcp.tool()
def sync_accounts() -> str:
    """Trigger account sync to refresh data from financial institutions."""
    try:
        with get_client() as client:
            response = client.post("/api/v1/sync")
            data = handle_response(response)

            logger.info("✅ Triggered account sync")
            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to sync accounts: {e}")
        return f"Error syncing accounts: {str(e)}"


@mcp.tool()
def get_usage() -> str:
    """Get API usage and rate limit information."""
    try:
        with get_client() as client:
            response = client.get("/api/v1/usage")
            data = handle_response(response)

            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get usage: {e}")
        return f"Error getting usage: {str(e)}"


@mcp.tool()
def list_chats() -> str:
    """Get all AI chat sessions from Sure."""
    try:
        with get_client() as client:
            response = client.get("/api/v1/chats")
            data = handle_response(response)

            # Handle paginated response
            chats = data.get("chats") or data.get("data") or data
            if isinstance(chats, dict):
                chats = chats.get("chats", [])

            logger.info(f"✅ Retrieved {len(chats) if isinstance(chats, list) else 'unknown'} chats")
            return json.dumps(chats, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to list chats: {e}")
        return f"Error listing chats: {str(e)}"


@mcp.tool()
def create_chat(title: Optional[str] = None) -> str:
    """
    Create a new AI chat session in Sure.

    Args:
        title: Optional title for the chat
    """
    try:
        with get_client() as client:
            payload: Dict[str, Any] = {}
            if title:
                payload["title"] = title

            response = client.post("/api/v1/chats", json=payload)
            data = handle_response(response)

            logger.info("✅ Created new chat")
            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to create chat: {e}")
        return f"Error creating chat: {str(e)}"


@mcp.tool()
def get_chat(chat_id: str) -> str:
    """
    Get a chat session by ID.

    Args:
        chat_id: The ID of the chat
    """
    try:
        with get_client() as client:
            response = client.get(f"/api/v1/chats/{chat_id}")
            data = handle_response(response)

            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to get chat: {e}")
        return f"Error getting chat: {str(e)}"


@mcp.tool()
def send_message(chat_id: str, content: str) -> str:
    """
    Send a message to Sure's AI assistant.

    Args:
        chat_id: The ID of the chat
        content: The message content
    """
    try:
        with get_client() as client:
            response = client.post(
                f"/api/v1/chats/{chat_id}/messages",
                json={"content": content}
            )
            data = handle_response(response)

            logger.info("✅ Sent message")
            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        return f"Error sending message: {str(e)}"


@mcp.tool()
def delete_chat(chat_id: str) -> str:
    """
    Delete a chat session.

    Args:
        chat_id: The ID of the chat to delete
    """
    try:
        with get_client() as client:
            response = client.delete(f"/api/v1/chats/{chat_id}")
            data = handle_response(response)

            logger.info(f"✅ Deleted chat {chat_id}")
            return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to delete chat: {e}")
        return f"Error deleting chat: {str(e)}"


def main():
    """Main entry point for the server."""
    transport = os.getenv("MCP_TRANSPORT", "streamable-http")
    if transport not in ("stdio", "sse", "streamable-http"):
        raise RuntimeError(
            f"❌ Invalid MCP_TRANSPORT '{transport}'. Must be 'stdio', 'sse', or 'streamable-http'."
        )

    if transport == "stdio":
        logger.info("Starting Sure MCP Server (stdio transport)...")
    else:
        logger.info(
            f"Starting Sure MCP Server ({transport} transport) on "
            f"{mcp.settings.host}:{mcp.settings.port}{mcp.settings.streamable_http_path}..."
        )

    try:
        mcp.run(transport=transport)
    except Exception as e:
        logger.error(f"Failed to run server: {str(e)}")
        raise


# Export for mcp run
app = mcp

if __name__ == "__main__":
    main()
