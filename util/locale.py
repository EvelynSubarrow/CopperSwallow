import fnmatch
from typing import Optional
from collections import OrderedDict

from flask import Request
from sqlalchemy.orm import Query

from IronSwallowORM.models import LocalisedReference

CS_ALL_STRINGS = [
    ("en_gb", "TERMS", "name_corpus", "Name (CORPUS)"),
    ("nb_no", "TERMS", "name_corpus", "Navn (CORPUS)"),

    ("en_gb", "TERMS", "name_darwin", "Name (Darwin)"),
    ("nb_no", "TERMS", "name_darwin", "Navn (Darwin)"),

    ("en_gb", "TERMS", "name_full", "Name (Full normalised)"),
    ("nb_no", "TERMS", "name_full", "Navn (Hele normalisert)"),

    ("en_gb", "TERMS", "category", "Category"),
    ("nb_no", "TERMS", "category", "Kategori"),

    ("en_gb", "TERMS", "operator", "Operator"),
    ("nb_no", "TERMS", "operator", "Operatør"),

    ("en_gb", "TERMS", "dropdown_any", "Any"),
    ("nb_no", "TERMS", "dropdown_any", "Alle"),

    ("en_gb", "TERMS", "dropdown_groups", "Groups"),
    ("nb_no", "TERMS", "dropdown_groups", "Grupper"),

    ("en_gb", "TERMS", "search", "Search"),
    ("nb_no", "TERMS", "search", "Søk")
    ]

def setup_copperswallow_strings(session):
    for locale,code_type,code,description in CS_ALL_STRINGS:
        session.merge(LocalisedReference(source="CS", locale=locale, code_type=code_type, code=code, description=description))

    session.flush()

class LocalisationSelector:
    def __init__(self, session, request: Request):
        self._map = OrderedDict()
        self._locales = [k for k,v in request.accept_languages]
        if request.args.get("locale"):
            self._locales = [request.args.get("locale")] + self._locales
        self._locales = [a.replace("-", "_") for a in self._locales]

        query: Query[LocalisedReference] = session.query(LocalisedReference).order_by(LocalisedReference.code)
        for reference in query:
            self._map[f"/{reference.source}/{reference.code_type}/{reference.code}/{reference.locale}"] = reference.description

    def get(self, source, code_type, code) -> Optional[str]:
        for locale in self._locales + ["en_gb"]:
            result = self._map.get(f"/{source}/{code_type}/{code}/{locale}")
            if result:
                return result


    def get_list(self, source, code_type) -> list:
        candidate_codes = OrderedDict([(a.split("/")[3], 1) for a in self._map if a.startswith(f"/{source}/{code_type}/")]).keys()
        candidate_results = [(a, self.get(source, code_type, a)) for a in candidate_codes]
        return [(a,b) for a,b in candidate_results if a]


    def get_is(self, code_type, code):
        return self.get("IS", code_type, code)


    def get_bplan(self, code_type, code):
        return self.get("BPLAN", code_type, code)

    def get_term(self, term):
        return self.get("CS", "TERMS", term)
