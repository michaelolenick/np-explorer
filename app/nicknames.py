"""Given-name nickname equivalence for person consolidation (owner, 2026-11-23; loader/consolidate.py).

FORMAL maps a formal given name to the short forms people use. `formals(name)` returns every formal name a first name
can stand for ("chris" -> christopher, christine, christian...; "katie" -> katherine, kathleen...). Two first names are
equivalent when they are equal, or when their formal sets overlap ("chris" ~ "christopher", "chris" ~ "christine",
but "christopher" !~ "christine"). A name that is nobody's short form stands only for itself.
"""
from __future__ import annotations

FORMAL = {
    "abigail": "abby gail abbie", "adam": "ad", "alan": "al allan allen", "albert": "al bert", "alexander": "alex al sandy xander",
    "alexandra": "alex alexa sandy lexi", "alfred": "al alf fred freddy", "alice": "allie ali", "allison": "allie ally ali",
    "amanda": "mandy manda", "andrew": "andy drew", "angela": "angie", "anthony": "tony", "antonio": "tony",
    "arthur": "art artie", "barbara": "barb barbie babs bobbie", "benjamin": "ben benny benji", "bernard": "bernie bern",
    "beverly": "bev", "bradley": "brad", "brenda": "bren", "bridget": "bridgette biddy", "caroline": "carrie carol",
    "catherine": "cathy cat katie kate kathy katherine kitty cathie", "charles": "chuck charlie chas", "charlotte": "lottie charlie",
    "christian": "chris", "christina": "chris christy tina chrissy", "christine": "chris christy tina chrissy",
    "christopher": "chris kit", "cynthia": "cindy cyndi", "daniel": "dan danny", "david": "dave davy", "deborah": "deb debbie debby",
    "debra": "deb debbie debby", "dennis": "denny den", "donald": "don donnie", "dorothy": "dot dotty dottie dolly",
    "douglas": "doug", "edward": "ed eddie ted teddy ned", "edwin": "ed eddie", "eleanor": "ellie nell nora",
    "elizabeth": "liz beth betty betsy eliza lizzie libby lisa liza ellie", "emily": "em emmy millie",
    "eric": "rick", "ernest": "ernie", "eugene": "gene", "frances": "fran frannie franny", "francis": "frank fran",
    "frederick": "fred freddie freddy rick", "gabriel": "gabe", "gabrielle": "gabby gabi", "geoffrey": "geoff jeff",
    "gerald": "jerry gerry", "gregory": "greg", "harold": "hal harry", "henry": "hank harry", "herbert": "herb bert",
    "howard": "howie", "isabel": "izzy bel", "jacob": "jake jack", "james": "jim jimmy jamie jay", "janet": "jan",
    "jason": "jay", "jeffrey": "jeff", "jennifer": "jen jenny jenn", "jeremiah": "jerry", "jeremy": "jer",
    "jessica": "jess jessie", "joanne": "jo joann", "johanna": "jo joanna", "john": "jack johnny jon", "jonathan": "jon jonny",
    "joseph": "joe joey", "joshua": "josh", "judith": "judy jude", "julia": "julie jules", "kathleen": "kathy katie kate kath",
    "katherine": "kathy katie kate kath kat kitty", "kenneth": "ken kenny", "kimberly": "kim kimmy", "kristen": "kris kristy",
    "kristin": "kris kristy", "kristina": "kris kristy tina", "lawrence": "larry lars", "leonard": "leo len lenny",
    "linda": "lin lindy", "lisa": "", "madeline": "maddy maddie", "margaret": "maggie meg peggy marge margie greta",
    "maria": "mia", "marjorie": "marge margie", "martha": "marty", "matthew": "matt mat", "maureen": "mo reenie",
    "melissa": "mel missy lissa", "michael": "mike mickey mick mikey", "michelle": "shelly mickey mich", "mitchell": "mitch",
    "nancy": "nan", "natalie": "nat", "nathan": "nate nat", "nathaniel": "nate nat nathan", "nicholas": "nick nicky",
    "nicole": "nikki nicki", "norman": "norm", "olivia": "liv livvy", "pamela": "pam", "patricia": "pat patty trish tricia patti",
    "patrick": "pat paddy rick", "peter": "pete", "philip": "phil", "phillip": "phil", "rachel": "rach", "randall": "randy",
    "randolph": "randy", "raymond": "ray", "rebecca": "becky becca beck", "richard": "rick dick rich ricky richie",
    "robert": "bob bobby rob robbie bert", "roberta": "bobbie bert robbie", "ronald": "ron ronnie", "rosemary": "rose rosie",
    "russell": "russ rusty", "samantha": "sam sammy", "samuel": "sam sammy", "sandra": "sandy sandi", "sarah": "sally sadie",
    "sara": "sally sadie", "sebastian": "seb", "stephanie": "steph stephie", "stephen": "steve stevie", "steven": "steve stevie",
    "susan": "sue susie suzy suzanne", "suzanne": "sue susie suzy", "sylvia": "syl", "terrence": "terry", "terrance": "terry",
    "teresa": "terry tess tessa theresa", "theresa": "terry tess tessa", "theodore": "ted teddy theo", "thomas": "tom tommy",
    "timothy": "tim timmy", "valerie": "val", "vanessa": "nessa", "veronica": "ronnie roni", "victoria": "vicky vicki tori",
    "vincent": "vince vin vinny", "virginia": "ginny ginger", "walter": "walt wally", "william": "bill will billy willy liam",
    "winifred": "winnie", "zachary": "zach zack", 
}
# Short forms that stand for more than one formal name are listed above under each; build the reverse map.
_FORMALS: dict[str, set[str]] = {}
for _formal, _shorts in FORMAL.items():
    _FORMALS.setdefault(_formal, set()).add(_formal)
    for _s in _shorts.split():
        _FORMALS.setdefault(_s, set()).add(_formal)
        _FORMALS[_s].add(_s)


def formals(first: str) -> set[str]:
    return _FORMALS.get(first, {first})


def first_equiv(a: str, b: str) -> bool:
    """Equal, or one is a short form of a formal name the other also stands for."""
    if a == b:
        return True
    return bool(formals(a) & formals(b)) and min(len(a), len(b)) >= 2


def keys(first: str) -> set[str]:
    """Blocking keys: two first names that are equivalent share at least one."""
    return {first} | formals(first)
