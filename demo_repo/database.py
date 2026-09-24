"""
Database Access Layer (Legacy 2018)
Simulates database transactions and records.
"""

from typing import Any, Dict, List, Optional


class Database:
    """Mock database connection for legacy services."""

    def __init__(self):
        self.records: Dict[str, Dict[str, Any]] = {}
        self.transactions: List[Dict[str, Any]] = []

    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Executes a simulated query."""
        return list(self.records.values())

    def save_transaction(self, tx_id: str, data: Dict[str, Any]) -> bool:
        self.transactions.append({"id": tx_id, **data})
        self.records[tx_id] = data
        return True

    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        return self.records.get(tx_id)


db = Database()
