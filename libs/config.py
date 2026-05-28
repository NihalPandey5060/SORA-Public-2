from dotenv import load_dotenv # type: ignore
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "your_default_secret_key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60*24*3)))  # Default: 3 days