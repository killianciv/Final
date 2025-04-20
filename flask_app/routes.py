# Author: Prof. MM Ghassemi <ghassem3@msu.edu>
from flask import current_app as app
from flask import render_template, redirect, request, session, url_for, copy_current_request_context
from flask_socketio import SocketIO, emit, join_room, leave_room, close_room, rooms, disconnect
from .utils.database.database  import database
from werkzeug.datastructures   import ImmutableMultiDict
from pprint import pprint
import json
import random
import functools
from . import socketio
from flask import jsonify  # delete_workout and edit_workout
from datetime import datetime  # extract_workout_data
from datetime import date, timedelta
import re  # extract_workout_data

db = database()

#######################################################################################
# AUTHENTICATION RELATED
#######################################################################################
# A session is like a second cookie in Flask. It is a dictionary that stores data
#   across requests. I can ask the session for information like the user's 'email'
def login_required(func):
    @functools.wraps(func)
    def secure_function(*args, **kwargs):
        if "email" not in session:
            return redirect(url_for("login", next=request.url))
        return func(*args, **kwargs)
    return secure_function
# Pull the current user's decrypted email from the session cookie for navbar display
# When this function is used by chat.html, it will return the username of the
#  person who SENT the message because their backend is doing the processing
def getUser():
    if 'email' in session:
        return db.reversibleEncrypt('decrypt', session['email'])
    else:
        return 'Unknown'

@app.route('/login')
def login():
    next_page = request.args.get('next') or '/home'  # Set it or else it becomes 'None'
    return render_template('login.html', user='Unknown', next=next_page)

@app.route('/logout')
def logout():
    session.pop('email', default=None)
    return redirect('/')

@app.route('/processlogin', methods = ["POST","GET"])
def processlogin():
    # Parse the form sent asynchronously by checkCredentials(). Concerned with the inputs name="email" and name="password"
    form_fields = dict((key, request.form.getlist(key)[0]) for key in list(request.form.keys()))
    print(f"Logged in with {form_fields['email']}")
    # Get next parameter
    next_page = form_fields.get('next', '/home')  # Default to /home if no next is provided
    # Call authenticate(). Returns {'success': 1} or {'failure': 0}
    auth_status = db.authenticate(form_fields['email'], form_fields['password'])
    if auth_status.get('success'):  # Use .get() to avoid KeyError
        try:
            # The session stores the encrypted email of the user
            session['email'] = db.reversibleEncrypt('encrypt', form_fields['email'])
        except Exception as e:
            print(f"Encryption error: {e}")
            return json.dumps({'success': 0, 'error': 'Encryption failed'})

    auth_status['next'] = next_page  # Add next page to response
    return json.dumps(auth_status)

@app.route('/processregister', methods=["POST", "GET"])
def processregister():
    form_fields = dict((key, request.form.getlist(key)[0]) for key in list(request.form.keys()))
    next_page = form_fields.get('next', '/home')  # Default to /home if no next is provided

    # Create the user
    print(f"Geristered with {form_fields['email']}")
    registration_status = db.createUser(form_fields['email'], form_fields['password'])

    # Regardless of success/failure, always say it succeeded (to deter brute force)
    try:
        session['email'] = db.reversibleEncrypt('encrypt', form_fields['email'])  # Log them in
    except Exception as e:
        print(f"Encryption error: {e}")
        return json.dumps({'success': 1, 'next': next_page, 'error': 'Encryption failed'})

    return json.dumps({'success': 1, 'next': next_page})

#######################################################################################
# MAIN STUFF I WORK ON
#######################################################################################
@app.route('/')
def root():
    return redirect('/login')

@app.route('/home')
@login_required  # So they can't simply type in the URL for /home.
def home():
    next_page = request.args.get('next') or '/home'  # Set it or else it becomes 'None'
    if getUser() == 'Unknown':
        # Redirect and remember the intended page via the `next` parameter
        return redirect(url_for('login', next=next_page))

    # Stuff needed for the Create_Event div:
    today = date.today()
    # Generate 5 weeks × 7 days = 35 dates. Make sure it starts on a Sunday and dates line up right
    day_index = {'Sun': 0, 'Mon': 1, 'Tue': 2, 'Wed': 3, 'Thu': 4, 'Fri': 5, 'Sat': 6}
    first_day_of_week = today.strftime('%a')  # e.g., 'Fri' the current day
    offset = day_index[first_day_of_week]
    calendar_days = [(today + timedelta(days=i)).strftime('%a %m/%d') for i in range(-offset, 35-offset)]

    # Stuff needed for the Join_Event div:
    invites = db.getJoinEventInvites(getUser())

    return render_template('home.html', user=getUser(), next=next_page, calendar_days=calendar_days,
                           first_day_of_week=first_day_of_week, today_str=today.strftime('%a %m/%d'), invites=invites)

