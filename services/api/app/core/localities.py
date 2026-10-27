"""Curated demo localities (Bengaluru) for users who deny browser geolocation.

Coordinates are public neighbourhood centroids, not anyone's address.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Locality:
    slug: str
    name: str
    city: str
    latitude: float
    longitude: float


LOCALITIES: tuple[Locality, ...] = (
    Locality("koramangala", "Koramangala", "Bengaluru", 12.9352, 77.6245),
    Locality("hsr-layout", "HSR Layout", "Bengaluru", 12.9116, 77.6474),
    Locality("btm-layout", "BTM Layout", "Bengaluru", 12.9166, 77.6101),
    Locality("indiranagar", "Indiranagar", "Bengaluru", 12.9719, 77.6412),
    Locality("jayanagar", "Jayanagar", "Bengaluru", 12.9250, 77.5938),
    Locality("bellandur", "Bellandur", "Bengaluru", 12.9260, 77.6762),
    Locality("marathahalli", "Marathahalli", "Bengaluru", 12.9591, 77.6974),
    Locality("whitefield", "Whitefield", "Bengaluru", 12.9698, 77.7500),
    Locality("malleshwaram", "Malleshwaram", "Bengaluru", 13.0035, 77.5709),
    Locality("electronic-city", "Electronic City", "Bengaluru", 12.8452, 77.6602),
)
