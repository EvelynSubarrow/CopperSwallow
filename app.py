#!/usr/bin/env python3

import logging, json
from collections import defaultdict

from operator import or_

import flask
from flask import Response
from flask import request
from flask import Flask, _app_ctx_stack

import sqlalchemy.orm

from IronSwallowORM.models import *


from util.locale import LocalisationSelector
from util import query, locale

with open("config.json") as f:
    config = json.load(f)

app = Flask(__name__)

engine = sqlalchemy.create_engine(config["database-string"], echo=config.get("echo-sql", False))
session_local = sqlalchemy.orm.sessionmaker(autocommit=True, autoflush=True, bind=engine)
app.session = sqlalchemy.orm.scoped_session(session_local, scopefunc=_app_ctx_stack.__ident_func__)

locale.setup_copperswallow_strings(app.session)

def no(*args, **kwargs):
    return

# Monkeypatch our autocommitting autoflushing session to do nothing with that
app.session.flush = no


class UnauthenticatedException(Exception): pass

def error_page(code, message):
    return flask.render_template('error.html', messages=["{0} - {1}".format(code, message)]), code

def format_time(dt, part):
    short = {"a": "arrival", "p": "pass", "d": "departure"}
    suffix = ""
    prefix = ""

    dt = dt["times"][short[part[0]]]

    if part[1]=="w":
        dt = dt.get("working")
        prefix += "s"
    elif part[1]==".":
        suffix += "."*bool(dt.get("actual")) or "~"
        dt = dt.get("estimated") or dt.get("actual")
    else:
        raise ValueError()

    if not dt:
        return ""
    else:
        return prefix + dt.strftime("%H%M") + "½"*(dt.second==30) + suffix

@app.route('/')
def index():
    return flask.render_template('index.html', operators=operator_categories(),
                    lc=LocalisationSelector(app.session, request), category="SMBF")


@app.route("/j/debug/<subsystem>")
def debug_json(subsystem):
    return Response(json.dumps([a.serialise() for a in app.session.query(SwallowDebug).filter(SwallowDebug.subsystem==subsystem)], indent=2, default=query.json_default), mimetype="application/json", status=200)


@app.route('/debug/<subsystem>')
def debug(subsystem):
    like = request.args.get("search", '', type=str)
    query = app.session.query(SwallowDebug).filter(SwallowDebug.subsystem==subsystem)
    if like:
        query = query.filter(SwallowDebug.disambiguation.like(like + "%"))

    return flask.render_template('debug.html', entries=query)


def strip_location_name(name):
    return name.upper().replace("LONDON", "").replace("GLASGOW", "").replace(" ", "").replace("-","").replace(".", "")


def operator_categories():
    operator_cats = OrderedDict()
    operators = app.session.query(DarwinOperator).order_by(DarwinOperator.category.desc()).order_by(DarwinOperator.operator)
    for operator in operators:
        operator_cats[operator.category] = operator_cats.get(operator.category, [])
        operator_cats[operator.category].append(operator)

    return operator_cats


@app.route('/location')
def locations():
    category = "".join(request.args.getlist("category", type=str)) or "SFBM"
    match = request.args.get("non_match", False, type=bool)
    disambiguation = request.args.get("disambiguate", False, type=bool)
    search = request.args.get("search", '', type=str)
    args_operator = request.args.get("operator", '', type=str)

    query = app.session.query(DarwinLocation).order_by(DarwinLocation.tiploc.asc())
    if category:
        query = query.filter(DarwinLocation.category.in_(list(category)))

    if disambiguation:
        stations_by_crs = defaultdict(list)
        q2 = app.session.query(DarwinLocation).filter(DarwinLocation.crs_darwin!=None)
        for station in q2:
            stations_by_crs[station.crs_darwin].append(station)
        station_dups = [k for k, v in stations_by_crs.items() if len(v) > 1]

        query = query.filter(DarwinLocation.crs_darwin.in_(station_dups)).order_by(DarwinLocation.crs_darwin.asc())
    else:
        query = query.order_by(DarwinLocation.tiploc.asc())

    if search:
        query = query.filter(or_(DarwinLocation.name_full.ilike("%" + search + "%"), DarwinLocation.name_darwin.ilike("%" + search + "%")))
    if args_operator:
        query = query.filter(DarwinLocation.operator == args_operator)
    if match:
        query = query.filter(DarwinLocation.name_darwin != DarwinLocation.name_full)
        query = [a for a in query if strip_location_name(a.name_darwin) != strip_location_name(a.name_full)]


    return flask.render_template('location_search.html', locations=query, operators=operator_categories(),
                        lc=LocalisationSelector(app.session, request),
                        args_operator=args_operator, category=category, search=search)


@app.route('/location/<location>')
def location(location):
    query = app.session.query(DarwinLocation).filter(DarwinLocation.tiploc==location)

    return flask.render_template("location_nonboard.html", location=query[0])


@app.route('/style')
def style():
    return app.send_static_file('style.css')


@app.route('/swallow')
def swallow():
    return app.send_static_file('swallow.svg')

@app.route('/main.js')
def main_js():
    return app.send_static_file('main.js')

@app.route('/json/departures/<location>', defaults={"time": "now"})
@app.route('/json/departures/<location>/<time>')
@app.route('/j/d/<location>', defaults={"time": "now"})
@app.route('/j/d/<location>/<time>')
def json_departures(location, time):
    failure_message = None
    status = 200
    try:
        if not location.isalnum(): raise ValueError
        if time=="now":
            time = datetime.datetime.now()
        else:
            time = datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S")

        response = query.station_board(location, time, period=500)


        if response:
            return Response(json.dumps(response, indent=2, default=query.json_default), mimetype="application/json", status=status)
        else:
            status, failure_message = 404, "Location(s) not found"
    # except ValueError as e:
    #     status, failure_message = 400, "Location codes must be alphanumeric, and the only permitted time is 'now'... for now"
    except Exception as e:
        logging.exception(e)
        if not failure_message:
            status, failure_message = 500, "Unhandled exception"
    return Response(json.dumps({"status": status, "message":failure_message}, indent=2), mimetype="application/json", status=status)

