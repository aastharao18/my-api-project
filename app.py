from flask import Flask, request
import psycopg2
import bcrypt
import math
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, create_refresh_token
from flask_smorest import Api, Blueprint
from flask.views import MethodView
import os

app = Flask(__name__)

# =========================
# 🔐 CONFIG
# =========================
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "secret")

app.config["API_TITLE"] = "My API"
app.config["API_VERSION"] = "v1"
app.config["OPENAPI_VERSION"] = "3.0.3"
app.config["OPENAPI_SWAGGER_UI_PATH"] = "/swagger"

app.config["OPENAPI_SECURITY_SCHEMES"] = {
    "BearerAuth": {
        "type": "http",
        "scheme": "bearer"
    }
}

jwt = JWTManager(app)
api = Api(app)

# =========================
# 🔌 DB (FIXED FOR RENDER)
# =========================
def get_conn():
    url = os.environ.get("DATABASE_URL")

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return psycopg2.connect(url)


# =========================
# 📦 BLUEPRINT
# =========================
blp = Blueprint("API", "api", description="All APIs")


# =========================
# 🔐 LOGIN
# =========================
@blp.route("/login")
class Login(MethodView):
    def post(self):
        try:
            data = request.get_json()

            conn = get_conn()
            cur = conn.cursor()

            cur.execute("SELECT password, role FROM customers WHERE email=%s;", (data["email"],))
            user = cur.fetchone()

            cur.close()
            conn.close()

            if not user:
                return {"error": "User not found"}, 404

            stored_password = user[0]

            # SAFE conversion
            if isinstance(stored_password, str):
                stored_password = stored_password.encode()

            if not bcrypt.checkpw(data["password"].encode(), stored_password):
                return {"error": "Wrong password"}, 401

            token = create_access_token(identity={
                "email": data["email"],
                "role": user[1]
            })

            refresh = create_refresh_token(identity={
                "email": data["email"],
                "role": user[1]
            })

            return {
                "access_token": token,
                "refresh_token": refresh
            }

        except Exception as e:
            print("LOGIN ERROR:", str(e))
            return {"error": "Server error"}, 500


# =========================
# 🔁 REFRESH
# =========================
@blp.route("/refresh")
class Refresh(MethodView):

    @jwt_required(refresh=True)
    def post(self):
        identity = get_jwt_identity()
        new_token = create_access_token(identity=identity)
        return {"access_token": new_token}


# =========================
# 👤 CUSTOMERS
# =========================
@blp.route("/customers")
class Customer(MethodView):

    def post(self):
        data = request.json

        if not data.get("email") or not data.get("password"):
            return {"success": False, "message": "Invalid input"}, 400

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT * FROM customers WHERE email=%s;", (data["email"],))
        if cur.fetchone():
            return {"success": False, "message": "Email exists"}, 400

        hashed = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt())

        cur.execute(
            "INSERT INTO customers (name,email,phone,password) VALUES (%s,%s,%s,%s)",
            (data["name"], data["email"], data["phone"], hashed.decode())
        )

        conn.commit()
        cur.close()
        conn.close()

        return {"success": True, "message": "Customer added"}

    @jwt_required()
    @blp.doc(security=[{"BearerAuth": []}])
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
            "success": True,
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
    @blp.doc(security=[{"BearerAuth": []}])
    def post(self):
        user = get_jwt_identity()

        if user["role"] != "admin":
            return {"error": "Admin only"}, 403

        data = request.json

        if data["price"] <= 0:
            return {"error": "Invalid price"}, 400

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT * FROM products WHERE sku=%s;", (data["sku"],))
        if cur.fetchone():
            return {"error": "SKU exists"}, 400

        cur.execute(
            "INSERT INTO products (name,price,sku,quantity) VALUES (%s,%s,%s,%s)",
            (data["name"], data["price"], data["sku"], data["quantity"])
        )

        conn.commit()
        cur.close()
        conn.close()

        return {"success": True, "message": "Product added"}

    @jwt_required()
    def get(self):
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT * FROM products;")
        rows = cur.fetchall()

        cur.close()
        conn.close()

        return {
            "success": True,
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
        user_email = user["email"]

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT id FROM customers WHERE email=%s;", (user_email,))
        user = cur.fetchone()

        if not user:
            return {"error": "User not found"}, 404

        user_id = user[0]
        products = data.get("products")

        try:
            for item in products:
                if item["qty"] <= 0:
                    return {"error": "Invalid qty"}, 400

                cur.execute("SELECT quantity FROM products WHERE sku=%s;", (item["sku"],))
                stock = cur.fetchone()

                if not stock or stock[0] < item["qty"]:
                    return {"error": "Stock issue"}, 400

            cur.execute("INSERT INTO orders (user_id) VALUES (%s) RETURNING id;", (user_id,))
            order_id = cur.fetchone()[0]

            for item in products:
                cur.execute("UPDATE products SET quantity=quantity-%s WHERE sku=%s;",
                            (item["qty"], item["sku"]))
                cur.execute("INSERT INTO order_product VALUES (%s,%s,%s)",
                            (order_id, item["sku"], item["qty"]))

            conn.commit()

        except Exception as e:
            conn.rollback()
            return {"error": str(e)}, 500

        finally:
            cur.close()
            conn.close()

        return {"success": True, "order_id": order_id}


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