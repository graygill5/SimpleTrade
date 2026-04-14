from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"

# -------- DATABASE --------
def get_db():
    return sqlite3.connect("app.db")

def init_db():
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    db.commit()
    db.close()

init_db()

# -------- LOGIN --------
@app.route("/", methods=["GET", "POST"])
def login():
    message = request.args.get("message", "")
    error = ""

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        if username == "" or password == "":
            error = "Please enter both username and password."
            return render_template("login.html", error=error, message=message)

        db = get_db()
        cur = db.cursor()

        cur.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        )
        user = cur.fetchone()
        db.close()

        if user:
            session["user"] = username
            return redirect("/dashboard")
        else:
            error = "Invalid username or password."

    return render_template("login.html", error=error, message=message)

# -------- SIGNUP --------
@app.route("/signup", methods=["POST"])
def signup():
    username = request.form["username"].strip()
    password = request.form["password"].strip()

    if username == "" or password == "":
        return render_template("login.html", error="Username and password cannot be empty.")

    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT * FROM users WHERE username=?", (username,))
    existing_user = cur.fetchone()

    if existing_user:
        db.close()
        return render_template("login.html", error="That username is already taken.")

    cur.execute(
        "INSERT INTO users (username, password) VALUES (?, ?)",
        (username, password)
    )
    db.commit()
    db.close()

    return redirect("/?message=Account created successfully. Please log in.")

# -------- DASHBOARD --------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    return render_template("dashboard.html", username=session["user"])

# -------- LOGOUT --------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/?message=You have been logged out.")

# -------- RUN --------
if __name__ == "__main__":
    app.run(debug=True)