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
        return bool(self.api_token and self.api_token.strip() and self.api_token != "dummy_token")

    async def get_board_schema(self, board_id: str) -> Dict[str, Any]:
        if not self.is_configured():
            return self._mock_board_schema(board_id)

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
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                MONDAY_API_URL,
                headers=self.headers,
                json={"query": query, "variables": {"boardId": [board_id]}}
            )
            data = resp.json()
            if "errors" in data:
                logger.error(f"Monday API error: {data['errors']}")
                raise Exception(f"Monday API schema error: {data['errors']}")
            
            boards = data.get("data", {}).get("boards", [])
            if not boards:
                raise Exception(f"Board with ID {board_id} not found in Monday.com workspace.")
            return boards[0]

    async def fetch_board_items(self, board_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.is_configured():
            return self._mock_board_items(board_id)

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

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                variables: Dict[str, Any] = {"boardId": [board_id], "limit": limit}
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
                    raise Exception(f"Monday API item fetch error: {data['errors']}")

                boards = data.get("data", {}).get("boards", [])
                if not boards:
                    break

                page = boards[0].get("items_page", {})
                page_items = page.get("items", [])
                items.extend(page_items)

                cursor = page.get("cursor")
                if not cursor or len(page_items) == 0:
                    break

        return items

    def _mock_board_schema(self, board_type_or_id: str) -> Dict[str, Any]:
        if "deal" in str(board_type_or_id).lower() or board_type_or_id == settings.DEALS_BOARD_ID:
            return {
                "id": board_type_or_id or "deals_board",
                "name": "Deals Pipeline Tracker",
                "description": "Sales deal funnel and pipeline stages",
                "columns": [
                    {"id": "name", "title": "Deal / Opportunity Name", "type": "name"},
                    {"id": "client", "title": "Client Name", "type": "text"},
                    {"id": "sector", "title": "Industry Sector", "type": "status"},
                    {"id": "stage", "title": "Deal Stage", "type": "status"},
                    {"id": "value", "title": "Deal Value", "type": "numbers"},
                    {"id": "prob", "title": "Win Probability (%)", "type": "numbers"},
                    {"id": "exp_close", "title": "Expected Close Date", "type": "date"},
                    {"id": "act_close", "title": "Actual Close Date", "type": "date"},
                    {"id": "owner", "title": "Deal Owner", "type": "people"},
                    {"id": "curr", "title": "Currency", "type": "text"}
                ]
            }
        else:
            return {
                "id": board_type_or_id or "work_orders_board",
                "name": "Work Orders & Project Execution Tracker",
                "description": "Operational drone flight missions and project execution",
                "columns": [
                    {"id": "name", "title": "Work Order Reference", "type": "name"},
                    {"id": "client", "title": "Client / Enterprise", "type": "text"},
                    {"id": "project", "title": "Project Title", "type": "text"},
                    {"id": "sector", "title": "Sector", "type": "status"},
                    {"id": "status", "title": "Execution Status", "type": "status"},
                    {"id": "start_date", "title": "Flight Start Date", "type": "date"},
                    {"id": "due_date", "title": "Target Delivery Date", "type": "date"},
                    {"id": "comp_date", "title": "Completion Date", "type": "date"},
                    {"id": "contract_val", "title": "Contract Value", "type": "numbers"},
                    {"id": "actual_cost", "title": "Operational Flight Cost", "type": "numbers"},
                    {"id": "pilot", "title": "Flight Lead / Chief Pilot", "type": "people"},
                    {"id": "location", "title": "Operational Site Location", "type": "text"}
                ]
            }

    def _mock_board_items(self, board_type_or_id: str) -> List[Dict[str, Any]]:
        if "deal" in str(board_type_or_id).lower() or board_type_or_id == settings.DEALS_BOARD_ID:
            return [
                {
                    "id": "deal_101",
                    "name": "Adani Solar Farm Drone Inspection Q3",
                    "updated_at": "2026-08-15T10:00:00Z",
                    "column_values": [
                        {"id": "client", "text": "Adani Green Energy Ltd.", "value": None, "type": "text"},
                        {"id": "sector", "text": "Energy & Utilities", "value": None, "type": "status"},
                        {"id": "stage", "text": "Won", "value": None, "type": "status"},
                        {"id": "value", "text": "$125,000", "value": "125000", "type": "numbers"},
                        {"id": "prob", "text": "100%", "value": "100", "type": "numbers"},
                        {"id": "exp_close", "text": "2026-06-30", "value": None, "type": "date"},
                        {"id": "act_close", "text": "2026-06-28", "value": None, "type": "date"},
                        {"id": "owner", "text": "Karan Sharma", "value": None, "type": "people"},
                        {"id": "curr", "text": "USD", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "deal_102",
                    "name": "Tata Power Transmission Line Thermal Survey",
                    "updated_at": "2026-08-10T14:30:00Z",
                    "column_values": [
                        {"id": "client", "text": "Tata Power Company", "value": None, "type": "text"},
                        {"id": "sector", "text": "Energy", "value": None, "type": "status"},
                        {"id": "stage", "text": "Negotiation", "value": None, "type": "status"},
                        {"id": "value", "text": "85000", "value": "85000", "type": "numbers"},
                        {"id": "prob", "text": "80%", "value": "80", "type": "numbers"},
                        {"id": "exp_close", "text": "15/09/2026", "value": None, "type": "date"},
                        {"id": "act_close", "text": None, "value": None, "type": "date"},
                        {"id": "owner", "text": "Ananya Roy", "value": None, "type": "people"},
                        {"id": "curr", "text": "USD", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "deal_103",
                    "name": "Vedanta Open Cast Mine Volumetric 3D Mapping",
                    "updated_at": "2026-07-20T09:15:00Z",
                    "column_values": [
                        {"id": "client", "text": "Vedanta Resources Ltd", "value": None, "type": "text"},
                        {"id": "sector", "text": "Mining", "value": None, "type": "status"},
                        {"id": "stage", "text": "Won", "value": None, "type": "status"},
                        {"id": "value", "text": "$210,000.00", "value": "210000", "type": "numbers"},
                        {"id": "prob", "text": "100", "value": "100", "type": "numbers"},
                        {"id": "exp_close", "text": "2026-05-15", "value": None, "type": "date"},
                        {"id": "act_close", "text": "2026-05-18", "value": None, "type": "date"},
                        {"id": "owner", "text": "Rahul Verma", "value": None, "type": "people"},
                        {"id": "curr", "text": "USD", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "deal_104",
                    "name": "NHAI Highway Corridor Survey Expressway 44",
                    "updated_at": "2026-08-22T11:00:00Z",
                    "column_values": [
                        {"id": "client", "text": "National Highways Authority of India", "value": None, "type": "text"},
                        {"id": "sector", "text": "Infrastructure", "value": None, "type": "status"},
                        {"id": "stage", "text": "Proposal", "value": None, "type": "status"},
                        {"id": "value", "text": "$160k", "value": "160000", "type": "numbers"},
                        {"id": "prob", "text": "60%", "value": "60", "type": "numbers"},
                        {"id": "exp_close", "text": "2026-10-30", "value": None, "type": "date"},
                        {"id": "act_close", "text": None, "value": None, "type": "date"},
                        {"id": "owner", "text": "Karan Sharma", "value": None, "type": "people"},
                        {"id": "curr", "text": "USD", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "deal_105",
                    "name": "NTPC Wind Turbine Blade Inspection Phase 2",
                    "updated_at": "2026-08-18T16:00:00Z",
                    "column_values": [
                        {"id": "client", "text": "NTPC Limited", "value": None, "type": "text"},
                        {"id": "sector", "text": "Renewable Energy", "value": None, "type": "status"},
                        {"id": "stage", "text": "Discovery", "value": None, "type": "status"},
                        {"id": "value", "text": "95,000", "value": "95000", "type": "numbers"},
                        {"id": "prob", "text": "30%", "value": "30", "type": "numbers"},
                        {"id": "exp_close", "text": "2026-11-15", "value": None, "type": "date"},
                        {"id": "act_close", "text": None, "value": None, "type": "date"},
                        {"id": "owner", "text": "Priya Nair", "value": None, "type": "people"},
                        {"id": "curr", "text": "USD", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "deal_106",
                    "name": "Reliance Telecom Tower Asset Audits (500 sites)",
                    "updated_at": "2026-08-01T12:00:00Z",
                    "column_values": [
                        {"id": "client", "text": "Reliance Jio Infocomm", "value": None, "type": "text"},
                        {"id": "sector", "text": "Telecom", "value": None, "type": "status"},
                        {"id": "stage", "text": "Lost", "value": None, "type": "status"},
                        {"id": "value", "text": "140000", "value": "140000", "type": "numbers"},
                        {"id": "prob", "text": "0%", "value": "0", "type": "numbers"},
                        {"id": "exp_close", "text": "2026-07-15", "value": None, "type": "date"},
                        {"id": "act_close", "text": "2026-07-20", "value": None, "type": "date"},
                        {"id": "owner", "text": "Ananya Roy", "value": None, "type": "people"},
                        {"id": "curr", "text": "USD", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "deal_107",
                    "name": "JSW Steel Plant Topographic Lidar Mapping",
                    "updated_at": "2026-08-25T17:45:00Z",
                    "column_values": [
                        {"id": "client", "text": "JSW Steel", "value": None, "type": "text"},
                        {"id": "sector", "text": "Mining & Metals", "value": None, "type": "status"},
                        {"id": "stage", "text": "Won", "value": None, "type": "status"},
                        {"id": "value", "text": "$180,000", "value": "180000", "type": "numbers"},
                        {"id": "prob", "text": "100%", "value": "100", "type": "numbers"},
                        {"id": "exp_close", "text": "2026-08-10", "value": None, "type": "date"},
                        {"id": "act_close", "text": "2026-08-12", "value": None, "type": "date"},
                        {"id": "owner", "text": "Rahul Verma", "value": None, "type": "people"},
                        {"id": "curr", "text": "USD", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "deal_108",
                    "name": "AgriCrop Precision Crop Health Drone Survey",
                    "updated_at": "2026-08-05T08:30:00Z",
                    "column_values": [
                        {"id": "client", "text": "AgriCrop Bio", "value": None, "type": "text"},
                        {"id": "sector", "text": "Agriculture", "value": None, "type": "status"},
                        {"id": "stage", "text": "Proposal", "value": None, "type": "status"},
                        {"id": "value", "text": "invalid_val", "value": None, "type": "numbers"},
                        {"id": "prob", "text": "50%", "value": "50", "type": "numbers"},
                        {"id": "exp_close", "text": "TBD / Next month", "value": None, "type": "date"},
                        {"id": "act_close", "text": None, "value": None, "type": "date"},
                        {"id": "owner", "text": "Priya Nair", "value": None, "type": "people"},
                        {"id": "curr", "text": "USD", "value": None, "type": "text"}
                    ]
                }
            ]
        else:
            return [
                {
                    "id": "wo_201",
                    "name": "WO-2026-089",
                    "updated_at": "2026-08-20T11:00:00Z",
                    "column_values": [
                        {"id": "client", "text": "Adani Green Energy", "value": None, "type": "text"},
                        {"id": "project", "text": "Khavda Solar Park Phase 1 Mapping", "value": None, "type": "text"},
                        {"id": "sector", "text": "Energy", "value": None, "type": "status"},
                        {"id": "status", "text": "Completed", "value": None, "type": "status"},
                        {"id": "start_date", "text": "2026-07-05", "value": None, "type": "date"},
                        {"id": "due_date", "text": "2026-07-25", "value": None, "type": "date"},
                        {"id": "comp_date", "text": "2026-07-22", "value": None, "type": "date"},
                        {"id": "contract_val", "text": "$125,000", "value": "125000", "type": "numbers"},
                        {"id": "actual_cost", "text": "$68,400", "value": "68400", "type": "numbers"},
                        {"id": "pilot", "text": "Capt. Vikram Singh", "value": None, "type": "people"},
                        {"id": "location", "text": "Kutch, Gujarat", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "wo_202",
                    "name": "WO-2026-090",
                    "updated_at": "2026-08-28T15:10:00Z",
                    "column_values": [
                        {"id": "client", "text": "Vedanta Resources", "value": None, "type": "text"},
                        {"id": "project", "text": "Lanjigarh Bauxite Stockpile Audit", "value": None, "type": "text"},
                        {"id": "sector", "text": "Mining", "value": None, "type": "status"},
                        {"id": "status", "text": "In Progress", "value": None, "type": "status"},
                        {"id": "start_date", "text": "2026-08-01", "value": None, "type": "date"},
                        {"id": "due_date", "text": "2026-09-10", "value": None, "type": "date"},
                        {"id": "comp_date", "text": None, "value": None, "type": "date"},
                        {"id": "contract_val", "text": "210,000 USD", "value": "210000", "type": "numbers"},
                        {"id": "actual_cost", "text": "112,000", "value": "112000", "type": "numbers"},
                        {"id": "pilot", "text": "Suresh Raina", "value": None, "type": "people"},
                        {"id": "location", "text": "Kalahandi, Odisha", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "wo_203",
                    "name": "WO-2026-091",
                    "updated_at": "2026-08-14T09:20:00Z",
                    "column_values": [
                        {"id": "client", "text": "JSW Steel Ltd.", "value": None, "type": "text"},
                        {"id": "project", "text": "Toranagallu Complex 3D Orthomosaic", "value": None, "type": "text"},
                        {"id": "sector", "text": "Mining & Metals", "value": None, "type": "status"},
                        {"id": "status", "text": "Scheduled", "value": None, "type": "status"},
                        {"id": "start_date", "text": "01-09-2026", "value": None, "type": "date"},
                        {"id": "due_date", "text": "30-09-2026", "value": None, "type": "date"},
                        {"id": "comp_date", "text": None, "value": None, "type": "date"},
                        {"id": "contract_val", "text": "$180,000", "value": "180000", "type": "numbers"},
                        {"id": "actual_cost", "text": "0", "value": "0", "type": "numbers"},
                        {"id": "pilot", "text": "Capt. Vikram Singh", "value": None, "type": "people"},
                        {"id": "location", "text": "Ballari, Karnataka", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "wo_204",
                    "name": "WO-2026-092",
                    "updated_at": "2026-08-19T13:40:00Z",
                    "column_values": [
                        {"id": "client", "text": "Tata Power", "value": None, "type": "text"},
                        {"id": "project", "text": "Mundra UMPP Transmission Corridor", "value": None, "type": "text"},
                        {"id": "sector", "text": "Utilities", "value": None, "type": "status"},
                        {"id": "status", "text": "Delayed", "value": None, "type": "status"},
                        {"id": "start_date", "text": "2026-07-10", "value": None, "type": "date"},
                        {"id": "due_date", "text": "2026-08-15", "value": None, "type": "date"},
                        {"id": "comp_date", "text": None, "value": None, "type": "date"},
                        {"id": "contract_val", "text": "90000", "value": "90000", "type": "numbers"},
                        {"id": "actual_cost", "text": "54000", "value": "54000", "type": "numbers"},
                        {"id": "pilot", "text": "Unassigned / Pilot shortage", "value": None, "type": "people"},
                        {"id": "location", "text": "Kutch, Gujarat", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "wo_205",
                    "name": "WO-2026-093",
                    "updated_at": "2026-08-02T10:15:00Z",
                    "column_values": [
                        {"id": "client", "text": "L&T Infrastructure", "value": None, "type": "text"},
                        {"id": "project", "text": "Mumbai Coastal Road Progress Monitoring", "value": None, "type": "text"},
                        {"id": "sector", "text": "Infra", "value": None, "type": "status"},
                        {"id": "status", "text": "Completed", "value": None, "type": "status"},
                        {"id": "start_date", "text": "2026-06-01", "value": None, "type": "date"},
                        {"id": "due_date", "text": "2026-07-31", "value": None, "type": "date"},
                        {"id": "comp_date", "text": "2026-07-29", "value": None, "type": "date"},
                        {"id": "contract_val", "text": "$145,000", "value": "145000", "type": "numbers"},
                        {"id": "actual_cost", "text": "$72,500", "value": "72500", "type": "numbers"},
                        {"id": "pilot", "text": "Rohan Deshmukh", "value": None, "type": "people"},
                        {"id": "location", "text": "Mumbai, Maharashtra", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "wo_206",
                    "name": "WO-2026-094",
                    "updated_at": "2026-08-26T18:00:00Z",
                    "column_values": [
                        {"id": "client", "text": "Adani Green Energy Ltd", "value": None, "type": "text"},
                        {"id": "project", "text": "Rajasthan Solar Plant Thermal Inspection", "value": None, "type": "text"},
                        {"id": "sector", "text": "Solar Energy", "value": None, "type": "status"},
                        {"id": "status", "text": "In Progress", "value": None, "type": "status"},
                        {"id": "start_date", "text": "2026-08-15", "value": None, "type": "date"},
                        {"id": "due_date", "text": "2026-09-20", "value": None, "type": "date"},
                        {"id": "comp_date", "text": None, "value": None, "type": "date"},
                        {"id": "contract_val", "text": "$110,000", "value": "110000", "type": "numbers"},
                        {"id": "actual_cost", "text": "$45,000", "value": "45000", "type": "numbers"},
                        {"id": "pilot", "text": "Capt. Vikram Singh", "value": None, "type": "people"},
                        {"id": "location", "text": "Bhadla, Rajasthan", "value": None, "type": "text"}
                    ]
                },
                {
                    "id": "wo_207",
                    "name": "WO-2026-095 (Corrupted item)",
                    "updated_at": "2026-08-12T14:20:00Z",
                    "column_values": [
                        {"id": "client", "text": None, "value": None, "type": "text"},
                        {"id": "project", "text": "Unnamed survey site", "value": None, "type": "text"},
                        {"id": "sector", "text": "Unknown Sector", "value": None, "type": "status"},
                        {"id": "status", "text": None, "value": None, "type": "status"},
                        {"id": "start_date", "text": None, "value": None, "type": "date"},
                        {"id": "due_date", "text": None, "value": None, "type": "date"},
                        {"id": "comp_date", "text": None, "value": None, "type": "date"},
                        {"id": "contract_val", "text": "-5000", "value": "-5000", "type": "numbers"},
                        {"id": "actual_cost", "text": None, "value": None, "type": "numbers"},
                        {"id": "pilot", "text": None, "value": None, "type": "people"},
                        {"id": "location", "text": None, "value": None, "type": "text"}
                    ]
                }
            ]

monday_client = MondayClient()
