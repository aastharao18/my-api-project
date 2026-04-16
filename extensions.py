from flask_jwt_extended import JWTManager
from flask_smorest import Api
from flask_sqlalchemy import SQLAlchemy

jwt = JWTManager()
api = Api()
db = SQLAlchemy()