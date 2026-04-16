from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint
from models.user import UserModel
from extensions import db
import bcrypt

blp = Blueprint("Auth", "auth", description="Authentication APIs")