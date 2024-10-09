from fastapi import FastAPI, Request,Query,Form,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import google.oauth2.id_token;
from google.auth.transport import requests
from google.cloud import firestore
import starlette.status as status
import json
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime,timedelta

app=FastAPI()

firebase_request_adapter = requests.Request()

# Initialize Firestore client with the correct project ID
firestore_db = firestore.Client(project="evproject-417219")

app.mount('/static', StaticFiles(directory='static'), name='static')
templates = Jinja2Templates(directory="templates") 


def getRoomSchedular(user_token):

    rooms = firestore_db.collection('rooms').document(user_token['user_id'])

    if not rooms.get().exists:
        room_data = {
        "room_number":0,
        "room_capacity":0,
        "room_available":"",
        "room_description":"",
        "user_id":""
        }
        firestore_db.collection("rooms").document(user_token['user_id']).set(room_data)
    return rooms

def validateFirebaseToken(id_token):
    if not id_token:
        return None

    user_token = None
    try:
        user_token=google.oauth2.id_token.verify_firebase_token(id_token,firebase_request_adapter)   
    except ValueError as err:
        print(str(err))
    return user_token

def fetch_available_rooms():
    rooms_ref = firestore_db.collection('rooms')
    rooms = rooms_ref.where('room_available', '==', "true").stream()

    available_rooms = []
    index = 1
    for room in rooms:
        room_data = room.to_dict()
        room_data['id'] = room.id
        room_data["index"] = index
        available_rooms.append(room_data)
        index += 1
    return available_rooms

def collection_exist(collection_name):
    try:
        firestore_db.collection(collection_name).get()
        return True
    except Exception as e:
        print(f"Error fetching bookings: {e}")
        return False


@app.post("/filter-query")
async def search(request: Request,dateFrom: str = Form(None)):
    if dateFrom is None:
        return RedirectResponse("/",status_code=status.HTTP_302_FOUND)
    else:  
        selected_date = datetime.strptime(dateFrom, '%Y-%m-%d').date()

        start_of_day = datetime.combine(selected_date, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)
        rooms_ref = firestore_db.collection("rooms")
        user_bookings = []
        allrooms = rooms_ref.stream()
        room_bookings = []
        for room in allrooms:
            room_id = room.id
            room_number = room.get('room_number')
            if room_number:
                # days_ref = rooms_ref.document(room_id).collection("days").where("date_from", "==", datetime.strptime(dateFrom, '%Y-%m-%dT%H:%M').strftime("%Y-%m-%d %H:%M")).stream()
                days_ref = rooms_ref.document(room_id).collection("days")\
                        .where("date_from", ">=", start_of_day.strftime("%Y-%m-%d %H:%M:%S"))\
                        .where("date_from", "<", end_of_day.strftime("%Y-%m-%d %H:%M:%S"))\
                        .stream()
                for day in days_ref:
                    day_data = day.to_dict()
                    try:
                        bookings = day.reference.collection("bookings").stream()

                        for booking in bookings:
                            booking_data = booking.to_dict()                         
                            booking_data['room_number'] = room_number             
                            booking_data['date_from'] = day_data['date_from']             
                            booking_data['date_to'] = day_data['date_to']             
                            room_bookings.append(booking_data)
                            # room_bookings[room_number].append(booking_data)
                    except Exception as e:
                        print(f"Error fetching bookings: {e}")
        if room_bookings:
            return templates.TemplateResponse("allRoomInfo.html", {"request": request, "filter_data": room_bookings,"dateFrom":dateFrom})
        else:
            print("No bookings found")
            return templates.TemplateResponse("allRoomInfo.html", {"request": request,"dateFrom":dateFrom,"filter_message":"No bookings found"})
          


