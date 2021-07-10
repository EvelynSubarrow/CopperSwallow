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

from src import location_list
from util.formatting import format_time

from util.locale import LocalisationSelector
from util import query, locale
from util.query import operator_categories
import util.query
import util.session_holder

with open("config.json") as f:
    config = json.load(f)

app = Flask(__name__)
app.register_blueprint(location_list.blueprint)

engine = sqlalchemy.create_engine(config["database-string"], echo=config.get("echo-sql", False))
session_local = sqlalchemy.orm.sessionmaker(autocommit=True, autoflush=True, bind=engine)
app.session = sqlalchemy.orm.scoped_session(session_local, scopefunc=_app_ctx_stack.__ident_func__)
util.session_holder.session = app.session

locale.setup_copperswallow_strings(app.session)

def no(*args, **kwargs):
    return

# Monkeypatch our autocommitting autoflushing session to do nothing with that
app.session.flush = no


class UnauthenticatedException(Exception): pass

def error_page(code, message):
    return flask.render_template('error.html', messages=["{0} - {1}".format(code, message)]), code



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



@app.route('/location/<location>')
def location(location):
    query = app.session.query(DarwinLocation).filter(
        or_(DarwinLocation.tiploc == location, DarwinLocation.crs_darwin == location))

    singular_crs = None
    best_name, best_code = None, None
    if query.count():
        singular_crs = query[0].crs_darwin
        best_name, best_code = query[0].name_full, query[0].tiploc
        if singular_crs and query.count() > 1:
            best_name, best_code = query[0].name_darwin, singular_crs
        elif singular_crs and query.count() == 1:
            best_code = singular_crs

    return flask.render_template("location_nonboard.html", locations=query, best_name=best_name, best_code=best_code)


@app.route('/style')
def style():
    return app.send_static_file('style.css')


@app.route('/swallow')
def swallow():
    return app.send_static_file('swallow.svg')


@app.route('/main.js')
def main_js():
    return app.send_static_file('main.js')


@app.route('/json/location/<location>/departures', defaults={"time": "now"})
@app.route('/json/location/<location>/departures/<time>')
def json_departures(location, time):
    failure_message = None
    status = 200
    try:
        if not location.isalnum(): raise ValueError
        if time == "now":
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


def compose_text_response(station_board):
    text = "Locations\n"

    for location in station_board["locations"].values():
        text += f"| {location['location_category']} {location['name_full']} ({location['tiploc']} {location['crs_darwin'] or ''})\n"
    if station_board["messages"]:
        text += "Messages\n"
        for message in station_board["messages"]:
            text += f"| {repr(message)}"
    text += "Services\n"
    for service in station_board["services"]:
        here = service["here"]
        here_plat = here["platform"]
        plat = ""
        if here_plat["platform"]:
            plat = "*"*here_plat["suppressed"] + here_plat["platform"] + "."*here_plat["confirmed"]
        text += f"| {format_time(here, 'dw'):<5} {format_time(here, 'd.'):<5} {plat:<4} {'/'.join([a['name_full'] for a in service['destinations']])}\n"

    return text


@app.route('/text/location/<location>/departures', defaults={"time": "now"})
@app.route('/text/location/<location>/departures/<time>')
def text_departures(location, time):
    failure_message = None
    status = 200
    try:
        if not location.isalnum(): raise ValueError
        if time == "now":
            time = datetime.datetime.now()
        else:
            time = datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S")

        response = query.station_board(location, time, period=500)


        if response:
            return Response(compose_text_response(response), mimetype="text/plain", status=status)
        else:
            status, failure_message = 404, "Location(s) not found"
    # except ValueError as e:
    #     status, failure_message = 400, "Location codes must be alphanumeric, and the only permitted time is 'now'... for now"
    except Exception as e:
        logging.exception(e)
        if not failure_message:
            status, failure_message = 500, "Unhandled exception"
    return Response(f"""| {status}: status\n| {failure_message}""", mimetype="text/plain", status=status)


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
