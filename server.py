from flask import Flask, render_template, request, redirect, url_for, flash, session
import requests

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure key

ACCOUNT_SERVER_URL = 'https://antlaw-games-accounts.onrender.com'  # Replace with your actual account server URL

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        response = requests.post(f'{ACCOUNT_SERVER_URL}/api/register', json={
            'email': email,
            'password': password,
            'confirm_password': confirm_password
        })
        if response.status_code == 201:
            flash('Registration successful. Please log in.')
            return redirect(url_for('login_page'))
        else:
            flash(response.json().get('error', 'Registration failed.'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        response = requests.post(f'{ACCOUNT_SERVER_URL}/api/login', json={
            'email': email,
            'password': password
        })
        if response.status_code == 200:
            token = response.json().get('token')
            session['auth_token'] = token
            flash('Login successful.')
            return redirect(url_for('dashboard'))
        else:
            flash(response.json().get('error', 'Login failed.'))
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    token = session.get('auth_token')
    if not token:
        flash('Please log in to access the dashboard.')
        return redirect(url_for('login_page'))
    headers = {'Authorization': f'Bearer {token}'}
    response = requests.get(f'{ACCOUNT_SERVER_URL}/api/user', headers=headers)
    if response.status_code == 200:
        user_data = response.json()
        return render_template('dashboard.html', user=user_data)
    else:
        flash('Session expired. Please log in again.')
        return redirect(url_for('login_page'))

@app.route('/logout')
def logout():
    session.pop('auth_token', None)
    flash('Logged out successfully.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