@app.route('/createevent', methods=["POST"])
def createevent():
    # Grab the data_d sent asynchronously by home.html's createAnEvent(), then create the event
    data = request.get_json()
    start_date = min(data['selected_dates'])
    end_date = max(data['selected_dates'])
    # getUser() returns the same decrypted email that is in the database
    status = db.createEvent(
        creator=getUser(),
        eventName=data['name'],
        startDate=start_date,
        endDate=end_date,
        selectedDates=data['selected_dates'],
        startTime=data['start_time'],
        endTime=data['end_time'],
        inviteesString=data['invitees']
    )
    print(f"Status of event creation: {status}")

    if 'success' in status:
        # Redirect to a unique event page using the id so the query to check who is allowed to view is easier
        event_id = status['event_id']
        eventpage = f"/event/{event_id}"
        return json.dumps({'success': True, 'eventpage': eventpage})  # .dumps lets the home.html JS use the value too
    else:
        return json.dumps({'success': False, 'error': status['failure']})

@app.route('/event/<int:event_id>')
@login_required
def view_event(event_id):
    # If the user is not signed in, force them to
    if getUser() == 'Unknown':
        return redirect(url_for('login'))

    # If they are signed in but were not invited, do not let them view
    user_email = getUser()  # This should give you the decrypted email from the session
    query = """SELECT * FROM events WHERE event_id = %s AND email = %s"""
    is_creator = db.query(query, parameters=(event_id, user_email))
    query = """SELECT * FROM invitees WHERE event_id = %s AND email = %s"""
    is_invited = db.query(query, parameters=(event_id, user_email))
    if not (is_creator or is_invited):
        # return "Access Denied", 403
        next_page = '/login'
        return redirect(url_for('login', next=next_page))

    # Fetch necessary information about the event
    invitees = db.query("SELECT email FROM invitees WHERE event_id = %s", (event_id,))
    invitees = [row["email"] for row in invitees]  # A list of emails
    dates = db.getEventDates(event_id)
    availability = db.getAvailability(event_id, getUser())
    return render_template("event.html", user=getUser(), invitees=invitees, event_id=event_id,
                           availability=availability, dates=dates)

# Asynchronous requests received from event.html's JS
@app.route('/save_availability', methods=['POST'])
@login_required
def save_availability():
    data = request.get_json()
    event_id = data['event_id']
    availability = data['availability']  # A list of {date, time, status}
    email = getUser()
    for entry in availability:
        if entry['status'] not in {'available', 'maybe', 'unavailable'}:
            return jsonify(success=False, error="Invalid status")
    db.saveAvailability(event_id, email, availability)
    return jsonify(success=True)


#######################################################################################
# CHATROOM RELATED
#######################################################################################
users_in_chat = set()
@app.route('/chat')
def chat():
    if getUser() == 'Unknown':
        # Save the original URL and redirect to /login with a `next` parameter
        return redirect(url_for('login', next=request.path))
    # Otherwise, just display /chat.
    return render_template('chat.html', user=getUser())
# After your DOM loaded, chat.html's script connected to the socket and automatically
#  sent a socket.emit('joined'). Now emit a 'status' message that says you (the getUser())
#  have joined the room. Even the sender will get this message
@socketio.on('joined', namespace='/chat')
def joined(message):
    sender_username = getUser()
    users_in_chat.add(sender_username)  # Track user as "in the chat"
    join_room('main')
    emit('status', {'sender_username': sender_username, 'msg': getUser() + ' has entered the room.', 'style': 'width: 100%;color:blue;text-align: right'}, room='main')
# You are leaving the room, which you did by clicking the <input> in chat.html
#  that sends a socket emission titled 'left'. Now emit a 'status' message that
#  says you (the getUser()) have left the room
@socketio.on('left', namespace='/chat')
def left(message):
    sender_username = getUser()
    # Only let them leave the room if they are in the room
    if sender_username in users_in_chat:
        users_in_chat.remove(sender_username)
        leave_room('main')
        emit('status', {'sender_username': sender_username, 'msg': getUser() + ' has left the room.', 'style':'width:100%;'}, room='main')
# I must make a URL that does the same thing as socket.emit('left') because if
#  the socket doesn't work on unload, I need to use a beacon, and all they
#  can do is redirection
@app.route('/leave_chat')
def leave_chat():
    # When I click 'Leave chat', I will redirect here
    # In here I cannot do socketio.emit('left', {}) because this code runs in the server,
    #  and an emit() sent from a server only goes to clients, which means my
    #  request for this exact server to run the 'left' function would fail.
    left({})  # This directly calls the server-side function
    return {'success': True}  # Response for sendBeacon()
# Step 2 for sending messages: Receives and reads incoming and outgoing messages
#   sent through chat.html's sendMessage()'s socket.emit().
@socketio.on('message', namespace='/chat')
def message(data):
    # This is being processed on the server-side of the sender, before being
    #  sent to other members of the server. So whoever sent the message will
    #  be returned by getUser().
    sender_username = getUser()
    msg_text = data.get('msg')
    # Send the message and username to ALL users
    emit('message', {'sender_username': sender_username, 'msg': msg_text}, room='main')

#######################################################################################
# OTHER
#######################################################################################
# He had this, but red line was under send_from_directory:
@app.route("/static/<path:path>")
def static_dir(path):
    return send_from_directory("static", path)
@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r









