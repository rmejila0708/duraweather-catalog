# DuraWeather catalogs

- **2026 catalog flipbook:** https://rmejila0708.github.io/duraweather-catalog/
- **Quick Ship flipbook:** https://rmejila0708.github.io/duraweather-catalog/quick-ship/

## Rebuild the Quick Ship flipbook

```
pip install pillow
python build_quickship_flipbook.py
```

It reads the live Quick Ship collection on duraweather.com (read-only), so prices and stock are current at build time.
Then commit and push the `quick-ship/` folder. Settings (prices on or off, hero photos, page layout) are at the top of the script.
