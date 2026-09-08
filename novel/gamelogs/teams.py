"""Team-name resolution: ncaahoopR team-directory names <-> Torvik / Wikipedia college names.
Rule-based: normalisation + expansion of directional/state abbreviations + an explicit alias table."""
import re, unicodedata

def nrm(s):
    s = s or ""
    for dash in ("\u2013", "\u2014", "\u2212", "\u2010", "\u2011"): s = s.replace(dash, " ")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = s.replace("'", "").replace("\u2019", "")
    s = s.replace("&", " and ").replace("_", " ").replace("-", " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\bmens? basketball\b", " ", s)
    s = re.sub(r"\bthe\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()

EXPAND = [(r"^cal st ", "cal state "), (r"^n ", "northern "), (r"^e ", "eastern "), (r"^w ", "western "),
          (r"^cent ", "central "), (r"^c ", "coastal "), (r"^ga ", "georgia "),
          (r"\bst$", "state"), (r"\bst\b", "saint"), (r"\bso$", "southern"),
          (r"\bmiss\b", "mississippi"), (r"\bfla\b", "florida"), (r"\bmt\b", "mount")]

def expand(k):
    for pat, rep in EXPAND:
        k = re.sub(pat, rep, k)
    return re.sub(r"\s+", " ", k).strip()

# team_dir -> canonical full program name (only where normalisation is not enough).
ALIAS = {
 "AR-Pine_Bluff": "arkansas pine bluff", "Abil_Christian": "abilene christian",
 "Albany": "albany ny", "American": "american university", "BYU": "brigham young",
 "Boston_U": "boston university", "C._Carolina": "coastal carolina",
 "CSU_Bakersfield": "cal st bakersfield", "CSU_Fullerton": "cal st fullerton",
 "CSU_Northridge": "cal st northridge", "Cal": "california",
 "Cal_Baptist": "california baptist", "Cal_Poly": "cal poly",
 "Cent_Conn_St": "central connecticut", "Charleston": "college of charleston",
 "Charleston_So": "charleston southern", "Detroit_Mercy": "detroit",
 "ECU": "east carolina", "ETSU": "east tennessee state", "FAU": "florida atlantic",
 "FGCU": "florida gulf coast", "FIU": "florida international",
 "Fair_Dickinson": "fairleigh dickinson", "Fort_Wayne": "purdue fort wayne",
 "G_Washington": "george washington", "Ga_Southern": "georgia southern",
 "Green_Bay": "green bay", "Hawai'i": "hawaii", "IUPUI": "iupui", "IU_Indy": "iu indy",
 "JMU": "james madison", "LA_Tech": "louisiana tech", "LIU": "long island",
 "LSU": "lsu", "Little_Rock": "arkansas little rock",
 "Long_Beach_St": "long beach state", "Long_Beach_State": "long beach state",
 "Louisiana": "louisiana lafayette", "Loyola-Chicago": "loyola chicago",
 "Loyola_(MD)": "loyola md", "Loyola_Mary": "loyola marymount",
 "MD-E_Shore": "maryland eastern shore", "Mcneese": "mcneese state",
 "Miami": "miami fl", "Miami_(OH)": "miami oh", "Mid_Tennessee": "middle tennessee",
 "Milwaukee": "milwaukee", "Miss_St": "mississippi state",
 "Miss_Valley_St": "mississippi valley state", "Mt_St_Mary's": "mount st marys",
 "NC_A&T": "north carolina a and t", "NC_Central": "north carolina central",
 "NC_State": "north carolina state", "NJIT": "njit", "Ole_Miss": "mississippi",
 "Omaha": "nebraska omaha", "PV_A&M": "prairie view a and m", "Penn": "pennsylvania",
 "Pitt": "pittsburgh", "Queens_University": "queens nc", "S_Carolina_St": "south carolina state",
 "S_Illinois": "southern illinois", "SE_Louisiana": "southeastern louisiana",
 "SE_Missouri_St": "southeast missouri state", "SF_Austin": "stephen f austin",
 "SIUE": "siu edwardsville", "SMU": "southern methodist", "Sacramento_St": "sacramento state",
 "Saint_Joe's": "saint josephs", "Saint_Mary's": "saint marys",
 "Sam_Houston": "sam houston state", "Southern": "southern university",
 "St._Thomas_-_Minnesota": "st thomas", "St_Bonaventure": "st bonaventure",
 "St_Francis_(BKN)": "st francis ny", "St_Francis_(PA)": "st francis pa",
 "St_John's": "st johns", "St_Peter's": "saint peters", "TCU": "texas christian",
 "Texas_A&M-CC": "texas a and m corpus chris", "Texas_A&M-Commerce": "texas a and m commerce",
 "The_Citadel": "citadel", "UAB": "alabama birmingham", "UCF": "central florida",
 "UCLA": "ucla", "UCSB": "santa barbara", "UC_Davis": "uc davis", "UC_Irvine": "uc irvine",
 "UC_Riverside": "uc riverside", "UC_San_Diego": "uc san diego", "UConn": "connecticut",
 "UIC": "illinois chicago", "UL_Monroe": "louisiana monroe", "UMBC": "maryland baltimore county",
 "UMKC": "kansas city", "UMass": "massachusetts", "UMass_Lowell": "massachusetts lowell",
 "UNC": "north carolina", "UNCG": "unc greensboro", "UNC_Asheville": "unc asheville",
 "UNC_Wilmington": "unc wilmington", "UNH": "new hampshire", "UNLV": "unlv",
 "URI": "rhode island", "USC": "southern california", "USC_Upstate": "usc upstate",
 "USF": "south florida", "UTEP": "texas el paso", "UTSA": "texas san antonio",
 "UT_Arlington": "texas arlington", "UT_Martin": "tennessee martin",
 "UT_Rio_Grande": "texas rio grande valley", "UVA": "virginia", "Utah_Tech": "utah tech",
 "VCU": "virginia commonwealth", "VMI": "vmi", "W_Kentucky": "western kentucky",
 "Washington_St": "washington state", "William_&_Mary": "william and mary",
 "Tenn_Tech": "tennessee tech", "Tennessee_St": "tennessee state",
 "Youngstown_St": "youngstown state", "North_Dakota_St": "north dakota state",
 "South_Dakota_St": "south dakota state", "New_Mexico_St": "new mexico state",
 "Jacksonville_St": "jacksonville state", "Northwestern_St": "northwestern state",
 "Appalachian_St": "appalachian state", "Boston_College": "boston college",
 "Southern_Miss": "southern miss", "Houston_Baptist": "houston baptist",
 "Houston_Christian": "houston christian", "Grambling": "grambling state",
 "Nicholls": "nicholls state", "Lamar": "lamar", "Dixie_State": "dixie state",
 "Bethune-Cookman": "bethune cookman", "Gardner-Webb": "gardner webb",
 "Presbyterian": "presbyterian", "Bryant": "bryant", "Merrimack": "merrimack",
 "Stonehill": "stonehill", "Lindenwood": "lindenwood", "Le_Moyne": "le moyne",
 "Bellarmine": "bellarmine", "Mercyhurst": "mercyhurst", "West_Georgia": "west georgia",
 "North_Alabama": "north alabama", "Southern_Indiana": "southern indiana",
 "Tarleton": "tarleton state", "Incarnate_Word": "incarnate word",
 "Texas_Southern": "texas southern", "Chicago_State": "chicago state",
 "Kennesaw_State": "kennesaw state", "N_Kentucky": "northern kentucky",
}

def key(team_dir):
    """Canonical join key for a ncaahoopR team directory name."""
    return expand(nrm(ALIAS.get(team_dir, team_dir)))

# extra join keys accepted for an external (Torvik / Wikipedia) name
EXTRA = {
 "unc": "north carolina", "north carolina tar heels": "north carolina",
 "st johns ny": "st johns", "saint johns": "st johns", "st josephs": "saint josephs",
 "saint joseph s": "saint josephs", "st marys ca": "saint marys",
 "saint mary s ca": "saint marys", "st peters": "saint peters",
 "mount saint marys": "mount st marys", "mt st marys": "mount st marys",
 "uc santa barbara": "santa barbara", "ucsb": "santa barbara",
 "cal state bakersfield": "cal st bakersfield", "cal state fullerton": "cal st fullerton",
 "cal state northridge": "cal st northridge", "csu bakersfield": "cal st bakersfield",
 "csun": "cal st northridge", "usc": "southern california",
 "ole miss": "mississippi", "pitt": "pittsburgh", "uconn": "connecticut",
 "byu": "brigham young", "smu": "southern methodist", "tcu": "texas christian",
 "vcu": "virginia commonwealth", "ucf": "central florida", "uab": "alabama birmingham",
 "utep": "texas el paso", "utsa": "texas san antonio", "uic": "illinois chicago",
 "umkc": "kansas city", "umass": "massachusetts", "umbc": "maryland baltimore county",
 "unlv": "unlv", "uri": "rhode island", "usf": "south florida", "unh": "new hampshire",
 "ecu": "east carolina", "etsu": "east tennessee state", "fau": "florida atlantic",
 "fgcu": "florida gulf coast", "fiu": "florida international", "jmu": "james madison",
 "liu brooklyn": "long island", "liu": "long island",
 "louisiana lafayette": "louisiana lafayette", "louisiana": "louisiana lafayette",
 "ul lafayette": "louisiana lafayette", "ul monroe": "louisiana monroe",
 "louisiana monroe": "louisiana monroe", "miami florida": "miami fl", "miami": "miami fl",
 "miami ohio": "miami oh", "middle tennessee state": "middle tennessee",
 "arkansas pine bluff": "arkansas pine bluff", "ipfw": "purdue fort wayne",
 "fort wayne": "purdue fort wayne", "unc greensboro": "unc greensboro",
 "north carolina greensboro": "unc greensboro", "north carolina asheville": "unc asheville",
 "north carolina wilmington": "unc wilmington", "unc charlotte": "charlotte",
 "north carolina a t": "north carolina a and t", "texas a m": "texas a and m",
 "texas a m corpus christi": "texas a and m corpus chris",
 "texas am corpus christi": "texas a and m corpus chris",
 "prairie view a m": "prairie view a and m", "alabama a m": "alabama a and m",
 "florida a m": "florida a and m", "william mary": "william and mary",
 "charleston": "college of charleston", "the citadel": "citadel",
 "detroit mercy": "detroit", "penn": "pennsylvania", "cal": "california",
 "california baptist": "california baptist", "seattle u": "seattle",
 "albany": "albany ny", "suny albany": "albany ny", "american": "american university",
 "boston u": "boston university", "grambling": "grambling state",
 "nicholls": "nicholls state", "mcneese": "mcneese state", "sam houston": "sam houston state",
 "tarleton": "tarleton state", "arkansas little rock": "arkansas little rock",
 "little rock": "arkansas little rock", "nebraska omaha": "nebraska omaha",
 "omaha": "nebraska omaha", "wisconsin milwaukee": "milwaukee",
 "wisconsin green bay": "green bay", "green bay": "green bay",
 "utah valley state": "utah valley", "dixie state": "dixie state",
 "utah tech": "utah tech", "purdue fort wayne": "purdue fort wayne",
 "queens": "queens nc", "st thomas mn": "st thomas", "saint thomas": "st thomas",
 "loyola marymount": "loyola marymount", "loyola maryland": "loyola md",
 "loyola md": "loyola md", "loyola il": "loyola chicago", "loyola chicago": "loyola chicago",
 "st francis brooklyn": "st francis ny", "saint francis pa": "st francis pa",
 "saint francis": "st francis pa", "central connecticut state": "central connecticut",
 "southeast missouri": "southeast missouri state", "southeastern louisiana": "southeastern louisiana",
 "stephen f austin": "stephen f austin", "siue": "siu edwardsville",
 "southern illinois edwardsville": "siu edwardsville", "njit": "njit",
 "iupui": "iupui", "iu indianapolis": "iu indy", "vmi": "vmi", "lsu": "lsu", "ucla": "ucla",
 "texas rio grande valley": "texas rio grande valley", "ut rio grande valley": "texas rio grande valley",
 "texas pan american": "texas rio grande valley", "abilene christian": "abilene christian",
 "maryland eastern shore": "maryland eastern shore", "mississippi valley state": "mississippi valley state",
 "south carolina state": "south carolina state", "southern": "southern university",
 "southern u": "southern university", "kansas city": "kansas city",
 "missouri kansas city": "kansas city", "north dakota state": "north dakota state",
 "south dakota state": "south dakota state", "usc upstate": "usc upstate",
 "south carolina upstate": "usc upstate", "cal poly": "cal poly",
 "cal poly slo": "cal poly", "long beach state": "long beach state",
 "cs bakersfield": "cal st bakersfield", "cs fullerton": "cal st fullerton",
 "cs northridge": "cal st northridge", "hawaii": "hawaii", "san jose state": "san jose state",
 "st bonaventure": "st bonaventure", "saint bonaventure": "st bonaventure",
 "saint louis": "saint louis", "st louis": "saint louis",
 "houston baptist": "houston baptist", "houston christian": "houston christian",
 "bethune cookman": "bethune cookman", "gardner webb": "gardner webb",
 "kent state": "kent state", "kent": "kent state",
}


EXTRA.update({
 "n c state": "north carolina state", "nc state": "north carolina state",
 "ut arlington": "texas arlington", "umass lowell": "massachusetts lowell",
 "cal baptist": "california baptist", "cal st northridge": "cal state northridge",
 "cal st fullerton": "cal state fullerton", "cal st bakersfield": "cal state bakersfield",
 "boston college": "boston college", "boston u": "boston university",
 "st johns": "saint johns", "st marys": "saint marys", "st peters": "saint peters",
 "st josephs": "saint josephs", "st thomas": "saint thomas",
 "college of charleston": "college of charleston",
})

def ekey(name):
    """Canonical join key for an external team name (Torvik / Wikipedia)."""
    k = nrm(name)
    if k in EXTRA: return expand(EXTRA[k])
    k2 = expand(k)
    if k2 in EXTRA: return expand(EXTRA[k2])
    return k2
