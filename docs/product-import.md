# JSON product import

Import product data (specs, reference price, source) and optionally parts you own, from JSON files
written by your own scripts, for example a scraper.

- **For the script author / AI agent:** give it
  [product-templates/AGENT_INSTRUCTIONS.md](product-templates/AGENT_INSTRUCTIONS.md). It is
  self-contained: fields, units, rules, every part type and an example.
- **Templates:** `docs/product-templates/<type>.schema.json` (JSON Schema) and `<type>.example.json`,
  one pair per part type. Also downloadable in the app (Inventory → Import JSON).
- **Import in the app:** Inventory → **Import JSON** → choose files → **Check files** → **Import**.
- **Import from the command line** (app closed, backup written first):
  `BikeLog.exe --import-products a.json b.json` (add `--dry-run` to only check). Exit code 1 if any file
  had errors.

Behaviour: each file is all-or-nothing; products are matched by type + maker + model, so re-importing
changes nothing and changed data updates the product (spec keys only in the app are kept); items are
added as spares and matched by label; scraped data is marked unverified unless the file says otherwise.

Templates and the instructions are generated from the code (`backend/bikelog/product_specs.py`); after
changing spec fields run `python -m bikelog --write-product-templates docs/product-templates`
(a test fails if they are out of date).
