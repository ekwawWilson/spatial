# Street addressing

*Everyone who can see a project can see the proposal and download the schedule. Writing it to the map needs the right to edit relationships (planners and district administrators).*

L.I. 2384 r.28 has every Assembly name its streets and number its properties. This page gives every street a **code** and every property a **number** worked out from where the property stands along its street. Open a project and choose **Addressing**.

What you see first is a **proposal**. Nothing changes on the map until you choose **Apply to the map**.

## Before you start
- Say which layers hold the **properties** and the **streets** (Relationships, Layers).
- Give the streets their **names**. A street without a name still gets a code and its properties still get numbers, but the address has no street name in it; the page counts these for you.
- Draw each street as **one line** from end to end. A street drawn in pieces is numbered piece by piece.

## How the numbers are worked out
- Each property belongs to the **nearest street** within reach (100 m unless the project says otherwise).
- Its number comes from its **distance from the start of the street**, with **odd numbers on one side and even on the other**.
- Two properties that come out with the same number get a letter: 53, 53A, 53B.

Choose how to number:

| Numbers | What it does | When to use it |
| --- | --- | --- |
| By distance, every 10 m | A property 535 m along is number 53 or 54. | The usual choice. A new building between two others gets a number in between; nothing is renumbered. |
| By distance, every metre | A property 535 m along is number 535 or 536. | Long roads with few properties. |
| One after another | 1, 3, 5 … on one side; 2, 4, 6 … on the other. | A fully built-up street that will not change. |

**Odd numbers on the:** left or right, as you travel from the street's start.

**Start each street from the end nearer:** give the latitude and longitude of a place, such as the town centre, and every street is numbered from its end nearer that place. Left blank, each street starts at the end it was drawn from.

Set these to the rules of the National Street Naming and Property Numbering Operational Manual as your Assembly applies them, and keep them the same across the district.

## Street codes
A street with a code keeps it. A street without one is given the next free code: the district's code and a number (`SMA-004`), in order of street name.

## Reading the proposal
- **Properties numbered:** how many of the layer's properties got a number.
- **Too far from any street:** properties beyond reach of every street. Draw the missing street, or check the property is in the right place.
- **Numbers that would change:** properties whose number on the map differs from the proposal. The table shows the number each has now, in red where it would change.
- **Download the schedule (CSV):** every address, for checking in the field and for the signage contractor. The page shows the first few hundred.

## Applying
**Apply to the map** writes each street's code, and each property's number and street name, into the layers' own fields (`street_code` on streets; `house_no` and `street` on properties, added if the layers do not have them). Only values that differ are written, and every change is in the audit log with who made it.

Applying twice changes nothing the second time. Changing the method later and applying again **renumbers** the properties: once number plates are up, treat the method as fixed.
