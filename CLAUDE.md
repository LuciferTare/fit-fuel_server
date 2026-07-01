# Fit&Fuel Server — Project Conventions

Django + DRF backend for the Fit&Fuel gym-management app (phone-based auth, UUID PKs, gym/trainer/member hierarchy). See `PROJECT.md` for full architecture notes.

## API Conventions

**No PATCH, anywhere.** `BaseModelViewSet` (`core/views.py`) excludes `patch` from `http_method_names`. Partial updates are done via **POST**, not PATCH:
- Full replace: `PUT /resource/{uuid}/` (unchanged, still uses PUT).
- Partial update: `POST /resource/{uuid}/update/` — implemented once via `BaseModelViewSet.partial_update_via_post` (an `@action(detail=True, methods=["post"], url_path="update")` that delegates to `self.partial_update`). All ViewSets inherit this for free.
- Other partial-state actions (`disable`, `assign-trainer`, etc.) are `@action(detail=True, methods=["post"], ...)` — detail routes already carry the uuid in the path, so no extra path param is needed.
- Self-service endpoints with no uuid in the path (e.g. `MemberProfileView` for `/member/profile/`) use `POST` for updates too, since there's no PATCH to fall back to.

When adding a new ViewSet or endpoint that needs partial updates, follow this pattern — do not add a `patch` method or re-enable PATCH.

**Response envelope.** `core/renderers.py::ResponseRenderer` wraps every response:
```json
{ "data": ..., "message": "", "status": 200, "time": "..." }
```
For paginated list responses, DRF's `results`/`count`/`next`/`previous` get flattened so `data` holds the list and `count`/`next`/`previous` sit alongside it at the top level (not nested under `results`). Don't write serializers/views that bypass this renderer for JSON responses.

## Documentation Policy

- **`API_DOCUMENTATION.md` must be updated whenever an API change is made** (new endpoint, changed method, changed request/response fields, changed serializer fields). Keep its JSON examples in sync with the actual serializer field order and the response envelope above.
- **Do not touch any other `.md` file** (`PROJECT.md`, `README.md`, files under `MDs/`, etc.) **unless explicitly asked.** These are known to already have some drift from `API_DOCUMENTATION.md` — leave them alone unless the user specifically requests updates there.
- **In `API_DOCUMENTATION.md`, document `enum` and `date` field types as `string`.** `API_DOCUMENTATION.md` is consumed by the Flutter application project, which just sees JSON strings — it has no concept of Python/DRF-level `enum` or `date` types. This is a documentation-only convention: keep the actual serializer/model field types (`ChoiceField`, `DateField`, etc.) unchanged in code.
