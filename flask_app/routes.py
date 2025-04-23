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

# Global variable to track the number of failed login attempts. It is global
#   because it must persist requests across both /login and /processlogin
failed_attempts = 0

@app.route('/login')
def login():
    global failed_attempts
    next_page = request.args.get('next') or '/home'  # Set it or else it becomes 'None'
    if not next_page or next_page == '/login':  # Do not let next="/login"
        next_page = '/home'
    return render_template('login.html', user='Unknown', failed_attempts=failed_attempts, next=next_page)

@app.route('/logout')
def logout():
    session.pop('email', default=None)
    return redirect('/')

@app.route('/processlogin', methods = ["POST","GET"])
def processlogin():
    global failed_attempts
    # Parse the form sent asynchronously by checkCredentials(). Concerned with the inputs name="email" and name="password"
    form_fields = dict((key, request.form.getlist(key)[0]) for key in list(request.form.keys()))
    print(f"Logged in with {form_fields['email']}")
    # Get next parameter
    next_page = form_fields.get('next', '/home')  # Default to /home if no next is provided
    if not next_page or next_page == '/login':  # Do not let next="/login"
        next_page = '/home'
    # Call authenticate(). Returns {'success': 1} or {'failure': 0}
    auth_status = db.authenticate(form_fields['email'], form_fields['password'])
    if auth_status.get('success'):  # Use .get() to avoid KeyError
        try:
            # The session stores the encrypted email of the user
            session['email'] = db.reversibleEncrypt('encrypt', form_fields['email'])
            failed_attempts = 0  # Reset failed attempts on success
        except Exception as e:
            print(f"Encryption error: {e}")
            return json.dumps({'success': 0, 'error': 'Encryption failed'})
    else:
        failed_attempts += 1  # Increment failed attempts on failure

    auth_status['next'] = next_page  # Add next page to response
    return json.dumps(auth_status)

@app.route('/processregister', methods=["POST", "GET"])
def processregister():
    global failed_attempts
    form_fields = dict((key, request.form.getlist(key)[0]) for key in list(request.form.keys()))
    next_page = form_fields.get('next', '/home')  # Default to /home if no next is provided
    if not next_page or next_page == '/login':  # Do not let next="/login"
        next_page = '/home'

    # Create the user
    print(f"Registered with {form_fields['email']}")
    registration_status = db.createUser(form_fields['email'], form_fields['password'])

    # Regardless of success/failure, always say it succeeded (to deter brute force)
    try:
        session['email'] = db.reversibleEncrypt('encrypt', form_fields['email'])  # Log them in
        failed_attempts = 0  # Reset failed attempts
    except Exception as e:
        print(f"Encryption error: {e}")
        return json.dumps({'success': 1, 'next': '/home', 'error': 'Encryption failed'})

    return json.dumps({'success': 1, 'next': next_page})

#######################################################################################
# MAIN STUFF I WORK ON
#######################################################################################
# Important:
# All dates are in the format "Fri 04/22"
# startTime and endTime are integers in [0, 24] like military time
# availability times are like "09:30:00"

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
    ### calendar_days = [(today + timedelta(days=i)).strftime('%a %m/%d') for i in range(-offset, 35-offset)]
    calendar_days = [(today + timedelta(days=i)).strftime('%m/%d/%y') for i in range(-offset, 35 - offset)]

    # Stuff needed for the Join_Event div:
    invites = db.getJoinEventInvites(getUser())

    return render_template('home.html', user=getUser(), next=next_page, calendar_days=calendar_days,
                           first_day_of_week=first_day_of_week, today_str=today.strftime('%m/%d/%y'), invites=invites)

@app.route('/createevent', methods=["POST"])
def createevent():
    # Grab the data_d sent asynchronously by home.html's createAnEvent(), then create the event
    data = request.get_json()

    # Convert strings without days of week, like "04/21/25", to datetime objects
    def extract_date(d):
        # return datetime.strptime(d.split()[1], "%m/%d/%y") worked when I had the day in front like "Fri ..."
        return datetime.strptime(d, "%m/%d/%y")
    sorted_dates = sorted(data['selected_dates'], key=extract_date)

    start_date = sorted_dates[0]
    end_date = sorted_dates[-1]

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
        return redirect(url_for('home'))

    # Fetch necessary information about the event
    invitees = db.query("SELECT email FROM invitees WHERE event_id = %s", (event_id,))
    invitees = [row["email"] for row in invitees]  # A list of emails
    date_range = db.getEventDateRange(event_id)  # ('04/20/25', '04/28/25')
    dates = db.getEventDates(event_id)  # ['04/20/25', '04/21/25', '04/22/25']
    times = db.getEventTimeRange(event_id)  # { 'start_time': 9, 'end_time': 17 }
    event_name = db.getEventName(event_id)
    availability = db.getAvailability(event_id, getUser())
    return render_template("event.html", user=getUser(), invitees=invitees,
                           event_id=event_id, event_name = event_name, availability=availability,
                           date_range=date_range, dates=dates, times=times)

#######################################################################################
# AVAILABILITY RELATED
#######################################################################################
@socketio.on('joined', namespace='/chat')
def handle_join(data):
    event_id = data.get('event_id')
    join_room(f'event_{event_id}')
    print(f"{getUser()} joined room: event_{event_id}")

# Save the availability data of the whole grid. This function is called by the
#  asynchronous request received from event.html's JS after a 'mouseup'.
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

# Someone just updated their availability grid, so I need to send the updated
#  heatmap to everybody. No data saving is needed; the JS line before the one
#  that called this already saved the data.
@socketio.on('send_update', namespace='/chat')
def handle_send_update(data):
    event_id = data['event_id']
    availability = data['availability']
    email = data['email']

    print(f"Received send_update emission from {email} for room 'event_{event_id}'")

    # Get group heatmap and emit
    heatmap = db.getHeatmap(event_id)
    print(f"Got the heatmap: \n{heatmap}")
    emit('heatmap_update', {'heatmap': heatmap}, room=f'event_{event_id}')

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









