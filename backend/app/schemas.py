from pydantic import BaseModel
from datetime import datetime

class SellerAccountIn(BaseModel):
    name: str
    region: str = "eu"
    marketplaces: str = "DE,FR,IT,ES"
    refresh_token: str
    lwa_client_id: str | None = None
    lwa_client_secret: str | None = None
    aws_access_key: str | None = None
    aws_secret_key: str | None = None
    role_arn: str | None = None

class SellerAccountOut(BaseModel):
    id: int
    name: str
    region: str
    marketplaces: str
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True
