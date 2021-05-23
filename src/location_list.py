import json
from collections import defaultdict

import flask
from flask import Blueprint, Response, request
from sqlalchemy import or_

from IronSwallowORM.models import DarwinLocation
from util import query
from util.formatting import strip_location_name
from util.locale import LocalisationSelector
from util.query import operator_categories
import util.session_holder

blueprint = Blueprint("LocationRoute", __name__)


def get_session():
    return util.session_holder.session


@blueprint.route('/j/location')
@blueprint.route('/json/location')
@blueprint.route('/location/json')
def js_locations():
    return Response(
        json.dumps([a.serialise(True) for a in get_session().query(DarwinLocation).order_by(DarwinLocation.tiploc)],
                   indent=2, default=query.json_default), mimetype="application/json", status=200)


@blueprint.route('/location/html')
@blueprint.route('/location')
@blueprint.route('/html/location')
def locations():
    category = "".join(request.args.getlist("category", type=str)) or "SFBM"
    match = request.args.get("non_match", False, type=bool)
    disambiguation = request.args.get("disambiguate", False, type=bool)
    search = request.args.get("search", '', type=str)
    args_operator = request.args.get("operator", '', type=str)

    query = get_session().query(DarwinLocation).order_by(DarwinLocation.tiploc.asc())
    if category:
        query = query.filter(DarwinLocation.category.in_(list(category)))

    if disambiguation:
        stations_by_crs = defaultdict(list)
        q2 = get_session().query(DarwinLocation).filter(DarwinLocation.crs_darwin!=None)
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
                        lc=LocalisationSelector(get_session(), request),
                        args_operator=args_operator, category=category, search=search)
