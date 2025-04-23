from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from models import Courier

class LoginForm(FlaskForm):
    username = StringField('Nazwa użytkownika', validators=[DataRequired()])
    password = PasswordField('Hasło', validators=[DataRequired()])
    remember = BooleanField('Zapamiętaj mnie')
    submit = SubmitField('Zaloguj się')

class RegistrationForm(FlaskForm):
    username = StringField('Nazwa użytkownika', validators=[
        DataRequired(), 
        Length(min=3, max=80, message='Nazwa użytkownika musi mieć od 3 do 80 znaków')
    ])
    email = StringField('Email', validators=[
        DataRequired(), 
        Email(message='Wprowadź poprawny adres email')
    ])
    password = PasswordField('Hasło', validators=[
        DataRequired(),
        Length(min=6, message='Hasło musi mieć co najmniej 6 znaków')
    ])
    password2 = PasswordField('Powtórz hasło', validators=[
        DataRequired(),
        EqualTo('password', message='Hasła muszą być identyczne')
    ])
    first_name = StringField('Imię')
    last_name = StringField('Nazwisko')
    phone = StringField('Telefon')
    submit = SubmitField('Zarejestruj się')
    
    def validate_username(self, username):
        """Sprawdza, czy nazwa użytkownika jest już zajęta"""
        courier = Courier.query.filter_by(username=username.data).first()
        if courier:
            raise ValidationError('Ta nazwa użytkownika jest już zajęta. Wybierz inną.')
            
    def validate_email(self, email):
        """Sprawdza, czy email jest już zajęty"""
        courier = Courier.query.filter_by(email=email.data).first()
        if courier:
            raise ValidationError('Ten adres email jest już zarejestrowany. Użyj innego adresu lub zaloguj się.')