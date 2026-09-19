"""Market registry — every market in the Nestova development-opportunities workbook.

`scannable` marks markets where a live parcel-data provider is wired up
(Miami-Dade and Maricopa County today). Buy-box matching is configured for
all of them; scans wait on a data source.
"""

MARKETS: tuple[tuple[str, str, bool], ...] = (
    # (id, label, scannable)
    ("miami-dade-fl", "Miami-Dade County, FL (pilot)", True),
    ("paradise-valley-az", "Paradise Valley, AZ", True),
    ("bel-air-beverly-hills-ca", "Los Angeles — Bel Air / Beverly Hills, CA", False),
    ("port-royal-naples-fl", "Naples — Port Royal, FL", False),
    ("bradenton-anna-maria-fl", "Bradenton Beach / Anna Maria Island, FL", False),
    ("las-vegas-henderson-nv", "Las Vegas / Henderson, NV", False),
    ("hamptons-ny", "The Hamptons, NY", False),
    ("seattle-eastside-wa", "Seattle Eastside — Medina / Hunts Point, WA", False),
    ("atherton-ca", "Atherton / Silicon Valley, CA", False),
    ("charlotte-nc", "Charlotte — Myers Park / Eastover, NC", False),
)


def market_ids() -> list[str]:
    return [m[0] for m in MARKETS]
