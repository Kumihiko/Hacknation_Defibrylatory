"""Współrzędne: kontrola zakresu Polski, wykrywanie zamienionych lat/lon, przeliczenie PUWG 1992 -> WGS84."""

from __future__ import annotations

import math

# Prostokąt obejmujący Polskę (z niewielkim marginesem)
LAT_MIN, LAT_MAX = 49.0, 54.9
LON_MIN, LON_MAX = 14.1, 24.2


def in_poland(lat: float | None, lon: float | None) -> bool:
    return lat is not None and lon is not None and LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX


def fix_coords(lat: float | None, lon: float | None) -> tuple[float, float] | None:
    """Zwraca poprawne (lat, lon) w Polsce albo None. Naprawia zamienioną kolejność (przypadek Marek)."""
    if lat is None or lon is None:
        return None
    if in_poland(lat, lon):
        return round(lat, 7), round(lon, 7)
    if in_poland(lon, lat):
        return round(lon, 7), round(lat, 7)
    return None


def to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def puwg1992_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """EPSG:2180 (PUWG 1992, x=easting, y=northing w kolejności GeoJSON) -> (lat, lon) WGS84.

    Odwzorowanie poprzeczne Merkatora na elipsoidzie GRS80 (różnica GRS80/WGS84 pomijalna),
    południk osiowy 19°E, k0 = 0.9993, FE = 500000, FN = -5300000. Szereg Krügera do 3. rzędu (dokładność < 1 mm).
    """
    a = 6378137.0
    f = 1 / 298.257222101
    k0 = 0.9993
    lon0 = math.radians(19.0)
    easting, northing = x - 500000.0, y + 5300000.0
    n = f / (2 - f)
    big_a = a / (1 + n) * (1 + n * n / 4 + n ** 4 / 64)
    xi, eta = northing / (k0 * big_a), easting / (k0 * big_a)
    beta = [n / 2 - 2 * n * n / 3 + 37 * n ** 3 / 96, n * n / 48 + n ** 3 / 15, 17 * n ** 3 / 480]
    xi_p = xi - sum(beta[j] * math.sin(2 * (j + 1) * xi) * math.cosh(2 * (j + 1) * eta) for j in range(3))
    eta_p = eta - sum(beta[j] * math.cos(2 * (j + 1) * xi) * math.sinh(2 * (j + 1) * eta) for j in range(3))
    chi = math.asin(math.sin(xi_p) / math.cosh(eta_p))
    delta = [2 * n - 2 * n * n / 3 - 2 * n ** 3, 7 * n * n / 3 - 8 * n ** 3 / 5, 56 * n ** 3 / 15]
    lat = chi + sum(delta[j] * math.sin(2 * (j + 1) * chi) for j in range(3))
    lon = lon0 + math.atan(math.sinh(eta_p) / math.cos(xi_p))
    return math.degrees(lat), math.degrees(lon)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))