def get_bookings(room_id: str, dateFrom: Optional[str] = None) -> List[Dict]:
    bookings = []
    try:
        if dateFrom is not None:
            days_ref = firestore_db.collection("rooms").document(room_id).collection("days").where("date_from", "==", dateFrom).stream()
        else:
            days_ref = firestore_db.collection("rooms").document(room_id).collection("days").stream()

        for day in days_ref:
            day_data = day.to_dict()
            day_id = day.id
            bookings_ref = day.reference.collection("bookings").stream()
            for booking in bookings_ref:
                booking_data = booking.to_dict()
                booking_data['date_from'] = day_data['date_from']
                booking_data['date_to'] = day_data['date_to']
                booking_data['booking_id'] = booking.id
                bookings.append(booking_data)
    except Exception as e:
        print(f"Error fetching bookings: {e}")

    return bookings



@app.get("/room/{room_id}")
def room_detail(request: Request, room_id: str,dateFrom: str = Query(None)):
    bookings = get_bookings(room_id,dateFrom)
    return templates.TemplateResponse("roomDetail.html", {"request": request, "room_number": room_id,"bookings":bookings})



@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    rooms = fetch_available_rooms()
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return templates.TemplateResponse("allRoomInfo.html", {"request": request, "user_token":None,"room_data":rooms})
    else:
        guest_email = user_token.get('email')
        user = getRoomSchedular(user_token) 
        rooms_ref = firestore_db.collection("rooms").where("user_id", "==", guest_email).stream()
        rooms_list = [{"room_id": doc.id, "room_number": doc.to_dict()["room_number"]} for doc in rooms_ref]
        user_bookings = []        
        for room in rooms_list:
            room_id = room['room_id']
            room_bookings = []
            days_ref = firestore_db.collection("rooms").document(room_id).collection("days")
            for day in days_ref.stream():
                day_data = day.to_dict()
                try:
                    
                    bookings = day.reference.collection("bookings").stream()

                    for booking in bookings:
                        booking_data = booking.to_dict()                         
                        booking_data['room_number'] = room['room_number']
                        booking_data['date_from'] = day_data['date_from']                     
                        booking_data['date_to'] = day_data['date_to']     
                        # print("booking dataaa", booking_data)                
                        room_bookings.append(booking_data)
                except Exception as e:
                    print(f"Error fetching bookings: {e}")
                    
            if room_bookings:
                user_bookings.extend(room_bookings)
                
        if user_bookings:
            return templates.TemplateResponse("allRoomInfo.html", {"request": request, "user_token": user_token, "room_data": rooms, "booking_data": user_bookings,"user_rooms":rooms_list})
        else:
            print("No bookings found",rooms)
            return templates.TemplateResponse("allRoomInfo.html", {"request": request, "user_token": user_token,"room_data": rooms,"user_rooms":rooms_list})
  

@app.get("/add-room",response_class=HTMLResponse)
async def updateForm(request:Request):
    return templates.TemplateResponse('addRoom.html',{'request':request})


@app.post("/add-room",response_class=RedirectResponse)
async def add_data(request: Request):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    # print("user token",user_token)
    guest_email = user_token.get('email')
    form = await request.form()  
    room_data = {"room_number": int(form['room_number']),
     "room_capacity": int(form['room_capacity']),
     "room_available":form['room_available'],
     "user_id":guest_email}

    room_query = firestore_db.collection('rooms') \
                           .where('room_number', '==', int(form['room_number'])) \
                           .limit(1) \
                           .stream()

    if len(list(room_query)) > 0:
        message = "Room with the same number already exists."
        # If an room with the same attributes exists, return without adding
        return templates.TemplateResponse("addRoom.html", {"request": request, "message": message})

    room_response = firestore_db.collection('rooms').document() 
    room_response.set(room_data,merge=True)
    # print("room_response data",room_response)
    return RedirectResponse("/",status_code=status.HTTP_302_FOUND)

@app.get("/login", response_class=HTMLResponse)
async def root(request: Request):

    id_token = request.cookies.get("token")
    error_message = "No error here"
    user_token = None

    if id_token:
        try:
            user_token = google.oauth2.id_token.verify_firebase_token(id_token, firebase_request_adapter)
        except ValueError as err:
            print(str(err))

    return templates.TemplateResponse('login.html', {'request': request, 'user_token': user_token, 'error_message': error_message})

