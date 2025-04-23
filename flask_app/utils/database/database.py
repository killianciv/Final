import mysql.connector
import glob
import json
import csv
from io import StringIO
import itertools
import hashlib
import os
import cryptography
from cryptography.fernet import Fernet
from math import pow
import re

class database:

    def __init__(self, purge = False):

        # Grab information from the configuration file
        self.database       = 'db'
        self.host           = '127.0.0.1'
        self.user           = 'master'
        self.port           = 3306
        self.password       = 'master'
        self.tables         = ['users', 'events', 'event_dates', 'invitees', 'availability']  # In order of foreign key dependency

        # NEW IN HW 3-----------------------------------------------------------------
        self.encryption     =  {   'oneway': {'salt' : b'averysaltysailortookalongwalkoffashortbridge',
                                                 'n' : int(pow(2,5)),
                                                 'r' : 9,
                                                 'p' : 1
                                             },
                                'reversible': { 'key' : '7pK_fnSKIjZKuv_Gwc--sZEMKn2zc8VvD6zS96XcNHE='}
                                }
        #-----------------------------------------------------------------------------

    def query(self, query = "SELECT * FROM users", parameters = None):
        # Always returns a list (a table) of dictionaries (rows) like
        #  [{col1: row1value, col2: row1value, ...}, {col1: row2value, col2: row2value, ...}]
        cnx = mysql.connector.connect(host     = self.host,
                                      user     = self.user,
                                      password = self.password,
                                      port     = self.port,
                                      database = self.database,
                                      charset  = 'latin1'
                                     )


        if parameters is not None:
            cur = cnx.cursor(dictionary=True)
            cur.execute(query, parameters)
        else:
            cur = cnx.cursor(dictionary=True)
            cur.execute(query)

        # Fetch one result
        row = cur.fetchall()
        cnx.commit()

        if "INSERT" in query:
            cur.execute("SELECT LAST_INSERT_ID()")
            row = cur.fetchall()
            cnx.commit()
        cur.close()
        cnx.close()
        return row

    def createTables(self, purge=False, data_path = 'flask_app/database/'):
        ''' FILL ME IN WITH CODE THAT CREATES YOUR DATABASE TABLES.'''

        #should be in order or creation - this matters if you are using foreign keys.
         
        if purge:
            for table in self.tables[::-1]:
                self.query(f"""DROP TABLE IF EXISTS {table}""")
            
        # Execute all SQL queries in the /database/create_tables directory.
        for table in self.tables:
            
            #Create each table using the .sql file in /database/create_tables directory.
            with open(data_path + f"create_tables/{table}.sql") as read_file:
                create_statement = read_file.read()
            self.query(create_statement)

            # Import the initial data
            try:
                params = []
                with open(data_path + f"initial_data/{table}.csv") as read_file:
                    scsv = read_file.read()            
                for row in csv.reader(StringIO(scsv), delimiter=','):
                    params.append(row)
            
                # Insert the data
                cols = params[0]; params = params[1:] 
                self.insertRows(table = table,  columns = cols, parameters = params)
            except:
                continue
                # print(f"No initial data in {table}")

    def insertRows(self, table='table', columns=['x','y'], parameters=[['v11','v12'],['v21','v22']]):
        
        # Check if there are multiple rows present in the parameters
        has_multiple_rows = any(isinstance(el, list) for el in parameters)
        keys, values      = ','.join(columns), ','.join(['%s' for x in columns])
        
        # Construct the query we will execute to insert the row(s)
        query = f"""INSERT IGNORE INTO {table} ({keys}) VALUES """
        if has_multiple_rows:
            for p in parameters:
                query += f"""({values}),"""
            query     = query[:-1] 
            parameters = list(itertools.chain(*parameters))
        else:
            query += f"""({values}) """                      

        insert_id = self.query(query,parameters)[0]['LAST_INSERT_ID()']         
        return insert_id

