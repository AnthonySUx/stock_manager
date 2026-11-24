# API errors

Handled HTTP errors return three fields:

| Field | Meaning |
|---|---|
| `code` | Stable identifier for client handling and translation |
| `params` | Structured values for that code, or an empty object |
| `detail` | Human-readable detail in the original response format |

Request validation returns `422 validation_error`. Its `detail` remains the
FastAPI array of issues with fields such as `loc`, `msg`, and `type`.
`params.errors` contains the same array. Non-finite values in validation
diagnostics are represented as strings so the response is valid JSON.

AI errors include a public detail message and an empty `params` object. Provider
diagnostics remain in the backend log. Explore's streamed `error` events retain their
code-only payload. See [Streamed Explore](recipes.md#streamed-explore).

## General HTTP errors

The backend uses these codes when a route or the HTTP framework has no more specific
code. Authentication errors retain the `WWW-Authenticate` header.

| HTTP | Code |
|---|---|
| 400 | `bad_request` |
| 401 | `unauthorized` |
| 403 | `forbidden` |
| 404 | `not_found` |
| 405 | `method_not_allowed` |
| 409 | `conflict` |
| 413 | `payload_too_large` |
| 415 | `unsupported_media_type` |
| 422 | `unprocessable_entity` |
| 429 | `too_many_requests` |
| 500 | `internal_error` |
| 502 | `bad_gateway` |
| 503 | `service_unavailable` |
| Other | `http_error` |

## Stock, restock, and categories

| HTTP | Code | When | Parameters |
|---|---|---|---|
| 400 | `no_fields_to_update` | A stock or restock PATCH contains no editable fields | |
| 400 | `invalid_category` | A category or category reference is invalid | |
| 400 | `category_required` | Completing restock needs a category | |
| 400 | `source_item_not_found` | A restock request refers to a missing stock item | |
| 400 | `invalid_item_clean_status` | Stock cleanup received an unsupported status | |
| 400 | `invalid_restock_clean_status` | Restock cleanup received a status other than done | |
| 404 | `item_not_found` | Stock item is missing | |
| 404 | `restock_not_found` | Restock item is missing | |
| 404 | `category_not_found` | Category is missing | |
| 409 | `category_delete_conflict` | Category cannot be deleted | |
| 409 | `restock_already_done` | Restock was completed or changed concurrently | |
| 409 | `item_already_consumed` | Stock has been used up | |
| 422 | `item_status_readonly` | Stock PATCH included a status key | |
| 422 | `restock_status_readonly` | Restock PATCH included a status key | |
| 422 | `restock_item_invalid` | Completing restock needs an owner or location | `field` |
| 422 | `expiration_before_purchase` | Unopened expiration precedes purchase | |
| 422 | `opened_expiration_before_opened` | Opened expiration precedes opening | |
| 422 | `consume_exceeds_stock` | Consumption exceeds available stock | `available` |

## Recipes and AI

| HTTP | Code | When | Parameters |
|---|---|---|---|
| 400 | `recipe_inventory_invalid` | Explore referenced unknown or unusable stock | |
| 404 | `recipe_not_found` | Recipe is missing | |
| 404 | `recipe_not_editable` | Recipe is missing or cannot be edited directly | |
| 404 | `recipe_not_deletable` | Recipe is missing or cannot be deleted directly | |
| 404 | `favorite_not_found` | Favorite is missing | |
| 409 | `cook_nothing_consumed` | Every requested deduction failed | `lines` |
| 422 | `duplicate_item` | Cook request repeats a stock item | `item_id` |
| 429 | `rate_limited` | AI request quota for the token has been reached | `retry_after` (seconds) |
| 500 | `ai_error` | General AI failure | |
| 502 | `ai_upstream_error` | AI provider failed or returned unusable output | |
| 503 | `ai_unavailable` | AI is disabled or unconfigured | |
| 503 | `ai_vision_unavailable` | AI image input is unconfigured | |

## Intake and speech

| HTTP | Code | Parameters |
|---|---|---|
| 413 | `intake_request_too_large` | `max_bytes` |
| 413 | `audio_too_large` | `max_bytes` |
| 422 | `intake_draft_too_large` | `max` |
| 422 | `intake_duplicate_temporary_id` | `id` |
| 422 | `intake_text_empty` | |
| 422 | `intake_text_too_long` | `max` |
| 422 | `intake_timezone_invalid` | |
| 422 | `intake_item_invalid` | `index`, `temporary_id`, `field` |
| 422 | `intake_image_type_unsupported` | `index` |
| 422 | `intake_multipart_invalid` | |
| 422 | `intake_images_missing` | |
| 422 | `intake_images_too_many` | `max` |
| 422 | `intake_image_too_large` | `index`, `max_bytes` |
| 422 | `audio_upload_invalid` | |
| 422 | `audio_format_unsupported` | `accepted` |
| 422 | `audio_too_long` | `max_seconds` |
| 502 | `asr_upstream_error` | |
| 503 | `asr_unavailable` | |

## Recipe photos

| Code | HTTP status | Parameters | Meaning |
| --- | --- | --- | --- |
| `media_unavailable` | 503 | — | `MEDIA_DIR` is unset. |
| `photo_not_found` | 404 | — | The photo does not exist, is outside the requested recipe, or its JPEG is missing. |
| `photo_type_unsupported` | 422 | — | The file signature is outside JPEG, PNG and WebP. |
| `photo_too_large` | 413 | — | The file is larger than 5 MiB. |
| `photo_invalid` | 422 | — | The server could not decode the photo or it exceeded the pixel limit. |
| `photo_upload_invalid` | 422 | — | The multipart request has missing, duplicate, or invalid fields. |
| `photo_group_invalid` | 422 | — | The request combines a step and a cook record for one photo. |
| `photo_step_invalid` | 422 | `step_numbers` | The recipe has no step with that number. The parameter lists valid step numbers in ascending order. |
| `photo_cook_record_invalid` | 422 | — | The cook record does not belong to the recipe or is not a cooked event. |
| `photo_limit_reached` | 422 | `group`, `limit` | The group already has the maximum number of user photos. |
| `photo_hidden_source_only` | 422 | — | Only an imported photo supports the `hidden` field. |
| `photo_source_readonly` | 409 | — | An imported photo cannot be deleted. |
| `photo_cover_invalid` | 422 | — | The selected photo is hidden or is outside the recipe. |
