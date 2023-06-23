import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    # select user's stock portfolio and cash total
    rows = db.execute("SELECT * FROM portfolio WHERE userid = :id", id=session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])

    # get cash value float
    cash = cash[0]['cash']
    # this will be total value of all stock holdings and cash
    sum = cash

    # add stock name, add current lookup value, add total value
    for row in rows:
        look = lookup(row['symbol'])
        row['name'] = look['name']
        row['price'] = look['price']
        row['total'] = row['price'] * row['shares']

        # increment sum
        sum += row['total']

        # convert price and total to usd format
        row['price'] = usd(row['price'])
        row['total'] = usd(row['total'])

    return render_template("index.html", rows=rows, cash=usd(cash), sum=usd(sum))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return  render_template("buy.html")
    else:
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        quote = lookup(symbol)


        if quote == None:
            return apology("must provide valid stock symbol", 400)

        if not shares:
            return apology("must provide number of shares", 403)
        if not shares.isdigit():
            return apology("You cannot purchase partial shares.")

        symbol = symbol.upper()
        shares = int(shares)
        purchase = quote['price'] * shares

        if shares < 1:
            return apology("Invalid No. of shares", 400)


        balance = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        balance = balance[0]['cash']
        remainder = balance - purchase

        if remainder < 0:
            return apology("insufficient funds", 403)

        row = db.execute("SELECT * FROM portfolio WHERE userid = :id AND symbol = :symbol",
                         id=session["user_id"], symbol=symbol)

        if len(row) != 1:
            db.execute("INSERT INTO portfolio (userid, symbol) VALUES (:id, :symbol)",
                       id=session["user_id"], symbol=symbol)


        oldshares = db.execute("SELECT shares FROM portfolio WHERE userid = :id AND symbol = :symbol",
                               id=session["user_id"], symbol=symbol)

        oldshares = oldshares[0]["shares"]

        newshares = oldshares + shares

        db.execute("UPDATE portfolio SET shares = :newshares WHERE userid = :id AND symbol = :symbol",
                   newshares=newshares, id=session["user_id"], symbol=symbol)

        db.execute("UPDATE users SET cash = :remainder WHERE id = :id",
                   remainder=remainder, id=session["user_id"])

        db.execute("INSERT INTO history (userid, symbol, shares, method, price) VALUES (:userid, :symbol, :shares, 'Buy', :price)",
                   userid=session["user_id"], symbol=symbol, shares=shares, price=quote['price'])

    # redirect to index page
    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute("SELECT * FROM history WHERE userid = :userid", userid=session["user_id"])

    # return history template
    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
        if request.method == "GET":
            return render_template("quote.html")
        else:
            symbol = lookup(request.form.get("symbol"))

            # if lookup() returns None, it's not a valid stock symbol
            if symbol == None:
                return apology("invalid stock symbol", 400)

            # Return template with stock quote, passing in symbol dict
            return render_template("quoted.html", symbol=symbol)



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (submitting the register form)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # ensure passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # save username and password hash in variables
        username = request.form.get("username")
        hash = generate_password_hash(request.form.get("password"))

        # Query database to ensure username isn't already taken
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=username)
        if len(rows) != 0:
            return apology("username is already taken", 400)

        # insert username and hash into database
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                   username=username, hash=hash)

        # redirect to login page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # if GET method, render sell.html form
    if request.method == "GET":

        # get the user's current stocks
        portfolio = db.execute("SELECT symbol FROM portfolio WHERE userid = :id",
                               id=session["user_id"])

        # render sell.html form, passing in current stocks
        return render_template("sell.html", portfolio=portfolio)

    # if POST method, sell stock
    else:
        # save stock symbol, number of shares, and quote dict from form
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        quote = lookup(symbol)
        rows = db.execute("SELECT * FROM portfolio WHERE userid = :id AND symbol = :symbol",
                          id=session["user_id"], symbol=symbol)

        # return apology if symbol invalid/ not owned
        if len(rows) != 1:
            return apology("must provide valid stock symbol", 400)

        # return apology if shares not provided. buy form only accepts positive integers
        if not shares:
            return apology("must provide number of shares", 400)

        # current shares of this stock
        oldshares = rows[0]['shares']

        # cast shares from form to int
        shares = int(shares)

        # return apology if trying to sell more shares than own
        if shares > oldshares:
            return apology("shares sold can't exceed shares owned", 400)

        # get current value of stock price times shares
        sold = quote['price'] * shares

        # add value of sold stocks to previous cash balance
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session['user_id'])
        cash = cash[0]['cash']
        cash = cash + sold

        # update cash balance in users table
        db.execute("UPDATE users SET cash = :cash WHERE id = :id",
                   cash=cash, id=session["user_id"])

        # subtract sold shares from previous shares
        newshares = oldshares - shares

        # if shares remain, update portfolio table with new shares
        if shares > 0:
            db.execute("UPDATE portfolio SET shares = :newshares WHERE userid = :id AND symbol = :symbol",
                       newshares=newshares, id=session["user_id"], symbol=symbol)

        # otherwise delete stock row because no shares remain
        else:
            db.execute("DELETE FROM portfolio WHERE symbol = :symbol AND userid = :id",
                       symbol=symbol, id=session["user_id"])

        # update history table
        db.execute("INSERT INTO history (userid, symbol, shares, method, price) VALUES (:userid, :symbol, :shares, 'Sell', :price)",
                   userid=session["user_id"], symbol=symbol, shares=shares, price=quote['price'])

        # redirect to index page
        return redirect("/")
if __name__ == '__main__':
    app.run()

