from pydantic import BaseModel


class CurrentUser(BaseModel):
    user_id: str
    username: str | None
    email: str | None
    display_name: str
    role: str

