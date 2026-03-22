"""
hospitals.py — Loads hospitals.csv from the DS project and exposes
a clean in-memory registry that the rest of the backend can query.

DS file: data/hospitals.csv
Columns (raw header row is a bit unusual — see below):
  PARISH,C,25  |  HEALTH_ARE,C,16  |  FACIL_TYPE,C,40  |  CEN_NAME,C,50
  CEN_CODE,C,8 |  ADDRESS,C,80     |  TELEPHONE,C,10   |  FACIL_STAT,C,16
  OWNERSHIP,C,16 | Z990__BEDS,N,10,0 | Z996__BEDS,N,10,0 | Z999__BEDS,N,10,0

HOW TO CONNECT YOUR DS PROJECT:
  Set DS_DATA_PATH to point at the data/ folder in your DS project, e.g.
      export DS_DATA_PATH=../../hospital-resource-optimisation-ds/data
  The service will load hospitals.csv from that path automatically.
  If DS_DATA_PATH is not set it falls back to the embedded snapshot below.
"""

import os
import csv
import io
from backend.models.schemas import FacilityInfo

# ── Embedded snapshot of hospitals.csv (public data, used when DS_DATA_PATH
#    is not configured so the API works out-of-the-box) ─────────────────────────
_HOSPITALS_CSV_SNAPSHOT = """PARISH,HEALTH_ARE,FACIL_TYPE,CEN_NAME,CEN_CODE,ADDRESS,TELEPHONE,FACIL_STAT,OWNERSHIP,Z990__BEDS,Z996__BEDS,Z999__BEDS
Kingston and St. Andrew,SE Health Region,Type S Specialist Hospital,Victoria Jubilee,01-24,"North Street, Kgn.",922-1700,Open,Public,215,176,177
Kingston and St. Andrew,SE Health Region,Type S Specialist Hospital,National Chest,01-23,"36 1/2 Barbican Rd., Kgn. 6",977-7071,Open,Private,73,100,100
Kingston and St. Andrew,SE Health Region,Type S Specialist Hospital,Bustamante,01-20,"Arthur Wint Dr., Kgn. 5",926-5721,Open,Public,244,253,253
Kingston and St. Andrew,SE Health Region,Type A Hospital,Kingston Public,01-02,"North Street, Kgn.",922-0227,Open,Public,442,360,399
Kingston and St. Andrew,SE Health Region,Type A Hospital,University,01-03,Mona,927-1620,Open,Quasi Public,0,0,0
Kingston and St. Andrew,SE Health Region,Type S Specialist Hospital,Sir John Golding,,7 Golding Ave.,927-2504,Open,Public,0,0,0
Kingston and St. Andrew,SE Health Region,Type S Specialist Hospital,Hope Institute,01-21,Elleston Flats,927-2111,Open,Public,52,45,44
Kingston and St. Andrew,SE Health Region,Type S Specialist Hospital,Bellevue,01-19,"16 Windward Rd., Kgn. 2",928-1380,Open,Public,1600,1190,1190
Kingston and St. Andrew,SE Health Region,Hospital,Andrews Memorial,,27 Hope Rd.,926-7401,Open,Private,0,0,0
Kingston and St. Andrew,SE Health Region,Hospital,Maxfield Medical,,69 Maxfield Ave.,926-1121,Open,Private,0,0,0
Kingston and St. Andrew,SE Health Region,Hospital,Medical Associates,,18 Tangerine Place,926-1400,Open,Private,0,0,0
Kingston and St. Andrew,SE Health Region,Hospital,Nuttal Memorial,,6 Caledonia Ave.,926-2139,Open,Private,0,0,0
Kingston and St. Andrew,SE Health Region,Hospital,St. Josephs,,22 Deanery Rd.,928-4955,Open,Private,0,0,0
St. Thomas,SE Health Region,Type C Hospital,Princess Margaret,03-18,"54 Lyssons Rd., Morant Bay P.O.",982-2304,Open,Public,52,98,98
Portland,NE Health Region,Type C Hospital,Port Antonio,04-16,Naylors Hill,993-2646,Open,Public,125,125,165
St. Mary,NE Health Region,Type C Hospital,Annotto Bay,05-08,Annotto Bay,996-2222,Open,Public,117,120,120
St. Mary,NE Health Region,Type C Hospital,Port Maria,05-17,"Trinity, Port Maria",994-2228,Open,Public,87,89,75
St. Ann,NE Health Region,Type B Hospital,St. Anns Bay,06-05,St. Anns Bay P.O.,972-2272,Open,Public,150,140,139
Trelawny,W Health Region,Type C Hospital,Falmouth,07-10,Golden Grove,954-3250,Open,Public,103,62,89
St. James,W Health Region,Type A Hospital,Cornwall Regional,08-01,"Mt. Salem, Montego Bay P.O.",952-6683,Open,Public,242,320,317
St. James,W Health Region,Hospital,Doctors Hospital,,Fairfield,952-1616,Open,Private,0,0,0
St. James,W Health Region,Hospital,Mobay Hope,,"Halfmoon, Rosehall",953-3981,Open,Private,0,0,0
St. James,W Health Region,Hospital,Faith Maternity,,"Clegg Close, Brandon Hill, Montego Bay P.O.",952-2266,Open,Private,0,0,0
Hanover,W Health Region,Type C Hospital,Noel Holmes,09-14,Fort Charlotte Dr.,956-2733,Open,Public,51,52,57
Westmoreland,W Health Region,Type B Hospital,Sav-la-mar,10-06,"Barracks Rd., Sav-la-mar",955-2133,Open,Public,131,168,189
Westmoreland,W Health Region,Hospital,Royal Medical,,"Lewis Street, Sav-la-mar",955-3154,Open,Private,0,0,0
St. Elizabeth,S Health Region,Type C Hospital,Black River,11-09,"45 High Street, Black River",965-2212,Open,Public,121,101,97
Manchester,S Health Region,Type B Hospital,Mandeville,12-04,32 Hargreaves Ave.,962-2067,Open,Public,163,168,155
Manchester,S Health Region,Specialist Hospital,Hargreaves Memorial,,32 Hargreaves Ave.,962-2040,Open,Private,0,0,0
Manchester,S Health Region,Type C Hospital,Percy Junor,12-15,Christiana P.O.,964-2322,Open,Public,122,120,120
Clarendon,S Health Region,Type C Hospital,May Pen,13-13,Muirhead Ave,986-2528,Open,Public,70,69,86
Clarendon,S Health Region,Type C Hospital,Lionel Town,13-12,Vere,986-3226,Open,Public,60,60,60
St. Catherine,SE Health Region,Type B Hospital,Spanish Town,14-07,"Burke Rd., Spanish Town",984-3031,Open,Public,282,280,300
St. Catherine,SE Health Region,Type C Hospital,Linstead,14-11,"Rodney Hall Rd., Linstead P.O.",984-2241,Open,Public,50,53,52
Kingston and St. Andrew,SE Health Region,Type A Hospital,Mona Rehabilitation,01-22,Mona,,Open,Public,90,0,71
"""


