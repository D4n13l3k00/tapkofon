from pydantic import BaseModel, ConfigDict, Field


class CommonSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pic_quality: int = Field(default=80, ge=1, le=100)
    pic_format: str = Field(default="jpeg", pattern="^(jpeg|png|webp)$")
    recognize_lang: str = Field(
        default="ru-RU",
        min_length=2,
        max_length=64,
        pattern=r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*$",
    )
    recognize_enabled: bool = True
    msg_regex_tme: bool = True


class AccessPolicy(BaseModel):
    password_hash: str = ""
    revision: int = 0

    @property
    def enabled(self) -> bool:
        return bool(self.password_hash)
