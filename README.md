# Generative AI in Scientific Research: survey results

Interactive results of the University of Sydney Faculty of Science survey on generative AI in research, run for the event on Thursday 12 November 2026.
The site is served by GitHub Pages from `docs/`.

## Data and privacy

The survey was anonymous.
The public data in `docs/data/` has no respondent IDs, Schools, timestamps or free text at the respondent level, and rows are shuffled.
Comment excerpts carry only the respondent's career stage and a random key that groups one person's excerpts.
Excerpts that could identify someone are withheld, and a few are lightly edited in [square brackets] to blur the field.
School counts are published as totals only.

## Rebuilding

`build_site.py` reads the private coded survey files (not in this repo) and writes `docs/`:

```bash
uv run --with pandas python build_site.py
```

Organized by A/Prof Ben Fulcher (School of Physics).
Survey coding and page built with Claude.
