import httpx
import json
import logging
from typing import Dict, Any, List, Optional
from backend.config import settings

logger = logging.getLogger(__name__)

MONDAY_API_URL = "https://api.monday.com/v2"

class MondayClient:
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or settings.MONDAY_API_TOKEN
        self.headers = {
            "Authorization": self.api_token,
            "API-Version": "2024-04",
            "Content-Type": "application/json"
        }

    def is_configured(self) -> bool:
        return bool(self.api_token and self.api_token.strip())

    async def get_board_schema(self, board_id: str) -> Dict[str, Any]:
        """Fetch board columns, titles, types and settings directly from Monday GraphQL API."""
        if not self.is_configured():
            raise RuntimeError("Monday.com API token is not configured. Please provide MONDAY_API_TOKEN.")

        if not board_id or not str(board_id).strip():
            raise ValueError("Board ID cannot be empty.")

        query = """
        query ($boardId: [ID!]) {
            boards(ids: $boardId) {
                id
                name
                description
                columns {
                    id
                    title
                    type
                    settings_str
                }
            }
        }
        """
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                MONDAY_API_URL,
                headers=self.headers,
                json={"query": query, "variables": {"boardId": [str(board_id)]}}
            )
            data = resp.json()
            if "errors" in data:
                logger.error(f"Monday API error: {data['errors']}")
                raise RuntimeError(f"Monday API schema error: {data['errors']}")
            
            boards = data.get("data", {}).get("boards", [])
            if not boards:
                raise RuntimeError(f"Board with ID {board_id} was not found in Monday.com workspace.")
            return boards[0]

    async def fetch_board_items(self, board_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch all live items from Monday.com board using cursor-based pagination."""
        if not self.is_configured():
            raise RuntimeError("Monday.com API token is not configured. Please provide MONDAY_API_TOKEN.")

        if not board_id or not str(board_id).strip():
            raise ValueError("Board ID cannot be empty.")

        items = []
        cursor = None

        query = """
        query ($boardId: [ID!], $cursor: String, $limit: Int) {
            boards(ids: $boardId) {
                items_page(limit: $limit, cursor: $cursor) {
                    cursor
                    items {
                        id
                        name
                        updated_at
                        column_values {
                            id
                            text
                            value
                            type
                        }
                    }
                }
            }
        }
        """

        async with httpx.AsyncClient(timeout=35.0) as client:
            while True:
                variables: Dict[str, Any] = {"boardId": [str(board_id)], "limit": limit}
                if cursor:
                    variables["cursor"] = cursor

                resp = await client.post(
                    MONDAY_API_URL,
                    headers=self.headers,
                    json={"query": query, "variables": variables}
                )
                data = resp.json()
                if "errors" in data:
                    logger.error(f"Monday API error: {data['errors']}")
                    raise RuntimeError(f"Monday API item fetch error: {data['errors']}")

                boards = data.get("data", {}).get("boards", [])
                if not boards:
                    break

                page = boards[0].get("items_page", {})
                page_items = page.get("items", [])
                items.extend(page_items)

                cursor = page.get("cursor")
                if not cursor or len(page_items) == 0:
                    break

        logger.info(f"Successfully fetched {len(items)} live items from Monday Board {board_id}")
        return items

monday_client = MondayClient()
