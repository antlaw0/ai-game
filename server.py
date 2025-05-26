from flask import Flask, render_template, redirect, url_for
import jwt
import os
SECRET_KEY=os.getenv('SECRET_KEY')


app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register-page')
def register_page():
    return render_template('register.html')

@app.route('/login-page')
def login_page():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    token = request.cookies.get('token')

    if not token:
        return redirect(url_for('login_page'))  # Redirect to login if no token

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        user_email = payload.get('email')

        if not user_email:
            raise jwt.InvalidTokenError()

        return render_template('dashboard.html', user={'email': user_email})

    except jwt.ExpiredSignatureError:
        return redirect(url_for('login_page'))  # Token expired
    except jwt.InvalidTokenError:
        return redirect(url_for('login_page'))  # Invalid token

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