def insert_day(room_id, day_data):
    
    date_from = datetime.strptime(day_data['date_from'], '%Y-%m-%d %H:%M')
    date_to = datetime.strptime(day_data['date_to'], '%Y-%m-%d %H:%M')
    
    date_from_str = date_from.strftime('%Y-%m-%d %H:%M')
    date_to_str = date_to.strftime('%Y-%m-%d %H:%M')
    query_from = firestore_db.collection('rooms').document(room_id).collection('days') \
        .where('date_from', '<=', date_to_str) \
        .where('date_to', '>=', date_from_str) \
        .limit(1).stream()
    if len(list(query_from)) > 0:
        return "0"
    else:
        return firestore_db.collection('rooms').document(room_id).collection('days').add(day_data)[1].id
    


def insert_booking(room_id, day_id, booking_data):
    bookings_ref = firestore_db.collection('rooms').document(room_id).collection('days').document(day_id).collection('bookings')
    doc_ref = bookings_ref.add(booking_data)
    return doc_ref[1].id


@app.get("/booking_room", response_class=HTMLResponse)
async def book_room(request: Request, room_id: str):
    id_token = request.cookies.get("token")
    error_message = "No error here"
    user_token = None
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return templates.TemplateResponse("login.html", {"request": request, "user_token":None,"room_id":None})
    else:
        return templates.TemplateResponse("bookingRoom.html", {"request": request, "room_id": room_id,"user_token":user_token})
    


@app.post("/booking_room",response_class=RedirectResponse)
async def book_room(request: Request,room_id: str = Form(...),dateFrom: str = Form(...), dateTo: str = Form(...), 
                    guest_name: str = Form(...), guest_email:str = Form(...),
                    phone: str = Form(...)):
    
    day_data = {"date_from": datetime.strptime(dateFrom, '%Y-%m-%dT%H:%M').strftime("%Y-%m-%d %H:%M"),
    "date_to": datetime.strptime(dateTo, '%Y-%m-%dT%H:%M').strftime("%Y-%m-%d %H:%M")}
    day_id = insert_day(room_id,day_data)
    
    if day_id == "0":
        message = "Unfortunately, the room you're interested in is already booked for the specified time period."
        return templates.TemplateResponse("bookingRoom.html", {"request": request,"room_id":room_id,"message":message})
    
        # Insert booking data
    booking_data = {
        "room_id": room_id, 
        "day_id": day_id,  
        "guest_name": guest_name,
        "guest_email": guest_email,
        "guest_phone":  phone
        }
    booking_id=insert_booking(room_id,day_id,booking_data)  
        
    return RedirectResponse("/",status_code=status.HTTP_302_FOUND)

@app.get("/edit_room")
async def get_room_bookings(request: Request, room_id: str, day_id: str):
    room_ref = firestore_db.collection("rooms").document(room_id)

    day_ref = room_ref.collection("days").document(day_id)
    day_data = day_ref.get()
    bookings_ref = day_ref.collection("bookings")
    room_bookings = []
    for booking in bookings_ref.stream():
        booking_data = booking.to_dict()
        booking_data['day_id'] = day_id
        booking_data['room_id'] = room_id
        booking_data['date_from'] = day_data.get('date_from')
        booking_data['date_to'] = day_data.get('date_to')
        booking_data['booking_id'] = booking.id
        room_bookings.append(booking_data)
    return templates.TemplateResponse("editRoom.html", {"request": request, "booking_data": room_bookings})

