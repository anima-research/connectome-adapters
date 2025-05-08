from pydantic import BaseModel
from typing import Any, Dict, Optional

class RequestEvent(BaseModel):
    """Request event model"""
    adapter_type: str
    request_id: str
    data: Optional[Dict[str, Any]] = None
