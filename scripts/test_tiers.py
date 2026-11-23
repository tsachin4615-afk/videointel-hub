name: Test All Tiers Separately

on:
  workflow_dispatch:
    inputs:
      tier:
        description: "Choose which tier to test across all channels"
        required: true
        default: "yt_html"
        type: choice
        options:
          - rss
          - yt_dlp
          - yt_html
          - mirrors

jobs:
  test-tier:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install yt-dlp (if testing yt_dlp)
        if: ${{ inputs.tier == 'yt_dlp' }}
        run: pip install --upgrade yt-dlp

      - name: Install scrapetube (if testing yt_html)
        if: ${{ inputs.tier == 'yt_html' }}
        run: pip install --upgrade scrapetube

      - name: Run selected tier test
        run: python scripts/test_tiers.py ${{ inputs.tier }}
