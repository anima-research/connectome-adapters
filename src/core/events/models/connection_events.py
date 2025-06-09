from pydantic import BaseModel

class ConnectionEvent(BaseModel):
    """Connection status event model"""
    adapter_type: str
