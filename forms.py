from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from models import User

class RegistrationForm(FlaskForm):
    username = StringField('Použivatelské meno', validators=[DataRequired(), Length(min=3, max=25)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Heslo', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Potvrď heslo', validators=[DataRequired(), EqualTo('password', message='Heslá sa musia zhodovať')])
    submit = SubmitField('Registrovať')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Toto používateľské meno už existuje.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data.lower().strip()).first()
        if user:
            raise ValidationError('Tento email už je zaregistrovaný.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Heslo', validators=[DataRequired()])
    submit = SubmitField('Prihlásiť sa')

