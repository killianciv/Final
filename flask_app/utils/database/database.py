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
    def createEvent(self, creator, eventName, startDate, endDate, selectedDates, startTime, endTime, inviteesString):
        # creator is the decrypted user email
        print("Inserting event with email:", creator)
        # Check if invitees list is in the right format (csv, optional space, required __@__.com)
        invitee_pattern = r"^([\w\.-]+@[\w\.-]+\.\w{2,}\s*,?\s*)+$"  # Ex: like johm@email.com,john2@email.com, john@email.com
        valid_invitee = re.match(invitee_pattern, inviteesString.strip())
        if not valid_invitee:
            return {'failure': 'Invalid format for invitees list'}
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
    # The event page will have a vertical column for each day, each labeled with a date.
    # On the left side of the availability div, it will have the hours like 8:00, 9:00,
    #  etc. with lines every half hour. Each date is horizontally diced into 30-minute
    #  time increments. It starts as totally unavailable.
    # Each invitee visiting the page is allowed to enter their availability by
    #  selecting an availability mode (available, maybe, unavailable) from a dropdown
    #  and then clicking
    #  a square or dragging across several squares or even across several days to apply
    #  that availability status to that half-hour slot.
    # I need to set up an availability database to save this information as well
    def getEventDates(self, event_id):
        query = "SELECT date FROM event_dates WHERE event_id = %s ORDER BY date ASC"
        return [row['date'] for row in self.query(query, parameters=(event_id,))]

    def saveAvailability(self, event_id, user_email, availability_data):
        """
            availability_data is a list of dictionaries like:
            [
                {"date": "2025-04-20", "time": "09:00:00", "status": "available"},
                {"date": "2025-04-20", "time": "09:30:00", "status": "maybe"},
                ...
            ]
        """
        for entry in availability_data:
            query = """
                    INSERT INTO availability (event_id, email, date, time, status)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE status = VALUES(status)
                """
            self.query(query, parameters=(event_id, user_email, entry['date'], entry['time'], entry['status']))

    def getAvailability(self, event_id, user_email):
        # Get their availability for each half-hour increment of each day of the event
        query = """
            SELECT date, time, status FROM availability
            WHERE event_id = %s AND email = %s
        """
        return self.query(query, parameters=(event_id, user_email))



