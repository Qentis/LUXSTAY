from datetime import datetime, date, timedelta
from sqlalchemy import create_engine, Column, Integer, DateTime, String, Text, ForeignKey, Date, select, exists
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship
from sqlalchemy.exc import IntegrityError
import os


engine = create_engine("sqlite:///booking.db", echo=True)


class Base(DeclarativeBase):
    pass

class Guest(Base):
    __tablename__ = "guests"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    contact = Column(String(255), nullable=False, unique=True)


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    address = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    image = Column(String)
    units = relationship("Unit", back_populates="property")
    owner_email = Column(String)

class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)

    title = Column(String(150), nullable=False)
    capacity = Column(Integer, nullable=False)  
    price_per_night = Column(Integer, nullable=False)

    property = relationship("Property", back_populates="units")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)

    guest_id = Column(Integer, ForeignKey("guests.id"), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)

    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)

    status = Column(String(50), default="pending") 
    created_at = Column(DateTime, default=datetime.utcnow)

    guest = relationship("Guest", backref="bookings")
    unit = relationship("Unit", backref="bookings")


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)



def add_guest(name, surname, contact):
    with SessionLocal() as session:
        try:
            guest = session.query(Guest).filter_by(contact=contact).first()

            if guest:
                print("Гость уже существует")
                return guest

            guest = Guest(
                name=name,
                surname=surname,
                contact=contact
            )

            session.add(guest)
            session.commit()
            session.refresh(guest)

            print("Гость создан")
            return guest

        except Exception as e:
            session.rollback()
            print("Ошибка:", e)
            return None

def add_property(name, address, description="", image=None, owner_email=""): 
    with SessionLocal() as session:
        try:
            prop = Property(
                name=name,
                address=address,
                description=description,
                image=image,
                owner_email=owner_email
            )
            session.add(prop)
            session.commit()
            session.refresh(prop)  

            print(f"Объект '{name}' добавлен.")
            return prop            

        except Exception as e:
            session.rollback()
            print(f"Ошибка: {e}")
            return None

def add_unit(property_id, title, capacity, price_per_night):
    with SessionLocal() as session:
        try:
            unit = Unit(
                property_id=property_id,
                title=title,
                capacity=capacity,
                price_per_night=price_per_night
            )
            session.add(unit)
            session.commit()
            print(f"Юнит '{title}' добавлен.")
        except Exception as e:
            session.rollback()
            print(f"Ошибка: {e}")

def add_booking(guest_id, unit_id, check_in, check_out): 

    with SessionLocal() as session:

        if not check_booking(check_in, check_out, unit_id):
            print("Даты заняты")
            return 0

        try:
            booking = Booking(
                guest_id=guest_id,
                unit_id=unit_id,
                check_in=check_in,
                check_out=check_out,
                status="confirmed"
            )

            session.add(booking)
            session.commit()

            print("Бронирование создано.")

        except Exception as e:
            session.rollback()
            print(f"Ошибка при бронировании: {e}")

def check_booking(check_in, check_out, unit_id):

    stmt = select(
        exists().where(
            Booking.unit_id == unit_id,
            Booking.check_in < check_out,
            Booking.check_out > check_in
        )
    )

    with SessionLocal() as session:
        is_taken = session.scalar(stmt)

    return not is_taken

def get_free_slots(bookings, days_ahead=30):
    sorted_bookings = sorted(bookings, key=lambda b: b.check_in)
    free_slots =[]
    current_date = date.today()
    end_date = current_date + timedelta(days=days_ahead)
    
    for b in sorted_bookings:
        if b.check_in > current_date:
            free_slots.append((current_date, b.check_in - timedelta(days=1)))
        if b.check_out > current_date:
            current_date = b.check_out + timedelta(days=1)
            
    if current_date < end_date:
        free_slots.append((current_date, end_date))
    return free_slots

def delete_property(id_property):
    with SessionLocal() as session:
        property = session.query(Property).filter_by(id=id_property).first()
        unit = session.query(Unit).filter_by(property_id=id_property).first()
        if unit:
            session.delete(unit)
        if property:
            image = property.image
            os.remove(f"static/uploads/{image}")
            session.delete(property)
        session.commit()

def delete_booking(id):
    with SessionLocal() as session:
        booking = session.query(Booking).filter_by(id=id).first()
        session.delete(booking)
        session.commit()


if __name__ == "__main__":
    Base.metadata.create_all(engine)
 
