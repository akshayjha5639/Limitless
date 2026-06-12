"""
Limitless — App Configuration
Loads environment variables from .env and exposes them as a typed Settings object.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # loads .env from project root


class Settings:
    # Gemini
    GEMINI_API_KEY:  str = os.getenv("GEMINI_API_KEY", "")

    # App
    APP_ENV:  str = os.getenv("APP_ENV",  "development")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")

    # PDF branding defaults
    PDF_PRIMARY_COLOR: str = os.getenv("PDF_PRIMARY_COLOR", "#1E6FD9")
    PDF_ACCENT_COLOR:  str = os.getenv("PDF_ACCENT_COLOR",  "#00C2CB")
    PDF_FOOTER_NOTE:   str = os.getenv("PDF_FOOTER_NOTE",   "Limitless Platform • v1.0")

    def validate(self):
        """Call on startup to catch missing critical vars early."""
        if not self.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Copy .env.example to .env and add your key from https://aistudio.google.com/app/apikey"
            )


settings = Settings()
