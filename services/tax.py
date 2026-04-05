def calc_progressive_ndfl_13_15(annual_taxable_income: float, annual_threshold: float = 5_000_000):
    taxable = max(float(annual_taxable_income), 0.0)
    threshold = max(float(annual_threshold), 0.0)

    if taxable <= threshold:
        tax = taxable * 0.13
    else:
        tax = threshold * 0.13 + (taxable - threshold) * 0.15

    net = taxable - tax
    return {
        "gross_taxable_annual": taxable,
        "tax_annual": round(tax, 2),
        "net_taxable_annual": round(net, 2),
    }


def calc_monthly_net_income(
    monthly_taxable_income: float,
    monthly_non_taxable_income: float = 0.0,
    annual_threshold: float = 5_000_000,
):
    annual_taxable = float(monthly_taxable_income) * 12
    annual_result = calc_progressive_ndfl_13_15(annual_taxable, annual_threshold=annual_threshold)

    monthly_tax = annual_result["tax_annual"] / 12
    monthly_taxable_net = annual_result["net_taxable_annual"] / 12
    monthly_total_net = monthly_taxable_net + float(monthly_non_taxable_income)

    return {
        "gross_taxable_monthly": round(float(monthly_taxable_income), 2),
        "non_taxable_monthly": round(float(monthly_non_taxable_income), 2),
        "tax_monthly": round(monthly_tax, 2),
        "net_taxable_monthly": round(monthly_taxable_net, 2),
        "net_total_monthly": round(monthly_total_net, 2),
    }
