from sqlalchemy import Column, Integer

from app.services.agent.orm_base import Base


def test_orm_base_assigns_default_tablename():
    class DemoRecord(Base):
        id = Column(Integer, primary_key=True)

    assert DemoRecord.__tablename__ == "demorecords"
