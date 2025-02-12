from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app)

# Store active users
active_users = {}

# Database Models
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    content = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_private = db.Column(db.Boolean, default=False)
    recipient = db.Column(db.String(50), nullable=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['username'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid username or password")
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            return render_template('register.html', error="Username already exists")
            
        user = User(username=username)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        return redirect(url_for('login'))
        
    return render_template('register.html')

@socketio.on('connect')
def handle_connect():
    if 'username' in session:
        active_users[request.sid] = session['username']
        emit('user_list', list(active_users.values()), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in active_users:
        del active_users[request.sid]
        emit('user_list', list(active_users.values()), broadcast=True)

@socketio.on('message')
def handle_message(data):
    if 'username' not in session:
        return
    
    username = session['username']
    content = data.get('message')
    recipient = data.get('recipient')
    timestamp = datetime.utcnow()
    
    # Save message to database
    message = Message(
        username=username,
        content=content,
        is_private=bool(recipient),
        recipient=recipient
    )
    db.session.add(message)
    db.session.commit()
    
    # Format message for display
    message_data = {
        'username': username,
        'content': content,
        'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    if recipient:
        # Private message
        for sid, user in active_users.items():
            if user in [recipient, username]:
                emit('private_message', message_data, room=sid)
    else:
        # Public message
        emit('message', message_data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
