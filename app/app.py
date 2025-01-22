import re  
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
import MySQLdb.cursors
from datetime import datetime, timedelta

app = Flask(__name__) 

app.secret_key = 'abcdefgh'
  
# MySQL configuration
app.config['MYSQL_HOST'] = 'db'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'password'
app.config['MYSQL_DB'] = 'cs353hw4db'
  
mysql = MySQL(app)  

time_zone = 3 #this can be adjustable for the location you are in I select 3 because Turkey is in time zone of UTC +3

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    message = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM User WHERE username = %s', (username,))
        user = cursor.fetchone()
        if user and user['password'] == password:              
            session['loggedin'] = True
            session['userid'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            return redirect(url_for('tasks'))  
        else:
            message = 'Invalid username or password!'
            return render_template('login.html', message=message)

    return render_template('login.html', message=message)  


@app.route('/register', methods=['GET', 'POST'])
def register():
    message = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form and 'email' in request.form:
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        cursor.execute('SELECT * FROM User WHERE username = %s', (username,))
        account = cursor.fetchone()
        
        cursor.execute('SELECT * FROM User WHERE email = %s', (email,))
        email_exists = cursor.fetchone()
        
        if account:
            message = 'Pick a more unique username, it has been taken before.'
        elif email_exists:
            message = 'This email is already registered. Please use a different email.'
        elif not username or not password or not email:
            message = 'Fill all of the blanks!'
        else:
            cursor.execute('INSERT INTO User (id, username, email, password) VALUES (NULL, %s, %s, %s)', (username, email, password,))
            mysql.connection.commit()
            message = 'Registration successful! You can now log in.'
            return redirect(url_for('login'))
    elif request.method == 'POST':
        message = 'Fill all of the blanks!'
    
    return render_template('register.html', message=message)


@app.route('/analysis', methods=['GET'])
def analysis():
    if 'userid' not in session:
        return redirect(url_for('login')) 

    user_id = session['userid']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    #List the title, type, deadline and status of all the tasks of the user in increasing order of deadlines
    cursor.execute(
        '''
        SELECT T.title, T.task_type, T.deadline, T.status
        FROM Task T
        WHERE T.user_id = %s
        ORDER BY T.deadline ASC;
        ''',
        (user_id,)
    )
    tasks_by_deadline = cursor.fetchall()

    #List the title, completion time, and the time spent for completion of the completed tasks  of the user in increasing order of completion time.
    cursor.execute(
        '''
        SELECT T.title, T.completion_time, TIMESTAMPDIFF(SECOND, T.creation_time, T.completion_time) AS time_spent
        FROM Task T
        WHERE T.user_id = %s AND T.status = "Done"
        ORDER BY T.completion_time ASC;
        ''',
        (user_id,)
    )
    completed_tasks = cursor.fetchall()

    #List the title, task type and deadline of uncompleted tasks of the user in increasing order  of deadlines. 
    cursor.execute(
        '''
        SELECT T.title, T.task_type, T.deadline
        FROM Task T
        WHERE T.user_id = %s AND T.status != "Done"
        ORDER BY T.deadline ASC;
        ''',
        (user_id,)
    )
    uncompleted_tasks = cursor.fetchall()

    #List the title and latency of the tasks of the user that were completed after their deadlines. 
    cursor.execute(
        '''
        SELECT T.title, TIMESTAMPDIFF(SECOND, T.deadline, T.completion_time) AS latency
        FROM Task T
        WHERE T.user_id = %s AND T.status = "Done" AND T.completion_time > T.deadline
        ORDER BY latency;
        ''',
    (user_id,)
    )

    late_completed_tasks = cursor.fetchall()

   #List the number of the completed tasks per task type for the user, in descending order.
    cursor.execute(
        '''
        SELECT T.task_type, COUNT(*) AS completed_tasks
        FROM Task T
        WHERE T.user_id = %s AND T.status = "Done"
        GROUP BY T.task_type
        ORDER BY completed_tasks DESC;
        ''',
        (user_id,)
    )
    tasks_per_type = cursor.fetchall()

    return render_template(
        'analysis.html',
        tasks_by_deadline=tasks_by_deadline,
        completed_tasks=completed_tasks,
        uncompleted_tasks=uncompleted_tasks,
        late_completed_tasks=late_completed_tasks,
        tasks_per_type=tasks_per_type
    )


@app.route('/tasks', methods=['GET'])
def tasks():
    if 'userid' not in session:
        return redirect(url_for('login'))  

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(
        '''
        SELECT * 
        FROM Task 
        WHERE user_id = %s
        ORDER BY 
            CASE 
                WHEN status = 'Todo' THEN deadline
                WHEN status = 'Done' THEN NULL
            END ASC,
            CASE 
                WHEN status = 'Done' THEN completion_time
                ELSE NULL
            END DESC
        ''',
        (session['userid'],)
    )
    tasks = cursor.fetchall()
    cursor.close()
    return render_template('tasks.html', tasks=tasks)


@app.route('/add_task', methods=['GET', 'POST'])
def add_task():
    if 'userid' not in session:
        return redirect(url_for('login'))  

    user_id = session['userid']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    current_date = datetime.now().date()

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        deadline = request.form['deadline']
        task_type = request.form['task_type']
        
        current_time = datetime.now() + timedelta(hours=time_zone) #added timedelta because Turkey is in UTC-3
        
        if datetime.strptime(deadline, '%Y-%m-%d').date() < current_date:
            cursor.execute('SELECT type FROM TaskType;')
            task_types = cursor.fetchall()
            return render_template(
                'add_task.html',
                error="Deadline cannot be in the past.",
                task_types=task_types,
                current_date=current_date
            )

        cursor.execute(
            '''
            INSERT INTO Task (title, description, status, deadline, creation_time, user_id, task_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
            ''',
            (title, description, 'Todo', deadline, current_time, user_id, task_type)
        )
        mysql.connection.commit()
        return redirect(url_for('tasks'))
    
    cursor.execute('SELECT type FROM TaskType;')
    task_types = cursor.fetchall()

    return render_template('add_task.html', task_types=task_types, current_date=current_date)

@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'])
def edit_task(task_id):
    if 'userid' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        deadline = request.form['deadline']
        task_type = request.form['task_type']

        current_date = datetime.now().date()
        if datetime.strptime(deadline, '%Y-%m-%d').date() < current_date:
            cursor.execute('SELECT type FROM TaskType')
            task_types = cursor.fetchall()
            return render_template(
                'edit_task.html',
                task={
                    'title': title,
                    'description': description,
                    'deadline': deadline,
                    'task_type': task_type
                },
                task_types=task_types,
                error="Deadline cannot be in the past.",
                current_date=current_date
            )

        cursor.execute(
            '''
            UPDATE Task 
            SET title = %s, description = %s, deadline = %s, task_type = %s 
            WHERE id = %s AND user_id = %s
            ''',
            (title, description, deadline, task_type, task_id, session['userid'])
        )
        mysql.connection.commit()
        return redirect(url_for('tasks'))

    cursor.execute(
        '''
        SELECT * FROM Task 
        WHERE id = %s AND user_id = %s
        ''',
        (task_id, session['userid'])
    )
    task = cursor.fetchone()

    cursor.execute('SELECT type FROM TaskType')
    task_types = cursor.fetchall()

    current_date = datetime.now().strftime('%Y-%m-%d')

    if task and task['deadline']:
        task['deadline'] = task['deadline'].strftime('%Y-%m-%d')

    return render_template(
        'edit_task.html',
        task=task,
        task_types=task_types,
        current_date=current_date
    )


@app.route('/delete_task/<int:task_id>', methods=['GET'])
def delete_task(task_id):
    if 'userid' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    cursor.execute(
        'DELETE FROM Task WHERE id = %s AND user_id = %s',
        (task_id, session['userid'])
    )
    mysql.connection.commit()
    return redirect(url_for('tasks'))

@app.route('/finish_task/<int:task_id>', methods=['GET'])
def finish_task(task_id):
    if 'userid' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    completion_time = datetime.now() + timedelta(hours=time_zone) #added timedelta because turkey is in UTC-3
    
    cursor.execute(
        '''
        UPDATE Task 
        SET status = %s, completion_time = %s 
        WHERE id = %s AND user_id = %s
        ''',
        ('Done', completion_time, task_id, session['userid'])
    )
    mysql.connection.commit()
    cursor.close()
    
    return redirect(url_for('tasks'))

@app.route('/undone_task/<int:task_id>', methods=['GET'])
def undone_task(task_id):
    if 'userid' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    cursor.execute(
        '''
        UPDATE Task 
        SET status = %s, completion_time = NULL 
        WHERE id = %s AND user_id = %s
        ''',
        ('Todo', task_id, session['userid'])
    )
    mysql.connection.commit()
    cursor.close()
    
    return redirect(url_for('tasks'))



@app.route('/add_task_type', methods=['GET', 'POST'])
def add_task_type():
    if 'userid' not in session:
        return redirect(url_for('login')) 
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if request.method == 'POST':
        task_type = request.form['task_type']

        cursor.execute('SELECT type FROM TaskType WHERE type = %s;', (task_type,))
        existing_type = cursor.fetchone()

        if existing_type:
            cursor.execute('SELECT type FROM TaskType;')
            task_types = cursor.fetchall()  
            return render_template(
                'add_task_type.html',
                error="Task Type already exists.",
                task_types=task_types
            )

        cursor.execute('INSERT INTO TaskType (type) VALUES (%s);', (task_type,))
        mysql.connection.commit()

        return redirect(url_for('add_task_type')) 

    cursor.execute('SELECT type FROM TaskType;')
    task_types = cursor.fetchall()

    return render_template('add_task_type.html', error=None, task_types=task_types)

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('loggedin', None)
    session.pop('userid', None)
    session.pop('username', None)
    session.pop('email', None)
    flash('You have successfully logged out! See you later!', 'success')
    return redirect(url_for('login'))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
