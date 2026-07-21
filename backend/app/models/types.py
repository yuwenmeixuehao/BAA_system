from sqlalchemy import Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import TypeDecorator


class MediumText(TypeDecorator[str]):
    """Use MySQL MEDIUMTEXT while retaining TEXT on other test/dev dialects."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[str]:
        if dialect.name == "mysql":
            return dialect.type_descriptor(MEDIUMTEXT())
        return dialect.type_descriptor(Text())
