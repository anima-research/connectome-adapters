from pydantic import BaseModel
from typing import List, Optional, Union

class SentMessageData(BaseModel):
    """Sent message data model"""
    message_ids: List[str]

class FetchedAttachmentData(BaseModel):
    """Fetched attachment data model"""
    content: str

class ReadFileData(BaseModel):
    """Read file data model"""
    file_content: str

class ViewDirectoryData(BaseModel):
    """View directory data model"""
    directories: Optional[List[str]] = []
    files: Optional[List[str]] = []

class ErrorData(BaseModel):
    """Error data model"""
    error: Optional[str] = None

class RequestEvent(BaseModel):
    """Request event model"""
    adapter_type: str
    request_id: str
    internal_request_id: Optional[str] = None
    data: Optional[
        Union[
            SentMessageData,
            FetchedAttachmentData,
            ReadFileData,
            ViewDirectoryData,
            ErrorData
        ]
    ] = None
