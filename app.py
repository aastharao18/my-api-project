from flask import Flask, request
import psycopg2
import bcrypt
import math
import os
from dotenv import load_dotenv
load_dotenv()

from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity,
    create_refresh_token
)

from flask_smorest import Api, Blueprint
from flask.views import MethodView

app = Flask(__name__)

# =========================
# 🔐 CONFIG
# =========================
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "secret")

app.config["API_TITLE"] = "My API"
app.config["API_VERSION"] = "v1"
app.config["OPENAPI_VERSION"] = "3.0.3"

jwt = JWTManager(app)
api = Api(app)

# =========================
# 🔌 DATABASE (FIXED FOR RENDER)
# =========================
def get_conn():
    url = os.environ.get("DATABASE_URL")
    print("DB URL:", url)  # DEBUG

    if not url:
        raise Exception("DATABASE_URL not set")

    #  FIX for Render
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return psycopg2.connect(url)


# =========================
# 📦 BLUEPRINT
# =========================
blp = Blueprint("API", "api", description="All APIs")


# =========================
# 🔐 LOGIN (FIXED)
# =========================
@blp.route("/login")
class Login(MethodView):
    def post(self):
        try:
            data = request.get_json()

            email = data.get("email")
            password = data.get("password")

            conn = get_conn()
            cur = conn.cursor()

            cur.execute(
                "SELECT password, role FROM customers WHERE email=%s;",
                (email,)
            )
            user = cur.fetchone()

            cur.close()
            conn.close()

            if not user:
                return {"error": "User not found"}, 404

            stored_password = user[0]

            # ❗ NULL password check
            if not stored_password:
                return {"error": "Password not set"}, 400

            #  FIX: always convert to bytes
           #  HANDLE BYTEA CORRECTLY
            if isinstance(stored_password, memoryview):
                stored_password = stored_password.tobytes()

            if isinstance(stored_password, str):
                stored_password = stored_password.encode("utf-8")

            if not bcrypt.checkpw(password.encode("utf-8"), stored_password):
                return {"error": "Wrong password"}, 401

            identity = {
                "email": email,
                "role": user[1]
            }

            return {
                "access_token": create_access_token(identity=identity),
                "refresh_token": create_refresh_token(identity=identity)
            }

        except Exception as e:
            print("LOGIN ERROR:", str(e))
            return {"error": str(e)}, 500


# =========================
# 🔁 REFRESH
# =========================
@blp.route("/refresh")
class Refresh(MethodView):

    @jwt_required(refresh=True)
    def post(self):
        identity = get_jwt_identity()
        return {"access_token": create_access_token(identity=identity)}


# =========================
# 👤 REGISTER (FIXED)
# =========================
@blp.route("/customers")
class Customer(MethodView):

    def post(self):
        try:
            data = request.json

            if not data.get("email") or not data.get("password"):
                return {"error": "Invalid input"}, 400

            conn = get_conn()
            cur = conn.cursor()

            # check duplicate
            cur.execute("SELECT id FROM customers WHERE email=%s;", (data["email"],))
            if cur.fetchone():
                return {"error": "Email exists"}, 400

            #  HASH FIX
            hashed = bcrypt.hashpw(
                    data["password"].encode("utf-8"),
                    bcrypt.gensalt()
                ).decode("utf-8")          # FORCE STRING (important)             # step 2  extra safety#  VERY IMPORTANT

            cur.execute(
                        "INSERT INTO customers (name,email,phone,password,role) VALUES (%s,%s,%s,%s,%s)",
                    (
                        data.get("name"),
                        data["email"],
                        data.get("phone"),
                        hashed,
                        "user"
                    )
                )

            conn.commit()
            cur.close()
            conn.close()

            return {"message": "Customer created"}

        except Exception as e:
            print("REGISTER ERROR:", str(e))
            return {"error": str(e)}, 500


    @jwt_required()
    def get(self):
        query = request.args.get("q", "")
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 5))
        offset = (page - 1) * limit

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*) FROM customers
            WHERE name ILIKE %s OR email ILIKE %s;
        """, (f"%{query}%", f"%{query}%"))

        total = cur.fetchone()[0]

        cur.execute("""
            SELECT id,name,email,phone FROM customers
            WHERE name ILIKE %s OR email ILIKE %s
            LIMIT %s OFFSET %s;
        """, (f"%{query}%", f"%{query}%", limit, offset))

        rows = cur.fetchall()

        cur.close()
        conn.close()

        return {
            "page": page,
            "total_pages": math.ceil(total / limit),
            "data": [
                {"id": r[0], "name": r[1], "email": r[2], "phone": r[3]}
                for r in rows
            ]
        }


# =========================
# 🛒 PRODUCTS
# =========================
@blp.route("/products")
class Product(MethodView):

    @jwt_required()
    def post(self):
        user = get_jwt_identity()

        if user["role"] != "admin":
            return {"error": "Admin only"}, 403

        data = request.json

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT id FROM products WHERE sku=%s;", (data["sku"],))
        if cur.fetchone():
            return {"error": "SKU exists"}, 400

        cur.execute(
            "INSERT INTO products (name,price,sku,quantity) VALUES (%s,%s,%s,%s)",
            (data["name"], data["price"], data["sku"], data["quantity"])
        )

        conn.commit()
        cur.close()
        conn.close()

        return {"message": "Product added"}


    @jwt_required()
    def get(self):
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT * FROM products;")
        rows = cur.fetchall()

        cur.close()
        conn.close()

        return {
            "data": [
                {"id": r[0], "name": r[1], "price": r[2], "sku": r[3], "quantity": r[4]}
                for r in rows
            ]
        }


# =========================
# 📦 ORDERS
# =========================
@blp.route("/orders")
class Order(MethodView):

    @jwt_required()
    def post(self):
        data = request.json
        user = get_jwt_identity()

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT id FROM customers WHERE email=%s;", (user["email"],))
        user_data = cur.fetchone()

        if not user_data:
            return {"error": "User not found"}, 404

        user_id = user_data[0]
        products = data.get("products", [])

        try:
            for item in products:
                cur.execute("SELECT quantity FROM products WHERE sku=%s;", (item["sku"],))
                stock = cur.fetchone()

                if not stock or stock[0] < item["qty"]:
                    return {"error": "Stock issue"}, 400

            cur.execute(
                "INSERT INTO orders (user_id) VALUES (%s) RETURNING id;",
                (user_id,)
            )
            order_id = cur.fetchone()[0]

            for item in products:
                cur.execute(
                    "UPDATE products SET quantity=quantity-%s WHERE sku=%s;",
                    (item["qty"], item["sku"])
                )

                cur.execute(
                    "INSERT INTO order_product VALUES (%s,%s,%s)",
                    (order_id, item["sku"], item["qty"])
                )

            conn.commit()

        except Exception as e:
            conn.rollback()
            return {"error": str(e)}, 500

        finally:
            cur.close()
            conn.close()

        return {"order_id": order_id}


# =========================
# REGISTER
# =========================
api.register_blueprint(blp)



# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)