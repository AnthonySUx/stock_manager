# AI-assisted stock intake

## Default shelf life

`default_shelf_life_days` is a category setting the intake flow will use to
estimate `suggested_unopened_expiration_date` from an item's purchase date.
The estimated date stays a suggestion until the user confirms an expiration date.

Category responses include this nullable field. Category creation and updates
accept an integer from 1 through 3650 days or `null`. Omit the field from a
PATCH request to keep the current value, or send `null` to clear it.

| Category slug | Days | Category slug | Days |
| --- | ---: | --- | ---: |
| `vegetables` | 7 | `fruit` | 7 |
| `meat` | 3 | `seafood` | 2 |
| `eggs` | 30 | `dairy` | 7 |
| `staples_grains` | 180 | `soy_products` | 5 |
| `seasonings_spices` | 365 | `baking` | 180 |
| `drinks` | 180 | `snacks` | 90 |
| `frozen_food` | 90 | `canned_packaged` | 365 |
| `ready_to_eat` | 2 | `other_food` | `null` |
| `baby_food` | 30 | `formula` | 365 |
| `pet_food` | 180 | `pet_treats` | 180 |
| `medicine` and `supplements` | `null` | All other categories | `null` |