#######################################################################################
# AUTHENTICATION RELATED
#######################################################################################
    def createUser(self, email='me@email.com', password='password', role='user'):
        # See if that username is already in the database. Duplicate because parameters must be a tuple
        equivalent_feedback = self.query("""SELECT * FROM users 
                                                  WHERE email = %s""",
                                        parameters=(email, ))
        if equivalent_feedback:
            return {'failure': 0}
        else:
            # Hash the password and make a database entry
            hashed_pass = self.onewayEncrypt(password)
            self.query("""INSERT INTO users (email, password, role) 
                                VALUES (%s, %s, %s)""",
                     parameters=(email, hashed_pass, role))
            return {'success': 1}

    def authenticate(self, email='me@email.com', password='password'):
        # See if that (username, password) exist in the database.
        hashed_pass = self.onewayEncrypt(password)
        equivalent_feedback = self.query("""SELECT * FROM users 
                                                    WHERE email = %s AND password = %s""",
                                         parameters=(email, hashed_pass))
        if equivalent_feedback:
            return {'success': 1}
        else:
            return {'failure': 0}

    def onewayEncrypt(self, string):
        encrypted_string = hashlib.scrypt(string.encode('utf-8'),
                                          salt = self.encryption['oneway']['salt'],
                                          n    = self.encryption['oneway']['n'],
                                          r    = self.encryption['oneway']['r'],
                                          p    = self.encryption['oneway']['p']
                                          ).hex()
        return encrypted_string

    def reversibleEncrypt(self, type, message):
        fernet = Fernet(self.encryption['reversible']['key'])
        
        if type == 'encrypt':
            message = fernet.encrypt(message.encode())
        elif type == 'decrypt':
            message = fernet.decrypt(message).decode()

        return message

#######################################################################################
# HOMEPAGE RELATED
#######################################################################################
    # All dates were in the format "Fri 04/22"
    # Dates are now like "01/22/25"
    # startTime and endTime are integers in [0, 24] like military time
    def createEvent(self, creator, eventName, startDate, endDate, selectedDates, startTime, endTime, inviteesString):
        # creator is the decrypted user email
        print("Creator of the new event:", creator)
        # # Check if invitees list is in the right format (csv, optional space, required __@__.com)
        # invitee_pattern = r"^([\w\.-]+@[\w\.-]+\.\w{2,}\s*,?\s*)+$"  # Ex: like johm@email.com,john2@email.com, john@email.com
        # valid_invitee = re.match(invitee_pattern, inviteesString.strip())
        # if not valid_invitee:
        #     return {'failure': 'Invalid format for invitees list'}
        # Check if an identical event already exists. Ignores start and end dates
        query = """SELECT * FROM events 
                   WHERE name = %s AND email = %s AND start_time = %s AND 
                         end_time = %s AND start_time = %s AND end_time = %s"""
        params = (eventName, creator, startDate, endDate, startTime, endTime)
        existing = self.query(query, parameters=params)
        if existing:
            return {'failure': 'Duplicate event'}

        # Insert the new event
        insert_event = """INSERT INTO events (name, email, start_date, end_date, start_time, end_time)
                          VALUES (%s, %s, %s, %s, %s, %s)"""
        self.query(insert_event, parameters=params)

        # Get the newly inserted event_id
        new_event_id = """SELECT MAX(event_id) AS event_id FROM events"""
        event_id = self.query(new_event_id)[0]['event_id']
        print(f"Event ID: {event_id}")
        for selected_date in selectedDates:
            self.query("INSERT INTO event_dates (event_id, date) VALUES (%s, %s)",
                       parameters=(event_id, selected_date))
        print(f"Selected dates: {selectedDates}")
        print(f"Start time: {startTime}")
        print(f"End time: {endTime}")

        # Parse invitee emails
        emails = [email.strip() for email in inviteesString.split(",")]
        emails.append(creator)
        for email in emails:
            insert_invitee = """INSERT INTO invitees (event_id, email)
                                VALUES (%s, %s)"""
            self.query(insert_invitee, parameters=(event_id, email))
        print(f"Invitees: {emails}")
        return {'success': 1, 'event_id': event_id}

    def getJoinEventInvites(self, user_email):
        query = """
                SELECT 
                    e.event_id,
                    e.name AS event_name,
                    u.email AS creator_email,
                    u.email AS creator_name,  -- you could change this to u.name if you add a name field later
                    e.start_date,
                    e.end_date
                FROM invitees i
                JOIN events e ON i.event_id = e.event_id
                JOIN users u ON e.email = u.email
                WHERE i.email = %s
            """
        params = (user_email,)
        return self.query(query, parameters=params)

