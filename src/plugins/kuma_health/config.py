from pydantic import BaseModel


class Config(BaseModel):
    """Existing Kuma Push monitor for this deployment; empty disables checks."""

    kuma_push_url: str = ""
