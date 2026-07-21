from pydantic import BaseModel


class AttachmentItem(BaseModel):
    attachment_id: str
    file_name: str
    file_path: str
    mime_type: str
    file_size: int
    parse_status: str


class DeleteAttachmentRequest(BaseModel):
    attachment_id: str


class DeleteAttachmentResult(BaseModel):
    attachment_id: str
    deleted: bool
