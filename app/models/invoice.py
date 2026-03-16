from sqlmodel import SQLModel, Field


class Invoice(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    amount: float
