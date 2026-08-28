# Cross-match unpack bug — one-line fix

`optimus/standalone/maps_scraper_standalone.py`, function `_match_new`, line 625.

`_safe_append` builds rows 7 wide (name, address, phone, website, category,
resi_hint, cell_hint). `_match_new` unpacks a fixed 5, so it raises
`ValueError: too many values to unpack (expected 5, got 7)` on the FIRST row of
every batch. The whole cross-match aborts and the caller swallows it as
`(cross-match skipped: ...)`.

Effect: the business-to-dot match has never written a row since the two hint
columns were added. `Upgrade Orange Biz` is frozen at 62.

## Fix

Replace:

```python
    for name, addr, phone, web, cat in new:
```

with:

```python
    for _row in new:
        name, addr, phone, web, cat = _row[:5]
```

Slicing rather than unpacking means adding a column can never silently kill the
match again.

Verified 2026-08-28: ValueError reproduced against the real row shape, fix
applied, py_compile clean. Base file md5 b9bf80084595a192e5e8f83b02b24f44;
fixed blob sha 339e5eca596725ce3e28e9c3666ddeb252ca44e5.
