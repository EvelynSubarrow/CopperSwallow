import datetime
from typing import Optional

import sqlalchemy.orm
from sqlalchemy import or_, and_

import app
from IronSwallowORM.models import *


def json_default(value) -> str:
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    elif isinstance(value, datetime.date):
        return value.isoformat()
    elif isinstance(value, datetime.time):
        return value.isoformat()
    else:
        raise ValueError(type(value))


def station_board(location: str, query_dt=None, period: int = 480, limit: int = 50, intermediate_tiploc=None, passenger_only=True, arrivals=False) -> dict:
    location = location.upper()
    out = OrderedDict()

    query_dt_last = query_dt + datetime.timedelta(minutes=period)

    out["locations"] = OrderedDict([(a.tiploc, a.serialise(False)) for a in app.app.session.query(DarwinLocation).filter(or_(DarwinLocation.crs_darwin==location, DarwinLocation.tiploc==location))])

    # TODO: This structure doesn't accommodate the possibility of mutiple CRS per query, nor for querying by ITPS CRS
    # TODO: Realistically it has to still be its own level to avoid duplication so this might be tricky
    singular_crs = None
    if out["locations"]: singular_crs = list(out["locations"].values())[0]["crs_darwin"]

    out["messages"] = [a.serialise(False) for a in app.app.session.query(DarwinMessage).filter(DarwinMessage.stations.any(singular_crs))]

    query = app.app.session.query(DarwinScheduleLocation).join(DarwinScheduleLocation.schedule).options(
        sqlalchemy.orm.joinedload(DarwinScheduleLocation.schedule)).filter(
        DarwinSchedule.is_deleted == False)

    if arrivals:
        query = query.filter(DarwinScheduleLocation.wta is not None,
                             DarwinScheduleLocation.tiploc.in_(list(out["locations"].keys())),
                             DarwinScheduleLocation.loc_type != "PP",
                             DarwinScheduleLocation.wta > query_dt,
                             DarwinScheduleLocation.wta < query_dt_last,
                             ).order_by(DarwinScheduleLocation.wta).limit(limit)
    else:
        query = query.filter(DarwinScheduleLocation.wtd is not None,
                            DarwinScheduleLocation.tiploc.in_(list(out["locations"].keys())),
                            DarwinScheduleLocation.loc_type != "PP",
                            DarwinScheduleLocation.wtd > query_dt,
                            DarwinScheduleLocation.wtd < query_dt_last,
                            ).order_by(DarwinScheduleLocation.wtd).limit(limit)

    out["services"] = [a.serialise(True) for a in query]

    return out

def service(sid, date=None) -> dict:
    service = app.app.session.query(DarwinSchedule).filter(
        or_(DarwinSchedule.rid == sid,
            and_(DarwinSchedule.uid == sid, DarwinSchedule.ssd == date)
            )
    ).first()
    if service:
        return service.serialise(True)


def last_retrieved() -> Optional[datetime.datetime]:
    result = app.app.session.query(LastReceivedSequence)
    if result.count():
        return result[0].time_acquired


def operator_categories():
    operator_cats = OrderedDict()
    operators = app.app.session.query(DarwinOperator).order_by(DarwinOperator.category.desc()).order_by(DarwinOperator.operator)
    for operator in operators:
        operator_cats[operator.category] = operator_cats.get(operator.category, [])
        operator_cats[operator.category].append(operator)

    return operator_cats