@app.post("/edit_room", response_class=HTMLResponse)
async def edit_room(request: Request):
    form = await request.form()
    room_id = form.get("room_id")
    day_id = form.get("day_id")
    booking_id = form.get("booking_id")
    guest_name = form.get("guest_name")
    guest_email = form.get("guest_email")
    guest_phone = form.get("guest_phone")
    date_from = form.get("date_from")
    date_to = form.get("date_to")
    print("bookingId",booking_id,date_from,date_to)
    try:
        room_ref = firestore_db.collection("rooms").document(room_id)
        day_ref = room_ref.collection("days").document(day_id)
        booking_ref = day_ref.collection("bookings").document(booking_id)
        
        date_from_str = datetime.strptime(date_from, '%Y-%m-%dT%H:%M').strftime("%Y-%m-%d %H:%M")
        print("date_from_str",date_from_str)
        date_to_str = datetime.strptime(date_to, '%Y-%m-%dT%H:%M').strftime("%Y-%m-%d %H:%M")
        print("date_to_str",date_to_str)
        
        query_from = firestore_db.collection('rooms').document(room_id).collection('days') \
            .where('date_from', '<=', date_to_str) \
            .where('date_to', '>=', date_from_str) \
            .limit(1).stream()

        if len(list(query_from)) > 0:
            message = "Unfortunately, the room you're interested in is already booked for the specified time period."
            return templates.TemplateResponse("bookingRoom.html", {"request": request,"room_id":room_id,"message":message})
    
        day_ref.update({
            "date_from": datetime.strptime(date_from, '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M'),
            "date_to": datetime.strptime(date_to, '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M')
        })

        booking_ref.update({
            "guest_name": guest_name,
            "guest_email": guest_email,
            "guest_phone": guest_phone,
        })        

        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)

    except Exception as e:
        return {"error": str(e)}

@app.post("/delete_room", response_class=RedirectResponse)
async def delete_room(request: Request,room_id: str = Form(...)):
    id_token = request.cookies.get("token")
    if not id_token:
        raise HTTPException(status_code=401, detail="Authorization required")

    user_token = validateFirebaseToken(id_token)
    if not user_token:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    room_ref = firestore_db.collection('rooms').document(room_id)
    room_doc = room_ref.get()

    if not room_doc.exists:
        raise HTTPException(status_code=404, detail="Room not found")

    room_data = room_doc.to_dict()

    if room_data.get('user_id') != user_token['email']:        
        raise HTTPException(status_code=403, detail="You are not authorized to delete this room.")

    bookings_ref = room_ref.collection("days").stream()
    for day in bookings_ref:
        day_data = day.to_dict()
        bookings_count = day.reference.collection("bookings").where('room_id', '==', room_id).get()
        if bookings_count:
            raise HTTPException(status_code=400, detail="Cannot delete room. There are bookings associated with it.")
    room_ref.delete()

    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)

@app.post("/delete_booking",response_class=RedirectResponse)
async def delete_room(request: Request, room_id: str = Form(...), day_id: str = Form(...), booking_id: str = Form(...)):
    
    id_token = request.cookies.get("token")
    user_token = None
    user_token = validateFirebaseToken(id_token)

    room_ref = firestore_db.collection('rooms').document(room_id)
    room_doc = room_ref.get()

    if room_doc.exists:
        room_data = room_doc.to_dict()

        if room_data.get('user_id') == user_token['email']:
            booking_ref = room_ref.collection("days").document(day_id).collection("bookings").document(booking_id)
            booking_doc = booking_ref.get()

            if booking_doc.exists:
                booking_ref.delete()
                return RedirectResponse("/",status_code=status.HTTP_302_FOUND)
            else:
                raise HTTPException(status_code=400, detail="Booking not found")
        else:
            raise HTTPException(status_code=403, detail="You are not authorized to delete this room.")
    else:
        raise HTTPException(status_code=404, detail="Room not found")

@app.post("/show_room_bookings", response_class=HTMLResponse)
async def show_room_bookings(request: Request, room_id: str = Form(None)):    
    if room_id is None:
        return RedirectResponse("/",status_code=status.HTTP_302_FOUND)
    bookings = get_bookings(room_id)
    return templates.TemplateResponse("roomDetail.html", {"request": request, "room_number": room_id,"bookings":bookings,"showingRoomDetail":True})