#######################################################################################
# EVENT PAGE RELATED
#######################################################################################
    def getEventName(self, event_id):
        query = "SELECT name FROM events WHERE event_id = %s"
        rows = self.query(query, parameters=(event_id,))
        return rows[0]['name']

    def getEventDateRange(self, event_id):
        query = "SELECT start_date, end_date FROM events WHERE event_id = %s"
        result = self.query(query, parameters=(event_id,))
        return (result[0]['start_date'], result[0]['end_date']) if result else None

    # # Returns ['Sun 04/20', 'Mon 04/21', 'Tue 04/22', 'Wed 04/23'] in order by date not by the day of week
    # def getEventDates(self, event_id):
    #     query = "SELECT date FROM event_dates WHERE event_id = %s ORDER BY date ASC"
    #     return [row['date'] for row in self.query(query, parameters=(event_id,))]
    # Returns ['04/20/25', '04/21/25', '04/22/25'] in order by date
    def getEventDates(self, event_id):
        query = "SELECT date FROM event_dates WHERE event_id = %s ORDER BY date ASC"
        return [row['date'] for row in self.query(query, parameters=(event_id,))]

    # Get the start and end times (ints in [0, 24]) of the event. Returns { 'start_time': 9, 'end_time': 17 }
    def getEventTimeRange(self, event_id):
        query = "SELECT start_time, end_time FROM events WHERE event_id = %s"
        result = self.query(query, parameters=(event_id,))
        return result[0] if result else None

    # The availability data is in a different format than what is used
    #  for getEventTimes because times can be by the half hour
    # availability_data is like:
    #   [{"date": "04/23/25", "time": "09:00:00", "status": "available"},
    #    {"date": "04/23/25", "time": "09:30:00", "status": "maybe"}, ...]
    def saveAvailability(self, event_id, user_email, availability_data):
        for entry in availability_data:  # For every cell we have data about
            query = """
                    INSERT INTO availability (event_id, email, date, time, status)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE status = VALUES(status)
                """
            self.query(query, parameters=(event_id, user_email, entry['date'], entry['time'], entry['status']))

    # Get the user's availability status for all squares. Format:
    # {'04/24/25': {'08:00:00': {'available': 0, 'maybe': 0, 'unavailable': 1},
    #               '08:30:00': {'available': 1, 'maybe': 0, 'unavailable': 0}, ...} ..}
    def getAvailability(self, event_id, user_email):
        # Get their availability for each half-hour increment of each day of the event
        query = """
            SELECT date, time, status FROM availability
            WHERE event_id = %s AND email = %s
        """
        return self.query(query, parameters=(event_id, user_email))

    # Return the heatmap for all squares. Format:
    # {'04/24/25': {'08:00:00': {'available': 0, 'maybe': 0, 'unavailable': 1},
    #   '08:30:00': {'available': 1, 'maybe': 0, 'unavailable': 0}, ...}
    def getHeatmap(self, event_id):
        rows = self.query("""
            SELECT date, time, status, COUNT(*) as count
            FROM availability
            WHERE event_id = %s
            GROUP BY date, time, status
        """, (event_id,))

        heatmap = {}
        for row in rows:
            date = row['date']
            time = row['time']
            status = row['status']
            count = row['count']

            if date not in heatmap:
                heatmap[date] = {}
            if time not in heatmap[date]:
                heatmap[date][time] = {'available': 0, 'maybe': 0, 'unavailable': 0}

            heatmap[date][time][status] = count

        print(f"Heatmap: {heatmap}")
        return heatmap




