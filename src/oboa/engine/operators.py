"""
Query operators for OBOA filters.
"""


text_operators = {
    "==": lambda column, value: column == value,
    "!=": lambda column, value: column != value,
    "like": lambda column, value: column.like(value),
    "notlike": lambda column, value: ~column.like(value),
    "in": lambda column, value: column.in_(value),
    "notin": lambda column, value: ~column.in_(value),
}


arithmetic_operators = {
    "==": lambda column, value: column == value,
    "!=": lambda column, value: column != value,
    ">": lambda column, value: column > value,
    ">=": lambda column, value: column >= value,
    "<": lambda column, value: column < value,
    "<=": lambda column, value: column <= value,
}
