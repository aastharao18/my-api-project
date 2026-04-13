from flask_jwt_extended import JWTManager
from flask_smorest import Api
from pymongo import MongoClient

jwt = JWTManager()
api = Api()

mongo = None

def init_mongo(app):
    global mongo
    mongo = MongoClient(app.config["MONGO_URI"]).get_database()