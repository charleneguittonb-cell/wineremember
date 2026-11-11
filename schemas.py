from typing import Literal, Optional

from pydantic import BaseModel, Field

WineColor = Literal["red", "white", "rosé", "sparkling", "sweet", "orange", "other"]


class LabelInfo(BaseModel):
    """What Claude reads on the bottle."""

    is_wine_label: bool = Field(description="False if the photos do not show a wine bottle or label")
    name: Optional[str] = Field(description="Name of the wine or cuvée, as written on the label")
    producer: Optional[str] = Field(description="Château, domaine, estate, house or producer")
    vintage: Optional[int] = Field(description="Vintage (harvest year); null if not visible or non-vintage")
    appellation: Optional[str] = Field(description="Appellation (AOC/AOP/DOC/AVA...), e.g. 'Pauillac'")
    region: Optional[str] = Field(description="Wine region in English, e.g. 'Bordeaux', 'Burgundy', 'Rioja'")
    country: Optional[str] = Field(description="Country, in English")
    color: Optional[WineColor] = Field(description="Wine style, inferred from the label, the bottle or the appellation")
    grapes: list[str] = Field(description="Grape varieties stated on the label or typical of the appellation")
    classification: Optional[str] = Field(description="E.g. 'Grand Cru Classé', 'Premier Cru', 'Reserva'")
    confidence: Literal["high", "medium", "low"] = Field(description="Overall confidence in the reading")


class WineSuggestion(BaseModel):
    name: str
    producer: Optional[str]
    appellation: Optional[str]
    region: Optional[str]
    color: Optional[WineColor]
    grapes: list[str]
    why: str = Field(description="One or two sentences explaining the resemblance to the reference wine")
    price_hint: Optional[str] = Field(description="Indicative price range, e.g. '€15-25'")


class SuggestionList(BaseModel):
    suggestions: list[WineSuggestion]


class SourceRef(BaseModel):
    title: str
    url: str


class SuggestedFields(BaseModel):
    """Wine record fields that the web research can fill in or correct."""
    producer: Optional[str]
    appellation: Optional[str]
    region: Optional[str]
    country: Optional[str]
    classification: Optional[str]
    grapes: list[str]


class Dossier(BaseModel):
    """What Claude found on the internet about a wine."""
    wine_description: str
    tasting_profile: Optional[str]
    producer_description: str
    producer_website: Optional[str]
    region_description: str
    vintage_description: Optional[str]
    drinking_window: Optional[str]
    food_pairings: list[str]
    critic_scores: list[str]
    suggested_fields: SuggestedFields
    sources: list[SourceRef]


class LinkIn(BaseModel):
    url: str = Field(min_length=10, max_length=500, pattern=r"^https?://[^\s]+$")
    label: Optional[str] = Field(default=None, max_length=120)


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=6, max_length=200)


class WineIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    producer: Optional[str] = None
    vintage: Optional[int] = Field(default=None, ge=1800, le=2100)
    appellation: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    color: Optional[WineColor] = None
    grapes: list[str] = []
    classification: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=5000)
    tasted_on: Optional[str] = None  # YYYY-MM-DD
    occasion: Optional[str] = Field(default=None, max_length=200)
    photo_ids: list[str] = Field(default=[], max_length=4)  # returned by /api/scan (front label first)


class WineUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    producer: Optional[str] = None
    vintage: Optional[int] = Field(default=None, ge=1800, le=2100)
    appellation: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    color: Optional[WineColor] = None
    grapes: Optional[list[str]] = None
    classification: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=5000)
    tasted_on: Optional[str] = None
    occasion: Optional[str] = Field(default=None, max_length=200)
