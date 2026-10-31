from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo

class Login(FlaskForm):
    email = StringField('Email', validators=[DataRequired(message='Please enter your email address.'), Email(message='Please enter a valid email account.')])
    submit = SubmitField('Login')

class Signup(FlaskForm):
    username = StringField('Username', validators=[DataRequired(message='Please enter a username.'), Length(min=3, max=80, message='Username must be between 3 and 80 characters.')])
    email = StringField('Email', validators=[DataRequired(message='Please enter your email address.'), Email(message='Please enter a valid email account.')])
    submit = SubmitField('Sign Up with OTP')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Send Reset OTP')

class ResetPasswordForm(FlaskForm):
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6, max=120)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('new_password', message='Passwords must match')])
    submit = SubmitField('Reset Password')

class ProfileUpdateForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    submit = SubmitField('Update Profile')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6, max=120)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('new_password', message='Passwords must match')])
    submit = SubmitField('Change Password')
