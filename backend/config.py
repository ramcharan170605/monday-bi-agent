import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://neondb_owner:npg_QCHxh4n2IrNO@ep-little-pond-a6sl2gzf.us-west-2.aws.neon.tech/neondb?sslmode=require"
    )
    MONDAY_API_TOKEN: str = os.getenv("MONDAY_API_TOKEN", "")
    WORK_ORDERS_BOARD_ID: str = os.getenv("WORK_ORDERS_BOARD_ID", "")
    DEALS_BOARD_ID: str = os.getenv("DEALS_BOARD_ID", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    PORT: int = int(os.getenv("PORT", "8000"))

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
