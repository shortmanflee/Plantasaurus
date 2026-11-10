from enum import StrEnum


class Environment(StrEnum):
    indoor = "indoor"
    outdoor = "outdoor"
    greenhouse = "greenhouse"
    covered = "covered"


class Aspect(StrEnum):
    N = "N"
    NE = "NE"
    E = "E"
    SE = "SE"
    S = "S"
    SW = "SW"
    W = "W"
    NW = "NW"
    none = "none"


class SunExposure(StrEnum):
    full_sun = "full_sun"
    part_shade = "part_shade"
    shade = "shade"


class Level(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class InstanceStatus(StrEnum):
    active = "active"
    dead = "dead"
    removed = "removed"
    given_away = "given_away"


class InstanceSource(StrEnum):
    bought = "bought"
    seed = "seed"
    cutting = "cutting"
    division = "division"
    gift = "gift"
    other = "other"


class EventType(StrEnum):
    # lifecycle / placement
    acquired = "acquired"
    planted = "planted"
    moved = "moved"
    transplanted = "transplanted"
    repotted = "repotted"
    died = "died"
    removed = "removed"
    given_away = "given_away"
    revived = "revived"
    # care
    watered = "watered"
    fed = "fed"
    pruned = "pruned"
    pest_disease = "pest_disease"
    treated = "treated"
    # growth
    flowered = "flowered"
    fruited = "fruited"
    harvested = "harvested"
    propagated = "propagated"
    # records
    photo = "photo"
    note = "note"
    assessment = "assessment"


# Event types that can only be created via instance action endpoints.
SYSTEM_EVENT_TYPES = {
    EventType.acquired,
    EventType.planted,
    EventType.moved,
    EventType.transplanted,
    EventType.repotted,
    EventType.died,
    EventType.removed,
    EventType.given_away,
    EventType.revived,
    EventType.propagated,
    EventType.assessment,
}


class YesNoMaybe(StrEnum):
    yes = "yes"
    no = "no"
    maybe = "maybe"


class KeepLocation(StrEnum):
    yes = "yes"
    no = "no"
    try_elsewhere = "try_elsewhere"


class CustomFieldEntity(StrEnum):
    plant = "plant"
    instance = "instance"
    area = "area"
    spot = "spot"


class CustomFieldType(StrEnum):
    text = "text"
    number = "number"
    bool = "bool"
    date = "date"
    select = "select"
