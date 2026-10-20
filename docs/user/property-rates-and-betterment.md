# Property rates and betterment

*Everyone can see the register; owners' names and contacts only those who may see personal data. Planners and district administrators keep it.*

Only the Assembly may levy rates in its district (Local Governance Act, 2016, Act 936). This page keeps the **register of rateable properties**, built from the map, with their valuations and bills; links it to the Assembly's **revenue system**; maps what has **never been billed** and what is **owing**; and runs **betterment** charges (L.I. 2384 r.40–41). Open a project and choose **Rates and betterment**.

## 1. Build the register from the map
Say which layer holds the properties (buildings or plots) under Relationships, Layers. Then **Add properties from the map**: one register entry per building, numbered by its property id, with its address where the [addressing](addressing.md) has given it one. Run it again after new buildings are mapped; only the new ones are added.

Click a property's number to set its **use**, **owner or ratepayer**, **rateable value**, **valuation reference** and **revenue account**.

## 2. Load the valuation list
From the Land Valuation Division, as a CSV with a header row:

| Column | Meaning |
| --- | --- |
| `number` or `valuation_ref` | which property |
| `rateable_value` | in GHS |
| `valued_on` | YYYY-MM-DD (optional) |
| `owner` | fills the owner where the register has none (optional) |

The page says how many rows matched a property, and lists those that didn't.

## 3. Set the rates and bill the year
Under **Rates**, add the rate for each use and year from the fee-fixing resolution:
- **Impost:** the share of the rateable value, e.g. `0.005`.
- **Minimum:** no bill is less than this.
- **Not yet valued:** a flat rate for properties without a rateable value.

Then **Bill the year**: each property without a bill for that year gets one, numbered like `SMA/PR/2026/00001`. Properties whose use has no rate are listed, not billed.

## 4. Link to the revenue system
- **Download for the revenue system:** the register as a CSV (number, address, use, owner, valuation, account, the latest bill and what's paid), to load into dLRev or whatever the Assembly uses.
- **From the revenue system:** load its bills and payments back, as a CSV with `property` (or `revenue_ref`), `year`, `bill`, `amount`, `paid`, `paid_on`. Every row is **reconciled**: it matches one property, or it is listed as unmatched so the account can be traced.
- Payments taken at the office can be recorded on a property directly.

## 5. See it on the map
**Show on the map** keeps a layer, *Property rates*, with a point on every property, coloured: **red** never billed, **orange** owing, **green** paid up. Use it to plan collection rounds and to find buildings that have never been on the roll.

## Betterment (L.I. 2384 r.40–41)
Where public works such as a road or a drain raise the value of land, the Assembly fixes a charge on the properties bettered.

1. **Add a betterment scheme:** the works, the date they were completed, the works' feature number on the map (click it with Identify), how far from the works land counts as bettered, and the charge: **a fixed sum** on each property, or **a share of each property's increase in value**.
2. **Find the bettered properties:** every register property within that distance gets a charge. For a share of the increase, type each property's increase in value (on the advice of the Lands Commission, r.41(1)).
3. **Publish the notice (Form 40):** download it, and record each way it was published: newspaper, posted on the land, Public Data Room (r.40(3)).
4. **Serve the assessment notices (Form 41)** on each owner **within 90 days of completion** (r.40(7)). The page counts those not yet served, and those served late.
5. **Certificates:** for each charge, a certificate of the sum due (conclusive evidence for recovery as a civil debt, r.41(2)–(3)) or, once paid, of payment (r.41(4)).

The notices and certificates say what the Regulations require; the Schedule's own layouts replace them when the Assembly supplies its forms.

## Not done yet
- Business operating permits linked to properties.
- Paying online or by mobile money: that goes through the revenue system or a payment provider, then comes back in its payments file.
