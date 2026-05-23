from flask import Flask, render_template, request, redirect, url_for, session
from flask_dance.contrib.google import make_google_blueprint, google
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename
from datetime import datetime
from PIL import Image
from sqlalchemy import or_
import os
from functools import wraps
from dotenv import load_dotenv
from db import (
    SessionLocal, Unit, Property, Guest, Booking,
    add_property, add_guest, add_booking, add_unit, get_free_slots, delete_property, delete_booking
)

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY")
@app.context_processor
def inject_google_status():
    return dict(google=google)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

blueprint = make_google_blueprint(
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    scope=[
        "openid", 
        "https://www.googleapis.com/auth/userinfo.email", 
        "https://www.googleapis.com/auth/userinfo.profile"
    ],
    offline=True,
    reprompt_consent=True
)
app.register_blueprint(blueprint, url_prefix="/login")

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not google.authorized:
            return redirect(url_for("google.login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def index():
    search_query = request.args.get("search", "").strip()
    min_price = request.args.get("min_price", type=int)
    max_price = request.args.get("max_price", type=int)
    capacity = request.args.get("capacity", type=int)

    with SessionLocal() as session:
        query = session.query(Unit).options(joinedload(Unit.property))
        if search_query:
            search_pattern = f"%{search_query}%"
            conditions = [
                Unit.title.ilike(search_pattern),
                Property.name.ilike(search_pattern),
                Property.address.ilike(search_pattern)
            ]
            query = query.join(Property).filter(or_(*conditions))
            

        if min_price is not None:
            query = query.filter(Unit.price_per_night >= min_price)
            

        if max_price is not None:
            query = query.filter(Unit.price_per_night <= max_price)
            

        if capacity is not None:
            query = query.filter(Unit.capacity >= capacity)

        units = query.all()

    return render_template(
        "index.html", 
        units=units,
        search=search_query,
        min_price=min_price if min_price is not None else "",
        max_price=max_price if max_price is not None else "",
        capacity=capacity if capacity is not None else ""
    )

@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    user_info = google.get("/oauth2/v2/userinfo").json()
    email = user_info["email"]

    if request.method == "POST":
        if request.form.get("property_id"):
            delete_property(request.form.get("property_id"))
        elif request.form.get("id_booking"):
            delete_booking(request.form.get("id_booking"))
        return redirect(url_for("dashboard"))

    with SessionLocal() as session:
        my_properties = session.query(Property).filter_by(owner_email=email).options(
            joinedload(Property.units).joinedload(Unit.bookings).joinedload(Booking.guest)
        ).all()

        my_trips = session.query(Booking).join(Guest).filter(Guest.contact == email).options(
            joinedload(Booking.unit).joinedload(Unit.property)
        ).all()

        return render_template(
            "dashboard.html", 
            properties=my_properties, 
            my_trips=my_trips,
            user_email=email
        )
    
@app.route("/book/<int:unit_id>", methods=["GET", "POST"])
@login_required
def book(unit_id):
    user_info = google.get("/oauth2/v2/userinfo").json()
    email = user_info["email"]

    with SessionLocal() as session:
        unit = session.query(Unit).options(joinedload(Unit.bookings)).get(unit_id)
        if not unit:
            return "Объект не найден", 404

        booked_dates = []
        for b in unit.bookings:
            booked_dates.append({
                "from": b.check_in.strftime("%Y-%m-%d"),
                "to": b.check_out.strftime("%Y-%m-%d")
            })
            
        free_slots = get_free_slots(unit.bookings)

    if request.method == "POST":
        name = request.form.get("name")
        surname = request.form.get("surname")
        check_in_str = request.form.get("check_in")
        check_out_str = request.form.get("check_out")
        
        try:
            check_in = datetime.strptime(check_in_str, "%Y-%m-%d").date()
            check_out = datetime.strptime(check_out_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return "Некорректный формат дат", 400

        if check_in >= check_out:
            return "Дата выезда должна быть позже даты заезда", 400
        guest = add_guest(name, surname, email)
        booking = add_booking(guest.id, unit_id, check_in, check_out)
        
        if booking == 0:
            return "Выбранные даты уже заняты", 400
            
        return redirect(url_for("dashboard"))

    return render_template(
        "booking.html", 
        unit=unit, 
        free_slots=free_slots, 
        booked_dates=booked_dates,
        user_info=user_info
    )

@app.route("/add_property", methods=["GET", "POST"])
@login_required
def add_property_page():
    if request.method == "POST":
        user_info = google.get("/oauth2/v2/userinfo").json()
        email = user_info["email"]

        name = request.form["name"]
        address = request.form["address"]
        description = request.form["description"]
        type_ = request.form.get("type")
        price = request.form.get("price", 50.0)
        capacity = request.form.get("capacity", 2)

        file = request.files.get("image")
        filename = None
        if file and file.filename:
                
                filename = secure_filename(file.filename)
                path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(path)
                img = Image.open(path)
                target_width = 800
                target_height = 500

                width, height = img.size

                target_ratio = target_width / target_height
                img_ratio = width / height

                if img_ratio > target_ratio:
                    new_width = int(height * target_ratio)

                    left = (width - new_width) // 2
                    top = 0
                    right = left + new_width
                    bottom = height

                else:
                    new_height = int(width / target_ratio)

                    left = 0
                    top = (height - new_height) // 2
                    right = width
                    bottom = top + new_height

                img = img.crop((left, top, right, bottom))

                img = img.resize((target_width, target_height))

                img.save(path)



        prop = add_property(name, address, description, filename, owner_email=email)
        add_unit(prop.id, type_, int(capacity), float(price))
        
        return redirect("/dashboard")

    return render_template("add_property.html")

@app.route("/logout")
def logout():
    session.clear() 
    return redirect(url_for("index"))

@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


    