@app.route('/json/service/<id>', defaults={"date": None})
@app.route('/json/service/<id>/<date>')
@app.route('/j/s/<id>', defaults={"date": None})
@app.route('/j/s/<id>/<date>')
def json_service(id, date):
    failure_message = None
    status = 200
    try:
        if not id.isalnum(): raise ValueError
        if date in ["now", "today"]:
            date = datetime.datetime.now().date()
        elif date!=None:
            date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

        response = query.service(id, date)

        if response:
            return Response(json.dumps(response, indent=2, default=query.json_default), mimetype="application/json", status=status)
        else:
            status, failure_message = 404, "Schedule not found"
    except ValueError as e:
        logging.exception(e)
        status, failure_message = 400, "/<rid> requires a valid RID, /<uid>/<date> requires a valid UID, and a ISO 8601 date, or 'now'"

    return Response(json.dumps({"status": status, "message":failure_message}, indent=2), mimetype="application/json", status=status)


@app.route('/departures/<location>', defaults={"time": "now"})
@app.route('/departures/<location>/<time>')
@app.route('/d/<location>', defaults={"time": "now"})
@app.route('/d/<location>/<time>')

@app.route('/location/<location>/departures', defaults={"time": "now"})
@app.route('/location/<location>/departures/<time>')
def html_location(location, time):
    try:
        if not location.isalnum(): raise ValueError

        notes = []

        if time == "now":
            time = datetime.datetime.now()
            notes.append("Departures are for time of request")
        else:
            time = datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S")

        last_retrieved = query.last_retrieved()
        if not last_retrieved or (datetime.datetime.utcnow()-last_retrieved).seconds > 300:
            notes.append("Last Darwin message was parsed more than five minutes ago, information is likely out of date.")

        board = query.station_board(location, time)
        if not board:
            return error_page(404, "No such location code is known")

    except ValueError as e:
        logging.exception(e)
        return error_page(400, "Location names must be alphanumeric, datestamp must be either ISO 8601 format (YYYY-MM-DDThh:mm:ss) or 'now'")

    return Response(
        flask.render_template("location.html", board=board, time=time, location=location, message=None,
                              notes=notes, format_time=format_time),
        status=200,
        mimetype="text/html"
    )


@app.route('/location/<location>/arrivals', defaults={"time": "now"})
@app.route('/location/<location>/arrivals/<time>')
def html_arrivals(location, time):
    try:
        if not location.isalnum(): raise ValueError

        notes = []

        if time == "now":
            time = datetime.datetime.now()
            notes.append("Departures are for time of request")
        else:
            time = datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S")

        last_retrieved = query.last_retrieved()
        if not last_retrieved or (datetime.datetime.utcnow()-last_retrieved).seconds > 300:
            notes.append("Last Darwin message was parsed more than five minutes ago, information is likely out of date.")

        board = query.station_board(location, time, arrivals=True)
        if not board:
            return error_page(404, "No such location code is known")

    except ValueError as e:
        logging.exception(e)
        return error_page(400, "Location names must be alphanumeric, datestamp must be either ISO 8601 format (YYYY-MM-DDThh:mm:ss) or 'now'")

    return Response(
        flask.render_template("location.html", board=board, time=time, location=location, message=None,
                              notes=notes, format_time=format_time),
        status=200,
        mimetype="text/html"
    )


@app.route('/service/<id>', defaults={"date": None})
@app.route('/service/<id>/<date>')
@app.route('/s/<id>', defaults={"date": None})
@app.route('/s/<id>/<date>')
def html_service(id, date):
    try:
        if not id.isalnum(): raise ValueError

        notes = []

        if date in ["now", "today"]:
            date = datetime.datetime.now().date()
        elif date != None:
            date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

        last_retrieved = query.last_retrieved()
        if not last_retrieved or (datetime.datetime.utcnow()-last_retrieved).seconds > 300:
            notes.append("Last Darwin message was parsed more than five minutes ago, information is likely out of date.")

        schedule = query.service(id, date)

        if not schedule:
            return error_page(404, "No such service is known")

    except ValueError as e:
        return error_page(400, "/<rid> requires a valid RID, /<uid>/<date> requires a valid UID, and a ISO 8601 date, or 'now'")
    except UnauthenticatedException as e:
        return error_page(403, "Unauthenticated")
    except Exception as e:
        return error_page(500, "Unhandled exception")
    return Response(
        flask.render_template("schedule.html", schedule=schedule, date=date, message=None, notes=notes, format_time=format_time),
        status=200,
        mimetype="text/html"
        )

@app.route("/redirect/schedule")
def redirect_schedule():
    uid = request.args.get("uid", '')
    date = request.args.get("date", '')
    return flask.redirect(flask.url_for("html_service", id=uid, date=date))

@app.route("/redirect/location")
def redirect_location():
    code = request.args.get("code", '')
    time = request.args.get("time", 'now')
    return flask.redirect(flask.url_for("html_location", location=code, time=time))


if __name__ == "__main__":
    app.logger.setLevel(logging.ERROR)

    try:
        # Super sneaky side module to do nefarious things
        __import__("_web").init(app)
    except ImportError as e:
        pass

    app.run(
        config.get("flask-host", "0.0.0.0"),
        config.get("flask-port", 36323),
        config.get("flask-debug", False),
        ssl_context=None)
