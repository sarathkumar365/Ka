from pydantic import Field, model_validator

from .common import KaModel, PartialDate


class Email(KaModel):
    address: str
    label: str = ""


class Phone(KaModel):
    number: str
    label: str = ""


class Language(KaModel):
    name: str
    level: str = ""


class Location(KaModel):
    city: str = ""
    region: str = ""
    country: str = ""


class Address(KaModel):
    address: str
    from_: PartialDate = Field(alias="from")
    to: PartialDate | None = None
    current: bool = False


class Link(KaModel):
    label: str
    url: str


class Profile(KaModel):
    name: str
    date_of_birth: PartialDate | None = None
    emails: list[Email] = []
    phones: list[Phone] = []
    languages: list[Language] = []
    location: Location | None = None
    addresses: list[Address] = []
    links: list[Link] = []
    summary: str = ""

    @model_validator(mode="after")
    def _one_current_address(self):
        if sum(a.current for a in self.addresses) > 1:
            raise ValueError("at most one address may be current")
        return self
