from fastapi import APIRouter, Depends, HTTPException, Response, status  # type: ignore
from db import get_db  
from models.routeModel import LoginModel, RegisterModel
from libs.validator import Validator
import bcrypt # type: ignore #
from model import User
from libs.security import create_access_token, hash_password, verify_token, get_cookie_token
auth_router = APIRouter(prefix="/api/auth", tags=["auth"]) 

@auth_router.post("/login", status_code=status.HTTP_200_OK)
async def login(login_data: LoginModel, response: Response, db=Depends(get_db)): 
    if not Validator.is_valid_email(login_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid email address"
        ) 
    
    if not Validator.is_strong_password(login_data.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a strong password"
        ) 
    

    is_authenticated, user = Validator.authenticate_user(login_data.email, login_data.password, db)
    if not is_authenticated or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    access_token = create_access_token(data={"user_id": user.id})
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="lax", max_age=60 * 60 * 24)
    
    return {"message": "Login successful", "access_token": access_token, "token_type": "cookie", "data" : {"user": {"email": login_data.email, "userId": user.id }}} 


@auth_router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(register_data: RegisterModel, db=Depends(get_db)):
    if not Validator.is_valid_email(register_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid email address"
        ) 
    if not Validator.is_strong_password(register_data.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a strong password"
        )
    if Validator.user_exists(register_data.email, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists"
        ) 
    
    hashedPassword = hash_password(register_data.password)

    try:
        new_user = User(
            email=register_data.email,
            password=hashedPassword,
            first_name=register_data.first_name,
            last_name=register_data.last_name
        )
        db.add(new_user)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the user"
        ) from e

    return {
        "message": "User registered successfully",
        "user": {
            "email": new_user.email,
            "first_name": new_user.first_name,
            "last_name": new_user.last_name
        }
    }


@auth_router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"message": "Logout successful"}

@auth_router.get("/user", status_code=status.HTTP_200_OK)
async def get_user_info(token: str = Depends(get_cookie_token), db=Depends(get_db)):
    token_data = verify_token(token)
    print(token_data)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name
    }