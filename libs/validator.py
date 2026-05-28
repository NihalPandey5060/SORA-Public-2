from datetime import datetime
import re 
from model import User
from libs.security import verify_password
class Validator:
    
    @staticmethod
    def is_valid_email(email: str) -> bool:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None 
    
    @staticmethod
    def is_strong_password(password: str) -> bool:
        if len(password) < 8:
            return False
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(not c.isalnum() for c in password)
        return has_upper and has_lower and has_digit and has_special 
    
    @staticmethod
    def is_valid_username(username: str) -> bool:
        
        pattern = r'^[a-zA-Z0-9_]{3,30}$'
        return re.match(pattern, username) is not None 
    
    @staticmethod
    def is_valid_phone_number(phone_number: str) -> bool:
        
        pattern = r'^\+?[1-9]\d{1,14}$'
        return re.match(pattern, phone_number) is not None  
    
    @staticmethod
    def is_valid_url(url: str) -> bool:
        
        pattern = r'^(https?|ftp)://[^\s/$.?#].[^\s]*$'
        return re.match(pattern, url) is not None
    
    @staticmethod
    def is_valid_date(date_str: str, date_format: str = "%Y-%m-%d") -> bool:
        
        try:
            datetime.strptime(date_str, date_format)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def authenticate_user(email: str, plain_password: str, db) -> tuple[bool, User | None]:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return False, None
        return (verify_password(plain_password, user.password) , user)
    
    @staticmethod
    def user_exists(email: str, db) -> bool:
        user = db.query(User).filter(User.email == email).first()
        return user is not None