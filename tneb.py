"""TNEB (TANGEDCO) domestic tariff — telescopic, bi-monthly.

Two tiers keyed on TOTAL bi-monthly consumption:
  <= 500 units: first 200 free, 201-400 @ 4.70, 401-500 @ 6.30
  >  500 units: first 100 free, 101-400 @ 4.70, 401-500 @ 6.30,
                501-600 @ 8.40, 601-800 @ 9.45, 801-1000 @ 10.50,
                above 1000 @ 11.55

Because the slabs are telescopic, a solar kWh displaces the household's
MOST EXPENSIVE units first, and pushing total consumption under 500 also
flips the tier (100 -> 200 free units). So the value of solar depends
entirely on the assumed gross consumption — there is no flat Rs/kWh.

No CT clamp: gross consumption is an ASSUMPTION supplied by the caller,
not a measurement. Under net metering, billed units ~= gross - solar;
excess exports carry forward as credit and are valued at 0 here
(conservative).
"""

TIER1 = [(200, 0.0), (400, 4.70), (500, 6.30)]
TIER2 = [(100, 0.0), (400, 4.70), (500, 6.30), (600, 8.40),
         (800, 9.45), (1000, 10.50), (float("inf"), 11.55)]


def bill(units):
    """Energy charge (Rs) for a bi-monthly consumption of `units` kWh."""
    if units <= 0:
        return 0.0
    slabs = TIER1 if units <= 500 else TIER2
    total, prev = 0.0, 0
    for upper, rate in slabs:
        take = min(units, upper) - prev
        if take <= 0:
            break
        total += take * rate
        prev = upper
    return round(total, 2)


def savings(gross_units, solar_units):
    """Rs saved in one bi-monthly cycle: bill without solar minus bill on
    the net-metered remainder. Excess export (solar > gross) is credited
    forward, valued 0 here."""
    net = max(gross_units - solar_units, 0.0)
    return round(bill(gross_units) - bill(net), 2)


def effective_rate(gross_units, solar_units):
    """Rs value of each solar kWh under the assumed consumption."""
    return round(savings(gross_units, solar_units) / solar_units, 2) \
        if solar_units > 0 else 0.0


if __name__ == "__main__":
    # spot checks against the published slab table
    assert bill(200) == 0.0                    # tier 1, all free
    assert bill(400) == 200 * 4.70             # 940
    assert bill(500) == 200 * 4.70 + 100 * 6.30            # 1570
    assert bill(600) == 300 * 4.70 + 100 * 6.30 + 100 * 8.40  # 2880
    assert bill(501) > bill(500)               # tier flip is a real cliff
    assert bill(1200) == (300 * 4.70 + 100 * 6.30 + 100 * 8.40
                          + 200 * 9.45 + 200 * 10.50 + 200 * 11.55)
    assert savings(600, 100) == bill(600) - bill(500)
    assert savings(300, 400) == bill(300)      # export excess valued 0
    print("tariff spot checks pass")
    for g in (400, 600, 800, 1000):
        print(f"gross {g:5d} units: bill Rs {bill(g):7.0f}   "
              f"400 solar units worth Rs {savings(g, 400):6.0f} "
              f"({effective_rate(g, 400):.2f}/kWh)")
