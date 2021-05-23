def format_time(dt, part):
    short = {"a": "arrival", "p": "pass", "d": "departure"}
    suffix = ""
    prefix = ""

    dt = dt["times"][short[part[0]]]

    if part[1] == "w":
        dt = dt.get("working")
        prefix += "s"
    elif part[1] == ".":
        suffix += "."*bool(dt.get("actual")) or "~"
        dt = dt.get("estimated") or dt.get("actual")
    else:
        raise ValueError()

    if not dt:
        return ""
    else:
        return prefix + dt.strftime("%H%M") + "½"*(dt.second == 30) + suffix


def strip_location_name(name: str):
    return name.upper().replace("LONDON", "").replace("GLASGOW", "").replace(" ", "").replace("-", "").replace(".", "")