def _safe_int(val: str) -> int:
    try:
        return int(val.strip())
    except (ValueError, AttributeError):
        return 0


def _load_from_csv(content: str) -> list[FacilityInfo]:
    """Parse CSV content into a list of FacilityInfo objects."""
    facilities = []
    reader = csv.DictReader(io.StringIO(content.strip()))
    for row in reader:
        # The raw CSV header uses compound keys like "PARISH,C,25" —
        # handle both raw and cleaned versions.
        code = (row.get("CEN_CODE") or row.get("CEN_CODE,C,8") or "").strip()
        if not code:
            continue  # skip rows without a facility code
        facilities.append(FacilityInfo(
            facility_code=code,
            name=(row.get("CEN_NAME") or row.get("CEN_NAME,C,50") or "").strip(),
            parish=(row.get("PARISH") or row.get("PARISH,C,25") or "").strip(),
            health_region=(row.get("HEALTH_ARE") or row.get("HEALTH_ARE,C,16") or "").strip(),
            facility_type=(row.get("FACIL_TYPE") or row.get("FACIL_TYPE,C,40") or "").strip(),
            ownership=(row.get("OWNERSHIP") or row.get("OWNERSHIP,C,16") or "").strip(),
            status=(row.get("FACIL_STAT") or row.get("FACIL_STAT,C,16") or "").strip(),
            beds_z990=_safe_int(row.get("Z990__BEDS") or row.get("Z990__BEDS,N,10,0") or "0"),
            beds_z996=_safe_int(row.get("Z996__BEDS") or row.get("Z996__BEDS,N,10,0") or "0"),
            beds_z999=_safe_int(row.get("Z999__BEDS") or row.get("Z999__BEDS,N,10,0") or "0"),
        ))
    return facilities


def load_hospitals() -> list[FacilityInfo]:
    """
    Load hospital data.  Prefers DS_DATA_PATH/hospitals.csv if set,
    otherwise falls back to the embedded snapshot.
    """
    ds_data_path = os.environ.get("DS_DATA_PATH", "")
    if ds_data_path:
        csv_path = os.path.join(ds_data_path, "hospitals.csv")
        if os.path.isfile(csv_path):
            with open(csv_path, "r", encoding="utf-8") as f:
                return _load_from_csv(f.read())

    return _load_from_csv(_HOSPITALS_CSV_SNAPSHOT)


# ── Module-level registry (loaded once at import time) ────────────────────────
_HOSPITALS: list[FacilityInfo] = load_hospitals()

# Only facilities that have a code AND at least some beds in Z999
ACTIVE_FACILITIES: list[FacilityInfo] = [
    h for h in _HOSPITALS if h.facility_code and h.beds_z999 > 0
]

# Facility code → FacilityInfo lookup
FACILITY_MAP: dict[str, FacilityInfo] = {
    f.facility_code: f for f in ACTIVE_FACILITIES
}


def get_facility(code: str) -> FacilityInfo | None:
    return FACILITY_MAP.get(code)
